import type { ReactNode } from "react";
import { cn, confTier, reviewStatusCN } from "@/lib/utils";

type Tone = "default" | "vermilion" | "teal" | "ok" | "warn" | "err" | "gold" | "ink";

const tones: Record<Tone, string> = {
  default: "bg-paper-3 text-ink-2 border-ink-line",
  vermilion: "bg-vermilion-tint text-vermilion-deep border-vermilion/30",
  teal: "bg-teal-tint text-teal-2 border-teal/30",
  ok: "bg-ok-soft text-ok border-ok/30",
  warn: "bg-warn-soft text-warn border-warn/30",
  err: "bg-err-soft text-err border-err/30",
  gold: "bg-gold-soft text-ink-2 border-gold/30",
  ink: "bg-ink text-paper border-ink",
};

export function Badge({
  children,
  tone = "default",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 text-2xs font-medium rounded-sm border whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ConfBadge({ value, className }: { value: number; className?: string }) {
  const tier = confTier(value);
  const tone = tier === "high" ? "ok" : tier === "mid" ? "warn" : "err";
  return (
    <Badge tone={tone} className={className}>
      置信 {value.toFixed(2)}
    </Badge>
  );
}

export function ReviewBadge({ status }: { status: string }) {
  const tone = status === "confirmed" ? "ok" : status === "rejected" ? "err" : "warn";
  return (
    <Badge tone={tone}>{reviewStatusCN(status)}</Badge>
  );
}

export default Badge;
