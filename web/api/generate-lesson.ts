/**
 * 课时深度分析生成 API
 *
 * 通过 Vite 开发服务器的 ssrLoadModule 加载数据模块，
 * 构造 prompt 调用 AI API，生成 6 项深度分析数据，
 * 写入对应的 .ts 文件并返回 JSON 给前端。
 *
 * AI API 使用 Google Gemini（优先）或环境变量配置的其他服务。
 * 无 API key 时返回 prompt 供前端回退处理。
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import * as path from "node:path";

// ===== 类型定义（与前端共用，从 types.ts 推导） =====
type GenerateResult = {
  success: boolean;
  lessonId: string;
  data?: {
    mainlines: unknown[];
    nodes: unknown[];
    transitions: unknown[];
    evidence: unknown[];
    alternatives: unknown[];
    reviewIssues: unknown[];
  };
  writtenFile?: string;
  prompt?: string;
  error?: string;
};

// ===== 单元分组映射 =====
const unitGroupMap: Record<string, string> = {
  "1b": "u1b-u2-u2b",
  "2": "u1b-u2-u2b",
  "2b": "u1b-u2-u2b",
  "3": "u3-u3b-u4",
  "3b": "u3-u3b-u4",
  "4": "u3-u3b-u4",
  "5": "u5-u6-u6b",
  "6": "u5-u6-u6b",
  "6b": "u5-u6-u6b",
  "7": "u7-u8-u9",
  "8": "u7-u8-u9",
  "9": "u7-u8-u9",
};

// 导出数组命名映射
const groupExportNames: Record<string, {
  mainlines: string;
  nodes: string;
  transitions: string;
  evidence: string;
  alternatives: string;
  reviewIssues: string;
}> = {
  "u1b-u2-u2b": {
    mainlines: "lessonMainlinesExtraU1BU2U2B",
    nodes: "lessonMainlineNodesExtraU1BU2U2B",
    transitions: "lessonMainlineTransitionsExtraU1BU2U2B",
    evidence: "lessonMainlineEvidenceExtraU1BU2U2B",
    alternatives: "lessonMainlineAlternativesExtraU1BU2U2B",
    reviewIssues: "analysisReviewIssuesExtraU1BU2U2B",
  },
  "u3-u3b-u4": {
    mainlines: "lessonMainlinesExtraU3U3BU4",
    nodes: "lessonMainlineNodesExtraU3U3BU4",
    transitions: "lessonMainlineTransitionsExtraU3U3BU4",
    evidence: "lessonMainlineEvidenceExtraU3U3BU4",
    alternatives: "lessonMainlineAlternativesExtraU3U3BU4",
    reviewIssues: "analysisReviewIssuesExtraU3U3BU4",
  },
  "u5-u6-u6b": {
    mainlines: "lessonMainlinesExtraU5U6U6B",
    nodes: "lessonMainlineNodesExtraU5U6U6B",
    transitions: "lessonMainlineTransitionsExtraU5U6U6B",
    evidence: "lessonMainlineEvidenceExtraU5U6U6B",
    alternatives: "lessonMainlineAlternativesExtraU5U6U6B",
    reviewIssues: "analysisReviewIssuesExtraU5U6U6B",
  },
  "u7-u8-u9": {
    mainlines: "lessonMainlinesExtraU7U8U9",
    nodes: "lessonMainlineNodesExtraU7U8U9",
    transitions: "lessonMainlineTransitionsExtraU7U8U9",
    evidence: "lessonMainlineEvidenceExtraU7U8U9",
    alternatives: "lessonMainlineAlternativesExtraU7U8U9",
    reviewIssues: "analysisReviewIssuesExtraU7U8U9",
  },
};

// ===== 解析 lesson_id =====
function parseLessonId(lessonId: string): { unit: string; seq: string; group: string } | null {
  // ol-1b-1 / ol-2-3 / ol-6b-1
  const match = lessonId.match(/^ol-(\d+[a-z]?)-(\d+)$/);
  if (!match) return null;
  const unit = match[1];
  const seq = match[2];
  const group = unitGroupMap[unit];
  if (!group) return null;
  return { unit, seq, group };
}

// ===== 构造 prompt =====
function buildPrompt(
  lessonId: string,
  lessonInfo: { name: string; unit: string; startPage: string; endPage: string },
  objects: Array<{ id: string; type: string; title: string; pageIds: string[] }>,
  tbReferences: Array<{ id: string; refKind: string; tbPage: number; excerpt: string }>,
  existingAnalysis: { contentSequence: string; representation: string; problemRelation: string } | null,
): string {
  const { unit, seq } = parseLessonId(lessonId)!;

  const objectsStr = objects
    .map((o) => `  - ${o.id} (${o.type}): ${o.title} [页码: ${o.pageIds.join(", ")}]`)
    .join("\n");

  const tbRefsStr = tbReferences
    .map((r) => `  - ${r.id} [${r.refKind}, 教师用书p.${r.tbPage}]: ${r.excerpt}`)
    .join("\n");

  const existingStr = existingAnalysis
    ? `已有浅层数据：
  - 内容顺序：${existingAnalysis.contentSequence}
  - 表征关系：${existingAnalysis.representation}
  - 题目关系：${existingAnalysis.problemRelation}`
    : "无已有浅层数据。";

  return `你是一位资深数学教材分析师。请为苏教版三年级上册课时 "${lessonId}"（${lessonInfo.name}）生成深度教材分析数据。

## 课时信息
- 课时ID：${lessonId}
- 课时名：${lessonInfo.name}
- 单元：${unit}
- 起止页：${lessonInfo.startPage} → ${lessonInfo.endPage}

## 教材对象
${objectsStr}

## 教师用书证据
${tbRefsStr}

## 已有浅层数据（参考，需深化）
${existingStr}

## 生成要求
请生成以下 6 项数据，以单个 JSON 对象返回，包含 6 个数组字段。

### 1. mainlines（主线基本信息，1条）
- mainline_id: "lm-${unit}-${seq}"
- lesson_id: "${lessonId}"
- main_mathematical_object: 必须具体到方法/规则（如"两位数乘一位数的竖式笔算方法"），不得只写课时名
- initial_object_state: 起始状态（学生已有基础）
- developed_object_state: 发展状态（本课结束时的状态）
- object_change_description: 对象变化描述
- mainline_summary: "节点A→节点B→节点C"的实际路径，含算式和情境
- source_type: "TEACHER_GUIDE_EXPLICIT" | "SYSTEM_STRUCTURAL_INFERENCE" | "TEXTBOOK_FACT"
- evidence_ids: 教师用书证据ID数组
- evidence_object_ids: 教材对象ID数组
- guide_support_status: "SUPPORTED_BY_GUIDE" | "PARTIALLY_SUPPORTED_BY_GUIDE" | "NOT_MENTIONED_IN_GUIDE"
- confidence: "high" | "medium"
- review_status: "approved"
- analysis_version: "v1.2.0"

### 2. nodes（主线节点，3-5条）
- mainline_node_id: "lmn-${unit}-${seq}-{n}"
- mainline_id: "lm-${unit}-${seq}"
- lesson_id: "${lessonId}"
- sequence_index: 从1开始
- node_title: "起点"/"关键变化"/"表征转化"/"独立运用"/"练习扩展"
- node_description: 具体描述该节点的教材内容
- main_object_ids: 必填，来自上述教材对象
- mathematical_object_state / question_state / task_state / representation_state: 具体状态
- source_type / evidence_ids / review_status

### 3. transitions（主线转换，N-1条）
- transition_id: "lmt-${unit}-${seq}-{n}"
- from_node_id / to_node_id
- mathematical_change / question_change / task_change / representation_change / support_change / context_change / response_requirement_change: 必须写明实际变化，不得为空
- change_types: 至少1个，可选值 MATHEMATICAL_OBJECT_CHANGE|QUESTION_CHANGE|TASK_CHANGE|REPRESENTATION_CHANGE|SUPPORT_CHANGE|CONTEXT_CHANGE|RESPONSE_REQUIREMENT_CHANGE
- transition_basis / source_type / evidence_ids / guide_support_status / confidence / review_status

### 4. evidence（主线证据，1-2条）
- mainline_evidence_id: "lme-${unit}-${seq}-{n}"
- mainline_id / lesson_id / node_id / transition_id
- evidence_type: "TEXTBOOK_FACT" | "TEACHER_GUIDE_EXPLICIT" | "SYSTEM_STRUCTURAL_INFERENCE"
- textbook_object_ids / teacher_guide_evidence_ids / evidence_description / support_status

### 5. alternatives（备选主线，0-1条）
- alternative_mainline_id: "lma-${unit}-${seq}"
- alternative_description / supporting_evidence_ids / conflicting_evidence_ids / reason_not_selected / review_status

### 6. reviewIssues（浅层分析拦截，至少1条）
- issue_id: "ari-${unit}-${seq}-{n}"
- category: "MAINLINE_SHALLOW" | "REPRESENTATION_GENERIC" | "EXAMPLE_ANALYSIS_INCOMPLETE" | "PRACTICE_ANALYSIS_INCOMPLETE" | "EVIDENCE_MISSING" | "INFERENCE_OVERREACH"
- issue_description / detected_pattern / affected_data_ids / severity / suggested_fix
- resolution_status: "fixed"
- resolution_note: "已修复"

## 禁用词表（不得出现）
由浅入深、图文结合、创设情境、自主探究、巩固知识、层层递进、循序渐进、从具体到抽象、数形结合

## 输出格式
返回单个 JSON 对象，结构如下：
{
  "mainlines": [...],
  "nodes": [...],
  "transitions": [...],
  "evidence": [...],
  "alternatives": [...],
  "reviewIssues": [...]
}
只返回 JSON，不要其他文字。`;
}

// ===== 调用 AI API =====
async function callAI(prompt: string): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;

  if (!apiKey) {
    throw new Error("NO_API_KEY");
  }

  const model = process.env.AI_MODEL || "gemini-2.0-flash";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.7,
      response_mime_type: "application/json",
      maxOutputTokens: 8192,
    },
  };

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`AI API error ${resp.status}: ${errText}`);
  }

  const data = await resp.json() as {
    candidates?: Array<{
      content?: { parts?: Array<{ text?: string }> };
    }>;
  };

  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) {
    throw new Error("AI API returned empty response");
  }

  return text;
}

// ===== 写入 .ts 文件 =====
function writeToTsFile(
  lessonId: string,
  group: string,
  data: {
    mainlines: unknown[];
    nodes: unknown[];
    transitions: unknown[];
    evidence: unknown[];
    alternatives: unknown[];
    reviewIssues: unknown[];
  },
  projectRoot: string,
): string {
  const exportNames = groupExportNames[group];
  if (!exportNames) throw new Error(`Unknown group: ${group}`);

  const filePath = path.join(
    projectRoot,
    "src",
    "data",
    `lessonAnalysis-extra-deep-${group}.ts`,
  );

  let fileContent: string;

  if (existsSync(filePath)) {
    // 文件已存在：读取并替换/追加
    const existing = readFileSync(filePath, "utf-8");

    // 检查是否已有该 lesson_id 的数据
    const hasLesson = existing.includes(`lesson_id: "${lessonId}"`);

    if (hasLesson) {
      // 替换：简单策略——重建整个文件
      // 提取其他课时的数据（过滤掉当前课时）
      fileContent = rebuildFile(group, exportNames, data);
    } else {
      // 追加：在数组末尾插入新条目
      fileContent = appendToFile(existing, exportNames, data);
    }
  } else {
    // 新文件
    fileContent = createNewFile(group, exportNames, data);
  }

  // 确保目录存在
  const dir = path.dirname(filePath);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });

  writeFileSync(filePath, fileContent, "utf-8");
  return filePath;
}

function createNewFile(
  _group: string,
  exportNames: typeof groupExportNames[string],
  data: {
    mainlines: unknown[];
    nodes: unknown[];
    transitions: unknown[];
    evidence: unknown[];
    alternatives: unknown[];
    reviewIssues: unknown[];
  },
): string {
  return `// 扩展课时深度分析数据（自动生成）
${getImports()}

export const ${exportNames.mainlines}: LessonMainline[] = ${JSON.stringify(data.mainlines, null, 2)};

export const ${exportNames.nodes}: LessonMainlineNode[] = ${JSON.stringify(data.nodes, null, 2)};

export const ${exportNames.transitions}: LessonMainlineTransition[] = ${JSON.stringify(data.transitions, null, 2)};

export const ${exportNames.evidence}: LessonMainlineEvidence[] = ${JSON.stringify(data.evidence, null, 2)};

export const ${exportNames.alternatives}: LessonMainlineAlternative[] = ${JSON.stringify(data.alternatives, null, 2)};

export const ${exportNames.reviewIssues}: AnalysisReviewIssue[] = ${JSON.stringify(data.reviewIssues, null, 2)};
`;
}

function getImports(): string {
  return `import type {
  LessonMainline,
  LessonMainlineNode,
  LessonMainlineTransition,
  LessonMainlineEvidence,
  LessonMainlineAlternative,
  AnalysisReviewIssue,
} from "./types";

import { ANALYSIS_VERSION } from "./lessonAnalysis";`;
}

function appendToFile(
  existing: string,
  exportNames: typeof groupExportNames[string],
  data: {
    mainlines: unknown[];
    nodes: unknown[];
    transitions: unknown[];
    evidence: unknown[];
    alternatives: unknown[];
    reviewIssues: unknown[];
  },
): string {
  let result = existing;

  // 对每个数组，在闭合 ]; 前追加新条目
  const arrays: Array<[keyof typeof data, string]> = [
    ["mainlines", exportNames.mainlines],
    ["nodes", exportNames.nodes],
    ["transitions", exportNames.transitions],
    ["evidence", exportNames.evidence],
    ["alternatives", exportNames.alternatives],
    ["reviewIssues", exportNames.reviewIssues],
  ];

  for (const [dataKey, exportName] of arrays) {
    const items = data[dataKey];
    if (items.length === 0) continue;

    const itemsStr = items.map((item) => `  ${JSON.stringify(item)},`).join("\n");

    // 找到对应数组的闭合 ];
    const pattern = new RegExp(
      `(export const ${exportName}[^\\]]*\\])\\s*;`,
    );
    const match = result.match(pattern);
    if (match) {
      // 在 ] 前插入新条目
      const insertPos = match.index! + match[1].length - 1; // ] 的位置
      result =
        result.slice(0, insertPos) +
        (result[insertPos - 1] === "[" ? "" : ",\n") +
        itemsStr.split(":").slice(1).join(":").slice(0, -1) + // 简化处理
        "\n" +
        result.slice(insertPos);
    }
  }

  return result;
}

function rebuildFile(
  group: string,
  exportNames: typeof groupExportNames[string],
  newData: {
    mainlines: unknown[];
    nodes: unknown[];
    transitions: unknown[];
    evidence: unknown[];
    alternatives: unknown[];
    reviewIssues: unknown[];
  },
): string {
  // 简化策略：用新数据完全替换（后续可优化为合并）
  return createNewFile(group, exportNames, newData);
}

// ===== 主入口 =====
export async function generateLessonAnalysis(
  lessonId: string,
  ssrLoadModule: (id: string) => Promise<Record<string, unknown>>,
  projectRoot: string,
): Promise<GenerateResult> {
  const parsed = parseLessonId(lessonId);
  if (!parsed) {
    return { success: false, lessonId, error: `无法解析 lesson_id: ${lessonId}` };
  }

  // 加载数据模块
  const dataMod = await ssrLoadModule("/src/data/index.ts");

  const officialLessons = dataMod.officialLessons as Array<{
    lesson_id: string;
    official_lesson_name: string;
    unit_id: string;
    start_page_id: string;
    end_page_id: string;
    included_object_ids: string[];
  }>;

  const objectsExtra = dataMod.objectsExtra as Array<{
    id: string;
    type: string;
    title: string;
    page_ids: string[];
  }>;

  const teacherBookReferences = dataMod.teacherBookReferences as Array<{
    id: string;
    ref_kind: string;
    tb_printed_page: number;
    excerpt: string;
    lesson_id: string;
  }>;

  const lessonContentSequencesExtra = dataMod.lessonContentSequencesExtra as Array<{
    lesson_id: string;
    sequence_summary?: string;
  }>;

  const representationRelationsExtra = dataMod.representationRelationsExtra as Array<{
    lesson_id: string;
    relation_summary?: string;
  }>;

  const problemRelationsExtra = dataMod.problemRelationsExtra as Array<{
    lesson_id: string;
    relation_summary?: string;
  }>;

  // 查找课时信息
  const lesson = officialLessons.find((l) => l.lesson_id === lessonId);
  if (!lesson) {
    return { success: false, lessonId, error: `未找到课时: ${lessonId}` };
  }

  // 提取教材对象
  const lessonObjects = objectsExtra.filter((o) =>
    lesson.included_object_ids?.includes(o.id),
  );

  // 提取教师用书证据（按单元前缀匹配）
  const tbRefs = teacherBookReferences.filter((r) => {
    const tbLessonId = r.lesson_id as string; // tbl-X-X
    const tbUnitMatch = tbLessonId.match(/^tbl-(\d+[a-z]?)-/);
    if (!tbUnitMatch) return false;
    return tbUnitMatch[1] === parsed.unit;
  });

  // 提取已有浅层数据
  const existingSeq = lessonContentSequencesExtra.find((s) => s.lesson_id === lessonId);
  const existingRep = representationRelationsExtra.find((r) => r.lesson_id === lessonId);
  const existingProb = problemRelationsExtra.find((r) => r.lesson_id === lessonId);

  const existingAnalysis = (existingSeq || existingRep || existingProb)
    ? {
        contentSequence: (existingSeq as { sequence_summary?: string })?.sequence_summary ?? "无",
        representation: (existingRep as { relation_summary?: string })?.relation_summary ?? "无",
        problemRelation: (existingProb as { relation_summary?: string })?.relation_summary ?? "无",
      }
    : null;

  // 构造 prompt
  const prompt = buildPrompt(
    lessonId,
    {
      name: lesson.official_lesson_name,
      unit: parsed.unit,
      startPage: lesson.start_page_id,
      endPage: lesson.end_page_id,
    },
    lessonObjects.map((o) => ({
      id: o.id,
      type: o.type,
      title: o.title,
      pageIds: o.page_ids,
    })),
    tbRefs.map((r) => ({
      id: r.id,
      refKind: r.ref_kind,
      tbPage: r.tb_printed_page,
      excerpt: r.excerpt,
    })),
    existingAnalysis,
  );

  // 调用 AI
  let aiResponse: string;
  try {
    aiResponse = await callAI(prompt);
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    if (errMsg === "NO_API_KEY") {
      return {
        success: false,
        lessonId,
        error: "NO_API_KEY",
        prompt,
      };
    }
    return { success: false, lessonId, error: errMsg, prompt };
  }

  // 解析 JSON
  let parsedData: {
    mainlines: unknown[];
    nodes: unknown[];
    transitions: unknown[];
    evidence: unknown[];
    alternatives: unknown[];
    reviewIssues: unknown[];
  };

  try {
    parsedData = JSON.parse(aiResponse);
  } catch {
    // 尝试提取 JSON 块
    const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        parsedData = JSON.parse(jsonMatch[0]);
      } catch {
        return {
          success: false,
          lessonId,
          error: "AI 返回内容无法解析为 JSON",
          prompt,
        };
      }
    } else {
      return {
        success: false,
        lessonId,
        error: "AI 返回内容无法解析为 JSON",
        prompt,
      };
    }
  }

  // 校验必要字段
  const requiredKeys = ["mainlines", "nodes", "transitions", "evidence", "reviewIssues"];
  for (const key of requiredKeys) {
    if (!Array.isArray((parsedData as Record<string, unknown>)[key])) {
      return {
        success: false,
        lessonId,
        error: `AI 返回数据缺少字段或类型错误: ${key}`,
        prompt,
      };
    }
  }

  // 确保 alternatives 是数组
  if (!Array.isArray(parsedData.alternatives)) {
    parsedData.alternatives = [];
  }

  // 写入文件
  let writtenFile: string | undefined;
  try {
    writtenFile = writeToTsFile(lessonId, parsed.group, parsedData, projectRoot);
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      lessonId,
      error: `文件写入失败: ${errMsg}`,
      prompt,
    };
  }

  return {
    success: true,
    lessonId,
    data: parsedData,
    writtenFile,
  };
}
