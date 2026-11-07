export const SCENE_END = 8200;
export const IGNITION = 2650;
export const UNFOLD = 5150;

export type TracePoint = { position: number; sell: boolean };

type Color = { glow: string; mid: string; light: string };
type Point = { x: number; y: number };
type Projected = Point & { near: boolean };
type Band = { angle: number; flatten: number; size: number; color: Color };
type Layout = {
  width: number; height: number; orb: DOMRect; center: Point; radius: number;
  track: { x: number; y: number; width: number };
};

const ICE: Color = { glow: '#2471ff', mid: '#53c8ff', light: '#d9f8ff' };
const AMBER: Color = { glow: '#fa5826', mid: '#ff9e51', light: '#ffefc9' };
const BANDS: Band[] = [
  { angle: -.35, flatten: .50, size: 1.45, color: ICE },
  { angle: .66, flatten: .49, size: 1.31, color: AMBER },
];
const TWO_PI = Math.PI * 2;
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const mix = (from: number, to: number, p: number) => from + (to - from) * p;
const ease = (p: number) => p * p * (3 - 2 * p);
const between = (now: number, from: number, to: number) => ease(clamp((now - from) / (to - from)));
const hash = (seed: number) => ((Math.sin(seed * 12.9898 + 78.233) * 43758.5453) % 1 + 1) % 1;

function orbit(band: Band, theta: number, seconds: number, center: Point, radius: number, lane = 0): Projected {
  const s = Math.sin(theta);
  const c = Math.cos(theta);
  const ripple = .058 * Math.sin(theta * 3 - seconds * 2.3) + .023 * Math.cos(theta * 7 + seconds * 3);
  const r = radius * (band.size + lane + ripple);
  const perspective = 1 + s * .11;
  const u = c * r * perspective;
  const v = s * r * band.flatten * perspective;
  const roll = band.angle + .16 * Math.sin(seconds * .57);
  return {
    x: center.x + u * Math.cos(roll) - v * Math.sin(roll),
    y: center.y + u * Math.sin(roll) + v * Math.cos(roll),
    near: s > 0,
  };
}

function drawBand(
  ctx: CanvasRenderingContext2D, band: Band, layout: Layout, seconds: number, near: boolean, strength: number,
) {
  if (strength < .015) return;
  const { center, radius } = layout;
  const head = seconds * (band.angle > 0 ? -1.25 : 1.48) + band.angle * 4.7;
  const tail = head - 4.6;
  const start = orbit(band, tail, seconds, center, radius);
  const end = orbit(band, head, seconds, center, radius);
  const glass = ctx.createLinearGradient(start.x, start.y, end.x, end.y);
  glass.addColorStop(0, band.color.glow + '00');
  glass.addColorStop(.20, band.color.glow + '81');
  glass.addColorStop(.55, band.color.mid + '60');
  glass.addColorStop(.82, band.color.light + 'a0');
  glass.addColorStop(1, band.color.mid + '16');
  ctx.fillStyle = glass;
  ctx.globalAlpha = strength * (near ? .95 : .71);
  let outer: Point[] = [];
  let inner: Point[] = [];
  function fillSurface() {
    if (outer.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(outer[0].x, outer[0].y);
      for (const point of outer.slice(1)) ctx.lineTo(point.x, point.y);
      for (const point of inner.reverse()) ctx.lineTo(point.x, point.y);
      ctx.closePath();
      ctx.fill();
    }
    outer = [];
    inner = [];
  }
  for (let i = 0; i <= 54; i++) {
    const p = i / 54;
    const theta = mix(tail, head, p);
    if ((Math.sin(theta) > 0) !== near) {
      if (outer.length) fillSurface();
      continue;
    }
    const twist = .78 + .22 * Math.cos(theta * 3 - seconds * 3.4);
    const width = Math.pow(Math.sin(p * Math.PI), .72) * twist * (band.color === ICE ? .24 : .155);
    outer.push(orbit(band, theta, seconds, center, radius, width));
    inner.push(orbit(band, theta, seconds, center, radius, -width * .55));
  }
  fillSurface();

  const sheen = ctx.createLinearGradient(start.x, start.y, end.x, end.y);
  sheen.addColorStop(0, 'transparent');
  sheen.addColorStop(.17, band.color.glow);
  sheen.addColorStop(.53, band.color.mid);
  sheen.addColorStop(.84, band.color.light);
  sheen.addColorStop(1, band.color.mid);
  ctx.strokeStyle = sheen;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  for (const [lane, width, opacity] of [
    [0, radius * .29, .13], [0, radius * .115, .30], [0, radius * .042, .45],
    [-.089, 1.2, .48], [.057, 1.8, .76], [0, 2.2, .99], [.113, 1.05, .59],
  ]) {
    let started = false;
    ctx.beginPath();
    for (let i = 0; i <= 54; i++) {
      const t = i / 54;
      const theta = mix(tail, head, t);
      const point = orbit(band, theta, seconds, center, radius, lane * Math.sin(t * Math.PI));
      if (point.near !== near) { started = false; continue; }
      if (started) ctx.lineTo(point.x, point.y);
      else ctx.moveTo(point.x, point.y);
      started = true;
    }
    ctx.lineWidth = width;
    ctx.globalAlpha = opacity * strength * (near ? 1 : .67);
    ctx.stroke();
  }
}

