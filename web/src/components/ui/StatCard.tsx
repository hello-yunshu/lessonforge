import { cn, pct } from "@/lib/utils";

type Props = {
  label: string;
  value: number; // 0..1
  target?: number; // 0..1
  hint?: string;
  invert?: boolean; // 越低越好
  className?: string;
};

/** 大号宋体数字指标卡 — 当前值/目标值/墨青进度条 */
export default function StatCard({ label, value, target, hint, invert, className }: Props) {
  const ratio = invert ? 1 - value : value;
  const barColor = ratio >= 0.9 ? "bg-teal" : ratio >= 0.8 ? "bg-warn" : "bg-err";
  const targetRatio = target ? (invert ? 1 - target : target) : undefined;
  return (
    <div
      className={cn(
        "relative bg-paper border border-ink-line rounded-sm p-4 hover:shadow-card-hover transition-shadow",
        className,
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-ink-3 leading-tight">{label}</span>
        {hint && (
          <span className="text-2xs text-ink-4 font-mono uppercase tracking-wider">{hint}</span>
        )}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-serif text-3xl font-bold text-ink tabular-nums">
          {pct(value, 0)}
        </span>
        {target !== undefined && (
          <span className="text-xs text-ink-4 font-mono">/ 目标 {pct(target, 0)}</span>
        )}
      </div>
      <div className="mt-3 relative h-1.5 bg-paper-3 rounded-full overflow-hidden">
        <div
          className={cn("h-full transition-all duration-700", barColor)}
          style={{ width: `${ratio * 100}%` }}
        />
        {targetRatio !== undefined && (
          <div
            className="absolute top-0 h-full w-px bg-ink"
            style={{ left: `${targetRatio * 100}%` }}
            title={`目标 ${pct(target, 0)}`}
          />
        )}
      </div>
    </div>
  );
}
