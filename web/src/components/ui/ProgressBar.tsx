import { cn } from "@/lib/utils";

type Props = {
  value: number; // 0..1
  showLabel?: boolean;
  tone?: "teal" | "vermilion" | "ink" | "gold" | "warn";
  className?: string;
};

export default function ProgressBar({ value, showLabel, tone = "teal", className }: Props) {
  const colors = {
    teal: "bg-teal",
    vermilion: "bg-vermilion",
    ink: "bg-ink",
    gold: "bg-gold",
    warn: "bg-warn",
  };
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 h-1 bg-paper-3 rounded-full overflow-hidden">
        <div
          className={cn("h-full transition-all duration-700", colors[tone])}
          style={{ width: `${Math.min(value, 1) * 100}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-2xs font-mono text-ink-3 tabular-nums w-10 text-right">
          {(value * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}
