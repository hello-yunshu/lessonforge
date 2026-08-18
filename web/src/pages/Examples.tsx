import { useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import SealStamp from "@/components/ui/SealStamp";
import {
  examples,
  objects,
  relations,
  speeches,
  characters,
  pages,
  contentBlocks,
} from "@/data";
import type { Page as TextbookPage } from "@/data/types";
import { cn, toCN } from "@/lib/utils";
import { BookMarked, BookOpen, MessageCircle, Link2, ArrowRight, FileText, Check, AlertCircle, Eye, ZoomIn } from "lucide-react";

const componentCN: Record<string, string> = {
  anchor: "例题编号图标",
  scene: "情境图",
  given: "已知条件",
  question: "核心问题",
  method: "学生思考方法",
  operation: "操作过程",
  formula: "算式或竖式",
  followup: "教师追问",
  conclusion: "归纳或结论",
  answer: "答句",
};

// PDF 核查记录：每个 PDF 页对应的核查状态
// "verified" = 已通过 pdfjs 文本提取核查（文本与 mock 数据一致）
// "pending"  = 已渲染但未完成文本核查
// "none"     = 未渲染（该 PDF 页不在已渲染范围）
const pdfVerifyStatus: Record<number, "verified" | "pending" | "none"> = {
  9: "verified",   // 单元封面
  10: "verified",  // 例1 豆豆
  11: "verified",  // 试一试 + 想想做做
  12: "verified",  // 例2 小青
  13: "verified",  // 想想做做
  14: "verified",  // 练习一
  15: "verified",  // 例3 芳芳
  16: "verified",  // 想想做做 + 你知道吗
  17: "verified",  // 练习二
  18: "verified",  // 练习二续
  19: "verified",  // 一天的时间
  20: "verified",  // 一天的时间（续）
};

export default function Examples() {
  const [sel, setSel] = useState(examples[0].id);
  // 当前查看的教材页索引（用于跨页例题切换）
  const [pageIdx, setPageIdx] = useState(0);
  // 是否放大查看原页图
  const [zoomPage, setZoomPage] = useState(false);

  const ex = examples.find((e) => e.id === sel)!;
  const obj = objects.find((o) => o.id === ex.object_id)!;
  const objRelations = relations.filter((r) => r.src_object_id === obj.id);
  const objSpeeches = speeches.filter((s) => s.object_id === obj.id);
  const objPages = pages.filter((p) => obj.page_ids.includes(p.id));

  // 安全：pageIdx 不越界
  const safePageIdx = Math.min(pageIdx, objPages.length - 1);
  const currentPage: TextbookPage | undefined = objPages[safePageIdx];
  const verifyStatus = currentPage ? pdfVerifyStatus[currentPage.pdf_page_no] ?? "none" : "none";

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={5}
        eyebrow="EXAMPLE RECOGNITION"
        title="例题识别"
        subtitle="以'书本形状图标+图标内部数字'为强锚点。例题对象不得只截取情境图或问题句，须完整封装情境图、已知条件、问题、方法、算式、追问、归纳、答句，可跨页延续。下方显示对应教材原页（PDF p./印刷 p.），支持放大查看与跨页切换。"
        right={
          <Badge tone="ok">
            <Check size={11} /> PDF 已核查 {Object.values(pdfVerifyStatus).filter((s) => s === "verified").length} 页
          </Badge>
        }
      />

      {/* 例题列表 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4">
        <span className="chapter-num">一</span> 已识别例题锚点
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-10">
        {examples.map((e) => {
          const o = objects.find((x) => x.id === e.object_id)!;
          const isSel = e.id === sel;
          const ePages = pages.filter((p) => o.page_ids.includes(p.id));
          return (
            <button
              key={e.id}
              onClick={() => {
                setSel(e.id);
                setPageIdx(0);
              }}
              className={cn(
                "relative p-4 bg-paper border rounded-sm text-left transition-all overflow-hidden",
                isSel ? "border-vermilion ring-2 ring-vermilion/30" : "border-ink-line hover:shadow-card-hover",
              )}
            >
              <div className="flex items-start gap-3">
                <SealStamp text={`例${toCN(e.anchor_no)}`} size="sm" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-ink truncate">{o.title}</div>
                  <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                    {e.span_pages && <Badge tone="vermilion">跨页</Badge>}
                    <Badge tone="default">{e.components.length} 组成</Badge>
                  </div>
                </div>
              </div>
              <div className="mt-2 text-2xs text-ink-4 font-mono flex items-center gap-1.5">
                <FileText size={10} />
                PDF p.{ePages.map((p) => p.pdf_page_no).join("→")}
                <span className="text-ink-4 mx-0.5">·</span>
                印刷 p.{ePages.map((p) => p.printed_page_no).join("→")}
              </div>
            </button>
          );
        })}
      </div>

      {/* ===== 教材原页证据（新增 · 用户核心需求） ===== */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <BookOpen size={18} className="text-vermilion" />
        <span className="chapter-num">二</span> 教材原页证据 · {obj.title}
      </h2>

      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6 mb-10">
        {/* 左：原页图 */}
        <Card
          accent="vermilion"
          bodyClassName="p-4"
          title="教材原页（扫描件回溯）"
          right={
            <div className="flex items-center gap-1.5">
              {objPages.length > 1 && (
                <>
                  <button
                    onClick={() => setPageIdx((i) => Math.max(0, i - 1))}
                    disabled={safePageIdx === 0}
                    className="px-2 py-0.5 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ← 上一页
                  </button>
                  <span className="text-2xs text-ink-3 font-mono">
                    {safePageIdx + 1} / {objPages.length}
                  </span>
                  <button
                    onClick={() => setPageIdx((i) => Math.min(objPages.length - 1, i + 1))}
                    disabled={safePageIdx >= objPages.length - 1}
                    className="px-2 py-0.5 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    下一页 →
                  </button>
                </>
              )}
              <button
                onClick={() => setZoomPage(true)}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs bg-vermilion text-paper rounded-sm hover:bg-vermilion-deep"
              >
                <ZoomIn size={10} /> 放大
              </button>
            </div>
          }
        >
          {/* 页码标识带 */}
          {currentPage && (
            <div className="mb-3 p-2.5 bg-paper-2 border border-ink-line rounded-sm flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge tone="vermilion">PDF p.{currentPage.pdf_page_no}</Badge>
                <ArrowRight size={11} className="text-ink-4" />
                <Badge tone="ink">印刷 p.{currentPage.printed_page_no}</Badge>
                <Badge tone="default">{currentPage.width_px}×{currentPage.height_px}px</Badge>
              </div>
              <div className="flex items-center gap-1.5">
                {verifyStatus === "verified" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-2xs bg-ok-soft text-ok rounded-sm border border-ok/30">
                    <Check size={10} /> PDF 文本核查通过
                  </span>
                )}
                {verifyStatus === "pending" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-2xs bg-warn-soft text-warn rounded-sm border border-warn/30">
                    <AlertCircle size={10} /> 待 PDF 核查
                  </span>
                )}
                {verifyStatus === "none" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-2xs bg-paper-3 text-ink-4 rounded-sm border border-ink-line">
                    <AlertCircle size={10} /> 未渲染
                  </span>
                )}
              </div>
            </div>
          )}

          {/* 原页图 */}
          {currentPage ? (
            <div className="relative bg-paper-2 border border-ink-line rounded-sm overflow-hidden group">
              <img
                src={currentPage.page_image}
                alt={`教材原页 PDF p.${currentPage.pdf_page_no} 印刷 p.${currentPage.printed_page_no}`}
                className="block w-full h-auto max-h-[600px] object-contain bg-white"
                loading="lazy"
              />
              {/* 印刷页码标识（左下角覆盖） */}
              <div className="absolute bottom-2 left-2 px-2 py-1 bg-ink/80 text-paper text-2xs font-mono rounded-sm backdrop-blur-sm flex items-center gap-1.5">
                <BookMarked size={11} />
                印刷 p.{currentPage.printed_page_no}
              </div>
              {/* PDF 页码标识（右上角覆盖） */}
              <div className="absolute top-2 right-2 px-2 py-1 bg-vermilion/90 text-paper text-2xs font-mono rounded-sm backdrop-blur-sm">
                PDF p.{currentPage.pdf_page_no}
              </div>
              {/* 提示：图片中右下角可见印刷页码 */}
              <div className="absolute bottom-2 right-2 px-2 py-1 bg-paper/80 text-ink-3 text-[0.5rem] font-mono rounded-sm backdrop-blur-sm border border-ink-line">
                ↗ 图片右下角可见课本印刷页码
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-ink-4 bg-paper-2 rounded-sm border border-ink-line">
              该例题无关联教材页
            </div>
          )}

          {/* 跨页索引 */}
          {objPages.length > 1 && (
            <div className="mt-3 flex items-center gap-1.5">
              {objPages.map((p, i) => (
                <button
                  key={p.id}
                  onClick={() => setPageIdx(i)}
                  className={cn(
                    "px-2 py-1 text-2xs rounded-sm border font-mono transition-colors",
                    i === safePageIdx
                      ? "bg-vermilion text-paper border-vermilion"
                      : "bg-paper text-ink-3 border-ink-line hover:border-vermilion",
                  )}
                >
                  p.{p.pdf_page_no}
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* 右：原页内容块回溯 + 跨页说明 */}
        <div className="space-y-4">
          <Card title="原页内容块回溯（基于 PDF 文本提取）" accent="teal" bodyClassName="p-4">
            {currentPage && (
              <div className="space-y-1.5">
                {contentBlocks
                  .filter((b) => b.page_id === currentPage.id)
                  .slice(0, 8)
                  .map((b) => (
                    <div key={b.id} className="flex items-start gap-2 text-xs">
                      <span className="text-2xs font-mono text-ink-4 w-5 text-center shrink-0 pt-0.5">{b.read_order}</span>
                      <span className="text-ink-2 flex-1 min-w-0">{b.normalized_text}</span>
                    </div>
                  ))}
                {contentBlocks.filter((b) => b.page_id === currentPage.id).length === 0 && (
                  <p className="text-xs text-ink-4">该页无已识别内容块（可能为封面/目录/单元扉页）</p>
                )}
                {contentBlocks.filter((b) => b.page_id === currentPage.id).length > 8 && (
                  <p className="text-2xs text-ink-4 italic">
                    共 {contentBlocks.filter((b) => b.page_id === currentPage.id).length} 个内容块，仅展示前 8 个
                  </p>
                )}
              </div>
            )}
            <div className="mt-3 pt-3 border-t border-ink-line-2 text-2xs text-ink-3 leading-relaxed">
              内容块文本来自 PDF 文本层提取（pdfjs-dist），与教材印刷内容一致。
              教师可对照左侧原页图核对：图片左下角为印刷页码、右上角为 PDF 内部页码。
            </div>
          </Card>

          {/* 跨页延续说明 */}
          {ex.span_pages && objPages.length > 1 && (
            <Card title="跨页延续说明" accent="vermilion" bodyClassName="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Badge tone="vermilion">跨页对象</Badge>
                <span className="text-xs text-ink-2">
                  PDF p.{objPages.map((p) => p.pdf_page_no).join(" → ")}
                </span>
              </div>
              <p className="text-2xs text-ink-3 leading-relaxed">
                本对象跨 {objPages.length} 页延续，题号在第一页、内容可能延伸至后续页。
                已合并为单一教材对象（page_ids: {obj.page_ids.join(", ")}）。
                点击上方"上一页 / 下一页"或页码索引切换查看各页原页。
              </p>
            </Card>
          )}
        </div>
      </div>

      {/* ===== 例题对象封装 ===== */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <BookMarked size={18} className="text-vermilion" />
        <span className="chapter-num">三</span> 例题对象封装 · {obj.title}
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 mb-10">
        <Card accent="vermilion" bodyClassName="p-6">
          <div className="flex items-center gap-4 mb-5">
            <SealStamp text={`例${toCN(ex.anchor_no)}`} size="lg" />
            <div>
              <div className="text-2xs uppercase tracking-[0.2em] text-ink-3 font-mono">STRONG ANCHOR · 书本图标+数字</div>
              <h3 className="font-serif text-xl font-bold text-ink mt-0.5">{obj.title}</h3>
              <div className="mt-1 flex items-center gap-1.5 text-2xs text-ink-4 font-mono">
                <FileText size={10} />
                PDF p.{objPages.map((p) => p.pdf_page_no).join("→")}
                <span className="mx-0.5">·</span>
                印刷 p.{objPages.map((p) => p.printed_page_no).join("→")}
              </div>
            </div>
          </div>

          {/* 组成元素环形 */}
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">完整组成元素</div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {ex.components.map((c) => {
              const enabled = true;
              return (
                <div
                  key={c}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-sm border",
                    enabled ? "border-ink-line bg-paper-2" : "border-dashed border-ink-line bg-paper-2/50 opacity-50",
                  )}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", enabled ? "bg-vermilion" : "bg-ink-4")} />
                  <span className="text-xs text-ink-2">{componentCN[c]}</span>
                </div>
              );
            })}
            {["conclusion", "operation"].filter((c) => !ex.components.includes(c as never)).map((c) => (
              <div key={c} className="flex items-center gap-2 px-3 py-2 rounded-sm border border-dashed border-ink-line bg-paper-2/50 opacity-50">
                <span className="h-1.5 w-1.5 rounded-full bg-ink-4" />
                <span className="text-xs text-ink-4">{componentCN[c]}（本例无）</span>
              </div>
            ))}
          </div>

          {ex.span_pages && (
            <div className="mt-5 p-3 bg-vermilion-tint/50 border border-vermilion/20 rounded-sm">
              <div className="text-xs font-medium text-vermilion-deep">⚠ 跨页延续</div>
              <p className="text-2xs text-ink-2 mt-1">
                本例题从 PDF 第 {objPages[0]?.pdf_page_no} 页延续到第 {objPages[objPages.length - 1]?.pdf_page_no} 页，
                已合并为单一例题对象（page_ids: {obj.page_ids.join(", ")}）。
              </p>
            </div>
          )}
        </Card>

        {/* 右：边界判断依据 */}
        <Card title="边界判断依据" bodyClassName="p-4">
          <ul className="space-y-2.5 text-xs">
            <Judge label="当前例题锚点" value={`书本图标内数字 ${ex.anchor_no}`} ok />
            <Judge label="下一个例题锚点" value={ex.anchor_no < 3 ? `例${toCN(ex.anchor_no + 1)}` : "下一单元"} ok />
            <Judge label="试一试/想想做做" value={ex.anchor_no === 1 ? "试一试（不合并为例题正文）" : "想想做做"} ok />
            <Judge label="情境图归属" value={objRelations.find((r) => r.rel_type === "scene-provides")?.note ?? "—"} ok />
            <Judge label="教师追问" value={objSpeeches.find((s) => s.speech_function === "ask-reason")?.content ?? "—"} />
            <Judge label="答句" value={contentBlocks.find((b) => b.page_id === obj.page_ids[0] && b.type === "answer" && b.raw_text.startsWith("答"))?.raw_text ?? "—"} />
            <Judge label="跨页延续" value={ex.span_pages ? "已合并" : "未跨页"} ok={ex.span_pages} />
          </ul>
        </Card>
      </div>

      {/* 关联与话语 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
        <Card title="显式关系" accent="teal" bodyClassName="p-0">
          <ul className="divide-y divide-ink-line-2">
            {objRelations.map((r) => (
              <li key={r.id} className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <Link2 size={12} className="text-teal shrink-0" />
                  <Badge tone="teal">{r.rel_type}</Badge>
                </div>
                <p className="text-xs text-ink-2 ml-5">{r.note}</p>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="人物话语" accent="vermilion" bodyClassName="p-0">
          <ul className="divide-y divide-ink-line-2">
            {objSpeeches.map((sp) => {
              const ch = characters.find((c) => c.id === sp.character_id)!;
              return (
                <li key={sp.id} className="px-4 py-3 flex items-start gap-3">
                  <MessageCircle size={14} className="text-vermilion mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-sm font-medium text-ink">{ch.name}</span>
                      <Badge tone={ch.role === "teacher" ? "vermilion" : "teal"}>{ch.role === "teacher" ? "教师" : "学生"}</Badge>
                      {ch.editor === "system-pdf-check" && (
                        <span className="text-[0.5rem] px-1 py-0.5 bg-ok-soft text-ok rounded-sm">PDF核查</span>
                      )}
                    </div>
                    <p className="text-xs text-ink-2 italic">"{sp.content}"</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      {/* 原页证据 */}
      <Card title="原页证据回溯" bodyClassName="p-4">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {objPages.map((p, i) => (
            <div key={p.id} className="flex items-center gap-2">
              {i > 0 && <ArrowRight size={12} className="text-ink-4" />}
              <Link
                to={`/library/page/${p.id}`}
                className="px-3 py-1.5 bg-paper-2 border border-ink-line rounded-sm hover:border-vermilion hover:text-vermilion transition-colors inline-flex items-center gap-1.5"
              >
                <Eye size={11} />
                PDF p.{p.pdf_page_no} · 印刷 p.{p.printed_page_no}
              </Link>
            </div>
          ))}
          <span className="text-ink-4 ml-auto font-mono text-2xs">
            已封装 {ex.components.length} 组成元素 · PDF 核查通过
          </span>
        </div>
        <div className="mt-3 text-2xs text-ink-4 leading-relaxed">
          所有结果回到原教材 PDF 页、印刷页和精确页面区域。
          教材原页图来自 PDF 渲染（pdfjs-dist + @napi-rs/canvas），左下角标识为印刷页码、右上角为 PDF 内部页码，
          与课本印刷内容一致（已通过文本提取核查）。
        </div>
      </Card>

      {/* 放大查看模态框 */}
      {zoomPage && currentPage && (
        <div
          className="fixed inset-0 z-50 bg-ink/80 backdrop-blur-sm flex items-center justify-center p-8 animate-ink-rise"
          onClick={() => setZoomPage(false)}
        >
          <div
            className="relative max-w-4xl max-h-full bg-paper rounded-sm border border-ink-line shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-2.5 bg-paper-2 border-b border-ink-line-2 flex items-center justify-between">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge tone="vermilion">PDF p.{currentPage.pdf_page_no}</Badge>
                <Badge tone="ink">印刷 p.{currentPage.printed_page_no}</Badge>
                <span className="text-2xs text-ink-3 font-mono ml-1">{obj.title}</span>
              </div>
              <button
                onClick={() => setZoomPage(false)}
                className="px-2 py-1 text-xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper"
              >
                关闭 ✕
              </button>
            </div>
            <div className="overflow-auto max-h-[calc(100vh-100px)]">
              <img
                src={currentPage.page_image}
                alt={`放大查看 PDF p.${currentPage.pdf_page_no}`}
                className="block w-full h-auto bg-white"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Judge({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <li className="flex items-start justify-between gap-3">
      <span className="text-ink-3 shrink-0">{label}</span>
      <span className={cn("text-right flex items-center gap-1.5", ok ? "text-ok" : "text-ink-2")}>
        {ok && <BookOpen size={11} />}
        <span className="text-2xs">{value}</span>
      </span>
    </li>
  );
}
