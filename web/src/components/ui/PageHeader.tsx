import type { ReactNode } from "react";
import { cn, toCN } from "@/lib/utils";

type Props = {
  no?: number; // 章节编号（自动转中文数字）
  eyebrow?: string; // 眉标小字
  title: string;
  subtitle?: string;
  right?: ReactNode;
  className?: string;
};

/** 页面/章节标题 — 编号 + 宋体大标题 + 副标题 + 朱砂墨线 */
export default function PageHeader({ no, eyebrow, title, subtitle, right, className }: Props) {
  return (
    <div className={cn("relative pb-6 mb-8", className)}>
      {/* 顶部细朱砂线 */}
      <div className="absolute -top-6 left-0 h-px w-16 bg-vermilion" />
      <div className="flex items-end justify-between gap-6">
        <div className="flex-1 min-w-0">
          {eyebrow && (
            <div className="mb-2 text-2xs uppercase tracking-[0.3em] text-ink-3 font-mono">
              {eyebrow}
            </div>
          )}
          <div className="flex items-baseline gap-4">
            {no !== undefined && (
              <span className="chapter-num text-2xl md:text-3xl shrink-0">
                {toCN(no)}、
              </span>
            )}
            <h1 className="font-serif text-3xl md:text-4xl font-bold text-ink leading-tight">
              {title}
            </h1>
          </div>
          {subtitle && (
            <p className="mt-3 text-sm text-ink-3 leading-relaxed max-w-3xl">{subtitle}</p>
          )}
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </div>
      {/* 底部墨线 */}
      <div className="mt-5 h-px bg-ink-line" />
    </div>
  );
}
