// 数据层统一出口（模拟关系型数据库表）
export * from "./types";
export * from "./textbook";
export * from "./blocks";
export * from "./objects";
export * from "./resources";
export * from "./workflow";
// 任务二：教师教学用书结构化资料库 + 教材解析验证
export * from "./teacherBook";
export * from "./verification";
// 任务三：正式教材课时划分与内容归属
export * from "./officialLessons";
// 任务四：课时内部教材内容关系与练习结构分析
export * from "./lessonAnalysis";
// 任务四扩展：第二至第九单元48课时的教材对象与分析数据
export * from "./objects-extra";
export * from "./lessonAnalysis-extra";
// 任务四补充：扩展课时深度分析数据（按单元分组，按需生成）
export * from "./lessonAnalysis-extra-deep-u1b-u2-u2b";
export * from "./lessonAnalysis-extra-deep-u3-u3b-u4";

// 常用查询助手
import { contentBlocks, coordinates, objects, examples } from ".";
import type {
  ContentBlock,
  Coordinate,
  TextbookObject,
  Example,
  BlockType,
} from "./types";

export const blocksByPage = (pageId: string): ContentBlock[] =>
  contentBlocks.filter((b) => b.page_id === pageId).sort((a, b) => a.read_order - b.read_order);

export const coordsByBlock = (blockId: string): Coordinate[] =>
  coordinates.filter((c) => c.block_id === blockId);

export const objectsBySection = (sectionId: string): TextbookObject[] =>
  objects.filter((o) => o.section_id === sectionId);

export const exampleByObject = (objectId: string): Example | undefined =>
  examples.find((e) => e.object_id === objectId);

export const blockTypeColor: Record<BlockType, string> = {
  title: "bg-ink/10 text-ink",
  text: "bg-paper-3 text-ink",
  q_no: "bg-teal-tint text-teal-2",
  example_icon: "bg-vermilion-tint text-vermilion-deep",
  section_icon: "bg-vermilion-tint text-vermilion-deep",
  scene: "bg-gold-soft text-ink",
  table: "bg-teal-tint text-teal-2",
  chart: "bg-teal-tint text-teal-2",
  geometry: "bg-teal-tint text-teal-2",
  formula: "bg-ink/5 text-ink font-mono",
  character: "bg-vermilion-soft text-vermilion-deep",
  speech_box: "bg-paper-2 text-ink-2",
  answer: "bg-ok/15 text-ok",
  answer_blank: "bg-paper-3 text-ink-3",
  decoration: "bg-paper-2 text-ink-4",
};
