import { useState, useMemo } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import {
  verifyItems,
  computeVerifySummaries,
  teacherBookLessons,
  teacherBookUnits,
} from "@/data";
import type { VerifyCheckType, VerifyStatus } from "@/data";
import { cn } from "@/lib/utils";
import {
  ShieldCheck,
  AlertTriangle,
  XCircle,
  Circle,
  Layers,
  FileSearch,
  ListTree,
  Link2,
  Filter,
  CheckCircle2,
} from "lucide-react";

const checkTypeMeta: Record<
  VerifyCheckType,
  { label: string; short: string; icon: typeof FileSearch; tone: "vermilion" | "teal" | "gold" | "ink" }
> = {
  "question-complete": { label: "题目完整性", short: "QC", icon: FileSearch, tone: "vermilion" },
  "lesson-retrieval": { label: "课时调取", short: "LR", icon: Layers, tone: "teal" },
  "exercise-set": { label: "练习集合", short: "ES", icon: ListTree, tone: "gold" },
  "binding-accuracy": { label: "绑定准确性", short: "BA", icon: Link2, tone: "ink" },
};

const statusMeta: Record<
  VerifyStatus,
  { label: string; tone: "ok" | "warn" | "err" | "default"; icon: typeof CheckCircle2 }
> = {
  pass: { label: "通过", tone: "ok", icon: CheckCircle2 },
  warn: { label: "警告", tone: "warn", icon: AlertTriangle },
  fail: { label: "失败", tone: "err", icon: XCircle },
  pending: { label: "待验", tone: "default", icon: Circle },
};

const evidenceLayerCN: Record<string, string> = {
  "textbook-page": "教材原页",
  "tb-text": "教师用书",
  "system-infer": "系统推断",
};

const evidenceLayerTone: Record<string, "vermilion" | "teal" | "gold"> = {
  "textbook-page": "vermilion",
  "tb-text": "teal",
  "system-infer": "gold",
};

