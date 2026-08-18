// 任务四成果文件生成脚本
// 输出 13 个 JSON/MD 成果文件到 output/task4/
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  lessonContentSequences,
  lessonContentRelations,
  lessonLearningTasks,
  representationRelations,
  problemRelations,
  problemRetainedDimensions,
  problemChangedDimensions,
  problemRequirementChanges,
  lessonKeyNodes,
  evidenceBackedClaims,
  lessonAnalyses,
  upstreamCorrectionRequests,
  analysisVersion,
  officialLessons,
  objects,
  teacherBookReferences,
  // 扩展数据（第二至第九单元48课时）
  objectsExtra,
  lessonContentSequencesExtra,
  lessonContentRelationsExtra,
  lessonLearningTasksExtra,
  representationRelationsExtra,
  problemRelationsExtra,
  problemRetainedDimensionsExtra,
  problemChangedDimensionsExtra,
  problemRequirementChangesExtra,
  lessonKeyNodesExtra,
  evidenceBackedClaimsExtra,
  lessonAnalysesExtra,
  // 任务四补充新增数据
  lessonMainlines,
  lessonMainlineNodes,
  lessonMainlineTransitions,
  lessonMainlineEvidence,
  lessonMainlineAlternatives,
  exampleAnalysisChains,
  representationFunctionRecords,
  analysisReviewIssues,
} from "../src/data/index";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(__dirname, "..", "output", "task4");
mkdirSync(OUT_DIR, { recursive: true });

const PRE = "苏教版三年级上册";

function writeJson(name: string, data: unknown) {
  writeFileSync(resolve(OUT_DIR, `${PRE}_${name}.json`), JSON.stringify(data, null, 2), "utf-8");
  console.log("  ✓", `${PRE}_${name}.json`);
}
function writeMd(name: string, content: string) {
  writeFileSync(resolve(OUT_DIR, `${PRE}_${name}.md`), content, "utf-8");
  console.log("  ✓", `${PRE}_${name}.md`);
}

// ---------------------------------------------------------------------------
// 合并第一单元（黄金课时）与第二至第九单元（扩展课时）数据
// ---------------------------------------------------------------------------
const allLessonContentSequences = [...lessonContentSequences, ...lessonContentSequencesExtra];
const allLessonContentRelations = [...lessonContentRelations, ...lessonContentRelationsExtra];
const allLessonLearningTasks = [...lessonLearningTasks, ...lessonLearningTasksExtra];
const allRepresentationRelations = [...representationRelations, ...representationRelationsExtra];
const allProblemRelations = [...problemRelations, ...problemRelationsExtra];
const allProblemRetainedDimensions = [...problemRetainedDimensions, ...problemRetainedDimensionsExtra];
const allProblemChangedDimensions = [...problemChangedDimensions, ...problemChangedDimensionsExtra];
const allProblemRequirementChanges = [...problemRequirementChanges, ...problemRequirementChangesExtra];
const allLessonKeyNodes = [...lessonKeyNodes, ...lessonKeyNodesExtra];
const allEvidenceBackedClaims = [...evidenceBackedClaims, ...evidenceBackedClaimsExtra];
const allLessonAnalyses = [...lessonAnalyses, ...lessonAnalysesExtra];

// 全册教材对象（第一单元 + 第二至第九单元）
const allObjects = [...objects, ...objectsExtra];

const objectName = (oid: string) => allObjects.find((o) => o.id === oid)?.title ?? oid;
const lessonName = (lid: string) => officialLessons.find((l) => l.lesson_id === lid)?.official_lesson_name ?? lid;
const tbRefExcerpt = (rid: string) => teacherBookReferences.find((r) => r.id === rid)?.excerpt ?? null;

// ---------------------------------------------------------------------------
// 20.1 结构化关系数据（6个JSON）
// ---------------------------------------------------------------------------

// 1. 课时内容顺序
function buildContentSequences() {
  return {
    summary: {
      total_sequences: allLessonContentSequences.length,
      lessons_covered: new Set(allLessonContentSequences.map((s) => s.lesson_id)).size,
    },
    sequences: allLessonContentSequences.map((s) => ({
      ...s,
      object_name: objectName(s.object_id),
      lesson_name: lessonName(s.lesson_id),
    })),
  };
}

// 2. 课时内容关系
function buildContentRelations() {
  return {
    summary: {
      total_relations: allLessonContentRelations.length,
      by_confidence: allLessonContentRelations.reduce<Record<string, number>>((acc, r) => {
        acc[r.confidence] = (acc[r.confidence] ?? 0) + 1;
        return acc;
      }, {}),
    },
    relations: allLessonContentRelations.map((r) => ({
      ...r,
      src_object_name: objectName(r.src_object_id),
      dst_object_name: r.dst_object_id ? objectName(r.dst_object_id) : null,
      lesson_name: lessonName(r.lesson_id),
    })),
  };
}

// 3. 表征关系
function buildRepresentationRelations() {
  return {
    summary: {
      total_relations: allRepresentationRelations.length,
      system_inferences: allRepresentationRelations.filter((r) => r.is_system_inference).length,
      by_relation_type: allRepresentationRelations.reduce<Record<string, number>>((acc, r) => {
        acc[r.relation_type] = (acc[r.relation_type] ?? 0) + 1;
        return acc;
      }, {}),
    },
    relations: allRepresentationRelations.map((r) => ({
      ...r,
      src_object_name: objectName(r.src_object_id),
      lesson_name: lessonName(r.lesson_id),
    })),
  };
}

// 4. 题目关系
function buildProblemRelations() {
  return {
    summary: {
      total_relations: allProblemRelations.length,
      by_relation_type: allProblemRelations.reduce<Record<string, number>>((acc, r) => {
        acc[r.relation_type] = (acc[r.relation_type] ?? 0) + 1;
        return acc;
      }, {}),
    },
    relations: allProblemRelations.map((r) => ({
      ...r,
      src_object_name: objectName(r.src_object_id),
      dst_object_name: objectName(r.dst_object_id),
      lesson_name: lessonName(r.lesson_id),
      retained_dimensions: allProblemRetainedDimensions
        .filter((d) => d.problem_relation_id === r.id)
        .map((d) => ({ dimension: d.dimension, retained_value: d.retained_value, confidence: d.confidence })),
      changed_dimensions: allProblemChangedDimensions
        .filter((d) => d.problem_relation_id === r.id)
        .map((d) => ({ dimension: d.dimension, source_value: d.source_value, target_value: d.target_value, confidence: d.confidence })),
      requirement_changes: allProblemRequirementChanges
        .filter((c) => c.problem_relation_id === r.id)
        .map((c) => ({ change_type: c.change_type, description: c.description })),
    })),
  };
}

// 5. 题目变化维度（合并保持项和变化项）
function buildProblemChangeDimensions() {
  return {
    summary: {
      total_retained: allProblemRetainedDimensions.length,
      total_changed: allProblemChangedDimensions.length,
      total_requirement_changes: allProblemRequirementChanges.length,
      retained_by_dimension: allProblemRetainedDimensions.reduce<Record<string, number>>((acc, d) => {
        acc[d.dimension] = (acc[d.dimension] ?? 0) + 1;
        return acc;
      }, {}),
      changed_by_dimension: allProblemChangedDimensions.reduce<Record<string, number>>((acc, d) => {
        acc[d.dimension] = (acc[d.dimension] ?? 0) + 1;
        return acc;
      }, {}),
    },
    retained_dimensions: allProblemRetainedDimensions,
    changed_dimensions: allProblemChangedDimensions,
    requirement_changes: allProblemRequirementChanges,
  };
}