function drawIgnition(ctx: CanvasRenderingContext2D, layout: Layout, age: number) {
  if (age < 0 || age > 1.48) return;
  const { x, y } = layout.center;
  const r = layout.radius;
  const envelope = Math.min(age / .10, 1) * (1 - ease(age / 1.48));
  const glow = ctx.createRadialGradient(x, y, r * .78, x, y, r * 2.1);
  glow.addColorStop(0, '#c9f7ff00');
  glow.addColorStop(.15, '#4cbbff83');
  glow.addColorStop(.48, '#2d70f428');
  glow.addColorStop(1, '#2340f100');
  ctx.globalAlpha = envelope;
  ctx.fillStyle = glow;
  ctx.fillRect(x - r * 2.1, y - r * 2.1, r * 4.2, r * 4.2);

  const wave = r * (1 + 1.1 * (1 - (1 - age / 1.48) ** 2));
  const prism = ctx.createLinearGradient(x - wave, y - wave * .3, x + wave, y + wave * .3);
  prism.addColorStop(0, '#67dfff08');
  prism.addColorStop(.22, ICE.light);
  prism.addColorStop(.55, '#688cff42');
  prism.addColorStop(.80, AMBER.mid);
  prism.addColorStop(1, '#ff976215');
  ctx.strokeStyle = prism;
  ctx.beginPath();
  ctx.ellipse(x, y, wave, wave * .73, -.27, 0, TWO_PI);
  ctx.lineWidth = r * .135;
  ctx.globalAlpha = envelope * .27;
  ctx.stroke();
  ctx.lineWidth = r * .035;
  ctx.globalAlpha = envelope * .39;
  ctx.stroke();
  ctx.lineWidth = 2.2;
  ctx.globalAlpha = envelope * .82;
  ctx.stroke();

  ctx.beginPath();
  ctx.ellipse(x, y, wave * 1.057, wave * .78, -.27, 0, TWO_PI);
  ctx.lineWidth = 1.2;
  ctx.globalAlpha = envelope * .42;
  ctx.stroke();
}

