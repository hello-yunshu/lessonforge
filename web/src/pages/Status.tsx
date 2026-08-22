import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import {
  phases,
  metrics,
  verifyItems,
  computeVerifySummaries,
  teacherBook,
  teacherBookLessons,
  teacherBookUnits,
  teacherBookReferences,
} from "@/data";
import { cn, toCN } from "@/lib/utils";
import {
  Gauge,
  CheckCircle2,
  Circle,
  Loader2,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BookMarked,
  ShieldCheck,
} from "lucide-react";

const phaseStatusMap = {
  done: { label: "已完成", tone: "ok" as const, icon: CheckCircle2, color: "text-ok" },
  "in-progress": { label: "进行中", tone: "warn" as const, icon: Loader2, color: "text-warn" },
  pending: { label: "未开始", tone: "default" as const, icon: Circle, color: "text-ink-4" },
};

const issues = [
  {
    no: 1,
    title: "手机倾斜照片定位准确率偏低",
    detail: "gs-15 回归未通过，residual=12.4px，需补充透视样本并优化单应性配准策略",
    severity: "high" as const,
    area: "上传定位",
  },
  {
    no: 2,
    title: "跨页对象完整率未达标",
    detail: "当前 0.86，目标 0.95。例2跨页边界判断存在内容归属歧义",
    severity: "high" as const,
    area: "练习识别",
  },
  {
    no: 3,
    title: "人物—气泡绑定准确率",
    detail: "当前 0.87，目标 0.95。白菜/青椒角色在话语框分离场景下偶有误绑",
    severity: "mid" as const,
    area: "角色资源库",
  },
  {
    no: 4,
    title: "整册处理未启动",
    detail: "黄金样本回归未全通过前，不进入整册无审核处理（阶段10）",
    severity: "low" as const,
    area: "黄金样本",
  },
];

const nextSteps = [
  { no: 1, text: "补充手机倾斜/黑白/透视黄金样本，优化配准策略使 gs-15 通过回归", to: "/golden-samples" },
  { no: 2, text: "完善跨页对象边界规则，提升跨页完整率至 0.95", to: "/examples" },
  { no: 3, text: "处理审核队列待审项，沉淀到资源库与回归集", to: "/review" },
  { no: 4, text: "回归全通过后发布 rule-v1.4，启动整册处理（阶段10）", to: "/corrections" },
  { no: 5, text: "扩充教师用书结构化至第二至七单元，覆盖全册课时与引用", to: "/teacher-book" },
  { no: 6, text: "修复解析验证 warn 项：玫瑰单价推理、练习二题组拆分、例3试一试独立对象", to: "/verify" },
];

type RillStatus = {
  upstreamLatest: string;
  supported: string;
  tested: string;
  installed: string | null;
  protocol: string;
  previewV3Compatibility: string;
};

