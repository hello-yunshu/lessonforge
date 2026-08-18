import type { VerifyItem, VerifySummary, VerifyCheckType } from "./types";

// 教材版权数据不随源码发布，保留类型与空结构。
export const verifyItems: VerifyItem[] = [];
export const verifySummaries: VerifySummary[] = [];

export const computeVerifySummaries = (): VerifySummary[] => [];
export const verifyItemsByType = (type: VerifyCheckType): VerifyItem[] => [];
export const verifyItemsByLesson = (lessonId: string): VerifyItem[] => [];