function drawGlassScan(ctx: CanvasRenderingContext2D, globe: HTMLImageElement, layout: Layout, age: number) {
  if (age < 0 || age > 1.55 || !globe.complete || !globe.naturalWidth) return;
  const { x, y } = layout.center;
  const r = layout.radius;
  const width = layout.orb.width;
  const p = ease(age / 1.55);
  const sweep = mix(-1.30 * r, 1.45 * r, p);
  const gap = r * (.19 + .11 * Math.sin(p * Math.PI));
  const rotation = -.51;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rotation);
  ctx.beginPath();
  ctx.moveTo(sweep - gap, -r * 1.32);
  ctx.bezierCurveTo(sweep - r * .57, -r * .42, sweep + r * .12, r * .57, sweep - gap * .41, r * 1.32);
  ctx.lineTo(sweep + gap, r * 1.32);
  ctx.bezierCurveTo(sweep + gap * .78, r * .39, sweep - r * .14, -r * .51, sweep + gap * .64, -r * 1.32);
  ctx.closePath();
  ctx.clip();
  ctx.rotate(-rotation);
  ctx.translate(-x, -y);
  // Magnify the existing orb only inside the moving curved band.
  ctx.globalCompositeOperation = 'source-over';
  ctx.globalAlpha = Math.min(age * 6, 1) * Math.min((1.55 - age) * 6, 1) * .91;
  ctx.filter = 'brightness(1.64) saturate(1.28)';
  const size = width * 1.105;
  ctx.drawImage(globe, x - size / 2 + r * .065, y - size / 2 - r * .035, size, size);
  ctx.restore();
}

type Particle = {
  color: Color; band: Band; position: number; theta: number;
  begin: number; duration: number; drift: number; reach: number; settle: number;
};

function gather(particle: Particle, p: number, layout: Layout) {
  const angle = particle.theta - particle.drift * (1 - p);
  const reach = 1 + particle.reach * (1 - ease(p));
  return orbit(particle.band, angle, p * 1.1, layout.center, layout.radius * reach);
}

function depart(particle: Particle, p: number, layout: Layout): Projected {
  const origin = orbit(particle.band, particle.theta, particle.settle * .001, layout.center, layout.radius);
  const destination = { x: layout.track.x + particle.position * layout.track.width, y: layout.track.y };
  const curve = Math.sin(p * Math.PI);
  return {
    x: mix(origin.x, destination.x, ease(p)) + curve * (particle.position - .50) * layout.radius * .91,
    y: mix(origin.y, destination.y, p * p) - curve * layout.radius * .35,
    near: true,
  };
}

function traceParticle(
  ctx: CanvasRenderingContext2D, progress: number, pointAt: (p: number) => Projected,
  color: Color, opacity: number, near: boolean,
) {
  const head = pointAt(progress);
  if (head.near !== near) return;
  ctx.beginPath();
  const back = Math.max(0, progress - .19);
  for (let i = 0; i <= 7; i++) {
    const point = pointAt(mix(back, progress, i / 7));
    if (i) ctx.lineTo(point.x, point.y);
    else ctx.moveTo(point.x, point.y);
  }
  ctx.lineWidth = 5.8;
  ctx.lineCap = 'round';
  ctx.strokeStyle = color.glow;
  ctx.globalAlpha = opacity * .28;
  ctx.stroke();
  ctx.lineWidth = 1.45;
  ctx.strokeStyle = color.mid;
  ctx.globalAlpha = opacity * .84;
  ctx.stroke();
  ctx.fillStyle = color.light;
  ctx.globalAlpha = opacity;
  ctx.beginPath();
  ctx.arc(head.x, head.y, 2.1, 0, TWO_PI);
  ctx.fill();
}

