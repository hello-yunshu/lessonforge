import { useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge, { ConfBadge } from "@/components/ui/Badge";
import { reviewTasks, contentBlocks, pages } from "@/data";
import { cn, blockTypeCN } from "@/lib/utils";
import {
  ListChecks,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

const reasonCN: Record<string, string> = {
  "new-icon": "未见过的新图标",
  "role-conflict": "角色识别冲突",
  "bubble-unclear": "人物与气泡绑定不清",
  "multi-owner": "图片可能属于多个题目",
  "span-page": "题目疑似跨页",
  "blank-ambiguous": "表格空白含义不清",
  "scale-unclear": "图中数字或刻度无法确认",
  "no-vs-example": "普通数字与例题编号冲突",
  "parse-conflict": "多个解析器结果不一致",
  "multi-candidate": "用户上传图片存在多个可能原页",
};

const reasonTone: Record<string, "vermilion" | "warn" | "teal" | "gold"> = {
  "multi-owner": "gold",
  "role-conflict": "vermilion",
  "scale-unclear": "warn",
  "decoration-adjacent": "teal",
};

export default function Review() {
  const pending = reviewTasks.filter((r) => r.status === "pending");
  const done = reviewTasks.filter((r) => r.status !== "pending");
  const [sel, setSel] = useState(pending[0]?.id ?? reviewTasks[0].id);
  const task = reviewTasks.find((r) => r.id === sel)!;
  const block = contentBlocks.find((b) => b.id === task.block_id);
  const page = block ? pages.find((p) => p.id === block.page_id) : undefined;

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={10}
        eyebrow="REVIEW QUEUE"
        title="审核队列"
        subtitle="系统不要求教师逐页检查全部结果，优先让教师审核低置信度与高风险项。教师确认后沉淀到资源库和回归测试集。"
        right={
          <div className="flex gap-2">
            <Badge tone="warn">{pending.length} 待审</Badge>
            <Badge tone="ok">{done.length} 已处理</Badge>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-6">
        {/* 待审列表 */}
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3 flex items-center gap-2">
            <ListChecks size={16} className="text-vermilion" /> 待审项
          </h2>
          <div className="space-y-2">
            {reviewTasks.map((r) => {
              const b = contentBlocks.find((x) => x.id === r.block_id);
              const isSel = r.id === sel;
              return (
                <button
                  key={r.id}
                  onClick={() => setSel(r.id)}
                  className={cn(
                    "w-full text-left p-3 bg-paper border rounded-sm transition-all",
                    isSel ? "border-vermilion ring-2 ring-vermilion/30" : "border-ink-line hover:shadow-card",
                    r.status !== "pending" && "opacity-60",
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Badge tone={reasonTone[r.reason] ?? "default"}>{reasonCN[r.reason]}</Badge>
                    <span className="text-2xs text-ink-4 ml-auto">优先级 {r.priority}</span>
                  </div>
                  <p className="text-xs text-ink-2 line-clamp-2">{r.detail}</p>
                  {b && (
                    <div className="mt-1.5 flex items-center gap-2">
                      <span className="text-2xs text-ink-4 font-mono">{b.id}</span>
                      <ConfBadge value={b.confidence} />
                      {r.status === "confirmed" && <Badge tone="ok">已确认</Badge>}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* 审核界面 */}
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3">人工审核</h2>
          <Card accent="vermilion">
            {/* 待审信息 */}
            <div className="flex items-start gap-3 mb-4 pb-4 border-b border-ink-line-2">
              <div className="flex h-10 w-10 items-center justify-center bg-vermilion-tint rounded-sm shrink-0">
                <AlertTriangle size={18} className="text-vermilion-deep" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <Badge tone={reasonTone[task.reason] ?? "default"}>{reasonCN[task.reason]}</Badge>
                  <Badge tone="default">优先级 {task.priority}</Badge>
                </div>
                <p className="mt-1.5 text-sm text-ink">{task.detail}</p>
              </div>
            </div>

            {/* 原页证据并排 */}
            {block && page && (
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">原页证据</div>
                  <Link
                    to={`/library/page/${page.id}`}
                    className="block bg-paper-2 border border-ink-line rounded-sm p-3 hover:border-vermilion transition-colors"
                  >
                    <div className="aspect-[3/4] grid-paper-fine bg-paper border border-ink-line-2 rounded-sm flex items-center justify-center mb-2">
                      <span className="text-2xs text-ink-4">PDF p.{page.pdf_page_no}</span>
                    </div>
                    <div className="text-2xs text-ink-3 font-mono">印刷 p.{page.printed_page_no}</div>
                  </Link>
                </div>
                <div>
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">内容块</div>
                  <div className="bg-paper-2 border border-ink-line rounded-sm p-3 space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge tone="default">{blockTypeCN(block.type)}</Badge>
                      <ConfBadge value={block.confidence} />
                    </div>
                    <div>
                      <div className="text-2xs text-ink-4 uppercase font-mono">原始文字</div>
                      <p className="text-xs text-ink-2 mt-0.5">{block.raw_text || "—"}</p>
                    </div>
                    <div>
                      <div className="text-2xs text-ink-4 uppercase font-mono">规范化文字</div>
                      <p className="text-xs text-ink-2 mt-0.5">{block.normalized_text || "—"}</p>
                    </div>
                    <div className="pt-2 border-t border-ink-line-2 text-2xs text-ink-4 font-mono">
                      块 {block.id} · 来源 {block.source}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 决策建议 */}
            {task.status === "pending" ? (
              <div className="space-y-3">
                <div className="bg-paper-2 border border-ink-line rounded-sm p-3">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1">系统建议</div>
                  <p className="text-xs text-ink-2">
                    {task.reason === "multi-owner" && "建议归属为共用材料（shared_material），不绑定单一题号。"}
                    {task.reason === "role-conflict" && "建议根据话语功能确认为教师角色，身份与功能分开保存。"}
                    {task.reason === "scale-unclear" && "建议人工确认刻度读数，纠错后沉淀为通用样本。"}
                    {task.reason === "decoration-adjacent" && "建议确认装饰图，不计入数学条件。"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-ok text-paper text-sm rounded-sm hover:opacity-90 transition-opacity">
                    <CheckCircle2 size={15} /> 确认并沉淀
                  </button>
                  <button className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-paper border border-ink-line text-ink-2 text-sm rounded-sm hover:border-err hover:text-err transition-colors">
                    <XCircle size={15} /> 驳回
                  </button>
                </div>
                <div className="text-2xs text-ink-4 text-center">
                  确认后将沉淀到资源库与回归测试集
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 p-3 bg-ok-soft/40 border border-ok/20 rounded-sm">
                <CheckCircle2 size={16} className="text-ok" />
                <span className="text-sm text-ink-2">该审核项已{task.status === "confirmed" ? "确认" : "驳回"}</span>
                <Link to="/corrections" className="ml-auto text-xs text-teal hover:underline flex items-center gap-1">
                  查看纠错记录 <ArrowRight size={11} />
                </Link>
              </div>
            )}
          </Card>

          {/* 审核原则 */}
          <Card className="mt-4" bodyClassName="p-4">
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">优先审核场景</div>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-2xs text-ink-2">
              {Object.entries(reasonCN).map(([k, v]) => (
                <li key={k} className="flex items-center gap-1.5">
                  <span className="text-vermilion">·</span> {v}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