export default function Verify() {
  const [filterType, setFilterType] = useState<VerifyCheckType | "all">("all");
  const [filterStatus, setFilterStatus] = useState<VerifyStatus | "all">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // 动态计算汇总
  const summaries = useMemo(() => computeVerifySummaries(), []);
  const totalItems = verifyItems.length;
  const totalPass = verifyItems.filter((i) => i.status === "pass").length;
  const totalWarn = verifyItems.filter((i) => i.status === "warn").length;
  const totalFail = verifyItems.filter((i) => i.status === "fail").length;

  // 过滤后的验证项
  const filteredItems = useMemo(() => {
    return verifyItems.filter((i) => {
      if (filterType !== "all" && i.check_type !== filterType) return false;
      if (filterStatus !== "all" && i.status !== filterStatus) return false;
      return true;
    });
  }, [filterType, filterStatus]);

  // 课时查询
  const lessonById = useMemo(() => {
    const m = new Map<string, { no: number; title: string; unitName: string }>();
    for (const l of teacherBookLessons) {
      const u = teacherBookUnits.find((u) => u.id === l.unit_id);
      m.set(l.id, { no: l.no, title: l.title, unitName: u?.name ?? "—" });
    }
    return m;
  }, []);

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={15}
        eyebrow="TEXTBOOK PARSING · VERIFICATION"
        title="教材解析能力验证"
        subtitle="利用教师用书中的明确内容范围和教材引用，验证教材题目是否完整、对象绑定是否准确、跨页调取是否遗漏、练习集合是否可靠。教师用书是参照与证据来源，不覆盖教材原页事实。"
        right={
          <div className="flex flex-col items-end gap-1">
            <Badge tone={totalFail > 0 ? "err" : totalWarn > 0 ? "warn" : "ok"}>
              {totalPass}/{totalItems} 通过
            </Badge>
            <Badge tone="default">{verifyItems.length} 项验证</Badge>
          </div>
        }
      />

      {/* 总览数字 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        {[
          { label: "验证项总数", value: `${totalItems}`, sub: "覆盖四类能力", tone: "default" as const },
          { label: "通过", value: `${totalPass}`, sub: `${((totalPass / totalItems) * 100).toFixed(0)}%`, tone: "ok" as const },
          { label: "警告", value: `${totalWarn}`, sub: "需补充完善", tone: "warn" as const },
          { label: "失败", value: `${totalFail}`, sub: "需纠错修复", tone: "err" as const },
          { label: "三层证据", value: "3", sub: "原页/原文/推断", tone: "vermilion" as const },
        ].map((m) => (
          <div key={m.label} className={cn(
            "bg-paper border rounded-sm p-3",
            m.tone === "ok" && "border-ok/30",
            m.tone === "warn" && "border-warn/30",
            m.tone === "err" && "border-err/30",
            m.tone === "default" && "border-ink-line",
            m.tone === "vermilion" && "border-vermilion/30",
          )}>
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">{m.label}</div>
            <div className={cn(
              "mt-1 font-serif text-xl font-bold",
              m.tone === "ok" && "text-ok",
              m.tone === "warn" && "text-warn",
              m.tone === "err" && "text-err",
              m.tone === "default" && "text-ink",
              m.tone === "vermilion" && "text-vermilion",
            )}>{m.value}</div>
            <div className="text-2xs text-ink-4 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* 四类验证汇总 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <ShieldCheck size={18} className="text-vermilion" />
        <span className="chapter-num">一</span> 四类验证能力汇总
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10">
        {summaries.map((s) => {
          const meta = checkTypeMeta[s.check_type];
          const Icon = meta.icon;
          const passRate = s.total > 0 ? (s.pass / s.total) * 100 : 0;
          return (
            <Card
              key={s.check_type}
              accent={meta.tone === "ink" ? "none" : meta.tone}
              className="cursor-pointer hover:shadow-card-hover transition-shadow"
              right={
                <button
                  onClick={() => setFilterType(s.check_type)}
                  className="text-2xs text-teal hover:underline"
                >
                  仅看此类
                </button>
              }
              title={
                <div className="flex items-center gap-2">
                  <Icon size={15} className={cn(
                    meta.tone === "vermilion" && "text-vermilion",
                    meta.tone === "teal" && "text-teal",
                    meta.tone === "gold" && "text-gold",
                    meta.tone === "ink" && "text-ink-2",
                  )} />
                  <span>{meta.label}</span>
                  <Badge tone="default">{s.total}</Badge>
                </div>
              }
              subtitle={s.description}
            >
              <div className="flex items-center gap-4 mb-3">
                <div className="flex-1">
                  <div className="flex items-baseline justify-between mb-1">
                    <span className="text-2xs text-ink-4 font-mono">通过率</span>
                    <span className="font-serif text-lg font-bold text-ink">
                      {passRate.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-1.5 bg-paper-3 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        passRate >= 80 ? "bg-ok" : passRate >= 50 ? "bg-warn" : "bg-err",
                      )}
                      style={{ width: `${passRate}%` }}
                    />
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 text-center">
                {([
                  { k: "pass", label: "通过", tone: "ok" as const, v: s.pass },
                  { k: "warn", label: "警告", tone: "warn" as const, v: s.warn },
                  { k: "fail", label: "失败", tone: "err" as const, v: s.fail },
                  { k: "pending", label: "待验", tone: "default" as const, v: s.pending },
                ]).map((c) => (
                  <div key={c.k} className="p-1.5 bg-paper-2 rounded-sm">
                    <div className={cn(
                      "font-serif text-sm font-bold",
                      c.tone === "ok" && "text-ok",
                      c.tone === "warn" && "text-warn",
                      c.tone === "err" && "text-err",
                      c.tone === "default" && "text-ink-3",
                    )}>{c.v}</div>
                    <div className="text-2xs text-ink-4">{c.label}</div>
                  </div>
                ))}
              </div>
            </Card>
          );
        })}
      </div>

      {/* 验证项明细 */}
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <h2 className="font-serif text-xl font-bold text-ink flex items-center gap-2">
          <Filter size={18} className="text-vermilion" />
          <span className="chapter-num">二</span> 验证项明细
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          {/* 类型过滤 */}
          <div className="flex items-center gap-1 p-0.5 bg-paper-2 border border-ink-line rounded-sm">
            <button
              onClick={() => setFilterType("all")}
              className={cn(
                "px-2.5 py-1 text-2xs rounded-sm transition-colors",
                filterType === "all" ? "bg-ink text-paper" : "text-ink-3 hover:text-ink",
              )}
            >
              全部类型
            </button>
            {(Object.keys(checkTypeMeta) as VerifyCheckType[]).map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={cn(
                  "px-2.5 py-1 text-2xs rounded-sm transition-colors",
                  filterType === t ? "bg-ink text-paper" : "text-ink-3 hover:text-ink",
                )}
              >
                {checkTypeMeta[t].label}
              </button>
            ))}
          </div>
          {/* 状态过滤 */}
          <div className="flex items-center gap-1 p-0.5 bg-paper-2 border border-ink-line rounded-sm">
            <button
              onClick={() => setFilterStatus("all")}
              className={cn(
                "px-2.5 py-1 text-2xs rounded-sm transition-colors",
                filterStatus === "all" ? "bg-ink text-paper" : "text-ink-3 hover:text-ink",
              )}
            >
              全部状态
            </button>
            {(["pass", "warn", "fail", "pending"] as VerifyStatus[]).map((s) => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={cn(
                  "px-2.5 py-1 text-2xs rounded-sm transition-colors",
                  filterStatus === s ? "bg-ink text-paper" : "text-ink-3 hover:text-ink",
                )}
              >
                {statusMeta[s].label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <Card bodyClassName="p-0">
        <div className="px-4 py-2.5 border-b border-ink-line-2 text-2xs text-ink-4 font-mono flex items-center justify-between">
          <span>显示 {filteredItems.length} / {verifyItems.length} 项</span>
          <span>点击展开详情</span>
        </div>
        <ul className="divide-y divide-ink-line-2">
          {filteredItems.map((item) => {
            const meta = checkTypeMeta[item.check_type];
            const sm = statusMeta[item.status];
            const StatusIcon = sm.icon;
            const expanded = expandedId === item.id;
            const lesson = item.lesson_id ? lessonById.get(item.lesson_id) : null;
            return (
              <li key={item.id} className="px-4">
                <button
                  onClick={() => setExpandedId(expanded ? null : item.id)}
                  className="w-full text-left py-3 flex items-start gap-3"
                >
                  <span className={cn(
                    "shrink-0 mt-0.5 flex h-7 w-7 items-center justify-center rounded-sm font-mono text-2xs font-bold",
                    meta.tone === "vermilion" && "bg-vermilion-tint text-vermilion-deep",
                    meta.tone === "teal" && "bg-teal-tint text-teal-2",
                    meta.tone === "gold" && "bg-gold-soft text-ink-2",
                    meta.tone === "ink" && "bg-ink/10 text-ink",
                  )}>
                    {meta.short}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-ink">{item.target_name}</span>
                      <Badge tone={sm.tone}>
                        <StatusIcon size={10} />
                        {sm.label}
                      </Badge>
                      {lesson && (
                        <Badge tone="default">课时{lesson.no} · {lesson.unitName}</Badge>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-ink-3 line-clamp-1">
                      {item.actual_in_system}
                    </div>
                  </div>
                </button>
                {expanded && (
                  <div className="pb-4 pl-10 pr-2 space-y-3">
                    {/* 三层证据标记 */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-2xs text-ink-4 font-mono">证据层：</span>
                      {item.evidence_layers.map((l) => (
                        <Badge key={l} tone={evidenceLayerTone[l]}>
                          {evidenceLayerCN[l]}
                        </Badge>
                      ))}
                    </div>
                    {/* 教师用书预期 */}
                    <div className="p-2.5 bg-teal-tint/30 border-l-2 border-l-teal rounded-sm">
                      <div className="text-2xs uppercase tracking-[0.15em] text-teal-2 font-mono mb-1">
                        教师用书预期（p.{item.tb_printed_page}）
                      </div>
                      <p className="text-xs text-ink-2 leading-relaxed">{item.expected_from_tb}</p>
                    </div>
                    {/* 系统实际结果 */}
                    <div className="p-2.5 bg-gold-soft/40 border-l-2 border-l-gold rounded-sm">
                      <div className="text-2xs uppercase tracking-[0.15em] text-ink-2 font-mono mb-1">
                        系统当前解析结果
                      </div>
                      <p className="text-xs text-ink-2 leading-relaxed">{item.actual_in_system}</p>
                    </div>
                    {/* 差异说明 */}
                    {item.diff_note && (
                      <div className={cn(
                        "p-2.5 border-l-2 rounded-sm",
                        item.status === "fail" ? "bg-err-soft/40 border-l-err" : "bg-warn-soft/40 border-l-warn",
                      )}>
                        <div className={cn(
                          "text-2xs uppercase tracking-[0.15em] font-mono mb-1",
                          item.status === "fail" ? "text-err" : "text-warn",
                        )}>
                          差异说明
                        </div>
                        <p className="text-xs text-ink-2 leading-relaxed">{item.diff_note}</p>
                      </div>
                    )}
                    {/* 对象/课时链接 */}
                    <div className="flex items-center gap-3 text-2xs text-ink-4 font-mono">
                      {item.textbook_object_id && <span>教材对象 {item.textbook_object_id}</span>}
                      {item.lesson_id && <span>课时 {item.lesson_id}</span>}
                    </div>
                  </div>
                )}
              </li>
            );
          })}
          {filteredItems.length === 0 && (
            <li className="px-4 py-8 text-center text-sm text-ink-4">
              当前筛选条件下无验证项
            </li>
          )}
        </ul>
      </Card>

      {/* 验证说明 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 mt-10 flex items-center gap-2">
        <ShieldCheck size={18} className="text-teal" />
        <span className="chapter-num">三</span> 验证方法与分层保存说明
      </h2>
      <Card>
        <div className="space-y-3 text-sm text-ink-2 leading-relaxed">
          <p>
            <strong className="text-ink">验证依据：</strong>
            以教师用书中的单元、课时、教材页码、例题和练习引用作为明确的内容范围和证据来源，对照系统当前的解析结果。
          </p>
          <p>
            <strong className="text-ink">分层保存：</strong>
            每条验证项同时标记三层证据 — 教材原页事实（textbook-page，来自 blocks.ts/objects.ts）、教师用书原文（tb-text，来自 teacherBook.ts）、系统推断（system-infer，来自 relations/mathStructures）。三者独立存储，不互相覆盖。
          </p>
          <p>
            <strong className="text-ink">不覆盖原则：</strong>
            教师用书是参照和证据来源，但不得直接覆盖教材原页事实。当教师用书与系统解析存在差异时，以 warn/fail 状态记录差异，并通过纠错流程（corrections）修复系统推断层，而非修改教材原页事实层。
          </p>
          <p>
            <strong className="text-ink">四类能力覆盖：</strong>
            题目完整性（隐藏条件/气泡/表格/相邻区域是否遗漏）、课时调取（跨页完整调取，不遗漏不重复不混入）、练习集合（同一课时多道练习独立完整且建立联系）、绑定准确性（对象-页面/单元/试一试-例题/共用材料归属）。
          </p>
        </div>
      </Card>

      <div className="mt-6 text-center text-2xs text-ink-4 font-mono">
        教材解析能力验证 · 三层证据分层保存 · 教师用书参照不覆盖教材原页事实
      </div>
    </div>
  );
}