export function createTraceScene(
  canvas: HTMLCanvasElement, globe: HTMLImageElement, rail: HTMLElement,
  marks: TracePoint[],
) {
  const ctx = canvas.getContext('2d', { alpha: true });
  const particles: Particle[] = marks.map((mark, i) => ({
    color: mark.sell ? AMBER : ICE,
    band: BANDS[mark.sell ? 1 : 0],
    position: mark.position,
    theta: TWO_PI * (i / marks.length + hash(i) * .25),
    begin: 80 + (i % 18) * 64 + Math.floor(i / 18) * 147,
    duration: 920 + hash(i + 17) * 550,
    drift: 1.45 + hash(i + 29) * 1.65,
    reach: .85 + hash(i + 88) * 1.25,
    settle: UNFOLD + mark.position * 1050 + hash(i + 4) * 245,
  }));
  let layout: Layout;
  let currentTime = 0;
  let disposed = false;
  const measure = () => {
    if (disposed) return;
    const bounds = canvas.getBoundingClientRect();
    const orb = globe.getBoundingClientRect();
    const line = rail.getBoundingClientRect();
    const width = bounds.width;
    const height = bounds.height;
    if (!width || !height) return;
    const ratio = Math.min(devicePixelRatio || 1, 1.5, Math.sqrt(3_000_000 / (width * height)));
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx?.setTransform(ratio, 0, 0, ratio, 0, 0);
    layout = {
      width, height, orb,
      center: { x: orb.x - bounds.x + orb.width / 2, y: orb.y - bounds.y + orb.height / 2 },
      radius: orb.width * .46,
      track: { x: line.x - bounds.x, y: line.y - bounds.y + line.height / 2, width: line.width },
    };
    // Resizing a canvas clears its pixels, including while the shared clock is paused.
    paint(currentTime);
  };
  const observer = new ResizeObserver(measure);
  observer.observe(canvas);
  observer.observe(globe);
  measure();

  function paint(t: number) {
    if (!ctx || !layout) return;
    const seconds = t / 1000;
    const energy = mix(.32, 1, between(t, IGNITION - 350, IGNITION + 400));
    const dissolve = 1 - between(t, UNFOLD, UNFOLD + 1200);
    const strength = energy * dissolve * between(t, 0, 900);
    ctx.clearRect(0, 0, layout.width, layout.height);
    for (const near of [false, true]) {
      ctx.globalCompositeOperation = 'lighter';
      if (!near) drawIgnition(ctx, layout, (t - IGNITION) / 1000);
      else drawGlassScan(ctx, globe, layout, (t - IGNITION) / 1000);
      for (const band of BANDS) drawBand(ctx, band, layout, seconds, near, strength);
      for (const particle of particles) {
        if (t >= particle.begin && t <= particle.begin + particle.duration) {
          const p = (t - particle.begin) / particle.duration;
          traceParticle(ctx, p, value => gather(particle, value, layout), particle.color,
            Math.min(p * 8, 1) * (1 - .53 * ease(p)), near);
        } else if (near && t >= particle.settle) {
          const p = clamp((t - particle.settle) / 1150);
          if (p < 1) {
            traceParticle(ctx, p, value => depart(particle, value, layout), particle.color, 1 - .50 * ease(p), near);
          } else {
            ctx.fillStyle = particle.color.mid;
            ctx.globalAlpha = .77 * (1 - between(t, SCENE_END - 180, SCENE_END));
            const x = layout.track.x + particle.position * layout.track.width;
            ctx.fillRect(x - 1, layout.track.y - 3, 2, 6);
          }
        }
      }
      if (!near && globe.complete && globe.naturalWidth) {
        // Cut the back of the band using the actual transparent orb asset.
        ctx.globalAlpha = between(t, 350, IGNITION);
        ctx.globalCompositeOperation = 'destination-out';
        ctx.drawImage(globe, layout.center.x - layout.orb.width / 2, layout.center.y - layout.orb.height / 2,
          layout.orb.width, layout.orb.height);
      }
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }

  // The shared Motion timeline now controls this original effect, including seek/replay.
  return {
    render(elapsed: number) { currentTime = Math.max(0, Math.min(elapsed, SCENE_END)); paint(currentTime); },
    dispose() {
      disposed = true;
      observer.disconnect();
      if (ctx && layout) ctx.clearRect(0, 0, layout.width, layout.height);
    },
  };
}
