import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import SealStamp from "@/components/ui/SealStamp";
import {
  LayoutDashboard,
  Library,
  Grid2x2,
  Stamp,
  Users,
  BookOpenCheck,
  ListTree,
  Sigma,
  ScanSearch,
  GitCommitVertical,
  ListChecks,
  Target,
  ScrollText,
  Gauge,
  BookMarked,
  ShieldCheck,
  ClipboardList,
  Network,
  BrainCircuit,
} from "lucide-react";

type NavItem = {
  to: string;
  label: string;
  icon: ReactNode;
  cn?: string; // 中文短标
};

type NavGroup = {
  title: string;
  items: NavItem[];
};

const groups: NavGroup[] = [
  {
    title: "教材基础",
    items: [
      { to: "/library", label: "教材标准库", icon: <Library size={16} /> },
      { to: "/library/page/p-010", label: "页面与内容块", icon: <Grid2x2 size={16} /> },
      { to: "/teacher-book", label: "教师用书资料库", icon: <BookMarked size={16} /> },
    ],
  },
  {
    title: "资源库",
    items: [
      { to: "/icons", label: "图标资源库", icon: <Stamp size={16} /> },
      { to: "/characters", label: "角色资源库", icon: <Users size={16} /> },
    ],
  },
  {
    title: "对象识别",
    items: [
      { to: "/examples", label: "例题识别", icon: <BookOpenCheck size={16} /> },
      { to: "/exercises", label: "练习识别", icon: <ListTree size={16} /> },
      { to: "/math-structure", label: "图片数学结构", icon: <Sigma size={16} /> },
    ],
  },
  {
    title: "协同工作流",
    items: [
      { to: "/locate", label: "上传定位", icon: <ScanSearch size={16} /> },
      { to: "/corrections", label: "纠错与版本", icon: <GitCommitVertical size={16} /> },
      { to: "/review", label: "审核队列", icon: <ListChecks size={16} /> },
      { to: "/verify", label: "教材解析验证", icon: <ShieldCheck size={16} /> },
    ],
  },
  {
    title: "正式课时",
    items: [
      { to: "/official-lessons", label: "正式课时目录", icon: <ClipboardList size={16} /> },
      { to: "/lesson-analysis", label: "课时教材分析", icon: <Network size={16} /> },
    ],
  },
  {
    title: "智能解析",
    items: [
      { to: "/doc-intelligence", label: "文档智能解析", icon: <BrainCircuit size={16} /> },
    ],
  },
  {
    title: "开发者",
    items: [
      { to: "/", label: "工作台", icon: <LayoutDashboard size={16} />, cn: "总览" },
      { to: "/golden-samples", label: "黄金样本与回归", icon: <Target size={16} /> },
      { to: "/specs", label: "规范文档中心", icon: <ScrollText size={16} /> },
      { to: "/status", label: "完成情况", icon: <Gauge size={16} /> },
    ],
  },
];

function isActive(pathname: string, to: string): boolean {
  if (to === "/") return pathname === "/";
  // /library/page/* 归到 /library 高亮（页面与内容块独立项除外）
  if (to.startsWith("/library/page")) return pathname.startsWith("/library/page");
  return pathname === to || pathname.startsWith(to + "/");
}

export default function Layout({ children }: { children: ReactNode }) {
  const { isLocked, lockedVersion } = useAppStore();
  const { pathname } = useLocation();

  return (
    <div className="flex h-full">
      {/* 侧栏 */}
      <aside className="w-64 shrink-0 h-full flex flex-col border-r border-ink-line bg-paper-2/60 backdrop-blur-sm">
        {/* 教材锁定徽记 */}
        <div className="px-5 pt-6 pb-5 border-b border-ink-line">
          <div className="flex items-center gap-3">
            <SealStamp text="苏教三上" size="sm" shape="square" />
            <div className="min-w-0">
              <div className="text-2xs uppercase tracking-[0.2em] text-ink-3 font-mono">
                TEXTBOOK · LOCKED
              </div>
              <div className="font-serif font-semibold text-sm text-ink truncate">
                苏教版 · 三 · 上
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-1.5">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                isLocked ? "bg-vermilion" : "bg-ink-4",
              )}
            />
            <span className="text-2xs text-ink-3 leading-tight">
              {isLocked ? "教材版本已锁定，不可切换" : lockedVersion}
            </span>
          </div>
        </div>

        {/* 导航 */}
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {groups.map((g) => (
            <div key={g.title} className="mb-5">
              <div className="px-3 mb-1.5 text-2xs uppercase tracking-[0.2em] text-ink-4 font-mono">
                {g.title}
              </div>
              <ul className="space-y-0.5">
                {g.items.map((it) => {
                  const active = isActive(pathname, it.to);
                  return (
                    <li key={it.to}>
                      <Link
                        to={it.to}
                        className={cn(
                          "group flex items-center gap-2.5 px-3 py-1.5 text-sm rounded-sm transition-colors",
                          active
                            ? "bg-ink text-paper font-medium"
                            : "text-ink-2 hover:bg-paper-3 hover:text-ink",
                        )}
                      >
                        <span className={cn(active ? "text-vermilion-soft" : "text-ink-3 group-hover:text-vermilion")}>
                          {it.icon}
                        </span>
                        <span className="truncate">{it.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* 底部版本 */}
        <div className="px-5 py-3 border-t border-ink-line text-2xs text-ink-4 font-mono">
          <div className="flex items-center justify-between">
            <span>rule-v1.3</span>
            <span>model-v0.4</span>
          </div>
          <div className="mt-1 text-ink-4">教材基础层 · 前端原型</div>
        </div>
      </aside>

      {/* 主区 */}
      <main className="flex-1 h-full overflow-y-auto">
        <div className="mx-auto max-w-[1200px] px-8 py-10">{children}</div>
      </main>
    </div>
  );
}
