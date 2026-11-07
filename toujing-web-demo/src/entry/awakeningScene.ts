import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

/** A deterministic, externally clocked light treatment around the DOM orb. */
export function createAwakeningScene(canvas: HTMLCanvasElement): { render: (time: number) => void; dispose: () => void } {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setClearColor(0x000000, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ReinhardToneMapping;
  renderer.toneMappingExposure = 1.15;
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
  camera.position.z = 10;
  const composer = new EffectComposer(renderer);
  const renderPass = new RenderPass(scene, camera);
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 1.9, 0.6, 0.12);
  const output = new OutputPass();
  composer.addPass(renderPass);
  composer.addPass(bloom);
  composer.addPass(output);

  const group = new THREE.Group();
  scene.add(group);
  const geometries: THREE.BufferGeometry[] = [];
  const materials: THREE.Material[] = [];
  const makeRing = (radius: number, tube: number, color: number, tilt: [number, number, number]) => {
    const geometry = new THREE.TorusGeometry(radius, tube, 8, 192);
    const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(2.2), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.set(...tilt);
    group.add(mesh);
    geometries.push(geometry);
    materials.push(material);
    return { mesh, material, tilt };
  };
  const rings = [
    makeRing(1.07, 0.018, 0x2a9fff, [1.13, 0.25, -0.52]),
    makeRing(1.13, 0.014, 0xff7b1a, [1.04, -0.45, 0.64]),
    makeRing(1.3, 0.008, 0x73c8ff, [0.55, 0.9, 0.22]),
    makeRing(1.43, 0.006, 0xffa13d, [0.8, -0.8, -0.3]),
  ];

  // The burst is fixed at creation; scaling it follows the caller's time exactly.
  let seed = 271828;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  const count = 720;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const blue = new THREE.Color(0x4eb8ff);
  const orange = new THREE.Color(0xff8b26);
  for (let i = 0; i < count; i++) {
    const angle = random() * Math.PI * 2;
    const radius = 0.35 + Math.pow(random(), 0.65) * 2.6;
    positions[i * 3] = Math.cos(angle) * radius;
    positions[i * 3 + 1] = Math.sin(angle) * radius * (0.4 + random() * 0.6);
    positions[i * 3 + 2] = (random() - 0.5) * 0.35;
    const color = i % 2 ? blue : orange;
    colors[i * 3] = color.r; colors[i * 3 + 1] = color.g; colors[i * 3 + 2] = color.b;
  }
  const dotsGeometry = new THREE.BufferGeometry();
  dotsGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  dotsGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const sprite = document.createElement('canvas');
  sprite.width = sprite.height = 64;
  const context = sprite.getContext('2d')!;
  const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
  gradient.addColorStop(0, '#fff'); gradient.addColorStop(0.18, '#fff'); gradient.addColorStop(0.45, '#ffffff66'); gradient.addColorStop(1, '#ffffff00');
  context.fillStyle = gradient; context.fillRect(0, 0, 64, 64);
  const glowTexture = new THREE.CanvasTexture(sprite);
  const dotsMaterial = new THREE.PointsMaterial({ map: glowTexture, size: 7, vertexColors: true, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true });
  const dots = new THREE.Points(dotsGeometry, dotsMaterial);
  group.add(dots);
  geometries.push(dotsGeometry);
  materials.push(dotsMaterial);
  const rayPositions: number[] = [], rayColors: number[] = [];
  for (let i = 0; i < 160; i++) {
    const angle = random() * Math.PI * 2, near = .6 + random() * 1.7, far = near + .2 + random() * 1.1;
    const color = i % 2 ? blue : orange;
    rayPositions.push(Math.cos(angle) * near, Math.sin(angle) * near, 0, Math.cos(angle) * far, Math.sin(angle) * far, 0);
    rayColors.push(color.r, color.g, color.b, color.r, color.g, color.b);
  }
  const rayGeometry = new THREE.BufferGeometry();
  rayGeometry.setAttribute('position', new THREE.Float32BufferAttribute(rayPositions, 3));
  rayGeometry.setAttribute('color', new THREE.Float32BufferAttribute(rayColors, 3));
  const rayMaterial = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  const rays = new THREE.LineSegments(rayGeometry, rayMaterial);
  group.add(rays); geometries.push(rayGeometry); materials.push(rayMaterial);

  let width = 1, height = 1, orbRadius = 1, disposed = false;
  const resize = () => {
    if (disposed) return;
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, rect.width); height = Math.max(1, rect.height);
    // Keep both device density and total render-target area bounded.
    const ratio = Math.min(window.devicePixelRatio || 1, 1.4, Math.sqrt(2_500_000 / (width * height)));
    renderer.setPixelRatio(ratio);
    renderer.setSize(width, height, false);
    composer.setPixelRatio(ratio);
    composer.setSize(width, height);
    camera.left = -width / 2; camera.right = width / 2;
    camera.top = height / 2; camera.bottom = -height / 2;
    camera.updateProjectionMatrix();
    orbRadius = (width <= 800 ? width * .34 : Math.min(width * 0.26, height * 0.42)) / 2;
  };
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const smooth = (v: number) => { const x = clamp(v); return x * x * (3 - 2 * x); };

  return {
    render(time) {
      if (disposed) return;
      const t = Math.max(0, time);
      const move = smooth((t - 16) / 3);
      group.position.set((0.18 * (1 - move)) * width, (0.10 - 0.09 * move) * height, 0);
      const intro = smooth(t / 2);
      const charge = smooth((t - 19) / 1.5);
      const blast = smooth((t - 20.5) / 1.8);
      const fade = 1 - smooth((t - 23) / 3);
      const scale = orbRadius * (1 - 0.4 * charge + 1.15 * blast);
      group.scale.setScalar(scale);
      rings.forEach(({ mesh, material, tilt }, i) => {
        mesh.rotation.set(tilt[0] + t * (i % 2 ? -0.08 : 0.06) + charge * 1.5, tilt[1] + t * 0.035 + charge, tilt[2] + t * (i % 2 ? 0.13 : -0.1) + charge * (i % 2 ? -3 : 3));
        material.opacity = intro * fade * (0.5 + 0.35 * charge + 0.15 * blast) * (i < 2 ? 1 : 0.7);
      });
      dots.scale.setScalar(0.28 + 0.72 * blast);
      dotsMaterial.opacity = intro * fade * (0.08 + 0.82 * blast);
      rays.scale.setScalar(.25 + 1.2 * blast);
      rayMaterial.opacity = Math.sin(blast * Math.PI) * .75 * fade;
      bloom.strength = 1.9 + charge * 1.5 - blast * .5;
      // Black is transparent under the caller's screen blend; no light remains after 26s.
      composer.render();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      observer.disconnect();
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((material) => material.dispose());
      renderPass.dispose();
      bloom.dispose();
      output.dispose();
      glowTexture.dispose();
      composer.dispose();
      renderer.dispose();
    },
  };
}
