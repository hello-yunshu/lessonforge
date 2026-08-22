import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import {
  officialLessons,
  lessonEvidences,
  objectLessonAssignments,
  lessonCatalog,
  pages,
  objects,
  teacherBookLessons,
} from "@/data";
import type { OfficialLesson } from "@/data";
import { cn, toCN } from "@/lib/utils";
import {
  BookOpen,
  FileText,
  Layers,
  ChevronRight,
  MapPin,
  ShieldCheck,
  Clock,
  AlertCircle,
  FileSearch,
  Lock,
  ExternalLink,
} from "lucide-react";

// 按单元分组课时
function groupByUnit(lessons: OfficialLesson[]) {
  const map = new Map<string, OfficialLesson[]>();
  for (const l of lessons) {
    if (!map.has(l.unit_id)) map.set(l.unit_id, []);
    map.get(l.unit_id)!.push(l);
  }
  return [...map.entries()];
}

// 单元名称映射
const unitNames: Record<string, string> = {
  "u-1": "第一单元 · 混合运算与数量关系（一）",
  "u-1b": "综合实践 · 一天的时间",
  "u-2": "第二单元 · 两、三位数乘一位数",
  "u-2b": "综合实践 · 曹冲称象的故事",
  "u-3": "第三单元 · 数据的收集与整理",
  "u-3b": "综合实践 · 了解你的好朋友",
  "u-4": "第四单元 · 毫米、分米和千米",
  "u-5": "第五单元 · 平移、旋转和轴对称",
  "u-6": "第六单元 · 两、三位数除以一位数",
  "u-6b": "综合实践 · 间隔排列",
  "u-7": "第七单元 · 数量关系的分析（一）",
  "u-8": "第八单元 · 观察物体（二）",
  "u-9": "期末复习",
};

// 审核状态 → Badge tone
const reviewTone: Record<string, "vermilion" | "teal" | "gold" | "default" | "ink"> = {
  approved: "teal",
  pending: "gold",
  "under-review": "gold",
  disputed: "vermilion",
};

const reviewCN: Record<string, string> = {
  approved: "已审核",
  pending: "待审核",
  "under-review": "审核中",
  disputed: "存在争议",
};

