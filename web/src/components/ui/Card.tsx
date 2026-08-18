import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type CardProps = {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  noPad?: boolean;
  accent?: "none" | "vermilion" | "teal" | "gold";
};

/** 墨线描边卡 — 宣纸暖白底，墨线边框 */
export function Card({
  title,
  subtitle,
  right,
  children,
  className,
  bodyClassName,
  noPad,
  accent = "none",
}: CardProps) {
  return (
    <div
      className={cn(
        "bg-paper shadow-card rounded-sm border border-ink-line transition-shadow hover:shadow-card-hover",
        accent === "vermilion" && "border-l-2 border-l-vermilion",
        accent === "teal" && "border-l-2 border-l-teal",
        accent === "gold" && "border-l-2 border-l-gold",
        className,
      )}
    >
      {(title || right) && (
        <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-3 border-b border-ink-line-2">
          <div className="min-w-0">
            {title && (
              <h3 className="font-serif font-semibold text-base text-ink leading-snug">{title}</h3>
            )}
            {subtitle && <p className="mt-1 text-xs text-ink-3 leading-relaxed">{subtitle}</p>}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </div>
      )}
      <div className={cn(!noPad && "p-5", bodyClassName)}>{children}</div>
    </div>
  );
}

export default Card;
