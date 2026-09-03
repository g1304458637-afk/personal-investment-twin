import { motion, useMotionValue, useReducedMotion, useSpring } from "motion/react";
import { useState, type PointerEvent } from "react";

import { cn } from "@/lib/utils";

export type MirrorOrbState = "idle" | "hover" | "thinking" | "active";

const sizeClass = {
  sm: "mirror-orb--sm",
  md: "mirror-orb--md",
  lg: "mirror-orb--lg",
};

export function MirrorOrb({
  state = "idle",
  size = "md",
  className,
}: {
  state?: Exclude<MirrorOrbState, "hover">;
  size?: keyof typeof sizeClass;
  className?: string;
}) {
  const [hovered, setHovered] = useState(false);
  const reducedMotion = useReducedMotion();
  const rotateXValue = useMotionValue(0);
  const rotateYValue = useMotionValue(0);
  const rotateX = useSpring(rotateXValue, { stiffness: 160, damping: 22, bounce: 0 });
  const rotateY = useSpring(rotateYValue, { stiffness: 160, damping: 22, bounce: 0 });
  const visualState: MirrorOrbState = hovered ? "hover" : state;

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (reducedMotion) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;
    rotateYValue.set(x * 7);
    rotateXValue.set(y * -7);
  };

  const reset = () => {
    setHovered(false);
    rotateXValue.set(0);
    rotateYValue.set(0);
  };

  return (
    <motion.div
      className={cn("mirror-orb", sizeClass[size], className)}
      data-state={visualState}
      role="img"
      aria-label={`Mirror Orb is ${visualState}`}
      onPointerEnter={() => setHovered(true)}
      onPointerMove={handlePointerMove}
      onPointerLeave={reset}
      style={{ rotateX, rotateY, transformPerspective: 700 }}
      whileHover={reducedMotion ? undefined : { y: -2 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className="mirror-orb__halo" aria-hidden="true" />
      <span className="mirror-orb__lens" aria-hidden="true">
        <span className="mirror-orb__caustic" />
        <span className="mirror-orb__core" />
        <span className="mirror-orb__reflection" />
        <span className="mirror-orb__rim" />
      </span>
    </motion.div>
  );
}
