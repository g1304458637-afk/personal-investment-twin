import "./MirrorOrbVisual.css";

export type MirrorOrbVisualState = "idle" | "hover" | "thinking" | "active";

export function MirrorOrbVisual({
  state = "idle",
  className,
  label,
  decorative = false,
}: {
  state?: MirrorOrbVisualState;
  className?: string;
  label?: string;
  decorative?: boolean;
}) {
  const classes = ["mirror-orb-visual", className].filter(Boolean).join(" ");

  return (
    <span
      className={classes}
      data-state={state}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : label ?? `Mirror Orb is ${state}`}
    >
      <span className="mirror-orb__halo" aria-hidden="true" />
      <span className="mirror-orb__lens" aria-hidden="true">
        <span className="mirror-orb__caustic" />
        <span className="mirror-orb__core" />
        <span className="mirror-orb__reflection" />
        <span className="mirror-orb__rim" />
      </span>
    </span>
  );
}
