import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import ProgressBar from "@/components/ui/ProgressBar";
import StatCard from "@/components/ui/StatCard";
import { goldenSamples, regressionTests, metrics, objects } from "@/data";
import { cn, toCN, fmtDate } from "@/lib/utils";
import { Target, CheckCircle2, XCircle, FlaskConical } from "lucide-react";

const categoryCN: Record<string, string> = {
  "example-icon": "例题书本图标",
  "student-roles": "多种学生角色",
  "teacher-roles": "多种教师角色",
  "multi-method": "一题多种学生方法",
  "teacher-followup": "教师追问",
  "hidden-condition": "图片中隐藏已知条件",
  "one-image-multi-q": "一图多问",
  "multi-image-one-q": "多图一题",
  "table-blank": "表格留空",
  "chart-scale": "统计图刻度",
  "geometry-mark": "几何图标记",
  "span-page-example": "跨页例题",
  "span-page-exercise": "跨页练习",
  "decoration-adjacent": "装饰图与数学图相邻",
  "photo-tilted-bw": "手机拍摄、黑白、缩放和透视照片",
};

export default function GoldenSamples() {
  const passed = regressionTests.filter((r) => r.passed).length;
  const total = regressionTests.length;
  const passRate = passed / total;

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={11}
        eyebrow="GOLDEN SAMPLES & REGRESSION"
        title="黄金样本与回归测试"
        subtitle="先从三年级上册选取覆盖不同版式的黄金样本，不直接无审核处理整册。15 类样本覆盖例题图标→手机透视照片。优先保证对象完整率、图片归属准确率、共用材料准确率、跨页完整率、原文定位准确率。"
      />

      {/* 概览 */}
      <div className="grid grid-cols-3 gap-3 mb-10">
        <div className="bg-paper border border-ink-line rounded-sm p-4 text-center">
          <div className="font-serif text-3xl font-bold text-ink">{total}</div>
          <div className="text-2xs text-ink-3 mt-1">黄金样本总数</div>
        </div>
        <div className="bg-paper border border-ink-line rounded-sm p-4 text-center">
          <div className="font-serif text-3xl font-bold text-ok">{passed}</div>
          <div className="text-2xs text-ink-3 mt-1">回归通过</div>
        </div>
        <div className="bg-paper border border-ink-line rounded-sm p-4 text-center">
          <div className="font-serif text-3xl font-bold text-err">{total - passed}</div>
          <div className="text-2xs text-ink-3 mt-1">回归未通过</div>
        </div>
      </div>

      {/* 样本与回归 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <Target size={18} className="text-vermilion" />
        <span className="chapter-num">一</span> 15 类黄金样本
      </h2>
      <Card className="mb-10" bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-line bg-paper-2 text-left">
                <th className="px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">#</th>
                <th className="px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">类别</th>
                <th className="px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">样本描述</th>
                <th className="px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">期望</th>
                <th className="px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">回归</th>
              </tr>
            </thead>
            <tbody>
              {goldenSamples.map((s, i) => {
                const rt = regressionTests.find((r) => r.sample_id === s.id);
                const obj = s.object_id ? objects.find((o) => o.id === s.object_id) : null;
                return (
                  <tr key={s.id} className="border-b border-ink-line-2 last:border-0 hover:bg-paper-2">
                    <td className="px-4 py-2.5 font-mono text-ink-4 text-2xs">{i + 1}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone="vermilion">{toCN(i + 1)}</Badge>
                      <span className="ml-2 text-xs text-ink-2">{categoryCN[s.category]}</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-ink-2">
                      {s.description}
                      {obj && (
                        <Link to="/examples" className="ml-1.5 text-teal hover:underline">↗ {obj.title.slice(0, 8)}</Link>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-2xs text-ink-3 font-mono">{s.expected}</td>
                    <td className="px-4 py-2.5">
                      {rt?.passed ? (
                        <span className="inline-flex items-center gap-1 text-ok text-xs">
                          <CheckCircle2 size={13} /> 通过
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-err text-xs">
                          <XCircle size={13} /> 失败
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-ink-line-2 bg-paper-2/50 flex items-center justify-between text-2xs">
          <span className="text-ink-3">回归运行时间：{fmtDate(regressionTests[0]?.ran_at ?? "")}</span>
          <span className="text-ink-4 font-mono">通过率 {(passRate * 100).toFixed(1)}%</span>
        </div>
      </Card>

      {/* 验收指标 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <FlaskConical size={18} className="text-teal" />
        <span className="chapter-num">二</span> 15 项核心验收指标
      </h2>

      {/* 优先级排序展示 */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
        {metrics.filter((m) => m.priority === 1).map((m) => (
          <StatCard
            key={m.key}
            label={m.name}
            value={m.current}
            target={m.target}
            hint={`优先级 ${m.priority}`}
            invert={m.key === "decoration-false"}
          />
        ))}
      </div>

      <Card bodyClassName="p-0">
        <div className="divide-y divide-ink-line-2">
          {metrics.map((m) => {
            const ratio = m.key === "decoration-false" ? 1 - m.current : m.current;
            const targetRatio = m.key === "decoration-false" ? 1 - m.target : m.target;
            const meetTarget = m.key === "decoration-false" ? m.current <= m.target : m.current >= m.target;
            return (
              <div key={m.key} className="px-4 py-3 flex items-center gap-4">
                <div className="w-56 shrink-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-ink font-medium">{m.name}</span>
                    {m.priority === 1 && <Badge tone="vermilion">P1</Badge>}
                  </div>
                  <div className="text-2xs text-ink-4 font-mono mt-0.5">{m.category}</div>
                </div>
                <div className="flex-1">
                  <ProgressBar
                    value={ratio}
                    tone={meetTarget ? "teal" : "warn"}
                    showLabel={false}
                  />
                </div>
                <div className="w-32 shrink-0 text-right">
                  <span className={cn("font-serif text-sm font-bold tabular-nums", meetTarget ? "text-ok" : "text-warn")}>
                    {(m.current * 100).toFixed(1)}%
                  </span>
                  <span className="text-2xs text-ink-4 font-mono ml-1">/ {(m.target * 100).toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="px-4 py-3 border-t border-ink-line-2 bg-paper-2/50 text-2xs text-ink-3">
          优先保证：1.对象完整率 2.图片归属准确率 3.共用材料准确率 4.跨页完整率 5.原文定位准确率
        </div>
      </Card>
    </div>
  );
}
