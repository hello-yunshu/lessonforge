import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge, { ConfBadge } from "@/components/ui/Badge";
import { corrections, versions } from "@/data";
import { cn, fmtDate } from "@/lib/utils";
import {
  GitCommitVertical,
  RotateCcw,
  CheckCircle2,
  XCircle,
  ArrowRight,
  History,
} from "lucide-react";

const iterMap = {
  1: { label: "即时修正", desc: "同一份教材中相同对象可立即使用已确认结果", tone: "teal" as const },
  2: { label: "资源库更新", desc: "新图标变体/新角色姿态/新反例/新边界规则/新共享材料规则", tone: "gold" as const },
  3: { label: "正式升级", desc: "积累足够样本并通过黄金样本回归测试后发布", tone: "vermilion" as const },
};

export default function Corrections() {
  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={9}
        eyebrow="CORRECTION & VERSION"
        title="纠错与版本"
        subtitle="每次纠错记录页面区域、原识别结果、教师修改结果、错误类型、规则版本、模型版本、原置信度、修改人、时间、适用范围、是否通用样本。三级迭代 + 版本号可审计可回滚。"
      />

      {/* 三级迭代说明 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4">
        <span className="chapter-num">一</span> 三级迭代机制
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-10">
        {[1, 2, 3].map((lvl) => {
          const m = iterMap[lvl as 1 | 2 | 3];
          return (
            <Card key={lvl} accent={m.tone}>
              <div className="flex items-center gap-2 mb-2">
                <span className="font-serif text-2xl font-bold text-vermilion">{lvl}</span>
                <Badge tone={m.tone}>{m.label}</Badge>
              </div>
              <p className="text-xs text-ink-2 leading-relaxed">{m.desc}</p>
            </Card>
          );
        })}
      </div>

      {/* 版本时间线 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <History size={18} className="text-vermilion" />
        <span className="chapter-num">二</span> 版本时间线
      </h2>
      <Card className="mb-10" bodyClassName="p-6">
        <ol className="relative border-l-2 border-ink-line ml-3 space-y-5">
          {versions.map((v) => (
            <li key={v.id} className="ml-6">
              <span
                className={cn(
                  "absolute -left-[9px] flex h-4 w-4 items-center justify-center rounded-full ring-4 ring-paper",
                  v.regression_passed ? "bg-ok" : "bg-err",
                )}
              />
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-serif text-lg font-bold text-ink">{v.version_no}</span>
                {v.regression_passed ? (
                  <Badge tone="ok"><CheckCircle2 size={10} /> 回归通过</Badge>
                ) : (
                  <Badge tone="err"><XCircle size={10} /> 回归未通过</Badge>
                )}
                {v.released_at !== "—" && (
                  <span className="text-2xs text-ink-4 font-mono">{fmtDate(v.released_at)}</span>
                )}
              </div>
              <p className="mt-1 text-xs text-ink-3">{v.notes}</p>
              <ul className="mt-2 space-y-1">
                {v.changeset.map((c, i) => (
                  <li key={i} className="text-xs text-ink-2 flex gap-1.5">
                    <span className="text-vermilion">·</span> {c}
                  </li>
                ))}
              </ul>
              {v.regression_passed && (
                <div className="mt-2 flex items-center gap-3">
                  <button className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-2 border border-ink-line rounded-sm text-ink-3 hover:border-vermilion hover:text-vermilion transition-colors">
                    <RotateCcw size={11} /> 回滚至此版本
                  </button>
                </div>
              )}
            </li>
          ))}
        </ol>
      </Card>

      {/* 纠错记录 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <GitCommitVertical size={18} className="text-vermilion" />
        <span className="chapter-num">三</span> 纠错记录
      </h2>
      <div className="space-y-3">
        {corrections.map((c) => {
          const m = iterMap[c.iteration];
          return (
            <Card key={c.id} accent={m.tone} bodyClassName="p-4">
              <div className="flex items-start gap-4">
                <div className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-serif font-bold",
                  m.tone === "teal" && "bg-teal-tint text-teal-2",
                  m.tone === "gold" && "bg-gold-soft text-ink",
                  m.tone === "vermilion" && "bg-vermilion-tint text-vermilion-deep",
                )}>
                  {c.iteration}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <Badge tone={m.tone}>{m.label}</Badge>
                    <span className="text-xs text-ink-3">{c.error_type}</span>
                    {c.is_universal && <Badge tone="gold">通用样本</Badge>}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                    <div className="bg-err-soft/40 border border-err/20 rounded-sm p-3">
                      <div className="text-2xs uppercase text-err font-mono mb-1">原识别结果</div>
                      <p className="text-xs text-ink-2">{c.original}</p>
                      <div className="mt-1.5"><ConfBadge value={c.original_confidence} /></div>
                    </div>
                    <div className="bg-ok-soft/40 border border-ok/20 rounded-sm p-3 flex flex-col">
                      <div className="text-2xs uppercase text-ok font-mono mb-1">教师修改结果</div>
                      <p className="text-xs text-ink-2">{c.revised}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-ink-3 font-mono">
                    <span>页面 {c.page_id}</span>
                    <span>块 {c.block_id}</span>
                    <span>规则 {c.rule_version}</span>
                    <span>模型 {c.model_version}</span>
                    <span>修改人 {c.editor}</span>
                    <span>{fmtDate(c.edited_at)}</span>
                  </div>
                </div>
                <ArrowRight className="text-ink-4 self-center" size={14} />
              </div>
            </Card>
          );
        })}
      </div>

      <div className="mt-6 p-4 bg-paper-2 border border-ink-line rounded-sm text-2xs text-ink-3 leading-relaxed">
        所有更新必须：有版本号 · 可审计 · 可回滚 · 保留旧结果 · 通过回归测试。不得在生产环境让 AI 未经审核自行修改正式规则。
      </div>
    </div>
  );
}
