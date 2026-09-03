import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-10 w-full rounded-md border border-border/80 bg-black/[0.08] px-3 text-sm text-foreground outline-none placeholder:text-muted/65 transition-[border-color,box-shadow,background-color] focus:border-accent/45 focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white/[0.035]",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
