import { motion, useSpring, useTransform } from "motion/react";
import { useEffect } from "react";

import { cn } from "@/lib/utils";

export function AnimatedNumber({
  value,
  format,
  className,
}: {
  value: number;
  format: (value: number) => string;
  className?: string;
}) {
  const spring = useSpring(value, {
    stiffness: 105,
    damping: 24,
    mass: 0.7,
  });
  const display = useTransform(spring, format);

  useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <motion.span className={cn("tabular-nums", className)}>{display}</motion.span>;
}
