import { Link } from "react-router-dom";
import { useState, useMemo } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { textbook, pages, units, sections } from "@/data";
import { cn, toCN } from "@/lib/utils";
import { FileText, Hash, ChevronRight, ChevronLeft, BookOpen, Layers } from "lucide-react";

const PAGE_SIZE = 8; // 每页显示8条

export default function Library() {
  const [selectedUnit, setSelectedUnit] = useState<string | null>(null); // null = 全部
  const [currentPage, setCurrentPage] = useState(0);

  // 按选中的单元过滤页面
  const filteredPages = useMemo(() => {
    if (!selectedUnit) return pages;
    const unit = units.find((u) => u.id === selectedUnit);
    if (!unit) return pages;
    return pages.filter(
      (p) => p.pdf_page_no >= unit.start_page && p.pdf_page_no <= unit.end_page,
    );
  }, [selectedUnit]);

  // 分页
  const totalPages = Math.max(1, Math.ceil(filteredPages.length / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages - 1);
  const pageStart = safePage * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, filteredPages.length);
  const visiblePages = filteredPages.slice(pageStart, pageEnd);

  const handleSelectUnit = (unitId: string | null) => {
    setSelectedUnit(unitId);
    setCurrentPage(0);
  };

  // 计算每个单元的页面数
  const unitPageCount = (unitId: string) => {
    const unit = units.find((u) => u.id === unitId);
    if (!unit) return 0;
    return pages.filter(
      (p) => p.pdf_page_no >= unit.start_page && p.pdf_page_no <= unit.end_page,
    ).length;
  };

  const selectedUnitData = selectedUnit ? units.find((u) => u.id === selectedUnit) : null;

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={1}
        eyebrow="TEXTBOOK STANDARD LIBRARY"
        title="教材标准库"
        subtitle="原始证据 / 页面内容块 / 语义对象 / 关系 / 数学结构 — 正式主数据以结构化数据库与原始证据为准，不以 Markdown 或向量库代替。"
        right={<Badge tone="vermilion">{textbook.edition}</Badge>}
      />

      {/* 元数据卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        {[
          { label: "版本", value: textbook.version, sub: "Jiangsu Education Edition" },
          { label: "年级 · 册次", value: `${textbook.grade} · ${textbook.volume}`, sub: "Grade 3 Vol.1" },
          { label: "总页数", value: `${textbook.page_count} 页`, sub: `PDF+印刷双页码` },
          { label: "已入库", value: `${pages.length} 页`, sub: `覆盖全教材` },
        ].map((m) => (
          <div key={m.label} className="bg-paper border border-ink-line rounded-sm p-4">
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">{m.label}</div>
            <div className="mt-1.5 font-serif text-xl font-bold text-ink">{m.value}</div>
            <div className="text-2xs text-ink-4 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* 哈希 */}
      <Card className="mb-8" bodyClassName="p-4 flex items-center gap-3">
        <Hash size={18} className="text-vermilion shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">原始 PDF SHA-256</div>
          <code className="text-xs text-ink-2 font-mono break-all">{textbook.pdf_hash}</code>
        </div>
        <Badge tone="ok">原始未修改</Badge>
      </Card>

      {/* 目录树 + 页面列表 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-6">
        {/* 左：目录结构（可点击） */}
        <div>
          <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
            <span className="chapter-num">一</span> 目录结构
            <span className="text-2xs text-ink-4 font-sans font-normal ml-1">点击单元筛选右侧页面</span>
          </h2>
          <Card bodyClassName="p-0">
            {/* 全部按钮 */}
            <button
              onClick={() => handleSelectUnit(null)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 transition-colors border-b border-ink-line-2",
                selectedUnit === null
                  ? "bg-vermilion-tint/60 border-l-4 border-l-vermilion"
                  : "hover:bg-paper-3 border-l-4 border-l-transparent",
              )}
            >
              <BookOpen size={16} className={cn("shrink-0", selectedUnit === null ? "text-vermilion" : "text-ink-3")} />
              <span className={cn("text-sm font-medium flex-1 text-left", selectedUnit === null ? "text-vermilion-deep font-bold" : "text-ink")}>
                全部单元
              </span>
              <Badge tone={selectedUnit === null ? "vermilion" : "default"}>{pages.length} 页</Badge>
            </button>
            <ul>
              {units.map((u) => {
                const isSel = selectedUnit === u.id;
                const isSub = "parent_id" in u && u.parent_id;
                const count = unitPageCount(u.id);
                return (
                  <li key={u.id} className={cn("border-b border-ink-line-2 last:border-b-0", isSub && "bg-paper-2/50")}>
                    <button
                      onClick={() => handleSelectUnit(u.id)}
                      className={cn(
                        "w-full flex items-center gap-3 px-4 py-3 transition-colors text-left",
                        isSub && "pl-8",
                        isSel
                          ? "bg-vermilion-tint/60 border-l-4 border-l-vermilion"
                          : "hover:bg-paper-3 border-l-4 border-l-transparent",
                      )}
                    >
                      <span className={cn("font-serif text-sm font-bold w-6 shrink-0", isSel ? "text-vermilion" : "text-vermilion/70")}>
                        {isSub ? "·" : toCN(u.no)}
                      </span>
                      <span className={cn("text-sm flex-1 truncate", isSel ? "text-vermilion-deep font-bold" : "text-ink font-medium")}>
                        {u.name}
                      </span>
                      <span className="text-2xs text-ink-4 font-mono shrink-0">
                        p.{u.start_page}–{u.end_page}
                      </span>
                      <Badge tone={isSel ? "vermilion" : "default"}>{count}</Badge>
                    </button>
                    {/* 该单元下的节 */}
                    {sections.filter((s) => s.unit_id === u.id).map((s) => (
                      <div key={s.id} className={cn("flex items-center gap-2 text-xs text-ink-3 pb-2", isSub ? "pl-12" : "pl-12")}>
                        <ChevronRight size={12} className="shrink-0" />
                        <span>{s.no}. {s.name}</span>
                      </div>
                    ))}
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>

        {/* 右：已入库页面（按单元过滤 + 分页） */}
        <div>
          <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
            <span className="chapter-num">二</span> 已入库页面
            {selectedUnitData && (
              <span className="text-sm font-sans font-normal text-vermilion-deep">
                · {selectedUnitData.name}
              </span>
            )}
          </h2>
          <Card bodyClassName="p-0">
            {/* 页面计数条 */}
            <div className="px-4 py-2 bg-paper-2 border-b border-ink-line-2 flex items-center justify-between text-2xs text-ink-3 font-mono">
              <span>
                第 {pageStart + 1}–{pageEnd} 条 / 共 {filteredPages.length} 条
                {selectedUnitData && ` · ${selectedUnitData.name}`}
              </span>
              <span>{totalPages > 1 ? `${safePage + 1}/${totalPages} 页` : "1 页"}</span>
            </div>
            {/* 页面列表 */}
            <ul className="divide-y divide-ink-line-2">
              {visiblePages.length === 0 && (
                <li className="px-4 py-8 text-center text-sm text-ink-4">
                  <FileText size={24} className="mx-auto mb-2 opacity-40" />
                  该单元暂无入库页面
                </li>
              )}
              {visiblePages.map((p) => {
                // 查找该页所属单元
                const pageUnit = units.find(
                  (u) => p.pdf_page_no >= u.start_page && p.pdf_page_no <= u.end_page,
                );
                return (
                  <li key={p.id}>
                    <Link
                      to={`/library/page/${p.id}`}
                      className="flex items-center gap-3 px-4 py-2.5 hover:bg-paper-3 transition-colors"
                    >
                      {/* 缩略图 */}
                      <div className="w-10 h-14 shrink-0 rounded-sm overflow-hidden border border-ink-line bg-white">
                        <img
                          src={p.page_image}
                          alt={`p.${p.pdf_page_no}`}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-ink font-medium">
                          PDF 第 {p.pdf_page_no} 页
                          {p.printed_page_no > 0 && (
                            <span className="text-ink-4 ml-1">· 印刷 p.{p.printed_page_no}</span>
                          )}
                        </div>
                        <div className="text-2xs text-ink-4 font-mono truncate">
                          {pageUnit ? pageUnit.name : "未分类"}
                        </div>
                      </div>
                      <Badge tone="default">{p.width_px}×{p.height_px}</Badge>
                      <ChevronRight size={14} className="text-ink-4 shrink-0" />
                    </Link>
                  </li>
                );
              })}
            </ul>
            {/* 翻页按钮 */}
            {totalPages > 1 && (
              <div className="px-4 py-2.5 bg-paper-2 border-t border-ink-line-2 flex items-center justify-between">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
                  disabled={safePage === 0}
                  className={cn(
                    "inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-sm border transition-colors",
                    safePage === 0
                      ? "bg-paper-3 text-ink-4 border-ink-line cursor-not-allowed"
                      : "bg-paper text-ink-2 border-ink-line hover:border-vermilion hover:text-vermilion",
                  )}
                >
                  <ChevronLeft size={12} /> 上一页
                </button>
                {/* 页码按钮 */}
                <div className="flex items-center gap-1">
                  {Array.from({ length: totalPages }, (_, i) => {
                    if (totalPages <= 7 || i === 0 || i === totalPages - 1 || Math.abs(i - safePage) <= 1) {
                      return (
                        <button
                          key={i}
                          onClick={() => setCurrentPage(i)}
                          className={cn(
                            "w-6 h-6 text-xs rounded-sm transition-colors",
                            i === safePage
                              ? "bg-vermilion text-paper font-bold"
                              : "text-ink-2 hover:bg-paper-3",
                          )}
                        >
                          {i + 1}
                        </button>
                      );
                    }
                    if (i === 1 || i === totalPages - 2) {
                      return <span key={i} className="text-ink-4 text-xs px-0.5">…</span>;
                    }
                    return null;
                  })}
                </div>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={safePage >= totalPages - 1}
                  className={cn(
                    "inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-sm border transition-colors",
                    safePage >= totalPages - 1
                      ? "bg-paper-3 text-ink-4 border-ink-line cursor-not-allowed"
                      : "bg-paper text-ink-2 border-ink-line hover:border-vermilion hover:text-vermilion",
                  )}
                >
                  下一页 <ChevronRight size={12} />
                </button>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
