import { useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import {
  exercises,
  objects,
  questionGroups,
  bigQuestions,
  smallQuestions,
  sharedMaterials,
  relations,
  pages,
} from "@/data";
import { cn, objectTypeCN } from "@/lib/utils";
import {
  FlaskConical,
  Lightbulb,
  ClipboardList,
  Share2,
  Layers,
  ArrowRight,
} from "lucide-react";

const sectionIcon = {
  try: FlaskConical,
  "think-do": Lightbulb,
  practice: ClipboardList,
};

const sectionCN = { try: "试一试", "think-do": "想想做做", practice: "练习" };

export default function Exercises() {
  // 选取想想做做 o-td1 作为主展示（含题组/大题/小题/共用材料）
  const tdObjects = objects.filter((o) => o.type === "think-do" || o.type === "try" || o.type === "exercise");
  const [sel, setSel] = useState("o-td1");
  const obj = objects.find((o) => o.id === sel)!;
  const exr = exercises.find((e) => e.object_id === obj.id);
  const groups = exr ? questionGroups.filter((g) => g.exercise_id === exr.id) : [];
  const objShared = sharedMaterials.filter((s) => s.consumer_object_ids.includes(obj.id));
  const objRelations = relations.filter((r) => r.src_object_id === obj.id);
  const objPages = pages.filter((p) => obj.page_ids.includes(p.id));

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={6}
        eyebrow="EXERCISE RECOGNITION"
        title="练习识别"
        subtitle="试一试、想想做做、练习是独立教材对象。结构：教材栏目 → 题组 → 大题 → 小题 → 内容组成部分。必须处理共用题干、共用图片/表格/统计图、一题多图、跨页、题号与内容分离等情形。"
      />

      {/* 栏目对象列表 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4">
        <span className="chapter-num">一</span> 栏目对象（独立教材对象，不合并为例题正文）
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-10">
        {tdObjects.map((o) => {
          const Icon = sectionIcon[exercises.find((e) => e.object_id === o.id)?.section_type ?? "think-do"];
          const isSel = o.id === sel;
          return (
            <button
              key={o.id}
              onClick={() => setSel(o.id)}
              className={cn(
                "p-4 bg-paper border rounded-sm text-left transition-all",
                isSel ? "border-teal ring-2 ring-teal/30" : "border-ink-line hover:shadow-card-hover",
              )}
            >
              <div className="flex items-center gap-3">
                <div className={cn("flex h-10 w-10 items-center justify-center rounded-sm", isSel ? "bg-teal-tint" : "bg-paper-3")}>
                  <Icon size={18} className={isSel ? "text-teal-2" : "text-ink-2"} />
                </div>
                <div className="flex-1 min-w-0">
                  <Badge tone={exercises.find((e) => e.object_id === o.id)?.section_type === "try" ? "vermilion" : "teal"}>
                    {sectionCN[exercises.find((e) => e.object_id === o.id)?.section_type ?? "think-do"]}
                  </Badge>
                  <div className="mt-1 text-sm text-ink font-medium truncate">{o.title}</div>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* 层级树 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <Layers size={18} className="text-teal" />
        <span className="chapter-num">二</span> 层级结构 · {objectTypeCN(obj.type)}
      </h2>
      <Card className="mb-10" bodyClassName="p-6">
        <div className="text-xs text-ink-3 mb-4">
          <span className="font-medium text-ink">{obj.title}</span> · 跨页 {objPages.map((p) => `p.${p.pdf_page_no}`).join("→")}
        </div>

        {/* 栏目 → 题组 → 大题 → 小题 */}
        <div className="space-y-3">
          {groups.length === 0 && (
            <div className="text-xs text-ink-4 italic">该栏目暂未结构化题组，仅有独立小题。</div>
          )}
          {groups.map((g) => {
            const bigs = bigQuestions.filter((b) => b.group_id === g.id);
            return (
              <div key={g.id} className="border-l-2 border-teal pl-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">题组</span>
                  <span className="text-sm font-medium text-ink">{g.label}</span>
                </div>
                <div className="space-y-2">
                  {bigs.map((bq) => {
                    const sms = smallQuestions.filter((s) => s.big_question_id === bq.id);
                    const sharedForBq = sharedMaterials.filter((s) => s.consumer_object_ids.includes(obj.id) && (s.description.includes(bq.q_no) || s.description.includes("铅笔")));
                    return (
                      <div key={bq.id} className="ml-3 border-l border-ink-line pl-3">
                        <div className="flex items-baseline gap-2">
                          <span className="font-serif text-sm font-bold text-vermilion">第 {bq.q_no} 题</span>
                          <span className="text-xs text-ink-2 flex-1">{bq.stem}</span>
                          {sharedForBq.length > 0 && (
                            <Badge tone="gold">
                              <Share2 size={9} /> 共用材料
                            </Badge>
                          )}
                        </div>
                        {sms.length > 0 && (
                          <ul className="mt-1.5 space-y-1">
                            {sms.map((sq) => (
                              <li key={sq.id} className="flex items-center gap-2 text-xs text-ink-2">
                                <span className="text-ink-4 font-mono">{sq.q_no}</span>
                                <span>{sq.stem}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* 共用材料 + 关系 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
        <Card title="共用材料归属" subtitle="先判断图片属于哪个教材对象，再抽取数学结构" accent="gold" bodyClassName="p-0">
          <ul className="divide-y divide-ink-line-2">
            {objShared.map((s) => (
              <li key={s.id} className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <Badge tone={s.kind === "chart" ? "teal" : s.kind === "table" ? "teal" : "gold"}>
                    {s.kind === "image" ? "情境图" : s.kind === "table" ? "表格" : s.kind === "chart" ? "统计图" : "几何图"}
                  </Badge>
                  <code className="text-2xs text-ink-4 font-mono">{s.id}</code>
                </div>
                <p className="text-xs text-ink-2 mt-1">{s.description}</p>
                <div className="mt-1.5 flex items-center gap-1 text-2xs text-ink-3">
                  <Share2 size={10} /> 被 {s.consumer_object_ids.length} 个对象共用
                </div>
              </li>
            ))}
            {objShared.length === 0 && (
              <li className="px-4 py-6 text-xs text-ink-4 text-center">本栏目无共用材料</li>
            )}
          </ul>
          <div className="px-4 py-3 border-t border-ink-line-2 bg-paper-2/50 text-2xs text-ink-3">
            不按"距离哪个文字最近"绑定，综合版面边界、题号、栏目、引线、题干"看图/根据下图"、图中编号、前后页连续、是否为解题必要条件。
          </div>
        </Card>

        <Card title="显式关系" accent="teal" bodyClassName="p-0">
          <ul className="divide-y divide-ink-line-2">
            {objRelations.map((r) => (
              <li key={r.id} className="px-4 py-3">
                <Badge tone={r.rel_type === "shared-table" ? "gold" : "teal"}>{r.rel_type}</Badge>
                <p className="text-xs text-ink-2 mt-1.5">{r.note}</p>
              </li>
            ))}
            {objRelations.length === 0 && (
              <li className="px-4 py-6 text-xs text-ink-4 text-center">无显式关系</li>
            )}
          </ul>
        </Card>
      </div>

      {/* 跨页与原页证据 */}
      {objPages.length > 0 && (
        <Card title="跨页与原页证据" bodyClassName="p-4">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {objPages.map((p, i) => (
              <div key={p.id} className="flex items-center gap-2">
                {i > 0 && <ArrowRight size={12} className="text-ink-4" />}
                <Link
                  to={`/library/page/${p.id}`}
                  className="px-3 py-1.5 bg-paper-2 border border-ink-line rounded-sm hover:border-teal hover:text-teal-2 transition-colors"
                >
                  PDF p.{p.pdf_page_no} · 印刷 p.{p.printed_page_no}
                </Link>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
