import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "secondary" | "ghost" | "outline" | "toolbar";
type ButtonSize = "default" | "sm" | "lg" | "icon";

const variantClasses: Record<ButtonVariant, string> = {
  default:
    "border border-[rgba(255,255,255,0.06)] bg-[var(--accent)] text-[#f7fbff] shadow-[0_12px_28px_rgba(76,139,245,0.22)] hover:bg-[var(--accent-strong)] hover:shadow-[0_16px_36px_rgba(76,139,245,0.28)]",
  secondary:
    "border border-[var(--line)] bg-[var(--panel-strong)] text-[var(--text)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-hover)]",
  ghost:
    "border border-transparent bg-transparent text-[var(--text-muted)] hover:border-[var(--line)] hover:bg-white/5 hover:text-[var(--text)]",
  outline:
    "border border-[var(--line-strong)] bg-white/[0.02] text-[var(--text)] hover:border-[var(--accent)] hover:bg-[var(--accent-soft)]",
  toolbar:
    "border border-[var(--line-strong)] bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))] text-[var(--text)] hover:border-[var(--accent)] hover:bg-[var(--accent-soft)]",
};

const sizeClasses: Record<ButtonSize, string> = {
  default: "h-10 px-4 py-2 text-[13px] font-[560]",
  sm: "h-8 rounded-[8px] px-3 text-[12px] font-[540]",
  lg: "h-11 px-5 text-[14px] font-[560]",
  icon: "size-10 px-0",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "default", size = "default", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] transition-[background,border-color,box-shadow,color,transform] duration-150 ease-out disabled:pointer-events-none disabled:opacity-60 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[rgba(76,139,245,0.14)]",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
});
