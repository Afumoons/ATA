import * as React from "react";
import { cn } from "@/lib/utils";

type BadgeVariant = "neutral" | "info" | "success" | "warning" | "critical";

const variantClasses: Record<BadgeVariant, string> = {
  neutral: "border-[rgba(210,225,241,0.12)] bg-white/[0.03] text-[var(--text-muted)]",
  info: "border-[rgba(76,139,245,0.32)] bg-[rgba(76,139,245,0.12)] text-[var(--info)]",
  success: "border-[rgba(47,191,113,0.28)] bg-[rgba(47,191,113,0.12)] text-[var(--success)]",
  warning: "border-[rgba(230,169,61,0.28)] bg-[rgba(230,169,61,0.12)] text-[var(--warning)]",
  critical: "border-[rgba(226,93,93,0.28)] bg-[rgba(226,93,93,0.12)] text-[var(--critical)]",
};

export function Badge({
  className,
  variant = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-2 font-mono text-[11px] uppercase tracking-[0.08em]",
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  );
}
