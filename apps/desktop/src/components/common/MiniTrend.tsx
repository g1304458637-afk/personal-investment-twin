import { cn } from "@/lib/utils";

export function MiniTrend({
  values,
  label,
  className,
}: {
  values: number[];
  label: string;
  className?: string;
}) {
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = maximum - minimum || 1;

  return (
    <div
      className={cn("mini-trend", className)}
      role="img"
      aria-label={`${label}: ${values.join(", ")}`}
    >
      {values.map((value, index) => (
        <span
          key={`${label}-${index}`}
          style={{ height: `${22 + ((value - minimum) / span) * 72}%` }}
        />
      ))}
    </div>
  );
}
