import { useParams, Link } from "react-router-dom";
import { useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge, { ConfBadge, ReviewBadge } from "@/components/ui/Badge";
import { pages, blocksByPage, coordsByBlock, blockTypeColor } from "@/data";
import type { ContentBlock, PixelRect, NormalizedRect } from "@/data";
import { cn, blockTypeCN, objectTypeCN } from "@/lib/utils";
import { ArrowLeft, Grid2x2, MapPin, ImageIcon, Square, ZoomIn, X } from "lucide-react";

const PAGE_W = 812;
const PAGE_H = 1131;

// 为每个块计算像素矩形：优先 pixel，没有则用 normalized 转换
function rectOf(block: ContentBlock): { left: number; top: number; w: number; h: number; source: "pixel" | "normalized" } | null {
  const px = coordsByBlock(block.id).find((x) => x.kind === "pixel");
  if (px && px.kind === "pixel") {
    const g = px.geometry as PixelRect;
    return { left: g.x, top: g.y, w: g.w, h: g.h, source: "pixel" };
  }
  const nm = coordsByBlock(block.id).find((x) => x.kind === "normalized");
  if (nm && nm.kind === "normalized") {
    const g = nm.geometry as NormalizedRect;
    return {
      left: g.nx * PAGE_W,
      top: g.ny * PAGE_H,
      w: g.nw * PAGE_W,
      h: g.nh * PAGE_H,
      source: "normalized",
    };
  }
  return null;
}

export default function PageView() {
  const { pageId = "p-010" } = useParams();
  const page = pages.find((p) => p.id === pageId);
  const blocks = blocksByPage(pageId);
  const [selected, setSelected] = useState<string | null>(blocks[0]?.id ?? null);
  const [showImage, setShowImage] = useState(true);
  const [showBoxes, setShowBoxes] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [zoom, setZoom] = useState(false);

  if (!page) return <div className="text-ink-3">页面不存在</div>;

  const selectedBlock = blocks.find((b) => b.id === selected);
  const selectedCoords = selectedBlock ? coordsByBlock(selectedBlock.id) : [];

  // 统计有坐标的块数
  const blocksWithRect = blocks.filter((b) => rectOf(b) !== null);

  return (
    <div className="animate-ink-rise">
      <Link
        to="/library"
        className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-vermilion mb-4"
      >
        <ArrowLeft size={12} /> 返回教材标准库
      </Link>
      <PageHeader
        no={2}
        eyebrow={`PAGE · PDF p.${page.pdf_page_no} / 印刷 p.${page.printed_page_no}`}
        title="页面与内容块"
        subtitle="每页拆分为带坐标的内容块。标准教材页坐标基于标准页面宽高的像素坐标，归一化坐标转换到 0–1，并支持四边形与不规则多边形。点击下方'显示原页图'可将 PDF 实际页面作为底图叠加，方框即对应图片上的内容块区域。"
        right={
          <div className="flex gap-2">
            <Badge tone="default">{page.width_px}×{page.height_px}px</Badge>
            <Badge tone="default">旋转 {page.rotation}°</Badge>
            <Badge tone="teal">{blocksWithRect.length}/{blocks.length} 有坐标</Badge>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-6">
        {/* 左：页面可视化（PDF 底图 + 内容块方框叠加） */}
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3 flex items-center gap-2">
            <Grid2x2 size={16} className="text-vermilion" /> 标准页面坐标 · PDF 原页叠加
          </h2>

          {/* 工具栏 */}
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <ToolToggle
              active={showImage}
              onClick={() => setShowImage((v) => !v)}
              icon={<ImageIcon size={11} />}
              label="原页底图"
              tone="vermilion"
            />
            <ToolToggle
              active={showBoxes}
              onClick={() => setShowBoxes((v) => !v)}
              icon={<Square size={11} />}
              label="内容块方框"
              tone="teal"
            />
            <ToolToggle
              active={showLabels}
              onClick={() => setShowLabels((v) => !v)}
              icon={<MapPin size={11} />}
              label="块标签"
              tone="default"
            />
            <button
              onClick={() => setZoom(true)}
              className="ml-auto inline-flex items-center gap-1 px-2 py-1 text-2xs bg-vermilion text-paper rounded-sm hover:bg-vermilion-deep"
            >
              <ZoomIn size={11} /> 放大查看
            </button>
          </div>

          <Card bodyClassName="p-3" noPad>
            <div className="relative bg-paper-2 rounded-sm border border-ink-line p-2">
              {/* 页面框（按比例缩放，与 PDF 原页同比例） */}
              <div
                className="relative grid-paper-fine bg-paper border border-ink-line overflow-hidden"
                style={{ aspectRatio: `${PAGE_W} / ${PAGE_H}` }}
              >
                {/* 底图：PDF 实际页面 */}
                {showImage && (
                  <img
                    src={page.page_image}
                    alt={`PDF p.${page.pdf_page_no}`}
                    className="absolute inset-0 w-full h-full object-cover bg-white pointer-events-none"
                    loading="lazy"
                  />
                )}

                {/* 内容块方框叠加层 */}
                {showBoxes &&
                  blocks.map((b) => {
                    const r = rectOf(b);
                    if (!r) return null;
                    const left = (r.left / PAGE_W) * 100;
                    const top = (r.top / PAGE_H) * 100;
                    const w = (r.w / PAGE_W) * 100;
                    const h = (r.h / PAGE_H) * 100;
                    const isSel = b.id === selected;
                    return (
                      <button
                        key={b.id}
                        onClick={() => setSelected(b.id)}
                        className={cn(
                          "absolute border-2 text-2xs leading-tight px-1 transition-all text-left overflow-hidden group",
                          isSel
                            ? "border-vermilion ring-2 ring-vermilion/40 z-20 bg-vermilion/30"
                            : "border-vermilion/70 hover:border-vermilion hover:bg-vermilion/20 z-10 bg-vermilion/10",
                          !showImage && blockTypeColor[b.type],
                        )}
                        style={{ left: `${left}%`, top: `${top}%`, width: `${w}%`, height: `${h}%` }}
                        title={`${blockTypeCN(b.type)} · ${b.normalized_text?.slice(0, 30) ?? ""}`}
                      >
                        {showLabels && (
                          <span
                            className={cn(
                              "font-mono text-[0.5rem] block truncate px-0.5 rounded-sm",
                              showImage
                                ? "bg-vermilion text-paper"
                                : "",
                            )}
                          >
                            {b.read_order}. {blockTypeCN(b.type)}
                          </span>
                        )}
                        {/* 坐标来源标记（pixel / normalized） */}
                        {r.source === "normalized" && (
                          <span className="absolute bottom-0 right-0 px-0.5 text-[0.4rem] bg-teal/70 text-paper font-mono rounded-tl-sm">
                            nm
                          </span>
                        )}
                      </button>
                    );
                  })}

                {/* 页码标识（右下角，对应 PDF 印刷页码位置） */}
                <div className="absolute bottom-1 right-1 px-1.5 py-0.5 bg-ink/70 text-paper text-[0.5rem] font-mono rounded-sm backdrop-blur-sm">
                  印刷 p.{page.printed_page_no}
                </div>
                {/* PDF 页码标识（左上角） */}
                <div className="absolute top-1 left-1 px-1.5 py-0.5 bg-vermilion/90 text-paper text-[0.5rem] font-mono rounded-sm backdrop-blur-sm">
                  PDF p.{page.pdf_page_no}
                </div>
                {/* 坐标系原点标识 */}
                <div className="absolute top-1 right-1 px-1.5 py-0.5 bg-paper/80 text-ink-3 text-[0.5rem] font-mono rounded-sm backdrop-blur-sm border border-ink-line">
                  (0,0) ↓→
                </div>
              </div>

              {/* 比例尺 */}
              <div className="mt-2 flex items-center justify-between text-2xs text-ink-4 font-mono px-1">
                <span>原点 (0,0)</span>
                <span>标准页 {PAGE_W}×{PAGE_H}px</span>
                <span>({PAGE_W},{PAGE_H})</span>
              </div>
            </div>

            {/* 说明 */}
            <div className="mt-3 px-1 text-2xs text-ink-3 leading-relaxed">
              {showImage ? (
                <>
                  <span className="text-vermilion-deep font-medium">原页底图已显示：</span>
                  红色方框为内容块区域，半透明背景可透过看到下方 PDF 实际内容。
                  点击方框可在右侧查看该块的详细坐标与文字。
                </>
              ) : (
                <>
                  <span className="text-ink-2 font-medium">原页底图已隐藏：</span>
                  方框按块类型着色，便于查看内容块分布。
                  点击"原页底图"按钮可重新显示 PDF 图片。
                </>
              )}
            </div>
          </Card>

          {/* 图例 */}
          <div className="mt-3">
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">内容块类型图例</div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(blockTypeColor).slice(0, 10).map(([k, v]) => (
                <span key={k} className={cn("px-1.5 py-0.5 text-2xs rounded-sm", v)}>
                  {blockTypeCN(k)}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* 右：内容块列表 + 坐标面板 */}
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3">
            内容块 · 阅读顺序 ({blocks.length})
          </h2>
          <div className="space-y-1.5 mb-6">
            {blocks.map((b) => {
              const isSel = b.id === selected;
              const hasRect = rectOf(b) !== null;
              return (
                <button
                  key={b.id}
                  onClick={() => setSelected(b.id)}
                  className={cn(
                    "w-full text-left flex items-center gap-3 px-3 py-2 rounded-sm border transition-all",
                    isSel
                      ? "border-vermilion bg-vermilion-tint/50"
                      : "border-ink-line bg-paper hover:border-ink-line-2 hover:bg-paper-2",
                  )}
                >
                  <span className="text-2xs font-mono text-ink-4 w-6 text-center shrink-0">{b.read_order}</span>
                  <span className={cn("px-1.5 py-0.5 text-2xs rounded-sm shrink-0", blockTypeColor[b.type])}>
                    {blockTypeCN(b.type)}
                  </span>
                  <span className="text-sm text-ink-2 flex-1 min-w-0 truncate">
                    {b.normalized_text || b.raw_text || "—"}
                  </span>
                  {!hasRect && (
                    <span className="text-[0.5rem] px-1 py-0.5 bg-paper-3 text-ink-4 rounded-sm" title="无结构化坐标">
                      无坐标
                    </span>
                  )}
                  {hasRect && (
                    <span className="text-[0.5rem] px-1 py-0.5 bg-teal-tint text-teal-2 rounded-sm" title="已有结构化坐标">
                      有坐标
                    </span>
                  )}
                  <ConfBadge value={b.confidence} />
                  <ReviewBadge status={b.review_status} />
                </button>
              );
            })}
          </div>

          {/* 选中块的坐标详情 */}
          {selectedBlock && (
            <Card title={`坐标详情 · ${blockTypeCN(selectedBlock.type)}`} accent="vermilion">
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <div className="text-2xs uppercase text-ink-3 font-mono">块 ID</div>
                    <code className="text-ink-2 font-mono">{selectedBlock.id}</code>
                  </div>
                  <div>
                    <div className="text-2xs uppercase text-ink-3 font-mono">识别来源</div>
                    <span className="text-ink-2">
                      {selectedBlock.source === "ocr" ? "OCR" : selectedBlock.source === "rule" ? "规则" : "人工"}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <div className="text-2xs uppercase text-ink-3 font-mono">原始文字</div>
                    <p className="text-ink-2">{selectedBlock.raw_text || "—"}</p>
                  </div>
                </div>

                <div className="pt-3 border-t border-ink-line-2">
                  <div className="text-2xs uppercase text-ink-3 font-mono mb-2 flex items-center gap-1">
                    <MapPin size={11} /> 三类坐标
                  </div>
                  <div className="space-y-2">
                    {selectedCoords.length === 0 && (
                      <p className="text-xs text-ink-4">
                        该块暂无结构化坐标（PDF 原页方框视图中不显示）。可补充 pixel/normalized/polygon 坐标以便精确定位。
                      </p>
                    )}
                    {selectedCoords.map((c) => (
                      <div key={c.id} className="bg-paper-2 rounded-sm p-2.5">
                        <div className="flex items-center gap-2 mb-1.5">
                          <Badge tone={c.kind === "polygon" ? "vermilion" : "teal"}>
                            {c.kind === "pixel" ? "标准页像素" : c.kind === "normalized" ? "归一化 0–1" : "多边形"}
                          </Badge>
                          <code className="text-2xs text-ink-4 font-mono">{c.id}</code>
                        </div>
                        {c.kind === "pixel" && (() => {
                          const g = c.geometry as { x: number; y: number; w: number; h: number };
                          return (
                            <div className="grid grid-cols-4 gap-2 text-2xs font-mono text-ink-2">
                              <div><span className="text-ink-4">x</span> {g.x}</div>
                              <div><span className="text-ink-4">y</span> {g.y}</div>
                              <div><span className="text-ink-4">w</span> {g.w}</div>
                              <div><span className="text-ink-4">h</span> {g.h}</div>
                            </div>
                          );
                        })()}
                        {c.kind === "normalized" && (() => {
                          const g = c.geometry as { nx: number; ny: number; nw: number; nh: number };
                          return (
                            <div className="grid grid-cols-4 gap-2 text-2xs font-mono text-ink-2">
                              <div><span className="text-ink-4">nx</span> {g.nx.toFixed(4)}</div>
                              <div><span className="text-ink-4">ny</span> {g.ny.toFixed(4)}</div>
                              <div><span className="text-ink-4">nw</span> {g.nw.toFixed(4)}</div>
                              <div><span className="text-ink-4">nh</span> {g.nh.toFixed(4)}</div>
                            </div>
                          );
                        })()}
                        {c.kind === "polygon" && (() => {
                          const g = c.geometry as { points: [number, number][] };
                          return (
                            <div className="flex flex-wrap gap-1.5">
                              {g.points.map((p, i) => (
                                <span
                                  key={i}
                                  className="px-1.5 py-0.5 text-2xs bg-paper rounded-sm font-mono text-ink-2"
                                >
                                  P{i}({p[0]},{p[1]})
                                </span>
                              ))}
                            </div>
                          );
                        })()}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-3 border-t border-ink-line-2 text-2xs text-ink-4 leading-relaxed">
                  坐标规范：用户照片坐标与标准教材坐标分开保存，通过单应性 / 局部网格变换映射。
                  信息严重缺失时降低置信度并提示重新拍摄，批注与教材标准内容分开保存。
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* 放大查看模态框：原页图 + 方框叠加 */}
      {zoom && (
        <div
          className="fixed inset-0 z-50 bg-ink/80 backdrop-blur-sm flex items-center justify-center p-8 animate-ink-rise"
          onClick={() => setZoom(false)}
        >
          <div
            className="relative max-w-4xl max-h-full bg-paper rounded-sm border border-ink-line shadow-2xl overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-2.5 bg-paper-2 border-b border-ink-line-2 flex items-center justify-between">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge tone="vermilion">PDF p.{page.pdf_page_no}</Badge>
                <Badge tone="ink">印刷 p.{page.printed_page_no}</Badge>
                <span className="text-2xs text-ink-3 font-mono ml-1">原页 + 内容块方框叠加</span>
              </div>
              <button
                onClick={() => setZoom(false)}
                className="px-2 py-1 text-xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper inline-flex items-center gap-1"
              >
                <X size={12} /> 关闭
              </button>
            </div>
            <div className="overflow-auto p-4 bg-paper-2">
              <div
                className="relative bg-paper border border-ink-line overflow-hidden mx-auto"
                style={{ width: "min(700px, 100%)", aspectRatio: `${PAGE_W} / ${PAGE_H}` }}
              >
                <img
                  src={page.page_image}
                  alt={`放大查看 PDF p.${page.pdf_page_no}`}
                  className="absolute inset-0 w-full h-full object-cover bg-white"
                />
                {blocks.map((b) => {
                  const r = rectOf(b);
                  if (!r) return null;
                  const left = (r.left / PAGE_W) * 100;
                  const top = (r.top / PAGE_H) * 100;
                  const w = (r.w / PAGE_W) * 100;
                  const h = (r.h / PAGE_H) * 100;
                  const isSel = b.id === selected;
                  return (
                    <button
                      key={b.id}
                      onClick={() => setSelected(b.id)}
                      className={cn(
                        "absolute border-2 transition-all overflow-hidden",
                        isSel
                          ? "border-vermilion ring-2 ring-vermilion/40 z-20 bg-vermilion/30"
                          : "border-vermilion/70 hover:border-vermilion hover:bg-vermilion/20 z-10 bg-vermilion/10",
                      )}
                      style={{ left: `${left}%`, top: `${top}%`, width: `${w}%`, height: `${h}%` }}
                      title={`${blockTypeCN(b.type)} · ${b.normalized_text?.slice(0, 40) ?? ""}`}
                    >
                      <span className="font-mono text-[0.6rem] block truncate px-1 bg-vermilion text-paper">
                        {b.read_order}. {blockTypeCN(b.type)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// 工具栏切换按钮
function ToolToggle({
  active,
  onClick,
  icon,
  label,
  tone,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  tone: "vermilion" | "teal" | "default";
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 px-2 py-1 text-2xs rounded-sm border transition-colors",
        active
          ? tone === "vermilion"
            ? "bg-vermilion text-paper border-vermilion"
            : tone === "teal"
              ? "bg-teal text-paper border-teal"
              : "bg-ink text-paper border-ink"
          : "bg-paper text-ink-2 border-ink-line hover:border-ink",
      )}
    >
      {icon}
      {label}
      <span className={cn("ml-0.5", active ? "opacity-90" : "opacity-40")}>
        {active ? "ON" : "OFF"}
      </span>
    </button>
  );
}
