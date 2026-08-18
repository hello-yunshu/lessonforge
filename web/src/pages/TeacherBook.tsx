import { useState, useMemo, useEffect, useRef } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import {
  teacherBook,
  teacherBookPages,
  teacherBookUnits,
  teacherBookLessons,
  teacherBookReferences,
} from "@/data";
import { cn, toCN } from "@/lib/utils";
import {
  BookMarked,
  BookOpen,
  Hash,
  Layers,
  FileText,
  Map as MapIcon,
  BookCopy,
  Quote,
  Boxes,
} from "lucide-react";

type Tab = "meta" | "pages" | "units" | "lessons" | "refs";

const tabs: { key: Tab; label: string; icon: typeof BookMarked }[] = [
  { key: "meta", label: "元信息", icon: BookMarked },
  { key: "pages", label: "页面映射", icon: FileText },
  { key: "units", label: "单元说明", icon: Layers },
  { key: "lessons", label: "课时划分", icon: BookOpen },
  { key: "refs", label: "教材引用", icon: Quote },
];

// 引用类型 → 中文
const refKindCN: Record<string, string> = {
  example: "例题",
  try: "试一试",
  "think-do": "想想做做",
  exercise: "练习",
  operation: "操作活动",
  scene: "情境图",
  formula: "算式",
};

const refKindTone: Record<string, "vermilion" | "teal" | "gold" | "default" | "ink"> = {
  example: "vermilion",
  try: "teal",
  "think-do": "teal",
  exercise: "gold",
  operation: "gold",
  scene: "default",
  formula: "ink",
};