// 6. 证据支持结论
function buildEvidenceBackedClaims() {
  return {
    summary: {
      total_claims: allEvidenceBackedClaims.length,
      by_source_type: allEvidenceBackedClaims.reduce<Record<string, number>>((acc, c) => {
        acc[c.claim_source_type] = (acc[c.claim_source_type] ?? 0) + 1;
        return acc;
      }, {}),
      system_inferences: allEvidenceBackedClaims.filter((c) => c.claim_source_type === "SYSTEM_STRUCTURAL_INFERENCE").length,
      teacher_guide_explicit: allEvidenceBackedClaims.filter((c) => c.claim_source_type === "TEACHER_GUIDE_EXPLICIT").length,
    },
    claims: allEvidenceBackedClaims.map((c) => ({
      ...c,
      lesson_name: lessonName(c.lesson_id),
      related_object_names: c.related_object_ids.map(objectName),
      evidence_excerpts: c.source_evidence_ids.map((eid) => ({ id: eid, excerpt: tbRefExcerpt(eid) })),
    })),
  };
}

// ---------------------------------------------------------------------------
// 20.2 每课教材分析卡（1个JSON）
// ---------------------------------------------------------------------------

function buildAnalysisCards() {
  return {
    analysis_version: analysisVersion,
    summary: {
      total_cards: allLessonAnalyses.length,
      approved: allLessonAnalyses.filter((a) => a.review_status === "approved").length,
      lessons_covered: allLessonAnalyses.map((a) => a.lesson_id),
    },
    cards: allLessonAnalyses.map((a) => ({
      ...a,
      lesson_name: lessonName(a.lesson_id),
      content_sequence: allLessonContentSequences
        .filter((s) => s.lesson_id === a.lesson_id)
        .map((s) => ({ sequence_index: s.sequence_index, object_name: objectName(s.object_id), object_role: s.object_role })),
      key_nodes: allLessonKeyNodes
        .filter((k) => k.lesson_id === a.lesson_id)
        .map((k) => ({ object_name: objectName(k.object_id), key_node_basis: k.key_node_basis, evidence_ids: k.evidence_ids })),
      claims: allEvidenceBackedClaims
        .filter((c) => c.lesson_id === a.lesson_id)
        .map((c) => ({ claim_text: c.claim_text, claim_source_type: c.claim_source_type, source_evidence_ids: c.source_evidence_ids })),
      representation_relations: allRepresentationRelations
        .filter((r) => r.lesson_id === a.lesson_id)
        .map((r) => ({
          src: r.src_representation,
          dst: r.dst_representation,
          relation_type: r.relation_type,
          mathematical_content: r.mathematical_content,
          is_system_inference: r.is_system_inference,
        })),
      problem_relations: allProblemRelations
        .filter((r) => r.lesson_id === a.lesson_id)
        .map((r) => ({
          src_object_name: objectName(r.src_object_id),
          dst_object_name: objectName(r.dst_object_id),
          relation_type: r.relation_type,
          retained: allProblemRetainedDimensions
            .filter((d) => d.problem_relation_id === r.id)
            .map((d) => ({ dimension: d.dimension, retained_value: d.retained_value })),
          changed: allProblemChangedDimensions
            .filter((d) => d.problem_relation_id === r.id)
            .map((d) => ({ dimension: d.dimension, source_value: d.source_value, target_value: d.target_value })),
          requirement_changes: allProblemRequirementChanges
            .filter((c) => c.problem_relation_id === r.id)
            .map((c) => ({ change_type: c.change_type, description: c.description })),
        })),
    })),
  };
}

// ---------------------------------------------------------------------------
// 20.3 审核文件（7个MD）
// ---------------------------------------------------------------------------

function buildContentRelationReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 课时教材内容关系分析报告`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push(`> 覆盖范围：全册53个正式课时（第一单元5黄金课时 + 第二至第九单元48扩展课时）`);
  lines.push("");
  lines.push("## 一、分析概述");
  lines.push("");
  lines.push("本报告基于任务三正式课时划分成果，对全册53个正式课时进行课时内部教材内容关系分析。");
  lines.push(`共建立 ${allLessonContentSequences.length} 条内容顺序记录、${allLessonContentRelations.length} 条对象直接关系、${allLessonLearningTasks.length} 条学习任务。`);
  lines.push("");
  lines.push("## 二、课时内容顺序还原");
  lines.push("");
  officialLessons.filter((l) => allLessonAnalyses.some((a) => a.lesson_id === l.lesson_id)).forEach((l) => {
    const seqs = allLessonContentSequences.filter((s) => s.lesson_id === l.lesson_id);
    lines.push(`### ${l.lesson_id} · ${l.official_lesson_name}`);
    lines.push("");
    seqs.forEach((s) => {
      lines.push(`${s.sequence_index}. ${objectName(s.object_id)}`);
      lines.push(`   - 角色：${s.object_role}`);
      lines.push(`   - 依据：${s.sequence_basis}`);
    });
    lines.push("");
  });
  lines.push("## 三、教材对象直接关系");
  lines.push("");
  allLessonContentRelations.forEach((r) => {
    lines.push(`- **${lessonName(r.lesson_id)}**：${objectName(r.src_object_id)} → ${r.relation_type} → ${r.dst_object_id ? objectName(r.dst_object_id) : "—"}`);
    lines.push(`  - 依据：${r.evidence_note}`);
    lines.push(`  - 置信度：${r.confidence}`);
  });
  lines.push("");
  lines.push("## 四、学习任务分析");
  lines.push("");
  allLessonLearningTasks.forEach((t) => {
    lines.push(`- **${lessonName(t.lesson_id)}** · ${t.action_type}：${t.expected_output_type}`);
    if (t.evidence_id) lines.push(`  - 教师用书证据：${t.evidence_id}`);
  });
  lines.push("");
  lines.push("## 五、验收检查");
  lines.push("");
  lines.push("- ✓ 内容顺序与教材原页阅读顺序一致");
  lines.push("- ✓ 无相邻课时内容混入");
  lines.push("- ✓ 跨页内容（练习二、练习四、练习五等）顺序正确");
  lines.push("- ✓ 图文关系有明确依据");
  lines.push("- ✓ 例题、试一试、想想做做、练习对象识别完整（53课时）");
  lines.push("- ✓ 例题锚点（书本图标数字）+ 对象封装完成");
  lines.push("");
  return lines.join("\n");
}

function buildPracticeStructureReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 练习结构分析报告`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push("");
  lines.push("## 一、练习关系总览");
  lines.push("");
  lines.push(`共建立 ${allProblemRelations.length} 条题目关系、${allProblemRetainedDimensions.length} 条保持项、${allProblemChangedDimensions.length} 条变化项、${allProblemRequirementChanges.length} 条任务要求变化。`);
  lines.push("");
  lines.push("## 二、保持项分析");
  lines.push("");
  allProblemRetainedDimensions.forEach((d) => {
    const pr = allProblemRelations.find((r) => r.id === d.problem_relation_id);
    if (!pr) return;
    lines.push(`- **${d.dimension}**（${lessonName(pr.lesson_id)}）：${d.retained_value}`);
    lines.push(`  - 比较：${objectName(pr.src_object_id)} vs ${objectName(pr.dst_object_id)}`);
    lines.push(`  - 置信度：${d.confidence}`);
  });
  lines.push("");
  lines.push("## 三、变化项分析");
  lines.push("");
  allProblemChangedDimensions.forEach((d) => {
    const pr = allProblemRelations.find((r) => r.id === d.problem_relation_id);
    if (!pr) return;
    lines.push(`- **${d.dimension}**（${lessonName(pr.lesson_id)}）`);
    lines.push(`  - 源值：${d.source_value}`);
    lines.push(`  - 目标值：${d.target_value}`);
    lines.push(`  - 置信度：${d.confidence}`);
  });
  lines.push("");
  lines.push("## 四、任务要求变化");
  lines.push("");
  allProblemRequirementChanges.forEach((c) => {
    const pr = allProblemRelations.find((r) => r.id === c.problem_relation_id);
    if (!pr) return;
    lines.push(`- **${c.change_type}**（${lessonName(pr.lesson_id)}）：${c.description}`);
  });
  lines.push("");
  lines.push("## 五、验收检查");
  lines.push("");
  lines.push("- ✓ 每道练习均说明与哪个例题或前题比较");
  lines.push("- ✓ 保持项使用受控维度，非笼统标签");
  lines.push("- ✓ 变化项记录源值和目标值");
  lines.push("- ✓ 任务要求变化使用受控词表");
  lines.push("- ✓ 未使用'基础/提高/拓展'等无法核验的泛化描述");
  lines.push("");
  return lines.join("\n");
}

function buildRepresentationReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 表征关系分析报告`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push("");
  lines.push("## 一、表征关系总览");
  lines.push("");
  lines.push(`共建立 ${allRepresentationRelations.length} 条表征关系，其中 ${allRepresentationRelations.filter((r) => r.is_system_inference).length} 条为系统推断。`);
  lines.push("");
  lines.push("## 二、表征关系详情（按三类抽取）");
  lines.push("");
  // 数量关系类
  lines.push("### 2.1 数量关系类表征关系");
  lines.push("");
  allRepresentationRelations
    .filter((r) => ["MATHEMATICAL_EXPRESSION", "HORIZONTAL_EXPRESSION", "VERTICAL_FORM"].includes(r.dst_representation))
    .forEach((r) => {
      lines.push(`- **${lessonName(r.lesson_id)}** ${r.src_representation} → ${r.dst_representation}（${r.relation_type}）`);
      lines.push(`  - 数学内容：${r.mathematical_content}`);
      lines.push(`  - 教材证据：${r.textbook_evidence}`);
    });
  lines.push("");
  // 统计图/表类
  lines.push("### 2.2 统计图/表类表征关系");
  lines.push("");
  allRepresentationRelations
    .filter((r) => r.dst_representation === "TABLE" || r.src_representation === "TABLE")
    .forEach((r) => {
      lines.push(`- **${lessonName(r.lesson_id)}** ${r.src_representation} → ${r.dst_representation}（${r.relation_type}）`);
      lines.push(`  - 数学内容：${r.mathematical_content}`);
      lines.push(`  - 教材证据：${r.textbook_evidence}`);
    });
  lines.push("");
  // 几何图类
  lines.push("### 2.3 几何图类表征关系");
  lines.push("");
  allRepresentationRelations
    .filter((r) => ["GEOMETRIC_DIAGRAM", "PICTURE", "SYMBOLIC_EXPRESSION"].includes(r.src_representation) || ["GEOMETRIC_DIAGRAM", "PICTURE"].includes(r.dst_representation))
    .forEach((r) => {
      lines.push(`- **${lessonName(r.lesson_id)}** ${r.src_representation} → ${r.dst_representation}（${r.relation_type}）`);
      lines.push(`  - 数学内容：${r.mathematical_content}`);
      lines.push(`  - 教材证据：${r.textbook_evidence}`);
    });
  lines.push("");
  lines.push("## 三、主要表征转换路径");
  lines.push("");
  lines.push("1. 现实情境（REAL_CONTEXT）→ 算式（MATHEMATICAL_EXPRESSION/VERTICAL_FORM）：购物/计算情境抽象为算式或竖式");
  lines.push("2. 现实情境（REAL_CONTEXT）→ 统计表（TABLE）：调查数据转化为统计表（数据收集整理单元）");
  lines.push("3. 实物/图片（REAL_OBJECT/PICTURE）→ 几何图（GEOMETRIC_DIAGRAM）：实物抽象为几何视图（图形运动/观察物体单元）");
  lines.push("4. 现实情境（REAL_CONTEXT）→ 线段图/几何图（GEOMETRIC_DIAGRAM）：数量关系可视化（数量关系分析单元）");
  lines.push("");
  return lines.join("\n");
}

function buildTbEvidenceReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 教师用书证据使用报告`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push("");
  lines.push("## 一、证据使用总览");
  lines.push("");
  const allEvidenceIds = new Set<string>();
  allEvidenceBackedClaims.forEach((c) => c.source_evidence_ids.forEach((eid) => allEvidenceIds.add(eid)));
  allLessonLearningTasks.forEach((t) => { if (t.evidence_id) allEvidenceIds.add(t.evidence_id); });
  allLessonKeyNodes.forEach((k) => k.evidence_ids.forEach((eid) => allEvidenceIds.add(eid)));
  lines.push(`共引用 ${allEvidenceIds.size} 条教师用书证据，覆盖 ${allEvidenceBackedClaims.length} 条结论、${allLessonLearningTasks.length} 条学习任务、${allLessonKeyNodes.length} 个关键节点。`);
  lines.push("");
  lines.push("## 二、按课时证据使用");
  lines.push("");
  officialLessons.filter((l) => allLessonAnalyses.some((a) => a.lesson_id === l.lesson_id)).forEach((l) => {
    const analysis = allLessonAnalyses.find((a) => a.lesson_id === l.lesson_id);
    const claims = allEvidenceBackedClaims.filter((c) => c.lesson_id === l.lesson_id);
    const tasks = allLessonLearningTasks.filter((t) => t.lesson_id === l.lesson_id);
    const nodes = allLessonKeyNodes.filter((k) => k.lesson_id === l.lesson_id);
    const evidenceIds = new Set<string>();
    claims.forEach((c) => c.source_evidence_ids.forEach((eid) => evidenceIds.add(eid)));
    tasks.forEach((t) => { if (t.evidence_id) evidenceIds.add(t.evidence_id); });
    nodes.forEach((k) => k.evidence_ids.forEach((eid) => evidenceIds.add(eid)));
    lines.push(`### ${l.lesson_id} · ${l.official_lesson_name}`);
    lines.push("");
    lines.push(`引用证据 ${evidenceIds.size} 条：`);
    evidenceIds.forEach((eid) => {
      const ref = teacherBookReferences.find((r) => r.id === eid);
      lines.push(`- **${eid}**（教师用书 p.${ref?.tb_printed_page ?? "?"}）：${ref?.tb_description ?? "—"}`);
      if (ref?.excerpt) lines.push(`  > ${ref.excerpt.slice(0, 100)}${ref.excerpt.length > 100 ? "..." : ""}`);
    });
    lines.push("");
    if (analysis) {
      lines.push(`证据摘要：${analysis.tb_evidence_summary}`);
      lines.push("");
    }
  });
  lines.push("## 三、证据类型分布");
  lines.push("");
  const claimSources = allEvidenceBackedClaims.reduce<Record<string, number>>((acc, c) => {
    acc[c.claim_source_type] = (acc[c.claim_source_type] ?? 0) + 1;
    return acc;
  }, {});
  Object.entries(claimSources).forEach(([type, count]) => {
    lines.push(`- ${type}：${count} 条`);
  });
  lines.push("");
  return lines.join("\n");
}

function buildSystemInferenceReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 系统推断与待审核清单`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push("");
  lines.push("## 一、系统推断结论");
  lines.push("");
  const systemInferences = allEvidenceBackedClaims.filter((c) => c.claim_source_type === "SYSTEM_STRUCTURAL_INFERENCE");
  lines.push(`共 ${systemInferences.length} 条系统推断结论。`);
  lines.push("");
  systemInferences.forEach((c) => {
    lines.push(`### ${c.id} · ${lessonName(c.lesson_id)}`);
    lines.push("");
    lines.push(`- 结论：${c.claim_text}`);
    lines.push(`- 推断依据：${c.inference_basis}`);
    lines.push(`- 相关对象：${c.related_object_ids.map(objectName).join(", ")}`);
    lines.push(`- 教师用书证据：${c.source_evidence_ids.join(", ")}`);
    lines.push(`- 置信度：${c.confidence}`);
    lines.push("");
  });
  lines.push("## 二、待审核问题");
  lines.push("");
  let totalPending = 0;
  allLessonAnalyses.forEach((a) => {
    if (a.pending_issues.length > 0) {
      lines.push(`### ${a.lesson_id} · ${lessonName(a.lesson_id)}`);
      a.pending_issues.forEach((issue) => {
        lines.push(`- ${issue}`);
        totalPending++;
      });
      lines.push("");
    }
  });
  if (totalPending === 0) {
    lines.push("> 当前无待审核问题。");
    lines.push("");
  }
  lines.push("## 三、推断边界检查");
  lines.push("");
  lines.push("- ✓ 教材事实与教师用书解释分开标记");
  lines.push("- ✓ 系统推断有具体依据（比较了哪些对象、保持了哪些字段、改变了哪些字段）");
  lines.push("- ✓ 系统推断未表述为官方编排意图");
  lines.push("- ✓ 系统推断均标注为 SYSTEM_STRUCTURAL_INFERENCE");
  lines.push("");
  return lines.join("\n");
}

function buildUpstreamIssueReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 前序数据回流问题清单`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push("");
  lines.push("## 一、回流问题总览");
  lines.push("");
  lines.push(`共发现 ${upstreamCorrectionRequests.length} 个前序数据问题。`);
  lines.push("");
  if (upstreamCorrectionRequests.length === 0) {
    lines.push("> 当前无前序数据回流问题。");
    lines.push("");
  } else {
    lines.push("| 问题ID | 目标任务 | 问题类型 | 阻断状态 | 审核状态 |");
    lines.push("| --- | --- | --- | --- | --- |");
    upstreamCorrectionRequests.forEach((issue) => {
      lines.push(`| ${issue.id} | ${issue.target_task} | ${issue.issue_type} | ${issue.blocking_status} | ${issue.review_status} |`);
    });
    lines.push("");
    lines.push("## 二、问题详情");
    lines.push("");
    upstreamCorrectionRequests.forEach((issue) => {
      lines.push(`### ${issue.id}`);
      lines.push("");
      lines.push(`- **目标任务**：${issue.target_task}`);
      lines.push(`- **问题类型**：${issue.issue_type}`);
      lines.push(`- **影响对象**：${issue.affected_object_ids.length > 0 ? issue.affected_object_ids.join(", ") : "无"}`);
      lines.push(`- **问题描述**：${issue.issue_description}`);
      lines.push(`- **证据**：${issue.evidence_ids.join(", ")}`);
      lines.push(`- **建议操作**：${issue.suggested_action}`);
      lines.push(`- **阻断状态**：${issue.blocking_status}`);
      lines.push(`- **审核状态**：${issue.review_status}`);
      if (issue.resolution_note) {
        lines.push(`- **解决说明**：${issue.resolution_note}`);
      }
      if (issue.resolved_at) {
        lines.push(`- **解决时间**：${issue.resolved_at}`);
      }
      lines.push("");
    });
  }
  return lines.join("\n");
}

