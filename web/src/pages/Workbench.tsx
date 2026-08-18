import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import StatCard from "@/components/ui/StatCard";
import SealStamp from "@/components/ui/SealStamp";
import Badge from "@/components/ui/Badge";
import {
  textbook,
  phases,
  metrics,
  reviewTasks,
  corrections,
  versions,
  verifyItems,
  computeVerifySummaries,
  teacherBook,
  teacherBookLessons,
} from "@/data";
import { cn, toCN, fmtDate } from "@/lib/utils";
import {
  Library,
  ScanSearch,
  ListChecks,
  GitCommitVertical,
  Target,
  ArrowUpRight,
  Lock,
  BookMarked,
  ShieldCheck,
} from "lucide-react";

const phaseStatusMap = {
  done: { label: "已完成", tone: "ok" as const },
  "in-progress": { label: "进行中", tone: "warn" as const },
  pending: { label: "未开始", tone: "default" as const },
};

const quickEntries = [
  { to: "/library", label: "浏览教材标准库", desc: "五层数字模型 · 目录 · 页面", icon: Library },
  { to: "/teacher-book", label: "教师用书资料库", desc: `${teacherBookLessons.length} 课时 · 结构化`, icon: BookMarked },
  { to: "/verify", label: "教材解析能力验证", desc: `${verifyItems.length} 项 · 四类验证`, icon: ShieldCheck },
  { to: "/review", label: "处理审核队列", desc: `${reviewTasks.filter((r) => r.status === "pending").length} 项待审`, icon: ListChecks },
];