export default function TeacherBook() {
  const [tab, setTab] = useState<Tab>("meta");
  const [selectedUnitId, setSelectedUnitId] = useState<string>(teacherBookUnits[0]?.id ?? "");
  const [selectedLessonId, setSelectedLessonId] = useState<string>(teacherBookLessons[0]?.id ?? "");
  // 跳转到教材引用：记录要滚动到的课时ID
  const [scrollToLessonId, setScrollToLessonId] = useState<string | null>(null);
  const refsContainerRef = useRef<HTMLDivElement>(null);

  // 按章节分组页面
  const pagesBySection = useMemo(() => {
    const map = new Map<string, typeof teacherBookPages>();
    for (const p of teacherBookPages) {
      if (!map.has(p.section)) map.set(p.section, []);
      map.get(p.section)!.push(p);
    }
    return [...map.entries()];
  }, []);

  const selectedUnit = teacherBookUnits.find((u) => u.id === selectedUnitId);

  // 单元级筛选联动：当前单元的课时与教材引用
  const filteredLessons = useMemo(
    () => teacherBookLessons.filter((l) => l.unit_id === selectedUnitId),
    [selectedUnitId],
  );

  const filteredReferences = useMemo(
    () =>
      teacherBookReferences.filter((r) => {
        const lesson = teacherBookLessons.find((l) => l.id === r.lesson_id);
        return lesson?.unit_id === selectedUnitId;
      }),
    [selectedUnitId],
  );

  // 按课时分组教材引用（保持课时顺序）
  const refsByLesson = useMemo(() => {
    const map = new Map<string, typeof teacherBookReferences>();
    for (const l of filteredLessons) {
      const refs = filteredReferences.filter((r) => r.lesson_id === l.id);
      if (refs.length > 0) map.set(l.id, refs);
    }
    return [...map.entries()];
  }, [filteredLessons, filteredReferences]);

  // 跳转到教材引用时自动滚动到对应课时位置
  useEffect(() => {
    if (tab === "refs" && scrollToLessonId) {
      const lessonId = scrollToLessonId;
      // 用双重 rAF 确保 refs tab 已完成 DOM 渲染后再查找目标元素
      const raf1 = requestAnimationFrame(() => {
        const raf2 = requestAnimationFrame(() => {
          const el = document.getElementById(`ref-lesson-${lessonId}`);
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
            el.classList.add("ring-2", "ring-vermilion");
            window.setTimeout(() => el.classList.remove("ring-2", "ring-vermilion"), 2000);
          }
          setScrollToLessonId(null);
        });
        // 清理：在 raf2 真正执行前若组件卸载则取消
        pendingCleanups.push(() => cancelAnimationFrame(raf2));
      });
      const pendingCleanups: Array<() => void> = [];
      return () => {
        cancelAnimationFrame(raf1);
        pendingCleanups.forEach((fn) => fn());
      };
    }
  }, [tab, scrollToLessonId]);

  // 切换单元时，自动选中该单元的第一个课时
  // 注意：依赖只含 selectedUnitId，确保点击课时按钮时不会重置选中
  useEffect(() => {
    const firstLesson = teacherBookLessons.find((l) => l.unit_id === selectedUnitId);
    if (firstLesson) {
      setSelectedLessonId(firstLesson.id);
    } else {
      setSelectedLessonId("");
    }
  }, [selectedUnitId]);

  const selectedLesson = teacherBookLessons.find((l) => l.id === selectedLessonId);

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={14}
        eyebrow="TEACHER BOOK · STRUCTURED LIBRARY"
        title="教师用书结构化资料库"
        subtitle="将配套教师教学用书处理为版本明确、章节清楚、可精确检索、可返回原文、能与教材对象建立映射的结构化资料库。教师用书是参照与证据来源，不覆盖教材原页事实。"
        right={
          <div className="flex flex-col items-end gap-1">
            <Badge tone="vermilion">{teacherBook.edition}</Badge>
            <Badge tone="default">印刷 {teacherBook.printed_page_start}-{teacherBook.printed_page_end} 页</Badge>
          </div>
        }
      />

      {/* 总览数字 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        {[
          { label: "总页数（PDF）", value: `${teacherBook.pdf_page_count}`, sub: `含二年级上册部分` },
          { label: "三上部分", value: `${teacherBook.pdf_page_end - teacherBook.pdf_page_start + 1}`, sub: `PDF p.${teacherBook.pdf_page_start}-${teacherBook.pdf_page_end}` },
          { label: "印刷页", value: `${teacherBook.printed_page_end - teacherBook.printed_page_start + 1}`, sub: `印刷 p.${teacherBook.printed_page_start}-${teacherBook.printed_page_end}` },
          { label: "单元说明", value: `${teacherBookUnits.length}`, sub: `含综合实践单元` },
          { label: "课时划分", value: `${teacherBookLessons.length}`, sub: `已结构化课时` },
        ].map((m) => (
          <div key={m.label} className="bg-paper border border-ink-line rounded-sm p-3">
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">{m.label}</div>
            <div className="mt-1 font-serif text-xl font-bold text-ink">{m.value}</div>
            <div className="text-2xs text-ink-4 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* Tab 切换 */}
      <div className="flex items-center gap-1 mb-6 border-b border-ink-line">
        {tabs.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2 text-sm border-b-2 -mb-px transition-colors",
                active
                  ? "border-vermilion text-ink font-medium"
                  : "border-transparent text-ink-3 hover:text-ink-2",
              )}
            >
              <t.icon size={14} className={active ? "text-vermilion" : ""} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* 元信息 */}
      {tab === "meta" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="版本与出版信息" accent="vermilion">
            <dl className="grid grid-cols-2 gap-y-3 gap-x-4 text-sm">
              {[
                { k: "版本", v: teacherBook.version },
                { k: "年级", v: teacherBook.grade },
                { k: "册次", v: teacherBook.volume },
                { k: "版次", v: teacherBook.edition },
                { k: "ISBN", v: teacherBook.isbn },
                { k: "CIP", v: teacherBook.cip },
                { k: "出版社", v: teacherBook.publisher },
                { k: "编著者", v: teacherBook.compiled_by },
              ].map((row) => (
                <div key={row.k}>
                  <dt className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">{row.k}</dt>
                  <dd className="mt-0.5 text-ink-2">{row.v}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="PDF 与印刷页映射" accent="teal">
            <div className="space-y-3 text-sm">
              <div className="flex items-start gap-3 p-3 bg-paper-2 rounded-sm">
                <BookCopy size={16} className="text-teal mt-0.5 shrink-0" />
                <div>
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">PDF 文件</div>
                  <div className="mt-0.5 text-ink-2 font-mono text-xs break-all">{teacherBook.pdf_file}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">PDF 总页数</div>
                  <div className="mt-1 font-serif text-lg font-bold text-ink">{teacherBook.pdf_page_count}</div>
                </div>
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">三上 PDF 范围</div>
                  <div className="mt-1 font-serif text-lg font-bold text-ink">
                    p.{teacherBook.pdf_page_start}-{teacherBook.pdf_page_end}
                  </div>
                </div>
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">印刷起始页</div>
                  <div className="mt-1 font-serif text-lg font-bold text-ink">{teacherBook.printed_page_start}</div>
                </div>
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">印刷结束页</div>
                  <div className="mt-1 font-serif text-lg font-bold text-ink">{teacherBook.printed_page_end}</div>
                </div>
              </div>
              <div className="p-3 bg-vermilion-tint/40 border border-vermilion/20 rounded-sm">
                <div className="flex items-start gap-2 text-xs text-vermilion-deep">
                  <BookMarked size={14} className="shrink-0 mt-0.5" />
                  <div>
                    三年级上册部分占 PDF 第 {teacherBook.pdf_page_start}-{teacherBook.pdf_page_end} 页，对应教师用书印刷第 {teacherBook.printed_page_start}-{teacherBook.printed_page_end} 页。映射规则：印刷页 = PDF 页 − {teacherBook.pdf_page_start - teacherBook.printed_page_start}。
                  </div>
                </div>
              </div>
            </div>
          </Card>

          <Card title="分层保存原则" accent="gold" className="lg:col-span-2">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              {[
                { layer: "教材原页事实", desc: "来自 blocks.ts / objects.ts，记录教材 PDF 原页内容，是事实底座，不可被覆盖。", tone: "vermilion" as const },
                { layer: "教师用书原文", desc: "来自 teacherBook.ts，记录教师用书原文片段与页码，作为参照与证据来源。", tone: "teal" as const },
                { layer: "系统推断", desc: "来自 relations / mathStructures，记录系统推断的关系与结构，可被纠错。", tone: "gold" as const },
              ].map((l) => (
                <div key={l.layer} className="p-3 border border-ink-line rounded-sm">
                  <Badge tone={l.tone}>{l.layer}</Badge>
                  <p className="mt-2 text-xs text-ink-3 leading-relaxed">{l.desc}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* 页面映射 */}
      {tab === "pages" && (
        <div className="space-y-6">
          <Card title="教师用书印刷页 ↔ PDF 页映射" subtitle="按章节分组，支持精确检索与原文定位">
            <div className="space-y-4">
              {pagesBySection.map(([section, pages]) => (
                <div key={section}>
                  <div className="flex items-center gap-2 mb-2">
                    <Hash size={13} className="text-vermilion" />
                    <h4 className="font-serif text-sm font-bold text-ink">{section}</h4>
                    <Badge tone="default">{pages.length} 页</Badge>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                    {pages.map((p) => (
                      <div
                        key={p.id}
                        className="p-2.5 bg-paper-2 border border-ink-line-2 rounded-sm text-xs hover:border-vermilion/40 transition-colors"
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-mono text-ink-4 text-2xs">PDF p.{p.pdf_page_no}</span>
                          <span className="font-mono text-ink-3 text-2xs">
                            {p.printed_page_no !== null ? `印刷 p.${p.printed_page_no}` : "无印刷页码"}
                          </span>
                        </div>
                        <p className="text-ink-2 leading-snug">{p.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* 单元说明 */}
      {tab === "units" && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {teacherBookUnits.map((u) => (
              <button
                key={u.id}
                onClick={() => setSelectedUnitId(u.id)}
                className={cn(
                  "px-3 py-1.5 text-xs rounded-sm border transition-colors",
                  selectedUnitId === u.id
                    ? "bg-ink text-paper border-ink"
                    : "bg-paper text-ink-2 border-ink-line hover:border-vermilion/40",
                )}
              >
                <span className="font-mono mr-1.5">{u.is_comprehensive_practice ? "综" : `U${u.no}`}</span>
                {u.name}
              </button>
            ))}
          </div>

          {selectedUnit && (
            <Card
              title={`第 ${toCN(selectedUnit.no)} 单元 · ${selectedUnit.name}`}
              subtitle={selectedUnit.is_comprehensive_practice ? "综合实践 / 探索规律" : "常规教学单元"}
              accent="vermilion"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                {[
                  { label: "课时数", value: `${selectedUnit.lesson_count}` },
                  { label: "教师用书页", value: `p.${selectedUnit.tb_printed_start}-${selectedUnit.tb_printed_end}` },
                  { label: "教材页范围", value: `p.${selectedUnit.textbook_printed_start}-${selectedUnit.textbook_printed_end}` },
                  { label: "教材单元 ID", value: selectedUnit.textbook_unit_id ?? "—", mono: true },
                ].map((m) => (
                  <div key={m.label} className="p-2.5 bg-paper-2 rounded-sm">
                    <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">{m.label}</div>
                    <div className={cn("mt-0.5 font-serif font-bold text-ink", m.mono && "font-mono text-sm")}>{m.value}</div>
                  </div>
                ))}
              </div>
              <div className="p-3 bg-paper-2 border-l-2 border-l-vermilion rounded-sm">
                <div className="text-2xs uppercase tracking-[0.15em] text-vermilion-deep font-mono mb-1">教学目标原文</div>
                <p className="text-sm text-ink-2 leading-relaxed">{selectedUnit.objectives_excerpt}</p>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* 课时划分 */}
      {tab === "lessons" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 p-3 bg-paper-2 border border-ink-line-2 rounded-sm">
            <div className="flex items-center gap-2 text-sm text-ink-2">
              <Layers size={14} className="text-vermilion" />
              <span>当前单元：</span>
              <span className="font-medium text-ink">
                {selectedUnit ? `${selectedUnit.is_comprehensive_practice ? "综合实践" : `第 ${toCN(selectedUnit.no)} 单元`} · ${selectedUnit.name}` : "—"}
              </span>
            </div>
            <Badge tone="default">{filteredLessons.length} 课时</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            {filteredLessons.map((l) => (
              <button
                key={l.id}
                onClick={() => setSelectedLessonId(l.id)}
                className={cn(
                  "px-3 py-1.5 text-xs rounded-sm border transition-colors",
                  selectedLessonId === l.id
                    ? "bg-ink text-paper border-ink"
                    : "bg-paper text-ink-2 border-ink-line hover:border-vermilion/40",
                )}
              >
                <span className="font-mono mr-1.5">课时{l.no}</span>
                {l.title}
              </button>
            ))}
          </div>

          {selectedLesson && (
            <Card
              title={`课时 ${selectedLesson.no} · ${selectedLesson.title}`}
              subtitle={`所属单元：${teacherBookUnits.find((u) => u.id === selectedLesson.unit_id)?.name ?? "—"}`}
              accent="teal"
            >
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">教材印刷页范围</div>
                  <div className="mt-1 font-serif text-base font-bold text-ink">
                    印 p.{selectedLesson.textbook_printed_pages.join(", ")}
                  </div>
                </div>
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">教材 PDF 页 ID</div>
                  <div className="mt-1 font-mono text-xs text-ink-2">
                    {selectedLesson.textbook_page_ids.join(", ")}
                  </div>
                </div>
                <div className="p-3 bg-paper-2 rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-ink-4 font-mono">引用教材对象</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {selectedLesson.textbook_object_ids.map((oid) => (
                      <Badge key={oid} tone="default">{oid}</Badge>
                    ))}
                  </div>
                </div>
              </div>

              <div className="p-3 bg-paper-2 border-l-2 border-l-teal rounded-sm mb-4">
                <div className="text-2xs uppercase tracking-[0.15em] text-teal-2 font-mono mb-1">教学建议（教师用书原文依据）</div>
                <p className="text-sm text-ink-2 leading-relaxed">{selectedLesson.teaching_suggestion}</p>
              </div>

              <div className="p-3 bg-vermilion-tint/30 border border-vermilion/20 rounded-sm mb-4">
                <div className="flex items-start gap-2 text-xs text-vermilion-deep">
                  <MapIcon size={14} className="shrink-0 mt-0.5" />
                  <div>
                    教师用书印刷页 {selectedLesson.tb_printed_pages.join(", ")}；该课时的教材对象覆盖印刷页 {selectedLesson.textbook_printed_pages.join(", ")}，用于跨页调取验证。
                  </div>
                </div>
              </div>

              {/* 查看本课时教材引用 */}
              {filteredReferences.some((r) => r.lesson_id === selectedLesson.id) && (
                <button
                  onClick={() => {
                    // 先切到 refs tab，再设置待滚动课时，触发滚动 effect
                    setTab("refs");
                    setScrollToLessonId(selectedLesson.id);
                  }}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-gold/10 border border-gold/30 rounded-sm text-ink-2 hover:bg-gold/20 transition-colors"
                >
                  <Quote size={14} className="text-gold" />
                  查看本课时教材引用（{filteredReferences.filter((r) => r.lesson_id === selectedLesson.id).length} 条）
                </button>
              )}
            </Card>
          )}
        </div>
      )}

      {/* 教材引用 */}
      {tab === "refs" && (
        <div className="space-y-4" ref={refsContainerRef}>
          <div className="flex items-center justify-between gap-3 p-3 bg-paper-2 border border-ink-line-2 rounded-sm">
            <div className="flex items-center gap-2 text-sm text-ink-2">
              <Layers size={14} className="text-vermilion" />
              <span>当前单元：</span>
              <span className="font-medium text-ink">
                {selectedUnit ? `${selectedUnit.is_comprehensive_practice ? "综合实践" : `第 ${toCN(selectedUnit.no)} 单元`} · ${selectedUnit.name}` : "—"}
              </span>
            </div>
            <Badge tone="default">{filteredReferences.length} 条引用</Badge>
          </div>
          <Card title="教师用书对教材对象的引用" subtitle="原文片段保留，可返回原文；教师用书引用不覆盖教材原页事实" accent="gold">
            <div className="mb-3 flex items-center gap-2 text-xs text-ink-3">
              <Boxes size={14} className="text-vermilion" />
              当前单元共 {filteredReferences.length} 条引用，按课时分组
            </div>
            <div className="space-y-6">
              {refsByLesson.map(([lessonId, refs]) => {
                const lesson = teacherBookLessons.find((l) => l.id === lessonId);
                if (!lesson) return null;
                return (
                  <div
                    key={lessonId}
                    id={`ref-lesson-${lessonId}`}
                    className="scroll-mt-4 rounded-sm transition-shadow"
                  >
                    <div className="flex items-center gap-2 mb-2 pb-1 border-b border-ink-line-2">
                      <BookOpen size={14} className="text-teal" />
                      <span className="font-serif text-sm font-bold text-ink">
                        课时{lesson.no} · {lesson.title}
                      </span>
                      <Badge tone="default">{refs.length} 条</Badge>
                    </div>
                    <div className="space-y-2">
                      {refs.map((r) => (
                        <div key={r.id} className="p-3 border border-ink-line-2 rounded-sm hover:border-vermilion/30 transition-colors">
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <Badge tone={refKindTone[r.ref_kind]}>{refKindCN[r.ref_kind]}</Badge>
                                <span className="text-sm font-medium text-ink">{r.tb_description}</span>
                              </div>
                              <div className="mt-1 flex items-center gap-3 text-2xs text-ink-4 font-mono">
                                <span>教师用书 p.{r.tb_printed_page}</span>
                                <span>→ 教材 p.{r.textbook_printed_page}</span>
                                <span>对象 {r.textbook_object_id ?? "—"}</span>
                              </div>
                            </div>
                          </div>
                          <div className="p-2.5 bg-paper-2 rounded-sm border-l-2 border-l-gold/40">
                            <div className="text-2xs text-ink-4 font-mono mb-1">原文片段</div>
                            <p className="text-xs text-ink-2 leading-relaxed italic">{r.excerpt}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