export default function Status() {
  const [rill, setRill] = useState<RillStatus | null>(null);
  useEffect(() => {
    let active = true;
    fetch("/api/di/health")
      .then((response) => response.json() as Promise<{ rill?: RillStatus }>)
      .then((body) => {
        if (active && body.rill) setRill(body.rill);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);
  const done = phases.filter((p) => p.status === "done").length;
  const inProg = phases.filter((p) => p.status === "in-progress").length;
  const overall = (done + inProg * 0.5) / phases.length;
  const p1Metrics = metrics.filter((m) => m.priority === 1);
  const p1Met = p1Metrics.filter((m) => m.key === "decoration-false" ? m.current <= m.target : m.current >= m.target).length;

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={13}
        eyebrow="PROJECT STATUS"
        title="完成情况"
        subtitle="当前阶段、遗留问题与下一步建议。每一阶段完成后先测试和审计，再进入下一阶段。不得为快速跑完整册而跳过对象边界、图片归属和证据回溯。"
      />

      {/* 总览数字 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
        <div className="bg-paper border border-ink-line rounded-sm p-4">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">整体进度</div>
          <div className="mt-1.5 flex items-baseline gap-1">
            <span className="font-serif text-2xl font-bold text-ink">{(overall * 100).toFixed(0)}</span>
            <span className="text-sm text-ink-3">%</span>
          </div>
          <div className="mt-2 h-1 bg-paper-3 rounded-full overflow-hidden">
            <div className="h-full bg-vermilion" style={{ width: `${overall * 100}%` }} />
          </div>
        </div>
        <div className="bg-paper border border-ink-line rounded-sm p-4">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">已完成阶段</div>
          <div className="mt-1.5 font-serif text-2xl font-bold text-ok">{done}/{phases.length}</div>
        </div>
        <div className="bg-paper border border-ink-line rounded-sm p-4">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">进行中</div>
          <div className="mt-1.5 font-serif text-2xl font-bold text-warn">{inProg}</div>
        </div>
        <div className="bg-paper border border-ink-line rounded-sm p-4">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">P1 指标达标</div>
          <div className="mt-1.5 font-serif text-2xl font-bold text-teal-2">{p1Met}/{p1Metrics.length}</div>
        </div>
      </div>

      <Card className="mb-10" bodyClassName="p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">
              RILLML CONSUMER CONTRACT
            </div>
            <h2 className="font-serif text-xl font-bold text-ink mt-1">Stable Runtime 版本边界</h2>
          </div>
          <Badge tone={rill?.installed ? "ok" : "default"}>
            {rill?.installed ? "Runtime 已安装" : "Runtime 未安装 / 未连接"}
          </Badge>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mt-5 text-xs">
          <div><div className="text-ink-4">Rill upstream latest</div><div className="font-mono text-ink mt-1">{rill?.upstreamLatest ?? "—"}</div></div>
          <div><div className="text-ink-4">LessonForge supported</div><div className="font-mono text-ink mt-1">{rill?.supported ?? "—"}</div></div>
          <div><div className="text-ink-4">LessonForge tested</div><div className="font-mono text-ink mt-1">{rill?.tested ?? "—"}</div></div>
          <div><div className="text-ink-4">Installed Rill</div><div className="font-mono text-ink mt-1">{rill?.installed ?? "—"}</div></div>
          <div><div className="text-ink-4">Protocol</div><div className="font-mono text-ink mt-1">{rill?.protocol ?? "—"}</div></div>
        </div>
        <div className="mt-4 text-xs text-ink-3">
          {rill?.previewV3Compatibility ?? "Preview v3 compatibility code: present/disabled；Production v3 runtime: not claimed"}
        </div>
      </Card>

      {/* 阶段状态 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <Gauge size={18} className="text-vermilion" />
        <span className="chapter-num">一</span> 十阶段状态
      </h2>
      <Card className="mb-10" bodyClassName="p-0">
        <ol className="divide-y divide-ink-line-2">
          {phases.map((p) => {
            const s = phaseStatusMap[p.status];
            const Icon = s.icon;
            return (
              <li key={p.no} className="flex items-start gap-4 px-5 py-3.5">
                <div className="shrink-0 mt-0.5">
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full font-serif text-xs font-bold",
                      p.status === "done" && "bg-ok text-paper",
                      p.status === "in-progress" && "bg-warn text-paper",
                      p.status === "pending" && "bg-paper-3 text-ink-3 border border-ink-line",
                    )}
                  >
                    {p.no}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-ink">{p.name}</span>
                    <Badge tone={s.tone}>
                      <Icon size={10} className={p.status === "in-progress" ? "animate-spin" : ""} />
                      {s.label}
                    </Badge>
                  </div>
                  <p className="text-xs text-ink-3 mt-1">{p.detail}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </Card>

      {/* 任务二：教师用书结构化与解析验证 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <BookMarked size={18} className="text-vermilion" />
        <span className="chapter-num">二</span> 任务二 · 教师用书结构化与解析验证
      </h2>
      <Card className="mb-10" bodyClassName="p-0">
        <div className="grid grid-cols-1 md:grid-cols-2 divide-x divide-ink-line-2">
          {/* 教师用书资料库状态 */}
          <Link to="/teacher-book" className="block p-5 hover:bg-paper-2 transition-colors">
            <div className="flex items-center gap-2 mb-3">
              <BookMarked size={15} className="text-vermilion" />
              <span className="font-serif font-bold text-ink">教师用书结构化资料库</span>
              <Badge tone="ok">已建成</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center mb-3">
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBookUnits.length}</div>
                <div className="text-2xs text-ink-4">单元说明</div>
              </div>
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBookLessons.length}</div>
                <div className="text-2xs text-ink-4">课时划分（第一单元）</div>
              </div>
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBookReferences.length}</div>
                <div className="text-2xs text-ink-4">教材引用条目</div>
              </div>
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBook.pdf_page_end - teacherBook.pdf_page_start + 1}</div>
                <div className="text-2xs text-ink-4">三上 PDF 页数</div>
              </div>
            </div>
            <p className="text-xs text-ink-3 leading-relaxed">
              三层证据分层保存：教材原页事实 / 教师用书原文 / 系统推断。教师用书是参照与证据来源，不覆盖教材原页事实。
            </p>
          </Link>
          {/* 解析验证状态 */}
          <Link to="/verify" className="block p-5 hover:bg-paper-2 transition-colors">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck size={15} className="text-teal" />
              <span className="font-serif font-bold text-ink">教材解析能力验证</span>
              {(() => {
                const pass = verifyItems.filter((i) => i.status === "pass").length;
                const warn = verifyItems.filter((i) => i.status === "warn").length;
                return (
                  <Badge tone={warn > 0 ? "warn" : "ok"}>
                    {pass}/{verifyItems.length} 通过 · {warn} 警告
                  </Badge>
                );
              })()}
            </div>
            <div className="space-y-1.5">
              {computeVerifySummaries().map((s) => {
                const rate = s.total > 0 ? Math.round((s.pass / s.total) * 100) : 0;
                const label = s.check_type === "question-complete" ? "题目完整性" :
                  s.check_type === "lesson-retrieval" ? "课时调取" :
                  s.check_type === "exercise-set" ? "练习集合" : "绑定准确性";
                return (
                  <div key={s.check_type} className="flex items-center gap-2">
                    <span className="text-xs text-ink-2 w-20 shrink-0">{label}</span>
                    <div className="flex-1 h-1.5 bg-paper-3 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          rate >= 80 ? "bg-ok" : rate >= 50 ? "bg-warn" : "bg-err",
                        )}
                        style={{ width: `${rate}%` }}
                      />
                    </div>
                    <span className="text-2xs text-ink-3 font-mono w-16 text-right">
                      {s.pass}/{s.total}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-xs text-ink-3 leading-relaxed">
              四类能力验证覆盖第一单元 6 课时。warn 项已记录差异说明，待通过纠错流程修复系统推断层。
            </p>
          </Link>
        </div>
      </Card>

      {/* 遗留问题 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <AlertTriangle size={18} className="text-warn" />
        <span className="chapter-num">三</span> 遗留问题与风险
      </h2>
      <div className="space-y-2.5 mb-10">
        {issues.map((iss) => (
          <Card
            key={iss.no}
            noPad
            bodyClassName="p-4"
            className={iss.severity === "high" ? "border-l-2 border-l-err" : iss.severity === "mid" ? "border-l-2 border-l-warn" : ""}
          >
            <div className="flex items-start gap-3">
              <span className="font-serif text-lg font-bold text-vermilion shrink-0">
                {toCN(iss.no)}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-ink">{iss.title}</span>
                  <Badge tone={iss.severity === "high" ? "err" : iss.severity === "mid" ? "warn" : "default"}>
                    {iss.severity === "high" ? "高" : iss.severity === "mid" ? "中" : "低"} 风险
                  </Badge>
                  <Badge tone="default">{iss.area}</Badge>
                </div>
                <p className="mt-1 text-xs text-ink-3">{iss.detail}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* 下一步建议 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <ArrowRight size={18} className="text-teal" />
        <span className="chapter-num">四</span> 下一步建议
      </h2>
      <Card>
        <ol className="space-y-3">
          {nextSteps.map((n) => (
            <li key={n.no} className="flex items-start gap-3">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-teal-tint text-teal-2 font-serif text-xs font-bold shrink-0">
                {n.no}
              </span>
              <Link to={n.to} className="flex-1 text-sm text-ink-2 hover:text-teal-2 transition-colors">
                {n.text}
              </Link>
              <ArrowUpRight size={13} className="text-ink-4 mt-1" />
            </li>
          ))}
        </ol>
      </Card>

      <div className="mt-6 text-center text-2xs text-ink-4 font-mono">
        教材基础层 · 前端原型 · rule-v1.3 · model-v0.4 · 苏教版三上专用
      </div>
    </div>
  );
}