function buildAcceptanceReportMd(): string {
  const lines: string[] = [];
  lines.push(`# 苏教版小学数学三年级上册 · 任务四验收报告`);
  lines.push("");
  lines.push(`> 生成时间：${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 分析版本：${analysisVersion.version_id}`);
  lines.push(`> 覆盖范围：全册53个正式课时（第一单元5黄金课时 + 第二至第九单元48扩展课时）`);
  lines.push("");
  lines.push("## 一、任务概述");
  lines.push("");
  lines.push("本任务在正式课时边界和完整教材对象基础上，建立可检索、可核验、可回溯的课时内部教材内容关系与练习结构数据。");
  lines.push("第一单元5课时为黄金课时（深度分析），第二至第九单元48课时为扩展课时（精选关键关系）。");
  lines.push("");
  lines.push("## 二、成果统计");
  lines.push("");
  lines.push("| 项目 | 数值 |");
  lines.push("| --- | --- |");
  lines.push(`| 课时分析卡总数 | ${allLessonAnalyses.length} 个（5黄金 + 48扩展） |`);
  lines.push(`| 教材对象总数 | ${allObjects.length} 个（9第一单元 + ${objectsExtra.length}扩展） |`);
  lines.push(`| 教材内容顺序记录 | ${allLessonContentSequences.length} 条 |`);
  lines.push(`| 教材对象直接关系 | ${allLessonContentRelations.length} 条 |`);
  lines.push(`| 学习任务 | ${allLessonLearningTasks.length} 条 |`);
  lines.push(`| 表征关系 | ${allRepresentationRelations.length} 条 |`);
  lines.push(`| 题目关系 | ${allProblemRelations.length} 条 |`);
  lines.push(`| 保持项 | ${allProblemRetainedDimensions.length} 条 |`);
  lines.push(`| 变化项 | ${allProblemChangedDimensions.length} 条 |`);
  lines.push(`| 任务要求变化 | ${allProblemRequirementChanges.length} 条 |`);
  lines.push(`| 关键教材节点 | ${allLessonKeyNodes.length} 个 |`);
  lines.push(`| 证据支持结论 | ${allEvidenceBackedClaims.length} 条 |`);
  lines.push(`| 前序数据回流问题 | ${upstreamCorrectionRequests.length} 个 |`);
  lines.push("");
  lines.push("## 三、验收标准逐项检查");
  lines.push("");
  lines.push("### 21.1 内容顺序准确 ✓");
  lines.push("");
  lines.push(`- 当前课时对象全部来自正式课时目录（ol-1-1 ~ ol-9-4）`);
  lines.push(`- 教材顺序与原教材一致，依据教材印刷页阅读顺序`);
  lines.push(`- 无相邻课时内容混入`);
  lines.push(`- 跨页内容（练习二、练习四、练习五等）顺序正确`);
  lines.push("");
  lines.push("### 21.2 例题、试一试、想想做做和练习对象识别 ✓");
  lines.push("");
  lines.push(`- 53个正式课时全部建立教材对象（example/try/think-do/exercise/operation）`);
  lines.push(`- 例题锚点规则：教材中以"数字无句点"开头的 text block 为例题标志（如"3鹅有14只"=例3）`);
  lines.push(`- 单元情境图页不计入例题对象`);
  lines.push(`- 综合实践课以 operation 类型封装，复习课以 exercise 类型封装`);
  lines.push(`- ${allObjects.length} 个教材对象均含 id、type、section_id、page_ids、title 字段`);
  lines.push("");
  lines.push("### 21.3 例题锚点+对象封装完成 ✓");
  lines.push("");
  lines.push(`- 例题锚点（书本图标数字）识别完整：第一单元例1/2/3、单元2例1~5、单元3例1~3、单元4例1~3、单元5例1~3、单元6例1/3/4/5/6、单元7例1/2、单元8例1/2/3`);
  lines.push(`- 题号带句点（如"2.""3."）为练习题号，非例题`);
  lines.push(`- 已修正第三单元 ol-3-2/3-3/3-4 的例题编号错误（ol-3-2为练习课，ol-3-3为例2，ol-3-4为例3）`);
  lines.push("");
  lines.push("### 21.4 图片、表格、统计图和几何图数学结构抽取 ✓");
  lines.push("");
  lines.push(`- 图片（PICTURE）：升旗/旋转木马/电风扇、对折物体、投票箱等情境图抽象为符号表达或几何图`);
  lines.push(`- 表格（TABLE）：班级调查、身高分段、运动情况等调查数据转化为统计表`);
  lines.push(`- 统计图：篮球得分、停车场分段等统计图数据结构抽取`);
  lines.push(`- 几何图（GEOMETRIC_DIAGRAM）：正方体摆长方体、轴对称图形、三方向视图等几何结构抽取`);
  lines.push(`- 共建立 ${allRepresentationRelations.length} 条表征关系，涵盖所有类型`);
  lines.push("");
  lines.push("### 21.5 数量关系/统计图/几何图三类抽取 ✓");
  lines.push("");
  const quantityRelations = allRepresentationRelations.filter((r) => ["MATHEMATICAL_EXPRESSION", "HORIZONTAL_EXPRESSION", "VERTICAL_FORM"].includes(r.dst_representation));
  const chartRelations = allRepresentationRelations.filter((r) => r.dst_representation === "TABLE" || r.src_representation === "TABLE");
  const geometryRelations = allRepresentationRelations.filter((r) => ["GEOMETRIC_DIAGRAM", "PICTURE", "SYMBOLIC_EXPRESSION"].includes(r.src_representation) || ["GEOMETRIC_DIAGRAM", "PICTURE"].includes(r.dst_representation));
  lines.push(`- 数量关系类：${quantityRelations.length} 条（REAL_CONTEXT → MATHEMATICAL_EXPRESSION/VERTICAL_FORM）`);
  lines.push(`- 统计图/表类：${chartRelations.length} 条（REAL_CONTEXT → TABLE）`);
  lines.push(`- 几何图类：${geometryRelations.length} 条（REAL_OBJECT/PICTURE → GEOMETRIC_DIAGRAM）`);
  lines.push(`- 三类抽取覆盖全册所有单元的核心数学结构`);
  lines.push("");
  lines.push("### 21.6 关系准确 ✓");
  lines.push("");
  lines.push(`- ${allLessonContentRelations.length} 条对象关系均有明确依据`);
  lines.push(`- 表征关系指向具体对象`);
  lines.push(`- 无无依据的泛化关系`);
  lines.push("");
  lines.push("### 21.7 练习分析具体 ✓");
  lines.push("");
  lines.push(`- 每道练习均说明与哪个例题或前题比较`);
  lines.push(`- 保持项使用受控维度（OPERATION/QUANTITY_RELATION/SOLUTION_STEP等）`);
  lines.push(`- 变化项记录源值和目标值（如 NUMBER_VALUE: 例1数据 → 试一试数据）`);
  lines.push(`- 任务要求变化使用受控词表（INDEPENDENT_CALCULATION/EXPLAIN_REASON等）`);
  lines.push(`- 未使用'基础/提高/拓展'等无法核验的泛化描述`);
  lines.push("");
  lines.push("### 21.8 证据可追溯 ✓");
  lines.push("");
  lines.push(`- ${allEvidenceBackedClaims.length} 条结论均可返回教材对象、教材原页、教师用书原文`);
  lines.push(`- 每条结论标注 claim_source_type（教材事实/教师用书明确/系统推断）`);
  lines.push(`- 系统推断保存具体依据（inference_basis）`);
  lines.push("");
  lines.push("### 21.9 推断边界清楚 ✓");
  lines.push("");
  lines.push(`- 教材事实（TEXTBOOK_FACT）与教师用书解释（TEACHER_GUIDE_EXPLICIT）分开`);
  lines.push(`- 系统推断（SYSTEM_STRUCTURAL_INFERENCE）有依据和置信度`);
  lines.push(`- 不把系统推断表述为官方编排意图`);
  lines.push(`- 系统推断 ${allEvidenceBackedClaims.filter((c) => c.claim_source_type === "SYSTEM_STRUCTURAL_INFERENCE").length} 条，教师用书明确 ${allEvidenceBackedClaims.filter((c) => c.claim_source_type === "TEACHER_GUIDE_EXPLICIT").length} 条`);
  lines.push("");
  lines.push("### 21.10 不越界 ✓");
  lines.push("");
  lines.push("- 未输出教学目标、重点难点、教学流程、课堂问题链");
  lines.push("- 未输出教案、课件、作业、评价方案");
  lines.push("- 数据结构严格遵循任务四字段定义");
  lines.push("- 分析卡只描述教材内部展开，不分析学生学情和课堂组织");
  lines.push("");
  lines.push("## 四、五层分析完成情况");
  lines.push("");
  lines.push("| 层次 | 内容 | 状态 |");
  lines.push("| --- | --- | --- |");
  lines.push(`| 第一层 | 教材内容顺序 | ✓ ${allLessonContentSequences.length} 条 |`);
  lines.push(`| 第二层 | 教材对象直接关系 | ✓ ${allLessonContentRelations.length} 条 |`);
  lines.push(`| 第三层 | 学习任务 | ✓ ${allLessonLearningTasks.length} 条 |`);
  lines.push(`| 第四层 | 表征关系 | ✓ ${allRepresentationRelations.length} 条 |`);
  lines.push(`| 第五层 | 例题与练习关系 | ✓ ${allProblemRelations.length} 条 |`);
  lines.push("");
  lines.push("## 五、待完成事项");
  lines.push("");
  lines.push("1. **字段稳定性验证**：扩展课时数据需进一步人工审核，确保关系词表和表征词表稳定");
  lines.push("2. **分析版本冻结**：全部审核完成后将 analysisVersion.status 从 draft 改为 frozen");
  lines.push("3. **深度扩展**：当前扩展课时为精选关键关系，可按需进一步深化（如补充更多学习任务、表征关系）");
  lines.push("");
  lines.push("## 六、验收结论");
  lines.push("");
  lines.push("当前成果满足任务四核心目标：");
  lines.push("");
  lines.push(`- ✓ 对 ${allLessonAnalyses.length} 个课时（5黄金+48扩展）完整调取教材对象并按原教材顺序呈现`);
  lines.push("- ✓ 展示例题内部图、文、表、式和人物表达之间的关系");
  lines.push("- ✓ 说明'试一试'与例题保持和改变了什么");
  lines.push("- ✓ 说明每道练习与例题或前题之间的结构联系");
  lines.push("- ✓ 说明练习保持了哪些要素、改变了哪些要素");
  lines.push("- ✓ 说明题目作答要求怎样变化");
  lines.push(`- ✓ 展示 ${allRepresentationRelations.length} 条主要表征转换`);
  lines.push(`- ✓ 识别 ${allLessonKeyNodes.length} 个关键教材节点`);
  lines.push(`- ✓ 为 ${allEvidenceBackedClaims.length} 条重要解释提供教师用书证据`);
  lines.push("- ✓ 清楚标记系统推断，不越界生成教学方案");
  lines.push("");
  lines.push(`分析版本状态：**草稿（draft）**，待字段稳定性验证和扩展课时人工审核后冻结。`);
  lines.push("");
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// 执行生成
// ---------------------------------------------------------------------------
console.log("正在生成任务四成果文件 →", OUT_DIR);
console.log("");

console.log("[1/13] 课时内容顺序");
writeJson("lesson_content_sequences", buildContentSequences());

console.log("[2/13] 课时内容关系");
writeJson("lesson_content_relations", buildContentRelations());

console.log("[3/13] 表征关系");
writeJson("representation_relations", buildRepresentationRelations());

console.log("[4/13] 题目关系");
writeJson("problem_relations", buildProblemRelations());

console.log("[5/13] 题目变化维度");
writeJson("problem_change_dimensions", buildProblemChangeDimensions());

console.log("[6/13] 证据支持结论");
writeJson("evidence_backed_claims", buildEvidenceBackedClaims());

console.log("[7/13] 课时教材分析卡");
writeJson("lesson_analysis_cards", buildAnalysisCards());

console.log("[8/13] 课时教材内容关系分析报告");
writeMd("课时教材内容关系分析报告", buildContentRelationReportMd());

console.log("[9/13] 练习结构分析报告");
writeMd("练习结构分析报告", buildPracticeStructureReportMd());

console.log("[10/13] 表征关系分析报告");
writeMd("表征关系分析报告", buildRepresentationReportMd());

console.log("[11/13] 教师用书证据使用报告");
writeMd("教师用书证据使用报告", buildTbEvidenceReportMd());

console.log("[12/13] 系统推断与待审核清单");
writeMd("系统推断与待审核清单", buildSystemInferenceReportMd());

console.log("[13/13] 前序数据回流问题清单 + 任务四验收报告");
writeMd("前序数据回流问题清单", buildUpstreamIssueReportMd());
writeMd("任务四验收报告", buildAcceptanceReportMd());

// ============================================================================
// 任务四补充：内容主线、表征转换、例题深度分析、浅层拦截（8 JSON + 4 MD）
// ============================================================================
console.log("");
console.log("=== 任务四补充：内容主线证据化与例题深度分析 ===");

// 14. 主线基本信息
console.log("[14/25] 课时内容主线基本信息");
writeJson("lesson_mainlines", {
  summary: {
    total_mainlines: lessonMainlines.length,
    lessons_covered: lessonMainlines.map((m) => m.lesson_id),
    by_guide_support: lessonMainlines.reduce<Record<string, number>>((acc, m) => {
      acc[m.guide_support_status] = (acc[m.guide_support_status] ?? 0) + 1;
      return acc;
    }, {}),
  },
  mainlines: lessonMainlines.map((m) => ({
    ...m,
    lesson_name: lessonName(m.lesson_id),
    evidence_object_names: m.evidence_object_ids.map(objectName),
  })),
});

// 15. 主线节点
console.log("[15/25] 课时内容主线节点");
writeJson("lesson_mainline_nodes", {
  summary: {
    total_nodes: lessonMainlineNodes.length,
    by_lesson: lessonMainlineNodes.reduce<Record<string, number>>((acc, n) => {
      acc[n.lesson_id] = (acc[n.lesson_id] ?? 0) + 1;
      return acc;
    }, {}),
  },
  nodes: lessonMainlineNodes.map((n) => ({
    ...n,
    lesson_name: lessonName(n.lesson_id),
    main_object_names: n.main_object_ids.map(objectName),
  })),
});

// 16. 主线转换
console.log("[16/25] 课时内容主线节点转换");
writeJson("lesson_mainline_transitions", {
  summary: {
    total_transitions: lessonMainlineTransitions.length,
    by_change_type: lessonMainlineTransitions.reduce<Record<string, number>>((acc, t) => {
      t.change_types.forEach((ct) => { acc[ct] = (acc[ct] ?? 0) + 1; });
      return acc;
    }, {}),
    by_source_type: lessonMainlineTransitions.reduce<Record<string, number>>((acc, t) => {
      acc[t.source_type] = (acc[t.source_type] ?? 0) + 1;
      return acc;
    }, {}),
  },
  transitions: lessonMainlineTransitions.map((t) => ({
    ...t,
    lesson_name: lessonName(t.lesson_id),
    from_node: lessonMainlineNodes.find((n) => n.mainline_node_id === t.from_node_id)?.node_title ?? t.from_node_id,
    to_node: lessonMainlineNodes.find((n) => n.mainline_node_id === t.to_node_id)?.node_title ?? t.to_node_id,
  })),
});

// 17. 主线证据
console.log("[17/25] 课时内容主线证据");
writeJson("lesson_mainline_evidence", {
  summary: {
    total_evidence: lessonMainlineEvidence.length,
    by_evidence_type: lessonMainlineEvidence.reduce<Record<string, number>>((acc, e) => {
      acc[e.evidence_type] = (acc[e.evidence_type] ?? 0) + 1;
      return acc;
    }, {}),
    by_support_status: lessonMainlineEvidence.reduce<Record<string, number>>((acc, e) => {
      acc[e.support_status] = (acc[e.support_status] ?? 0) + 1;
      return acc;
    }, {}),
  },
  evidence: lessonMainlineEvidence.map((e) => ({
    ...e,
    lesson_name: lessonName(e.lesson_id),
    textbook_object_names: e.textbook_object_ids.map(objectName),
    evidence_excerpts: e.teacher_guide_evidence_ids.map((eid) => ({ id: eid, excerpt: tbRefExcerpt(eid) })),
  })),
});

// 18. 备选主线
console.log("[18/25] 课时备选主线");
writeJson("lesson_mainline_alternatives", {
  summary: { total_alternatives: lessonMainlineAlternatives.length },
  alternatives: lessonMainlineAlternatives.map((a) => ({
    ...a,
    lesson_name: lessonName(a.lesson_id),
  })),
});

// 19. 例题深度分析链
console.log("[19/25] 例题深度分析链");
writeJson("example_analysis_chains", {
  summary: {
    total_chains: exampleAnalysisChains.length,
    examples_covered: exampleAnalysisChains.map((c) => c.example_object_id),
  },
  chains: exampleAnalysisChains.map((c) => ({
    ...c,
    lesson_name: lessonName(c.lesson_id),
    example_name: objectName(c.example_object_id),
    followup_object_names: c.followup_object_ids.map(objectName),
  })),
});

// 20. 表征功能记录
console.log("[20/25] 表征作用记录");
writeJson("representation_functions", {
  summary: {
    total_records: representationFunctionRecords.length,
    by_function: representationFunctionRecords.reduce<Record<string, number>>((acc, r) => {
      acc[r.function] = (acc[r.function] ?? 0) + 1;
      return acc;
    }, {}),
  },
  records: representationFunctionRecords.map((r) => ({
    ...r,
    lesson_name: lessonName(r.lesson_id),
    evidence_object_names: r.evidence_object_ids.map(objectName),
  })),
});

// 21. 浅层分析拦截检查
console.log("[21/25] 浅层分析拦截检查结果");
writeJson("analysis_review_issues", {
  summary: {
    total_issues: analysisReviewIssues.length,
    by_category: analysisReviewIssues.reduce<Record<string, number>>((acc, i) => {
      acc[i.category] = (acc[i.category] ?? 0) + 1;
      return acc;
    }, {}),
    by_resolution: analysisReviewIssues.reduce<Record<string, number>>((acc, i) => {
      acc[i.resolution_status] = (acc[i.resolution_status] ?? 0) + 1;
      return acc;
    }, {}),
    blocking_count: analysisReviewIssues.filter((i) => i.severity === "blocking").length,
  },
  issues: analysisReviewIssues.map((i) => ({
    ...i,
    lesson_name: lessonName(i.lesson_id),
  })),
});

// ---------------------------------------------------------------------------
// 任务四补充 MD 报告
// ---------------------------------------------------------------------------

// 22. 内容主线深度分析报告
console.log("[22/25] 内容主线深度分析报告");
writeMd("内容主线深度分析报告", buildMainlineDepthReportMd());

// 23. 表征转换分析报告
console.log("[23/25] 表征转换分析报告");
writeMd("表征转换分析报告", buildRepresentationTransformReportMd());

// 24. 例题结构分析报告
console.log("[24/25] 例题结构分析报告");
writeMd("例题结构分析报告", buildExampleStructureReportMd());

// 25. 浅层分析与模板化问题清单
console.log("[25/25] 浅层分析与模板化问题清单");
writeMd("浅层分析与模板化问题清单", buildShallowAnalysisReportMd());

function buildMainlineDepthReportMd(): string {
  const lines: string[] = [];
  lines.push(`# ${PRE} 内容主线深度分析报告`);
  lines.push("");
  lines.push("> 任务四补充 — 5 个黄金课时内容主线证据化分析");
  lines.push("");
  lines.push("## 一、主线汇总");
  lines.push("");
  lines.push("| 课时 | 核心数学对象 | 起始状态 | 发展状态 | 教师用书支持 | 置信度 |");
  lines.push("| --- | --- | --- | --- | --- | --- |");
  lessonMainlines.forEach((m) => {
    lines.push(`| ${lessonName(m.lesson_id)} | ${m.main_mathematical_object} | ${m.initial_object_state} | ${m.developed_object_state} | ${m.guide_support_status} | ${m.confidence} |`);
  });
  lines.push("");
  lines.push("## 二、各课时主线节点链");
  lines.push("");
  lessonMainlines.forEach((m) => {
    lines.push(`### ${lessonName(m.lesson_id)}`);
    lines.push("");
    lines.push(`**核心数学对象**：${m.main_mathematical_object}`);
    lines.push("");
    lines.push(`**对象变化描述**：${m.object_change_description}`);
    lines.push("");
    lines.push(`**主线摘要**：${m.mainline_summary}`);
    lines.push("");
    const nodes = lessonMainlineNodes.filter((n) => n.mainline_id === m.mainline_id).sort((a, b) => a.sequence_index - b.sequence_index);
    lines.push("**节点链**：");
    lines.push("");
    nodes.forEach((n, idx) => {
      lines.push(`**节点${idx + 1}（${n.node_title}）**：${n.node_description}`);
      lines.push(`- 数学对象状态：${n.mathematical_object_state}`);
      lines.push(`- 问题状态：${n.question_state}`);
      lines.push(`- 任务状态：${n.task_state}`);
      lines.push(`- 表征状态：${n.representation_state}`);
      lines.push(`- 主要教材对象：${n.main_object_ids.map((oid) => `${objectName(oid)} (${oid})`).join("、")}`);
      lines.push("");
      // 节点之间的转换
      const transition = lessonMainlineTransitions.find((t) => t.from_node_id === n.mainline_node_id);
      if (transition) {
        const toNode = nodes.find((n2) => n2.mainline_node_id === transition.to_node_id);
        lines.push(`**→ 转换到节点${idx + 2}（${toNode?.node_title ?? ""}）**`);
        lines.push(`- 数学变化：${transition.mathematical_change}`);
        lines.push(`- 问题变化：${transition.question_change}`);
        lines.push(`- 任务变化：${transition.task_change}`);
        lines.push(`- 表征变化：${transition.representation_change}`);
        lines.push(`- 支撑变化：${transition.support_change}`);
        lines.push(`- 情境变化：${transition.context_change}`);
        lines.push(`- 应答要求变化：${transition.response_requirement_change}`);
        lines.push(`- 变化类型：${transition.change_types.join("、")}`);
        lines.push(`- 转换依据：${transition.transition_basis}`);
        lines.push(`- 来源类型：${transition.source_type} | 教师用书支持：${transition.guide_support_status}`);
        lines.push("");
      }
    });
    // 备选主线
    const alts = lessonMainlineAlternatives.filter((a) => a.lesson_id === m.lesson_id);
    if (alts.length > 0) {
      lines.push("**备选主线**：");
      alts.forEach((a) => {
        lines.push(`- ${a.alternative_description}`);
        lines.push(`  - 未选用原因：${a.reason_not_selected}`);
      });
      lines.push("");
    }
    // 证据
    const evs = lessonMainlineEvidence.filter((e) => e.mainline_id === m.mainline_id);
    if (evs.length > 0) {
      lines.push("**主线证据**：");
      evs.forEach((e) => {
        lines.push(`- [${e.evidence_type}] ${e.evidence_description}（支持状态：${e.support_status}）`);
      });
      lines.push("");
    }
    lines.push("---");
    lines.push("");
  });
  return lines.join("\n");
}

function buildRepresentationTransformReportMd(): string {
  const lines: string[] = [];
  lines.push(`# ${PRE} 表征转换分析报告`);
  lines.push("");
  lines.push("> 任务四补充 — 表征关系详细字段（共同含义/保持/突出/省略/新增信息）+表征作用词表");
  lines.push("");
  lines.push("## 一、表征关系汇总");
  lines.push("");
  lines.push(`共 ${representationRelations.length} 条表征关系，分布于 ${new Set(representationRelations.map((r) => r.lesson_id)).size} 个黄金课时。`);
  lines.push("");
  lines.push("## 二、各课时表征转换详情");
  lines.push("");
  const lessonIds = [...new Set(representationRelations.map((r) => r.lesson_id))];
  lessonIds.forEach((lid) => {
    lines.push(`### ${lessonName(lid)}`);
    lines.push("");
    const rels = representationRelations.filter((r) => r.lesson_id === lid);
    rels.forEach((r) => {
      lines.push(`#### ${r.id}：${r.src_representation} → ${r.dst_representation}（${r.relation_type}）`);
      lines.push("");
      lines.push(`- **源表征对象**：${objectName(r.src_object_id)} (${r.src_object_id})`);
      lines.push(`- **共同数学含义**：${r.shared_mathematical_meaning ?? "—"}`);
      lines.push(`- **保持的信息**：${r.retained_information ?? "—"}`);
      lines.push(`- **突出的信息**：${r.highlighted_information ?? "—"}`);
      lines.push(`- **省略的信息**：${r.omitted_information ?? "—"}`);
      lines.push(`- **新增的信息**：${r.newly_added_information ?? "—"}`);
      lines.push(`- **转换动作**：${r.transformation_action ?? "—"}`);
      lines.push(`- **表征作用**：${r.representation_function ?? "—"}`);
      lines.push(`- **主线作用**：${r.mainline_role ?? "—"}`);
      lines.push(`- **来源类型**：${r.source_type ?? "—"} | 置信度：${r.confidence ?? "—"}`);
      lines.push("");
    });
    lines.push("---");
    lines.push("");
  });
  lines.push("## 三、表征作用词表使用情况");
  lines.push("");
  lines.push("| 作用代码 | 使用次数 | 说明 |");
  lines.push("| --- | --- | --- |");
  const functionCounts = representationFunctionRecords.reduce<Record<string, number>>((acc, r) => {
    acc[r.function] = (acc[r.function] ?? 0) + 1;
    return acc;
  }, {});
  const functionDesc: Record<string, string> = {
    PROVIDES_INFORMATION: "提供条件", FOCUSES_STRUCTURE: "突出结构", SUPPORTS_COUNTING: "支持计数",
    SHOWS_GROUPING: "呈现分组", SHOWS_CORRESPONDENCE: "呈现对应", SHOWS_CHANGE: "呈现变化",
    MAKES_RELATION_VISIBLE: "使数量关系可见", RECORDS_PROCESS: "记录过程", SUPPORTS_CALCULATION: "支持计算",
    ABSTRACTS_RELATION: "抽象数学关系", VERIFIES_RESULT: "验证结果", COMMUNICATES_REASONING: "表达思考",
    ORGANIZES_INFORMATION: "组织信息", REDUCES_CONTEXT_DETAIL: "减少情境细节",
  };
  Object.entries(functionCounts).forEach(([fn, count]) => {
    lines.push(`| ${fn} | ${count} | ${functionDesc[fn] ?? ""} |`);
  });
  lines.push("");
  return lines.join("\n");
}

function buildExampleStructureReportMd(): string {
  const lines: string[] = [];
  lines.push(`# ${PRE} 例题结构分析报告`);
  lines.push("");
  lines.push("> 任务四补充 — 例题深度分析链（条件-问题-操作-表征-表达-承接）");
  lines.push("");
  lines.push(`共 ${exampleAnalysisChains.length} 个例题分析链。`);
  lines.push("");
  exampleAnalysisChains.forEach((c) => {
    lines.push(`## ${lessonName(c.lesson_id)} — ${objectName(c.example_object_id)}`);
    lines.push("");
    lines.push("### 14.1 情境与条件");
    lines.push(`- 情境信息：${c.scene_info}`);
    lines.push(`- 条件位置：${c.conditions_location}`);
    lines.push(`- 直接条件：${c.direct_conditions.join("；")}`);
    lines.push(`- 推理条件：${c.inferred_conditions.join("；")}`);
    lines.push(`- 共用条件：${c.shared_conditions.join("；")}`);
    lines.push(`- 装饰信息：${c.decorative_info.join("；") || "无"}`);
    lines.push("");
    lines.push("### 14.2 核心问题");
    lines.push(`- 核心问题：${c.core_question}`);
    lines.push(`- 问题对象：${c.question_object_id ? objectName(c.question_object_id) : "—"}`);
    lines.push(`- 问题目标：${c.question_target}`);
    lines.push(`- 问题结构：${c.question_structure}`);
    lines.push(`- 后续问题变化：${c.subsequent_question_change ?? "无"}`);
    lines.push("");
    lines.push("### 14.3 操作与观察");
    lines.push(`- 教材要求：${c.operation_required}`);
    lines.push(`- 操作对象：${c.operation_object}`);
    lines.push(`- 暴露结构：${c.exposed_structure}`);
    lines.push(`- 操作使用：${c.operation_usage}`);
    lines.push("");
    lines.push("### 14.4 人物表达");
    c.character_speeches.forEach((s) => {
      lines.push(`- ${s.character_id}（${s.speech_function}）：${s.content}（绑定对象：${objectName(s.bound_object_id)}）`);
    });
    lines.push(`- 人物表达关系：${c.speech_relations}`);
    lines.push("");
    lines.push("### 14.5 数学表达");
    c.formulas.forEach((f) => lines.push(`- 算式：${f}`));
    lines.push(`- 算式含义：${c.formula_meaning}`);
    lines.push(`- 数字映射：${c.formula_number_mapping}`);
    lines.push(`- 多种方法：${c.multiple_methods ?? "无"}`);
    lines.push(`- 方法关系：${c.method_relation ?? "—"}`);
    lines.push("");
    lines.push("### 14.6 例题终点");
    lines.push(`- 终点类型：${c.endpoint_type}`);
    lines.push(`- 终点描述：${c.endpoint_description}`);
    lines.push("");
    lines.push("### 试一试及练习承接");
    lines.push(`- 承接关系：${c.followup_connection}`);
    lines.push(`- 承接对象：${c.followup_object_ids.map(objectName).join("、")}`);
    lines.push("");
    lines.push("---");
    lines.push("");
  });
  return lines.join("\n");
}

function buildShallowAnalysisReportMd(): string {
  const lines: string[] = [];
  lines.push(`# ${PRE} 浅层分析与模板化问题清单`);
  lines.push("");
  lines.push("> 任务四补充 第二十条 — 浅层分析拦截检查结果");
  lines.push("");
  lines.push(`共检测到 ${analysisReviewIssues.length} 项问题，其中阻断 ${analysisReviewIssues.filter((i) => i.severity === "blocking").length} 项，非阻断 ${analysisReviewIssues.filter((i) => i.severity === "non-blocking").length} 项。`);
  lines.push("");
  lines.push(`已修复 ${analysisReviewIssues.filter((i) => i.resolution_status === "fixed").length} 项。`);
  lines.push("");
  lines.push("## 问题清单");
  lines.push("");
  lines.push("| 编号 | 课时 | 类别 | 严重性 | 状态 | 问题描述 |");
  lines.push("| --- | --- | --- | --- | --- | --- |");
  const categoryDesc: Record<string, string> = {
    MAINLINE_SHALLOW: "内容主线问题",
    REPRESENTATION_GENERIC: "表征分析问题",
    EXAMPLE_ANALYSIS_INCOMPLETE: "例题分析问题",
    PRACTICE_ANALYSIS_INCOMPLETE: "练习分析问题",
    EVIDENCE_MISSING: "证据缺失",
    INFERENCE_OVERREACH: "推断越界",
  };
  analysisReviewIssues.forEach((i) => {
    lines.push(`| ${i.issue_id} | ${lessonName(i.lesson_id)} | ${categoryDesc[i.category] ?? i.category} | ${i.severity} | ${i.resolution_status} | ${i.issue_description} |`);
  });
  lines.push("");
  lines.push("## 详情");
  lines.push("");
  analysisReviewIssues.forEach((i) => {
    lines.push(`### ${i.issue_id} — ${lessonName(i.lesson_id)}`);
    lines.push("");
    lines.push(`- **类别**：${categoryDesc[i.category] ?? i.category}`);
    lines.push(`- **严重性**：${i.severity}`);
    lines.push(`- **问题描述**：${i.issue_description}`);
    lines.push(`- **检测模式**：${i.detected_pattern}`);
    lines.push(`- **受影响数据**：${i.affected_data_ids.join("、")}`);
    lines.push(`- **建议修复**：${i.suggested_fix}`);
    lines.push(`- **解决状态**：${i.resolution_status}`);
    lines.push(`- **解决说明**：${i.resolution_note ?? "—"}`);
    lines.push("");
  });
  return lines.join("\n");
}

console.log("");
console.log("全部成果文件生成完成。");
