import { create } from "zustand";
import { textbook } from "@/data";

interface AppState {
  // 教材版本锁定（教师进入时主动选择，系统不得擅自切换）
  lockedTextbookId: string;
  lockedVersion: string; // 苏教版—三年级—上册
  isLocked: boolean;
  lock: () => void;
  // 侧栏折叠
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  lockedTextbookId: textbook.id,
  lockedVersion: "苏教版 · 三年级 · 上册",
  isLocked: true,
  lock: () => set({ isLocked: true }),
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