// 置信度 → Badge tone
const confidenceCN: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export default function OfficialLessonsPage() {
  const [selectedLessonId, setSelectedLessonId] = useState<string>(officialLessons[0]?.lesson_id ?? "");
  const [showEvidence, setShowEvidence] = useState(false);

  const grouped = useMemo(() => groupByUnit(officialLessons), []);
  const selectedLesson = officialLessons.find((l) => l.lesson_id === selectedLessonId);
  const selectedEvidences = lessonEvidences.filter((e) => e.lesson_id === selectedLessonId);
  const selectedAssignment = objectLessonAssignments.filter((a) => a.primary_lesson_id === selectedLessonId);
  const tbLesson = selectedLesson
    ? teacherBookLessons.find((l) => l.id === selectedLesson.recommended_period_source_id)
    : null;

  // 获取页面信息
  const lessonPages = selectedLesson
    ? selectedLesson.included_page_ids.map((pid) => pages.find((p) => p.id === pid)).filter(Boolean)
    : [];

  // 获取对象信息
  const lessonObjects = selectedLesson
    ? selectedLesson.included_object_ids.map((oid) => objects.find((o) => o.id === oid)).filter(Boolean)
    : [];

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={15}
        eyebrow="OFFICIAL LESSON CATALOG · TASK 3"
        title="正式课时划分与内容归属"
        subtitle="经过教材原页、完整教材对象、教师用书证据和人工审核共同确认的教材内容范围。这是后续教材分析的唯一课时边界基准。"
        right={
          <div className="flex flex-col items-end gap-1">
            <Badge tone={lessonCatalog.status === "frozen" ? "teal" : "gold"}>
              {lessonCatalog.status === "frozen" ? "已冻结" : "草稿"}
            </Badge>
            <Badge tone="default">{officialLessons.length} 个正式课时</Badge>
          </div>
        }
      />

      {/* 总览数字 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        {[
          { label: "正式课时", value: `${officialLessons.length}`, sub: "已剔除5个机动课时" },
          { label: "已审核", value: `${officialLessons.filter((l) => l.review_status === "approved").length}`, sub: "第一单元已对象化" },
          { label: "待审核", value: `${officialLessons.filter((l) => l.review_status === "pending").length}`, sub: "待对象化后精确归属" },
          { label: "对象归属", value: `${objectLessonAssignments.length}`, sub: "第一单元9个对象" },
          { label: "跨页课时", value: `${officialLessons.filter((l) => l.cross_page_flag).length}`, sub: "跨多页课时数" },
        ].map((m) => (
          <div key={m.label} className="bg-paper border border-ink-line rounded-sm p-3">
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">{m.label}</div>
            <div className="mt-1 font-serif text-xl font-bold text-ink">{m.value}</div>
            <div className="text-2xs text-ink-4 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-6">
        {/* 左侧：单元→课时树 */}
        <div className="w-72 shrink-0">
          <Card title="课时目录" accent="vermilion" className="sticky top-4">
            <div className="space-y-3 max-h-[calc(100vh-200px)] overflow-y-auto">
              {grouped.map(([unitId, unitLessons]) => (
                <div key={unitId}>
                  <div className="flex items-center gap-1.5 px-1 mb-1.5">
                    <Layers size={12} className="text-vermilion" />
                    <span className="text-2xs uppercase tracking-[0.1em] text-ink-3 font-mono font-medium">
                      {unitNames[unitId] ?? unitId}
                    </span>
                  </div>
                  <ul className="space-y-0.5">
                    {unitLessons.map((l) => {
                      const active = selectedLessonId === l.lesson_id;
                      return (
                        <li key={l.lesson_id}>
                          <button
                            onClick={() => setSelectedLessonId(l.lesson_id)}
                            className={cn(
                              "w-full flex items-center gap-2 px-2 py-1.5 text-xs rounded-sm text-left transition-colors",
                              active
                                ? "bg-ink text-paper"
                                : "text-ink-2 hover:bg-paper-3",
                            )}
                          >
                            <span className={cn("font-mono text-2xs shrink-0", active ? "text-vermilion-soft" : "text-ink-4")}>
                              {String(l.lesson_sequence_in_book).padStart(2, "0")}
                            </span>
                            <span className="truncate flex-1">{l.official_lesson_name}</span>
                            {l.review_status === "approved" && (
                              <ShieldCheck size={11} className={active ? "text-teal-soft" : "text-teal"} />
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* 右侧：课时详情 */}
        <div className="flex-1 min-w-0">
          {selectedLesson && (
            <div className="space-y-4">
              {/* 课时标题卡 */}
              <Card
                title={`第 ${toCN(selectedLesson.lesson_sequence_in_book)} 课 · ${selectedLesson.official_lesson_name}`}
                subtitle={`${unitNames[selectedLesson.unit_id] ?? selectedLesson.unit_id} · 课时 ${selectedLesson.lesson_sequence_in_unit}`}
                accent="vermilion"
                right={
                  <div className="flex items-center gap-2">
                    <Badge tone={reviewTone[selectedLesson.review_status]}>
                      {reviewCN[selectedLesson.review_status]}
                    </Badge>
                    <Badge tone="default">置信度 {confidenceCN[selectedLesson.segmentation_confidence]}</Badge>
                  </div>
                }
              >
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {[
                    { label: "全册顺序", value: `第 ${selectedLesson.lesson_sequence_in_book} 课`, icon: BookOpen },
                    { label: "建议课时", value: `${selectedLesson.recommended_school_periods} 课时`, icon: Clock },
                    { label: "起止页", value: `p.${pages.find(p=>p.id===selectedLesson.start_page_id)?.printed_page_no}–${pages.find(p=>p.id===selectedLesson.end_page_id)?.printed_page_no}`, icon: FileText },
                    { label: "跨页标记", value: selectedLesson.cross_page_flag ? "跨页课时" : "单页课时", icon: MapPin },
                  ].map((m) => (
                    <div key={m.label} className="p-2.5 bg-paper-2 rounded-sm">
                      <div className="flex items-center gap-1 text-2xs uppercase tracking-[0.1em] text-ink-4 font-mono">
                        <m.icon size={11} />
                        {m.label}
                      </div>
                      <div className="mt-0.5 font-serif font-bold text-ink text-sm">{m.value}</div>
                    </div>
                  ))}
                </div>

                {/* 划分依据 */}
                <div className="p-3 bg-paper-2 border-l-2 border-l-vermilion rounded-sm">
                  <div className="text-2xs uppercase tracking-[0.15em] text-vermilion-deep font-mono mb-1.5">划分依据</div>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedLesson.segmentation_basis.map((b) => (
                      <Badge key={b} tone="default">
                        {b === "teacher-book-evidence" ? "教师用书证据" :
                         b === "textbook-structure" ? "教材显性结构" :
                         b === "object-continuity" ? "对象连续性" : "人工审核"}
                      </Badge>
                    ))}
                  </div>
                  {selectedLesson.review_note && (
                    <p className="mt-2 text-xs text-ink-3 leading-relaxed">{selectedLesson.review_note}</p>
                  )}
                </div>
              </Card>

              {/* 包含页面 */}
              <Card title="包含页面" subtitle={`共 ${lessonPages.length} 页`} accent="teal">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {lessonPages.map((p) => (
                    <Link
                      key={p!.id}
                      to={`/library/page/${p!.id}`}
                      className="group block p-3 bg-paper-2 border border-ink-line rounded-sm hover:border-vermilion/40 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-2xs text-ink-4">PDF p.{p!.pdf_page_no}</span>
                        <span className="font-serif font-bold text-ink">印刷 p.{p!.printed_page_no}</span>
                      </div>
                      <div className="aspect-[812/1131] bg-paper-3 rounded-sm overflow-hidden mb-2 relative">
                        <img
                          src={p!.page_image}
                          alt={`印刷 p.${p!.printed_page_no}`}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                        />
                      </div>
                      <div className="flex items-center gap-1 text-2xs text-ink-3 group-hover:text-vermilion">
                        <ExternalLink size={10} />
                        查看原页
                      </div>
                    </Link>
                  ))}
                </div>
              </Card>

              {/* 教材对象归属 */}
              <Card
                title="教材对象归属"
                subtitle={lessonObjects.length > 0 ? `共 ${lessonObjects.length} 个对象已归属` : "待对象化"}
                accent="gold"
              >
                {lessonObjects.length > 0 ? (
                  <div className="space-y-2">
                    {lessonObjects.map((obj) => {
                      const assignment = selectedAssignment.find((a) => a.object_id === obj!.id);
                      const typeCN = obj!.type === "example" ? "例题" :
                                    obj!.type === "try" ? "试一试" :
                                    obj!.type === "think-do" ? "想想做做" :
                                    obj!.type === "exercise" ? "练习" : "操作";
                      const tone = obj!.type === "example" ? "vermilion" :
                                   obj!.type === "try" || obj!.type === "think-do" ? "teal" :
                                   obj!.type === "exercise" ? "gold" : "default";
                      return (
                        <div key={obj!.id} className="flex items-center gap-3 p-2.5 bg-paper-2 border border-ink-line-2 rounded-sm">
                          <Badge tone={tone as "vermilion" | "teal" | "gold" | "default"}>{typeCN}</Badge>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-ink font-medium truncate">{obj!.title}</div>
                            <div className="text-2xs text-ink-4 font-mono">{obj!.id} · {assignment?.assignment_confidence === "high" ? "高置信度" : "中置信度"}</div>
                          </div>
                          <ShieldCheck size={14} className="text-teal shrink-0" />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="p-4 bg-paper-2 border border-ink-line-2 rounded-sm flex items-center gap-2 text-sm text-ink-3">
                    <AlertCircle size={14} className="text-gold" />
                    <span>该课时所属单元尚未完成教材对象化，对象级边界待后续补充。当前边界基于教师用书课时候选和教材页面结构确定。</span>
                  </div>
                )}
              </Card>

              {/* 教师用书证据（可折叠） */}
              <Card
                title="划分证据与教师用书依据"
                subtitle={`${selectedEvidences.length} 条证据`}
                accent="none"
                right={
                  <button
                    onClick={() => setShowEvidence(!showEvidence)}
                    className="text-2xs text-ink-3 hover:text-vermilion flex items-center gap-1"
                  >
                    {showEvidence ? "收起" : "展开"}
                    <ChevronRight size={11} className={cn("transition-transform", showEvidence && "rotate-90")} />
                  </button>
                }
              >
                {showEvidence && (
                  <div className="space-y-2">
                    {selectedEvidences.map((ev) => (
                      <div key={ev.id} className="p-2.5 bg-paper-2 border-l-2 border-l-teal rounded-sm">
                        <div className="flex items-center gap-2 mb-1">
                          <FileSearch size={12} className="text-teal" />
                          <Badge tone="teal">
                            {ev.evidence_kind === "tb-text" ? "教师用书原文" :
                             ev.evidence_kind === "textbook-page" ? "教材原页" :
                             ev.evidence_kind === "object-range" ? "对象范围" :
                             ev.evidence_kind === "system-infer" ? "系统推断" : "人工审核"}
                          </Badge>
                          {ev.textbook_printed_page && (
                            <span className="text-2xs text-ink-4 font-mono">教材 p.{ev.textbook_printed_page}</span>
                          )}
                        </div>
                        <p className="text-xs text-ink-2 leading-relaxed">{ev.description}</p>
                      </div>
                    ))}
                    {tbLesson && (
                      <div className="p-2.5 bg-vermilion-tint/30 border border-vermilion/20 rounded-sm">
                        <div className="text-2xs uppercase tracking-[0.1em] text-vermilion-deep font-mono mb-1">教师用书课时候选</div>
                        <div className="text-sm text-ink-2">{tbLesson.title}</div>
                        <div className="text-2xs text-ink-4 mt-1">{tbLesson.teaching_suggestion.substring(0, 120)}...</div>
                      </div>
                    )}
                  </div>
                )}
              </Card>

              {/* 审核信息 */}
              <Card title="审核与版本" accent="none">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                  <div>
                    <div className="text-2xs uppercase tracking-[0.1em] text-ink-4 font-mono">审核状态</div>
                    <div className="mt-0.5">
                      <Badge tone={reviewTone[selectedLesson.review_status]}>
                        {reviewCN[selectedLesson.review_status]}
                      </Badge>
                    </div>
                  </div>
                  <div>
                    <div className="text-2xs uppercase tracking-[0.1em] text-ink-4 font-mono">审核人</div>
                    <div className="mt-0.5 text-ink-2">{selectedLesson.reviewer ?? "待审核"}</div>
                  </div>
                  <div>
                    <div className="text-2xs uppercase tracking-[0.1em] text-ink-4 font-mono">目录版本</div>
                    <div className="mt-0.5 text-ink-2 font-mono">{selectedLesson.lesson_catalog_version}</div>
                  </div>
                  {selectedLesson.alternative_segmentation && (
                    <div className="col-span-2 md:col-span-3 p-2 bg-gold/10 border border-gold/30 rounded-sm">
                      <div className="text-2xs text-gold font-mono mb-0.5">备选划分方案</div>
                      <div className="text-xs text-ink-2">{selectedLesson.alternative_segmentation}</div>
                    </div>
                  )}
                  {selectedLesson.segmentation_dispute && (
                    <div className="col-span-2 md:col-span-3 p-2 bg-vermilion-tint/30 border border-vermilion/20 rounded-sm">
                      <div className="text-2xs text-vermilion-deep font-mono mb-0.5">争议说明</div>
                      <div className="text-xs text-ink-2">{selectedLesson.segmentation_dispute}</div>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* 目录版本信息 */}
      <div className="mt-8 p-4 bg-paper-2 border border-ink-line rounded-sm">
        <div className="flex items-center gap-2 mb-3">
          <Lock size={14} className="text-ink-3" />
          <h4 className="font-serif text-sm font-bold text-ink">课时目录版本信息</h4>
          <Badge tone={lessonCatalog.status === "frozen" ? "teal" : "gold"}>
            {lessonCatalog.status === "frozen" ? "已冻结" : "草稿"}
          </Badge>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {[
            { k: "目录ID", v: lessonCatalog.catalog_id },
            { k: "版本", v: lessonCatalog.version },
            { k: "教材版本", v: lessonCatalog.edition_id },
            { k: "创建时间", v: lessonCatalog.created_at },
          ].map((r) => (
            <div key={r.k}>
              <div className="text-2xs uppercase tracking-[0.1em] text-ink-4 font-mono">{r.k}</div>
              <div className="mt-0.5 text-ink-2 font-mono">{r.v}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 space-y-1">
          {lessonCatalog.change_log.map((log, i) => (
            <div key={i} className="text-2xs text-ink-3 flex items-start gap-1.5">
              <span className="text-vermilion mt-0.5">·</span>
              <span>{log}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