export default function Workbench() {
  const priority1 = metrics.filter((m) => m.priority === 1).slice(0, 6);
  const pendingReviews = reviewTasks.filter((r) => r.status === "pending").length;
  const currentVersion = versions.find((v) => v.regression_passed);

  return (
    <div className="animate-ink-rise">
      <PageHeader
        eyebrow="AI 助力教师备课 · 教材基础层"
        title="教材数字化解析工作台"
        subtitle="严格限定新版苏教版小学数学三年级上册。本工作台汇总教材锁定状态、十阶段进度与核心验收指标，所有结果可回溯至原 PDF 页与精确区域。"
      />

      {/* 教材锁定卡 */}
      <div className="relative mb-10 overflow-hidden rounded-sm border-2 border-vermilion/40 bg-paper">
        <div className="absolute top-0 right-0 w-2/3 h-full opacity-[0.04] bg-[radial-gradient(circle_at_70%_30%,#B33A3A,transparent_60%)]" />
        <div className="relative flex flex-col md:flex-row items-start md:items-center gap-6 p-6">
          <SealStamp text="苏教版三上" size="xl" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Badge tone="vermilion">
                <Lock size={10} /> 教材版本已锁定
              </Badge>
              <Badge tone="default">{textbook.edition}</Badge>
              <Badge tone="default">124 页</Badge>
            </div>
            <h2 className="font-serif text-2xl font-bold text-ink leading-tight">
              {textbook.version} · {textbook.grade} · {textbook.volume}
            </h2>
            <p className="mt-1 text-xs text-ink-3 font-mono break-all">
              PDF SHA-256: {textbook.pdf_hash}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4 text-center shrink-0">
            <div>
              <div className="font-serif text-2xl font-bold text-vermilion">{phases.filter((p) => p.status === "done").length}</div>
              <div className="text-2xs text-ink-3 mt-0.5">已完成阶段</div>
            </div>
            <div>
              <div className="font-serif text-2xl font-bold text-warn">{phases.filter((p) => p.status === "in-progress").length}</div>
              <div className="text-2xs text-ink-3 mt-0.5">进行中</div>
            </div>
            <div>
              <div className="font-serif text-2xl font-bold text-ink-3">{pendingReviews}</div>
              <div className="text-2xs text-ink-3 mt-0.5">待审核项</div>
            </div>
          </div>
        </div>
        <div className="border-t border-vermilion/20 bg-vermilion-tint/40 px-6 py-2.5 text-2xs text-vermilion-deep">
          ⚠ 系统不得擅自切换教材版本；当前不划分课时、不生成教学设计、不分析学情、不进行核心素养映射。
        </div>
      </div>

      {/* 十阶段进度 */}
      <Card
        title="十阶段执行进度"
        subtitle="按推荐执行顺序，每阶段完成先测试审计再进入下一阶段"
        className="mb-10"
        bodyClassName="p-0"
      >
        <ol className="divide-y divide-ink-line-2">
          {phases.map((p) => {
            const s = phaseStatusMap[p.status];
            return (
              <li key={p.no} className="flex items-start gap-4 px-5 py-3">
                <div className="shrink-0 mt-0.5">
                  <span
                    className={cn(
                      "flex h-7 w-7 items-center justify-center rounded-full font-serif text-xs font-bold",
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
                    <Badge tone={s.tone}>{s.label}</Badge>
                  </div>
                  <p className="text-xs text-ink-3 mt-0.5">{p.detail}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </Card>

      {/* 核心验收指标 */}
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-serif text-xl font-bold text-ink">
          <span className="chapter-num">一</span> 核心验收指标
        </h2>
        <Link to="/golden-samples" className="text-xs text-teal hover:underline flex items-center gap-1">
          全部15项指标 <ArrowUpRight size={12} />
        </Link>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-10">
        {priority1.map((m) => (
          <StatCard
            key={m.key}
            label={m.name}
            value={m.current}
            target={m.target}
            hint={m.category}
            invert={m.key === "decoration-false"}
          />
        ))}
      </div>

      {/* 任务二：教师用书结构化与教材解析验证 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4">
        <span className="chapter-num">二</span> 教师用书结构化与解析验证
      </h2>
      <Card className="mb-10" accent="teal" bodyClassName="p-0">
        <div className="grid grid-cols-1 md:grid-cols-2 divide-x divide-ink-line-2">
          {/* 教师用书资料库 */}
          <Link to="/teacher-book" className="block p-5 hover:bg-paper-2 transition-colors">
            <div className="flex items-center gap-2 mb-3">
              <BookMarked size={16} className="text-vermilion" />
              <span className="font-serif font-bold text-ink">教师用书结构化资料库</span>
              <Badge tone="vermilion">{teacherBook.edition}</Badge>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center mb-3">
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBookLessons.length}</div>
                <div className="text-2xs text-ink-4">已结构化课时</div>
              </div>
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBook.pdf_page_end - teacherBook.pdf_page_start + 1}</div>
                <div className="text-2xs text-ink-4">三上 PDF 页数</div>
              </div>
              <div className="p-2 bg-paper-2 rounded-sm">
                <div className="font-serif text-lg font-bold text-ink">{teacherBook.printed_page_end - teacherBook.printed_page_start + 1}</div>
                <div className="text-2xs text-ink-4">印刷页数</div>
              </div>
            </div>
            <p className="text-xs text-ink-3 leading-relaxed">
              版本明确、章节清楚、可精确检索、可返回原文、能与教材对象建立映射。教师用书是参照与证据来源，不覆盖教材原页事实。
            </p>
          </Link>
          {/* 教材解析能力验证 */}
          <Link to="/verify" className="block p-5 hover:bg-paper-2 transition-colors">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck size={16} className="text-teal" />
              <span className="font-serif font-bold text-ink">教材解析能力验证</span>
              {(() => {
                const pass = verifyItems.filter((i) => i.status === "pass").length;
                const warn = verifyItems.filter((i) => i.status === "warn").length;
                const fail = verifyItems.filter((i) => i.status === "fail").length;
                return (
                  <Badge tone={fail > 0 ? "err" : warn > 0 ? "warn" : "ok"}>
                    {pass}/{verifyItems.length} 通过
                  </Badge>
                );
              })()}
            </div>
            <div className="grid grid-cols-4 gap-2 text-center mb-3">
              {computeVerifySummaries().map((s) => (
                <div key={s.check_type} className="p-2 bg-paper-2 rounded-sm">
                  <div className={cn(
                    "font-serif text-sm font-bold",
                    s.fail > 0 ? "text-err" : s.warn > 0 ? "text-warn" : "text-ok",
                  )}>
                    {s.total > 0 ? Math.round((s.pass / s.total) * 100) : 0}%
                  </div>
                  <div className="text-2xs text-ink-4">
                    {s.check_type === "question-complete" ? "题目完整" :
                     s.check_type === "lesson-retrieval" ? "课时调取" :
                     s.check_type === "exercise-set" ? "练习集合" : "绑定准确"}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-ink-3 leading-relaxed">
              四类能力验证：题目完整性、课时调取、练习集合、绑定准确性。三层证据分层保存：教材原页/教师用书原文/系统推断。
            </p>
          </Link>
        </div>
      </Card>

      {/* 快速入口 + 当前版本 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <h2 className="font-serif text-xl font-bold text-ink mb-4">
            <span className="chapter-num">三</span> 快速入口
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {quickEntries.map((e) => (
              <Link
                key={e.to}
                to={e.to}
                className="group flex items-center gap-3 p-4 bg-paper border border-ink-line rounded-sm hover:border-vermilion hover:shadow-card-hover transition-all"
              >
                <div className="flex h-10 w-10 items-center justify-center bg-paper-3 group-hover:bg-vermilion-tint rounded-sm transition-colors">
                  <e.icon size={18} className="text-ink-2 group-hover:text-vermilion-deep transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-ink group-hover:text-vermilion-deep">{e.label}</div>
                  <div className="text-xs text-ink-3 mt-0.5">{e.desc}</div>
                </div>
                <ArrowUpRight size={14} className="text-ink-4 group-hover:text-vermilion transition-colors" />
              </Link>
            ))}
          </div>
        </div>

        <div>
          <h2 className="font-serif text-xl font-bold text-ink mb-4">
            <span className="chapter-num">四</span> 当前规则版本
          </h2>
          <Card accent="vermilion">
            {currentVersion && (
              <>
                <div className="flex items-baseline justify-between">
                  <span className="font-serif text-2xl font-bold text-vermilion">
                    {currentVersion.version_no}
                  </span>
                  <Badge tone="ok">回归通过</Badge>
                </div>
                <p className="text-xs text-ink-3 mt-2">{currentVersion.notes}</p>
                <div className="mt-3 text-2xs text-ink-4 font-mono">
                  发布 {fmtDate(currentVersion.released_at)}
                </div>
                <ul className="mt-3 space-y-1.5">
                  {currentVersion.changeset.map((c, i) => (
                    <li key={i} className="text-xs text-ink-2 flex gap-1.5">
                      <span className="text-vermilion">·</span> {c}
                    </li>
                  ))}
                </ul>
                <div className="mt-4 pt-3 border-t border-ink-line-2">
                  <Link to="/corrections" className="text-xs text-teal hover:underline flex items-center gap-1">
                    查看全部 {versions.length} 个版本 <ArrowUpRight size={12} />
                  </Link>
                </div>
              </>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
