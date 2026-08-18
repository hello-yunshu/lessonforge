import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 置信度 → 颜色档 */
export function confTier(c: number): "high" | "mid" | "low" {
  if (c >= 0.9) return "high";
  if (c >= 0.8) return "mid";
  return "low";
}

/** 置信度百分比 */
export function pct(c: number, digits = 1): string {
  return `${(c * 100).toFixed(digits)}%`;
}

/** 中文数字 1→一 2→二 ... 12→十二 */
const cnNums = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
export function toCN(n: number): string {
  if (n <= 10) return cnNums[n];
  if (n < 20) return `十${cnNums[n - 10]}`;
  if (n < 100) {
    const t = Math.floor(n / 10);
    const o = n % 10;
    return `${cnNums[t]}十${o ? cnNums[o] : ""}`;
  }
  return String(n);
}

/** 审核状态中文 */
export function reviewStatusCN(s: string): string {
  return { pending: "待审", confirmed: "已确认", rejected: "已驳回" }[s] ?? s;
}

/** 教材对象类型中文 */
export function objectTypeCN(t: string): string {
  return {
    example: "例题",
    try: "试一试",
    "think-do": "想想做做",
    exercise: "练习",
    operation: "操作活动",
  }[t] ?? t;
}

/** 内容块类型中文 */
export function blockTypeCN(t: string): string {
  return {
    title: "标题",
    text: "正文",
    q_no: "题号",
    example_icon: "例题图标",
    section_icon: "栏目图标",
    scene: "情境图",
    table: "表格",
    chart: "统计图",
    geometry: "几何图",
    formula: "算式",
    character: "角色",
    speech_box: "话语框",
    answer_blank: "作答空格",
    decoration: "装饰图",
  }[t] ?? t;
}

/** 格式化日期 YYYY-MM-DD HH:mm */
export function fmtDate(d: string | Date): string {
  const date = typeof d === "string" ? new Date(d) : d;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(
    date.getHours(),
  )}:${p(date.getMinutes())}`;
}
