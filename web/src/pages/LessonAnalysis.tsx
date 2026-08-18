import { useState, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import {
  officialLessons,
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
  // 任务四补充新增数据（黄金课时深度分析）
  lessonMainlines,
  lessonMainlineNodes,
  lessonMainlineTransitions,
  lessonMainlineEvidence,
  lessonMainlineAlternatives,
  exampleAnalysisChains,
  representationFunctionRecords,
  analysisReviewIssues,
  // 扩展课时深度分析数据（按单元分组，按需生成）
  lessonMainlinesExtraU1BU2U2B,
  lessonMainlineNodesExtraU1BU2U2B,
  lessonMainlineTransitionsExtraU1BU2U2B,
  lessonMainlineEvidenceExtraU1BU2U2B,
  lessonMainlineAlternativesExtraU1BU2U2B,
  analysisReviewIssuesExtraU1BU2U2B,
  lessonMainlinesExtraU3U3BU4,
  lessonMainlineNodesExtraU3U3BU4,
  lessonMainlineTransitionsExtraU3U3BU4,
  lessonMainlineEvidenceExtraU3U3BU4,
  lessonMainlineAlternativesExtraU3U3BU4,
  analysisReviewIssuesExtraU3U3BU4,
} from "@/data";
import type {
  ActionType,
  RepresentationType,
  ProblemRelationType,
  ClaimSourceType,
  RepresentationFunction,
  TransformationAction,
  MainlineChangeType,
  GuideSupportStatus,
  ProblemSequenceRole,
  AnalysisReviewIssueCategory,
  LessonMainline,
  LessonMainlineNode,
  LessonMainlineTransition,
  LessonMainlineEvidence,
  LessonMainlineAlternative,
  AnalysisReviewIssue,
} from "@/data/types";
import {
  Network,
  BookOpen,
  Layers,
  GitBranch,
  Target,
  ScrollText,
  AlertTriangle,
  Eye,
  EyeOff,
  ArrowLeft,
  CheckCircle2,
  Share2,
  GitCommit,
  Flag,
} from "lucide-react";

// 受控词表中文映射
const actionTypeCN: Record<ActionType, string> = {
  OBSERVE: "观察", OPERATE: "操作", COUNT: "数数", COMPARE: "比较", CLASSIFY: "分类",
  CALCULATE: "计算", FILL_IN: "填写", DRAW: "画图", EXPRESS: "表达", EXPLAIN: "解释",
  CHOOSE: "选择", ESTIMATE: "估计", DISCOVER: "发现", VERIFY: "验证", GENERALIZE: "概括",
  APPLY: "应用", SOLVE_PROBLEM: "解决问题", REFLECT: "反思",
};

const representationCN: Record<RepresentationType, string> = {
  REAL_OBJECT: "实物", REAL_CONTEXT: "现实情境", PICTURE: "情境图",
  OPERATION_DIAGRAM: "操作图", GEOMETRIC_DIAGRAM: "几何图", NUMBER_LINE: "数轴",
  TABLE: "表格", VERTICAL_FORM: "竖式", HORIZONTAL_EXPRESSION: "横式",
  MATHEMATICAL_EXPRESSION: "算式", VERBAL_EXPRESSION: "语言表达",
  SYMBOLIC_EXPRESSION: "符号表达", CHARACTER_SPEECH: "人物表达",
};

const problemRelationCN: Record<ProblemRelationType, string> = {
  SAME_LESSON: "同课时", SAME_SECTION: "同栏目", FOLLOWS: "位于其后", PRECEDES: "位于其前",
  SHARED_STEM: "共用题干", SHARED_CONTEXT: "共用情境", SHARED_IMAGE: "共用图片",
  SHARED_TABLE: "共用表格", SUBPROBLEM_OF: "属其小题", CONTINUES: "跨页延续",
  DIRECTLY_CORRESPONDS_TO: "直接对应", PRACTICES_SAME_STRUCTURE: "练习相同结构",
  CHANGES_DATA_FROM: "改变数据", CHANGES_CONTEXT_FROM: "改变情境",
  CHANGES_REPRESENTATION_FROM: "改变表征", CHANGES_QUESTION_FROM: "改变问题",
  REVERSES_RELATION_FROM: "转换关系方向", REMOVES_EXPLICIT_SUPPORT_FROM: "减少显性支撑",
  ADDS_CONDITION_TO: "增加条件", COMBINES_ELEMENTS_FROM: "综合多个前置要素",
  APPLIES_IN_NEW_CONTEXT: "用于新情境",
};

const claimSourceCN: Record<ClaimSourceType, string> = {
  TEXTBOOK_FACT: "教材事实",
  TEACHER_GUIDE_EXPLICIT: "教师用书明确",
  OTHER_AUTHORITY_EXPLICIT: "其他权威",
  SYSTEM_STRUCTURAL_INFERENCE: "系统推断",
  HUMAN_REVIEWED_INFERENCE: "人工审核推断",
};

const claimSourceTone: Record<ClaimSourceType, "default" | "teal" | "vermilion" | "gold" | "ink"> = {
  TEXTBOOK_FACT: "default",
  TEACHER_GUIDE_EXPLICIT: "teal",
  OTHER_AUTHORITY_EXPLICIT: "gold",
  SYSTEM_STRUCTURAL_INFERENCE: "vermilion",
  HUMAN_REVIEWED_INFERENCE: "ink",
};

// 任务四补充：受控词表中文映射
const representationFunctionCN: Record<RepresentationFunction, string> = {
  PROVIDES_INFORMATION: "提供条件",
  FOCUSES_STRUCTURE: "突出结构",
  SUPPORTS_COUNTING: "支持计数",
  SHOWS_GROUPING: "呈现分组",
  SHOWS_CORRESPONDENCE: "呈现对应",
  SHOWS_CHANGE: "呈现变化",
  MAKES_RELATION_VISIBLE: "使数量关系可见",
  RECORDS_PROCESS: "记录过程",
  SUPPORTS_CALCULATION: "支持计算",
  ABSTRACTS_RELATION: "抽象数学关系",
  VERIFIES_RESULT: "验证结果",
  COMMUNICATES_REASONING: "表达思考",
  ORGANIZES_INFORMATION: "组织信息",
  REDUCES_CONTEXT_DETAIL: "减少情境细节",
};

const transformationActionCN: Record<TransformationAction, string> = {
  ABSTRACT: "抽象",
  TRANSLATE: "翻译",
  REPRESENT: "表征",
  DECOMPOSE: "分解",
  COMPOSE: "组合",
  TRANSFORM: "转换",
  RECODE: "重新编码",
};

const mainlineChangeCN: Record<MainlineChangeType, string> = {
  MATHEMATICAL_OBJECT_CHANGE: "数学对象变化",
  QUESTION_CHANGE: "问题变化",
  TASK_CHANGE: "任务变化",
  REPRESENTATION_CHANGE: "表征变化",
  SUPPORT_CHANGE: "支撑变化",
  CONTEXT_CHANGE: "情境变化",
  RESPONSE_REQUIREMENT_CHANGE: "应答要求变化",
};

const guideSupportCN: Record<GuideSupportStatus, string> = {
  SUPPORTED_BY_GUIDE: "教师用书明确支持",
  PARTIALLY_SUPPORTED_BY_GUIDE: "教师用书部分支持",
  NOT_MENTIONED_IN_GUIDE: "教师用书未提及",
  CONFLICTS_WITH_GUIDE: "与教师用书冲突",
};

const guideSupportTone: Record<GuideSupportStatus, "ok" | "teal" | "warn" | "err"> = {
  SUPPORTED_BY_GUIDE: "ok",
  PARTIALLY_SUPPORTED_BY_GUIDE: "teal",
  NOT_MENTIONED_IN_GUIDE: "warn",
  CONFLICTS_WITH_GUIDE: "err",
};

const problemSequenceRoleCN: Record<ProblemSequenceRole, string> = {
  FIRST_DIRECT_APPLICATION: "首次直接运用",
  SAME_STRUCTURE_REPETITION: "同结构重复",
  DATA_VARIATION: "数据变化",
  CONTEXT_VARIATION: "情境变化",
  REPRESENTATION_VARIATION: "表征变化",
  QUESTION_VARIATION: "问题变化",
  RELATION_DIRECTION_VARIATION: "关系方向变化",
  SUPPORT_REDUCTION: "显性支撑减少",
  MULTI_ELEMENT_COMBINATION: "综合多个前置要素",
  NEW_CONTEXT_APPLICATION: "新情境应用",
};

const reviewIssueCategoryCN: Record<AnalysisReviewIssueCategory, string> = {
  MAINLINE_SHALLOW: "内容主线浅层",
  REPRESENTATION_GENERIC: "表征分析通用",
  EXAMPLE_ANALYSIS_INCOMPLETE: "例题分析不完整",
  PRACTICE_ANALYSIS_INCOMPLETE: "练习分析不完整",
  EVIDENCE_MISSING: "证据缺失",
  INFERENCE_OVERREACH: "推断越界",
};

const reviewIssueCategoryTone: Record<AnalysisReviewIssueCategory, "warn" | "err" | "vermilion" | "gold"> = {
  MAINLINE_SHALLOW: "err",
  REPRESENTATION_GENERIC: "warn",
  EXAMPLE_ANALYSIS_INCOMPLETE: "vermilion",
  PRACTICE_ANALYSIS_INCOMPLETE: "vermilion",
  EVIDENCE_MISSING: "warn",
  INFERENCE_OVERREACH: "gold",
};

const exampleEndpointCN: Record<string, string> = {
  textbook_conclusion: "教材直接给出结论",
  character_method: "人物表达方法",
  fill_in_completion: "通过填空完成表达",
  concrete_instance: "只呈现具体实例",
  student_generalization: "要求学生自行概括",
};

export default function LessonAnalysisPage() {
  // 合并第一单元（黄金课时）与第二至第九单元（扩展课时）数据
  const allLessonAnalyses = useMemo(() => [...lessonAnalyses, ...lessonAnalysesExtra], []);
  const allObjects = useMemo(() => [...objects, ...objectsExtra], []);
  const allSequences = useMemo(() => [...lessonContentSequences, ...lessonContentSequencesExtra], []);
  const allRelations = useMemo(() => [...lessonContentRelations, ...lessonContentRelationsExtra], []);
  const allTasks = useMemo(() => [...lessonLearningTasks, ...lessonLearningTasksExtra], []);
  const allRepRelations = useMemo(() => [...representationRelations, ...representationRelationsExtra], []);
  const allProbRelations = useMemo(() => [...problemRelations, ...problemRelationsExtra], []);
  const allRetained = useMemo(() => [...problemRetainedDimensions, ...problemRetainedDimensionsExtra], []);
  const allChanged = useMemo(() => [...problemChangedDimensions, ...problemChangedDimensionsExtra], []);
  const allReqChanges = useMemo(() => [...problemRequirementChanges, ...problemRequirementChangesExtra], []);
  const allKeyNodes = useMemo(() => [...lessonKeyNodes, ...lessonKeyNodesExtra], []);
  const allClaims = useMemo(() => [...evidenceBackedClaims, ...evidenceBackedClaimsExtra], []);

  // 显示有分析数据的全部课时（全册53课时）
  const analyzedLessonIds = useMemo(
    () => new Set(allLessonAnalyses.map((a) => a.lesson_id)),
    [allLessonAnalyses],
  );
  const analyzedLessons = officialLessons.filter((l) => analyzedLessonIds.has(l.lesson_id));

  // 按单元分组（lesson_id 形如 ol-1-1 / ol-1b-1 / ol-2-1，取前两段作为单元键）
  const groupedLessons = useMemo(() => {
    const groups: { unitKey: string; unitLabel: string; lessons: typeof analyzedLessons }[] = [];
    const unitLabels: Record<string, string> = {
      "ol-1": "单元一 混合运算与数量关系（一）",
      "ol-1b": "综合实践·一天的时间",
      "ol-2": "单元二 两、三位数乘一位数",
      "ol-2b": "综合实践·曹冲称象的故事",
      "ol-3": "单元三 数据的收集与整理",
      "ol-3b": "综合实践·了解你的好朋友",
      "ol-4": "单元四 毫米、分米和千米",
      "ol-5": "单元五 平移、旋转和轴对称",
      "ol-6": "单元六 两、三位数除以一位数",
      "ol-6b": "探索规律·间隔排列",
      "ol-7": "单元七 数量关系的分析（一）",
      "ol-8": "单元八 观察物体（二）",
      "ol-9": "单元九 期末复习",
    };
    analyzedLessons.forEach((l) => {
      const parts = l.lesson_id.split("-");
      const unitKey = parts.slice(0, 2).join("-"); // ol-1 / ol-1b / ol-2 ...
      let group = groups.find((g) => g.unitKey === unitKey);
      if (!group) {
        group = { unitKey, unitLabel: unitLabels[unitKey] ?? unitKey, lessons: [] };
        groups.push(group);
      }
      group.lessons.push(l);
    });
    return groups;
  }, [analyzedLessons]);

  const [selectedLessonId, setSelectedLessonId] = useState<string>(analyzedLessons[0]?.lesson_id ?? "");
  const [reviewMode, setReviewMode] = useState(false);
  const [activeTab, setActiveTab] = useState<"mainline" | "representation" | "practice" | "evidence">("mainline");

  const selectedLesson = officialLessons.find((l) => l.lesson_id === selectedLessonId);
  const analysis = allLessonAnalyses.find((a) => a.lesson_id === selectedLessonId);

  const sequences = allSequences.filter((s) => s.lesson_id === selectedLessonId);
  const relations = allRelations.filter((r) => r.lesson_id === selectedLessonId);
  const tasks = allTasks.filter((t) => t.lesson_id === selectedLessonId);
  const repRelations = allRepRelations.filter((r) => r.lesson_id === selectedLessonId);
  const probRelations = allProbRelations.filter((r) => r.lesson_id === selectedLessonId);
  const keyNodes = allKeyNodes.filter((k) => k.lesson_id === selectedLessonId);
  const claims = allClaims.filter((c) => c.lesson_id === selectedLessonId);
  const upstreamIssues = upstreamCorrectionRequests;

  // 任务四补充：深度分析数据（黄金课时 + 扩展课时合并）
  const allMainlines = useMemo(() => [
    ...lessonMainlines,
    ...lessonMainlinesExtraU1BU2U2B,
    ...lessonMainlinesExtraU3U3BU4,
  ], []);
  const allMainlineNodes = useMemo(() => [
    ...lessonMainlineNodes,
    ...lessonMainlineNodesExtraU1BU2U2B,
    ...lessonMainlineNodesExtraU3U3BU4,
  ], []);
  const allMainlineTransitions = useMemo(() => [
    ...lessonMainlineTransitions,
    ...lessonMainlineTransitionsExtraU1BU2U2B,
    ...lessonMainlineTransitionsExtraU3U3BU4,
  ], []);
  const allMainlineEvidence = useMemo(() => [
    ...lessonMainlineEvidence,
    ...lessonMainlineEvidenceExtraU1BU2U2B,
    ...lessonMainlineEvidenceExtraU3U3BU4,
  ], []);
  const allMainlineAlternatives = useMemo(() => [
    ...lessonMainlineAlternatives,
    ...lessonMainlineAlternativesExtraU1BU2U2B,
    ...lessonMainlineAlternativesExtraU3U3BU4,
  ], []);
  const allReviewIssues = useMemo(() => [
    ...analysisReviewIssues,
    ...analysisReviewIssuesExtraU1BU2U2B,
    ...analysisReviewIssuesExtraU3U3BU4,
  ], []);

  // ===== 运行时生成数据的内存态（AI 生成后直接显示，无需刷新） =====
  const [runtimeMainlines, setRuntimeMainlines] = useState<LessonMainline[]>([]);
  const [runtimeNodes, setRuntimeNodes] = useState<LessonMainlineNode[]>([]);
  const [runtimeTransitions, setRuntimeTransitions] = useState<LessonMainlineTransition[]>([]);
  const [runtimeEvidence, setRuntimeEvidence] = useState<LessonMainlineEvidence[]>([]);
  const [runtimeAlternatives, setRuntimeAlternatives] = useState<LessonMainlineAlternative[]>([]);
  const [runtimeReviewIssues, setRuntimeReviewIssues] = useState<AnalysisReviewIssue[]>([]);

  // 生成状态
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generatePrompt, setGeneratePrompt] = useState<string | null>(null);
  const [showPromptPanel, setShowPromptPanel] = useState(false);

  // 清理运行时数据（切换课时时）
  const clearRuntime = useCallback((lessonId: string) => {
    setRuntimeMainlines((prev) => prev.filter((m) => m.lesson_id !== lessonId));
    setRuntimeNodes((prev) => prev.filter((n) => n.lesson_id !== lessonId));
    setRuntimeTransitions((prev) => prev.filter((t) => t.lesson_id !== lessonId));
    setRuntimeEvidence((prev) => prev.filter((e) => e.lesson_id !== lessonId));
    setRuntimeAlternatives((prev) => prev.filter((a) => a.lesson_id !== lessonId));
    setRuntimeReviewIssues((prev) => prev.filter((i) => i.lesson_id !== lessonId));
  }, []);

  // 一键生成深度分析
  const handleGenerate = useCallback(async (lessonId: string) => {
    setGenerating(true);
    setGenerateError(null);
    setGeneratePrompt(null);
    setShowPromptPanel(false);

    try {
      const resp = await fetch("/api/generate-lesson-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lessonId }),
      });

      const result = await resp.json() as {
        success: boolean;
        lessonId: string;
        data?: {
          mainlines: LessonMainline[];
          nodes: LessonMainlineNode[];
          transitions: LessonMainlineTransition[];
          evidence: LessonMainlineEvidence[];
          alternatives: LessonMainlineAlternative[];
          reviewIssues: AnalysisReviewIssue[];
        };
        writtenFile?: string;
        prompt?: string;
        error?: string;
      };

      if (result.success && result.data) {
        // 生成成功：合并到运行时态
        clearRuntime(lessonId);
        setRuntimeMainlines((prev) => [...prev, ...result.data!.mainlines]);
        setRuntimeNodes((prev) => [...prev, ...result.data!.nodes]);
        setRuntimeTransitions((prev) => [...prev, ...result.data!.transitions]);
        setRuntimeEvidence((prev) => [...prev, ...result.data!.evidence]);
        setRuntimeAlternatives((prev) => [...prev, ...result.data!.alternatives]);
        setRuntimeReviewIssues((prev) => [...prev, ...result.data!.reviewIssues]);
        setGenerateError(null);
      } else if (result.error === "NO_API_KEY" && result.prompt) {
        // 无 API key：显示 prompt 供用户手动处理
        setGeneratePrompt(result.prompt);
        setShowPromptPanel(true);
        setGenerateError("未配置 AI API Key（GEMINI_API_KEY 环境变量），已生成 prompt 供你复制发给 AI 助手。生成后将 JSON 粘贴到下方文本框即可显示。");
      } else {
        setGenerateError(result.error ?? "生成失败");
        if (result.prompt) {
          setGeneratePrompt(result.prompt);
          setShowPromptPanel(true);
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      setGenerateError(`网络请求失败: ${errMsg}。请确保开发服务器正在运行。`);
    } finally {
      setGenerating(false);
    }
  }, [clearRuntime]);

  // 粘贴 JSON 结果并解析
  const [pasteJsonText, setPasteJsonText] = useState("");
  const [pasteError, setPasteError] = useState<string | null>(null);

  const handlePasteResult = useCallback((lessonId: string) => {
    setPasteError(null);
    try {
      const parsed = JSON.parse(pasteJsonText) as {
        mainlines?: LessonMainline[];
        nodes?: LessonMainlineNode[];
        transitions?: LessonMainlineTransition[];
        evidence?: LessonMainlineEvidence[];
        alternatives?: LessonMainlineAlternative[];
        reviewIssues?: AnalysisReviewIssue[];
      };

      if (!parsed.mainlines || !Array.isArray(parsed.mainlines)) {
        setPasteError("JSON 缺少 mainlines 数组");
        return;
      }

      clearRuntime(lessonId);
      setRuntimeMainlines((prev) => [...prev, ...(parsed.mainlines ?? [])]);
      setRuntimeNodes((prev) => [...prev, ...(parsed.nodes ?? [])]);
      setRuntimeTransitions((prev) => [...prev, ...(parsed.transitions ?? [])]);
      setRuntimeEvidence((prev) => [...prev, ...(parsed.evidence ?? [])]);
      setRuntimeAlternatives((prev) => [...prev, ...(parsed.alternatives ?? [])]);
      setRuntimeReviewIssues((prev) => [...prev, ...(parsed.reviewIssues ?? [])]);
      setPasteJsonText("");
      setShowPromptPanel(false);
      setGenerateError(null);
    } catch {
      setPasteError("无法解析 JSON，请检查格式");
    }
  }, [clearRuntime, pasteJsonText]);

  // 合并静态数据 + 运行时数据
  const combinedMainlines = useMemo(() => [...allMainlines, ...runtimeMainlines], [allMainlines, runtimeMainlines]);
  const combinedNodes = useMemo(() => [...allMainlineNodes, ...runtimeNodes], [allMainlineNodes, runtimeNodes]);
  const combinedTransitions = useMemo(() => [...allMainlineTransitions, ...runtimeTransitions], [allMainlineTransitions, runtimeTransitions]);
  const combinedEvidence = useMemo(() => [...allMainlineEvidence, ...runtimeEvidence], [allMainlineEvidence, runtimeEvidence]);
  const combinedAlternatives = useMemo(() => [...allMainlineAlternatives, ...runtimeAlternatives], [allMainlineAlternatives, runtimeAlternatives]);
  const combinedReviewIssues = useMemo(() => [...allReviewIssues, ...runtimeReviewIssues], [allReviewIssues, runtimeReviewIssues]);

  const mainline = combinedMainlines.find((m) => m.lesson_id === selectedLessonId);
  const mainlineNodes = combinedNodes
    .filter((n) => n.lesson_id === selectedLessonId)
    .sort((a, b) => a.sequence_index - b.sequence_index);
  const mainlineTransitions = combinedTransitions.filter((t) => t.lesson_id === selectedLessonId);
  const mainlineEvidence = combinedEvidence.filter((e) => e.lesson_id === selectedLessonId);
  const mainlineAlternatives = combinedAlternatives.filter((a) => a.lesson_id === selectedLessonId);
  const exampleChains = exampleAnalysisChains.filter((c) => c.lesson_id === selectedLessonId);
  const repFunctionRecords = representationFunctionRecords.filter((r) => r.lesson_id === selectedLessonId);
  const reviewIssues = combinedReviewIssues.filter((i) => i.lesson_id === selectedLessonId);
  const hasDeepAnalysis = !!mainline;
  const isGoldenLesson = !!mainline;

  const objectName = (oid: string) => {
    const obj = allObjects.find((o) => o.id === oid);
    return obj?.title ?? oid;
  };
  const tbRefExcerpt = (rid: string) => {
    const ref = teacherBookReferences.find((r) => r.id === rid);
    return ref?.excerpt ?? null;
  };

  return (
    <div className="animate-ink-rise">
      <Link
        to="/official-lessons"
        className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-vermilion mb-4"
      >
        <ArrowLeft size={12} /> 返回正式课时目录
      </Link>

      <PageHeader
        no={4}
        eyebrow="TASK · 课时内部教材内容关系与练习结构分析"
        title="课时教材分析"
        subtitle="在正式课时边界和完整教材对象基础上，建立可检索、可核验、可回溯的课时内部教材内容关系与练习结构数据。覆盖全册53个正式课时（第一单元5黄金课时 + 第二至第九单元48扩展课时）。"
        right={
          <div className="flex items-center gap-2">
            <Badge tone="teal">分析版本 {analysisVersion.version_id}</Badge>
            <Badge tone={analysisVersion.status === "frozen" ? "ok" : "warn"}>
              {analysisVersion.status === "frozen" ? "已冻结" : "草稿"}
            </Badge>
            <button
              onClick={() => setReviewMode((v) => !v)}
              className={cn(
                "inline-flex items-center gap-1 px-3 py-1.5 text-xs rounded-sm border transition-colors",
                reviewMode
                  ? "bg-vermilion text-paper border-vermilion"
                  : "bg-paper text-ink-2 border-ink-line hover:border-vermilion",
              )}
            >
              {reviewMode ? <Eye size={12} /> : <EyeOff size={12} />}
              {reviewMode ? "审核模式" : "普通模式"}
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr_360px] gap-6">
        {/* 左：课时列表（按单元分组） */}
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3 flex items-center gap-2">
            <BookOpen size={16} className="text-vermilion" /> 课时目录
            <Badge tone="default">{analyzedLessons.length} 课时</Badge>
          </h2>
          <div className="space-y-4 max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
            {groupedLessons.map((group) => (
              <div key={group.unitKey}>
                <div className="text-2xs font-medium text-ink-4 uppercase tracking-wider mb-1.5 px-1 sticky top-0 bg-paper">
                  {group.unitLabel}
                </div>
                <div className="space-y-1">
                  {group.lessons.map((l) => {
                    const isActive = l.lesson_id === selectedLessonId;
                    const isGolden = lessonAnalyses.some((a) => a.lesson_id === l.lesson_id);
                    return (
                      <button
                        key={l.lesson_id}
                        onClick={() => setSelectedLessonId(l.lesson_id)}
                        className={cn(
                          "w-full text-left px-3 py-2 rounded-sm border transition-all",
                          isActive
                            ? "border-vermilion bg-vermilion-tint/50"
                            : "border-ink-line bg-paper hover:border-ink-line-2 hover:bg-paper-2",
                        )}
                      >
                        <div className="flex items-center gap-1.5">
                          <div className="text-2xs font-mono text-ink-4">{l.lesson_id}</div>
                          {isGolden && (
                            <span className="text-2xs text-gold font-medium" title="黄金课时（深度分析）">★</span>
                          )}
                        </div>
                        <div className="text-sm text-ink-2 leading-snug mt-0.5">{l.official_lesson_name}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* 前序回流问题 */}
          {upstreamIssues.length > 0 && (
            <div className="mt-6">
              <h3 className="font-serif text-sm font-bold text-ink mb-2 flex items-center gap-1.5">
                <AlertTriangle size={14} className="text-warn" /> 前序数据回流
              </h3>
              <div className="space-y-1.5">
                {upstreamIssues.map((issue) => (
                  <div key={issue.id} className="px-3 py-2 bg-warn-soft/30 border border-warn/30 rounded-sm">
                    <div className="text-2xs font-mono text-warn">{issue.id}</div>
                    <p className="text-xs text-ink-2 mt-1 leading-relaxed">{issue.issue_description}</p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <Badge tone={issue.blocking_status === "blocking" ? "err" : "warn"}>
                        {issue.blocking_status === "blocking" ? "阻断" : "非阻断"}
                      </Badge>
                      <Badge tone="default">目标：{issue.target_task}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 中：教材内容主体 */}
        <div>
          {selectedLesson && (
            <>
              <h2 className="font-serif text-base font-bold text-ink mb-3 flex items-center gap-2">
                <Layers size={16} className="text-vermilion" /> 教材内容顺序
                <Badge tone="default">{sequences.length} 个对象</Badge>
              </h2>

              {/* 内容顺序流 */}
              <div className="space-y-2 mb-6">
                {sequences.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-start gap-3 px-4 py-3 bg-paper border border-ink-line rounded-sm"
                  >
                    <div className="shrink-0 w-7 h-7 rounded-full bg-vermilion text-paper flex items-center justify-center text-xs font-mono font-bold">
                      {s.sequence_index}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-ink font-medium leading-snug">
                        {objectName(s.object_id)}
                      </div>
                      <div className="text-xs text-ink-3 mt-1 leading-relaxed">{s.object_role}</div>
                      {reviewMode && (
                        <div className="mt-1.5 text-2xs text-ink-4 font-mono">
                          {s.object_id} · 依据：{s.sequence_basis}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* 对象直接关系 */}
              {reviewMode && relations.length > 0 && (
                <Card title="教材对象直接关系" accent="teal" bodyClassName="p-3">
                  <div className="space-y-1.5">
                    {relations.map((r) => (
                      <div key={r.id} className="flex items-center gap-2 text-xs px-2 py-1.5 bg-paper-2 rounded-sm">
                        <code className="text-2xs text-ink-4 font-mono shrink-0">{r.src_object_id}</code>
                        <span className="text-vermilion-deep font-medium shrink-0">{r.relation_type}</span>
                        <span className="text-ink-3">→</span>
                        <code className="text-2xs text-ink-4 font-mono shrink-0">{r.dst_object_id ?? "—"}</code>
                        <span className="text-ink-2 flex-1 truncate">{r.evidence_note}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* 学习任务 */}
              {reviewMode && tasks.length > 0 && (
                <Card title="学习任务" accent="gold" bodyClassName="p-3" className="mt-4">
                  <div className="space-y-1.5">
                    {tasks.map((t) => (
                      <div key={t.id} className="flex items-center gap-2 text-xs px-2 py-1.5 bg-paper-2 rounded-sm">
                        <Badge tone="teal">{actionTypeCN[t.action_type]}</Badge>
                        <span className="text-ink-2 flex-1 truncate">{t.expected_output_type}</span>
                        {t.evidence_id && (
                          <code className="text-2xs text-ink-4 font-mono">{t.evidence_id}</code>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
        </div>

        {/* 右：分析侧栏 */}
        <div>
          {analysis && (
            <>
              {/* 侧栏 Tab */}
              <div className="flex gap-1 mb-3 p-1 bg-paper-2 rounded-sm border border-ink-line">
                {([
                  { key: "mainline", label: "内容主线", icon: <Network size={12} /> },
                  { key: "representation", label: "表征", icon: <GitBranch size={12} /> },
                  { key: "practice", label: "例题练习", icon: <Target size={12} /> },
                  { key: "evidence", label: "证据", icon: <ScrollText size={12} /> },
                ] as const).map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={cn(
                      "flex-1 inline-flex items-center justify-center gap-1 px-2 py-1.5 text-xs rounded-sm transition-colors",
                      activeTab === tab.key
                        ? "bg-ink text-paper font-medium"
                        : "text-ink-3 hover:text-ink",
                    )}
                  >
                    {tab.icon} {tab.label}
                  </button>
                ))}
              </div>

              {/* 内容主线 */}
              {activeTab === "mainline" && (
                <div className="space-y-3">
                  {/* 黄金课时：主线基本信息 + 节点链 */}
                  {isGoldenLesson && mainline && (
                    <>
                      <Card title="本课内容主线" accent="vermilion" bodyClassName="p-4">
                        <div className="space-y-2">
                          <div>
                            <div className="text-2xs text-ink-4 font-medium uppercase tracking-wider">核心数学对象</div>
                            <div className="text-sm text-ink font-medium mt-0.5">{mainline.main_mathematical_object}</div>
                          </div>
                          <div className="grid grid-cols-1 gap-2 mt-2">
                            <div className="px-2.5 py-1.5 bg-paper-2 rounded-sm border-l-2 border-ink-3">
                              <div className="text-2xs text-ink-4">起始状态</div>
                              <div className="text-xs text-ink-2 mt-0.5 leading-relaxed">{mainline.initial_object_state}</div>
                            </div>
                            <div className="px-2.5 py-1.5 bg-vermilion-tint/40 rounded-sm border-l-2 border-vermilion">
                              <div className="text-2xs text-vermilion-deep">发展状态</div>
                              <div className="text-xs text-ink-2 mt-0.5 leading-relaxed">{mainline.developed_object_state}</div>
                            </div>
                          </div>
                          <p className="text-xs text-ink-2 leading-relaxed mt-2">{mainline.mainline_summary}</p>
                          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                            <Badge tone={guideSupportTone[mainline.guide_support_status]}>
                              {guideSupportCN[mainline.guide_support_status]}
                            </Badge>
                            <Badge tone={claimSourceTone[mainline.source_type]}>
                              {claimSourceCN[mainline.source_type]}
                            </Badge>
                            {reviewMode && (
                              <code className="text-2xs text-ink-4 font-mono">{mainline.mainline_id}</code>
                            )}
                          </div>
                        </div>
                      </Card>

                      {/* 主线节点链 */}
                      <Card
                        title="主线节点链"
                        subtitle={`${mainlineNodes.length} 节点 / ${mainlineTransitions.length} 转换`}
                        accent="gold"
                        bodyClassName="p-3"
                      >
                        <div className="space-y-1.5">
                          {mainlineNodes.map((node) => {
                            const transition = mainlineTransitions.find((t) => t.from_node_id === node.mainline_node_id);
                            return (
                              <div key={node.mainline_node_id}>
                                <div className="px-3 py-2 bg-paper-2 rounded-sm border-l-2 border-gold">
                                  <div className="flex items-center gap-2">
                                    <div className="shrink-0 w-5 h-5 rounded-full bg-gold text-ink flex items-center justify-center text-2xs font-mono font-bold">
                                      {node.sequence_index}
                                    </div>
                                    <div className="text-sm text-ink font-medium flex-1">{node.node_title}</div>
                                    {reviewMode && (
                                      <code className="text-2xs text-ink-4 font-mono">{node.mainline_node_id}</code>
                                    )}
                                  </div>
                                  <p className="text-xs text-ink-3 mt-1.5 leading-relaxed pl-7">{node.node_description}</p>
                                  <div className="mt-1.5 pl-7 space-y-0.5">
                                    <div className="text-2xs text-ink-4">
                                      <span className="text-ink-3 font-medium">数学对象：</span>{node.mathematical_object_state}
                                    </div>
                                    <div className="text-2xs text-ink-4">
                                      <span className="text-ink-3 font-medium">问题：</span>{node.question_state}
                                    </div>
                                    <div className="text-2xs text-ink-4">
                                      <span className="text-ink-3 font-medium">任务：</span>{node.task_state}
                                    </div>
                                    <div className="text-2xs text-ink-4">
                                      <span className="text-ink-3 font-medium">表征：</span>{node.representation_state}
                                    </div>
                                  </div>
                                  {node.main_object_ids.length > 0 && (
                                    <div className="mt-1.5 pl-7 flex flex-wrap gap-1">
                                      {node.main_object_ids.map((oid) => (
                                        <span key={oid} className="text-2xs px-1.5 py-0.5 bg-teal-tint/60 text-teal-2 rounded-sm">
                                          {objectName(oid)}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                                {/* 节点之间的转换 */}
                                {transition && (
                                  <div className="ml-4 my-1 px-3 py-1.5 bg-vermilion-tint/30 rounded-sm border-l-2 border-vermilion">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      <GitCommit size={11} className="text-vermilion shrink-0" />
                                      {transition.change_types.map((ct) => (
                                        <Badge key={ct} tone="vermilion">{mainlineChangeCN[ct]}</Badge>
                                      ))}
                                    </div>
                                    <div className="mt-1 space-y-0.5">
                                      {transition.mathematical_change && (
                                        <div className="text-2xs text-ink-3">
                                          <span className="text-vermilion-deep font-medium">数学：</span>{transition.mathematical_change}
                                        </div>
                                      )}
                                      {transition.question_change && (
                                        <div className="text-2xs text-ink-3">
                                          <span className="text-vermilion-deep font-medium">问题：</span>{transition.question_change}
                                        </div>
                                      )}
                                      {transition.task_change && (
                                        <div className="text-2xs text-ink-3">
                                          <span className="text-vermilion-deep font-medium">任务：</span>{transition.task_change}
                                        </div>
                                      )}
                                      {transition.representation_change && (
                                        <div className="text-2xs text-ink-3">
                                          <span className="text-vermilion-deep font-medium">表征：</span>{transition.representation_change}
                                        </div>
                                      )}
                                      {transition.support_change && (
                                        <div className="text-2xs text-ink-3">
                                          <span className="text-vermilion-deep font-medium">支撑：</span>{transition.support_change}
                                        </div>
                                      )}
                                      {transition.response_requirement_change && (
                                        <div className="text-2xs text-ink-3">
                                          <span className="text-vermilion-deep font-medium">应答：</span>{transition.response_requirement_change}
                                        </div>
                                      )}
                                    </div>
                                    {reviewMode && (
                                      <div className="mt-1 flex items-center gap-1.5">
                                        <Badge tone={guideSupportTone[transition.guide_support_status]}>
                                          {guideSupportCN[transition.guide_support_status]}
                                        </Badge>
                                        <code className="text-2xs text-ink-4 font-mono">{transition.transition_id}</code>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </Card>

                      {/* 备选主线（审核模式） */}
                      {reviewMode && mainlineAlternatives.length > 0 && (
                        <Card title="备选主线" subtitle={`${mainlineAlternatives.length} 条`} accent="none" className="border-l-2 border-l-ink" bodyClassName="p-3">
                          <div className="space-y-2">
                            {mainlineAlternatives.map((alt) => (
                              <div key={alt.alternative_mainline_id} className="px-3 py-2 bg-ink/5 rounded-sm border-l-2 border-ink-3">
                                <div className="flex items-center gap-1.5 mb-1">
                                  <Share2 size={11} className="text-ink-3" />
                                  <code className="text-2xs text-ink-4 font-mono">{alt.alternative_mainline_id}</code>
                                  <Badge tone="default">{alt.review_status}</Badge>
                                </div>
                                <p className="text-xs text-ink-2 leading-relaxed">{alt.alternative_description}</p>
                                <p className="text-2xs text-warn mt-1.5">
                                  <span className="font-medium">未选用原因：</span>{alt.reason_not_selected}
                                </p>
                                {alt.supporting_evidence_ids.length > 0 && (
                                  <div className="mt-1 flex flex-wrap gap-1">
                                    <span className="text-2xs text-ok font-medium">支持：</span>
                                    {alt.supporting_evidence_ids.map((eid) => (
                                      <code key={eid} className="text-2xs text-ok font-mono">{eid}</code>
                                    ))}
                                  </div>
                                )}
                                {alt.conflicting_evidence_ids.length > 0 && (
                                  <div className="mt-0.5 flex flex-wrap gap-1">
                                    <span className="text-2xs text-err font-medium">冲突：</span>
                                    {alt.conflicting_evidence_ids.map((eid) => (
                                      <code key={eid} className="text-2xs text-err font-mono">{eid}</code>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </Card>
                      )}

                      {/* 主线证据（审核模式） */}
                      {reviewMode && mainlineEvidence.length > 0 && (
                        <Card title="主线证据" subtitle={`${mainlineEvidence.length} 条`} accent="teal" bodyClassName="p-3">
                          <div className="space-y-1.5">
                            {mainlineEvidence.map((ev) => (
                              <div key={ev.mainline_evidence_id} className="px-2 py-1.5 bg-paper-2 rounded-sm">
                                <div className="flex items-center gap-1.5 mb-1">
                                  <Badge tone={claimSourceTone[ev.evidence_type]}>
                                    {claimSourceCN[ev.evidence_type]}
                                  </Badge>
                                  <Badge tone={guideSupportTone[ev.support_status]}>
                                    {guideSupportCN[ev.support_status]}
                                  </Badge>
                                </div>
                                <p className="text-2xs text-ink-2 leading-relaxed">{ev.evidence_description}</p>
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {ev.textbook_object_ids.map((oid) => (
                                    <code key={oid} className="text-2xs text-teal-2 font-mono">{oid}</code>
                                  ))}
                                  {ev.teacher_guide_evidence_ids.map((eid) => (
                                    <code key={eid} className="text-2xs text-ink-4 font-mono">{eid}</code>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </Card>
                      )}
                    </>
                  )}

                  {/* 扩展课时（无深度分析）：一键生成 + 回退面板 */}
                  {!isGoldenLesson && (
                    <Card title="教材内容主线" accent="vermilion" bodyClassName="p-4">
                      <p className="text-sm text-ink-2 leading-relaxed">{analysis.content_sequence_summary}</p>
                      <div className="mt-3 pt-3 border-t border-ink-line-2">
                        <div className="text-2xs text-ink-4 font-medium uppercase tracking-wider mb-1.5">
                          深度分析（主线+节点链+转换+备选+证据+浅层拦截）
                        </div>
                        <p className="text-xs text-ink-3 mb-2 leading-relaxed">
                          点击下方按钮直接生成深度分析。系统会自动读取教师用书和教材对象资源库，调用 AI 生成数据并显示在此处。
                        </p>

                        {/* 生成按钮 */}
                        <button
                          onClick={() => handleGenerate(selectedLessonId)}
                          disabled={generating}
                          className={cn(
                            "inline-flex items-center gap-1 px-3 py-1.5 text-xs rounded-sm transition-colors",
                            generating
                              ? "bg-ink-3 text-paper cursor-wait"
                              : "bg-vermilion text-paper hover:bg-vermilion-deep",
                          )}
                        >
                          {generating ? (
                            <>
                              <span className="inline-block h-3 w-3 border-2 border-paper/40 border-t-paper rounded-full animate-spin" />
                              正在生成中...
                            </>
                          ) : (
                            <>
                              <GitBranch size={12} /> 生成深度分析
                            </>
                          )}
                        </button>

                        {/* 生成成功提示 */}
                        {hasDeepAnalysis && !generating && !generateError && (
                          <div className="mt-2 px-3 py-1.5 bg-ok-soft text-ok text-xs rounded-sm border border-ok/30">
                            ✓ 深度分析已生成并显示在上方。{runtimeMainlines.some((m) => m.lesson_id === selectedLessonId) ? "（运行时数据，刷新页面后需重新生成或由开发者写入文件）" : ""}
                          </div>
                        )}

                        {/* 错误提示 */}
                        {generateError && (
                          <div className="mt-2 px-3 py-2 bg-warn-soft text-warn text-xs rounded-sm border border-warn/30 leading-relaxed">
                            ⚠ {generateError}
                          </div>
                        )}

                        {/* 回退面板：复制 prompt + 粘贴 JSON */}
                        {showPromptPanel && generatePrompt && (
                          <div className="mt-3 space-y-2 animate-ink-rise">
                            {/* Prompt 显示区 */}
                            <div>
                              <div className="text-2xs text-ink-3 font-medium mb-1">方法一：复制 prompt 发给 AI</div>
                              <div className="relative">
                                <pre className="text-2xs text-ink-2 bg-paper-2 border border-ink-line rounded-sm p-2.5 max-h-32 overflow-y-auto whitespace-pre-wrap break-all pr-20">
                                  {generatePrompt}
                                </pre>
                                <button
                                  onClick={() => {
                                    navigator.clipboard?.writeText(generatePrompt).then(
                                      () => alert("Prompt 已复制到剪贴板"),
                                      () => alert("剪贴板不可用，请手动选择文本复制"),
                                    );
                                  }}
                                  className="absolute top-1.5 right-1.5 px-2 py-0.5 text-2xs bg-vermilion text-paper rounded-sm hover:bg-vermilion-deep"
                                >
                                  复制
                                </button>
                              </div>
                            </div>

                            {/* JSON 粘贴区 */}
                            <div>
                              <div className="text-2xs text-ink-3 font-medium mb-1">方法二：将 AI 返回的 JSON 粘贴到下方</div>
                              <textarea
                                value={pasteJsonText}
                                onChange={(e) => setPasteJsonText(e.target.value)}
                                rows={6}
                                placeholder='粘贴 AI 返回的 JSON，格式：{"mainlines":[...],"nodes":[...],"transitions":[...],"evidence":[...],"alternatives":[...],"reviewIssues":[...]}'
                                className="w-full px-2.5 py-1.5 text-2xs font-mono bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion resize-none placeholder:text-ink-4"
                              />
                              {pasteError && (
                                <div className="mt-1 text-2xs text-err">{pasteError}</div>
                              )}
                              <div className="mt-1.5 flex gap-2">
                                <button
                                  onClick={() => handlePasteResult(selectedLessonId)}
                                  disabled={!pasteJsonText.trim()}
                                  className={cn(
                                    "inline-flex items-center gap-1 px-2.5 py-1 text-2xs rounded-sm transition-colors",
                                    pasteJsonText.trim()
                                      ? "bg-ok text-paper hover:bg-ok/90"
                                      : "bg-paper-3 text-ink-4 cursor-not-allowed",
                                  )}
                                >
                                  <CheckCircle2 size={11} /> 解析并显示
                                </button>
                                <button
                                  onClick={() => {
                                    setShowPromptPanel(false);
                                    setGenerateError(null);
                                    setPasteJsonText("");
                                    setPasteError(null);
                                  }}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2"
                                >
                                  关闭
                                </button>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </Card>
                  )}

                  {/* 关键教材节点（所有课时） */}
                  <Card title="关键教材节点" subtitle={`${keyNodes.length} 个`} accent="gold" bodyClassName="p-4">
                    <div className="space-y-2">
                      {keyNodes.map((k) => (
                        <div key={k.id} className="px-3 py-2 bg-paper-2 rounded-sm border-l-2 border-gold">
                          <div className="text-sm text-ink font-medium">{objectName(k.object_id)}</div>
                          <p className="text-xs text-ink-3 mt-1 leading-relaxed">{k.key_node_basis}</p>
                          {reviewMode && (
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {k.evidence_ids.map((eid) => (
                                <code key={eid} className="text-2xs text-ink-4 font-mono">{eid}</code>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </Card>
                  {!isGoldenLesson && (
                    <p className="text-xs text-ink-3 px-1">{analysis.key_nodes_summary}</p>
                  )}
                </div>
              )}

              {/* 表征联系 */}
              {activeTab === "representation" && (
                <div className="space-y-3">
                  <Card title="表征关系摘要" accent="teal" bodyClassName="p-4">
                    <p className="text-sm text-ink-2 leading-relaxed">{analysis.representation_summary}</p>
                  </Card>
                  {repRelations.map((r) => {
                    const hasDetailed = !!(r.shared_mathematical_meaning || r.retained_information || r.highlighted_information || r.omitted_information);
                    const funcRecords = repFunctionRecords.filter((fr) => fr.representation_relation_id === r.id);
                    return (
                      <Card key={r.id} bodyClassName="p-3" className="border-l-2 border-l-teal">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <Badge tone="teal">{representationCN[r.src_representation]}</Badge>
                          <span className="text-vermilion-deep text-xs font-medium">{r.relation_type}</span>
                          <span className="text-ink-3">→</span>
                          <Badge tone="teal">{representationCN[r.dst_representation]}</Badge>
                          {r.is_system_inference && <Badge tone="vermilion">推断</Badge>}
                          {r.transformation_action && (
                            <Badge tone="gold">{transformationActionCN[r.transformation_action]}</Badge>
                          )}
                          {r.representation_function && (
                            <Badge tone="ink">{representationFunctionCN[r.representation_function]}</Badge>
                          )}
                        </div>
                        <p className="text-xs text-ink-2 leading-relaxed">{r.mathematical_content}</p>

                        {/* 任务四补充：表征转换详细字段 */}
                        {hasDetailed && (
                          <div className="mt-2 space-y-1.5 px-2.5 py-2 bg-teal-tint/20 rounded-sm">
                            {r.shared_mathematical_meaning && (
                              <div className="text-2xs">
                                <span className="text-teal-2 font-medium">共同数学含义：</span>
                                <span className="text-ink-2">{r.shared_mathematical_meaning}</span>
                              </div>
                            )}
                            {r.retained_information && (
                              <div className="text-2xs">
                                <span className="text-ok font-medium">保持信息：</span>
                                <span className="text-ink-2">{r.retained_information}</span>
                              </div>
                            )}
                            {r.highlighted_information && (
                              <div className="text-2xs">
                                <span className="text-vermilion-deep font-medium">突出信息：</span>
                                <span className="text-ink-2">{r.highlighted_information}</span>
                              </div>
                            )}
                            {r.omitted_information && (
                              <div className="text-2xs">
                                <span className="text-warn font-medium">省略信息：</span>
                                <span className="text-ink-2">{r.omitted_information}</span>
                              </div>
                            )}
                            {r.newly_added_information && (
                              <div className="text-2xs">
                                <span className="text-gold font-medium">新增信息：</span>
                                <span className="text-ink-2">{r.newly_added_information}</span>
                              </div>
                            )}
                            {r.mainline_role && (
                              <div className="text-2xs">
                                <span className="text-ink-3 font-medium">主线作用：</span>
                                <span className="text-ink-2">{r.mainline_role}</span>
                              </div>
                            )}
                          </div>
                        )}

                        {/* 表征作用记录（审核模式） */}
                        {reviewMode && funcRecords.length > 0 && (
                          <div className="mt-2 space-y-1">
                            <div className="text-2xs text-ink-4 font-medium">表征作用记录：</div>
                            {funcRecords.map((fr) => (
                              <div key={fr.id} className="px-2 py-1 bg-paper-2 rounded-sm">
                                <div className="flex items-center gap-1.5">
                                  <Badge tone="ink">{representationFunctionCN[fr.function]}</Badge>
                                  <Badge tone={claimSourceTone[fr.source_type]}>{claimSourceCN[fr.source_type]}</Badge>
                                </div>
                                <p className="text-2xs text-ink-2 mt-1 leading-relaxed">{fr.function_description}</p>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* 教师用书证据 */}
                        {reviewMode && (
                          <div className="mt-1.5">
                            <p className="text-2xs text-ink-4">教材证据：{r.textbook_evidence}</p>
                            {r.teacher_guide_evidence_ids && r.teacher_guide_evidence_ids.length > 0 && (
                              <div className="mt-0.5 flex flex-wrap gap-1">
                                {r.teacher_guide_evidence_ids.map((eid) => (
                                  <div key={eid} className="group relative">
                                    <code className="text-2xs text-teal-2 font-mono cursor-help underline decoration-dotted">{eid}</code>
                                    {tbRefExcerpt(eid) && (
                                      <div className="hidden group-hover:block absolute z-10 left-0 top-full mt-1 w-72 p-2 bg-paper border border-ink-line rounded-sm shadow-card text-2xs text-ink-2 leading-relaxed">
                                        {tbRefExcerpt(eid)}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </Card>
                    );
                  })}
                </div>
              )}

              {/* 例题与练习 */}
              {activeTab === "practice" && (
                <div className="space-y-3">
                  {/* 黄金课时：例题深度分析链 */}
                  {isGoldenLesson && exampleChains.length > 0 && (
                    <Card
                      title="例题深度分析链"
                      subtitle={`${exampleChains.length} 个例题`}
                      accent="vermilion"
                      bodyClassName="p-3"
                    >
                      <div className="space-y-3">
                        {exampleChains.map((chain) => (
                          <div key={chain.chain_id} className="px-3 py-2.5 bg-paper-2 rounded-sm border-l-2 border-vermilion">
                            <div className="flex items-center gap-1.5 mb-2">
                              <Flag size={12} className="text-vermilion shrink-0" />
                              <div className="text-sm text-ink font-medium flex-1">{objectName(chain.example_object_id)}</div>
                              {reviewMode && (
                                <code className="text-2xs text-ink-4 font-mono">{chain.chain_id}</code>
                              )}
                            </div>

                            {/* 14.1 情境与条件 */}
                            <div className="space-y-1 mb-2">
                              <div className="text-2xs text-vermilion-deep font-medium">情境与条件</div>
                              <p className="text-2xs text-ink-2 leading-relaxed pl-2">{chain.scene_info}</p>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">条件位置：</span>{chain.conditions_location}
                              </div>
                              {chain.direct_conditions.length > 0 && (
                                <div className="text-2xs text-ink-3 pl-2">
                                  <span className="text-ok">直接条件：</span>{chain.direct_conditions.join("；")}
                                </div>
                              )}
                              {chain.inferred_conditions.length > 0 && (
                                <div className="text-2xs text-ink-3 pl-2">
                                  <span className="text-warn">推断条件：</span>{chain.inferred_conditions.join("；")}
                                </div>
                              )}
                              {chain.decorative_info.length > 0 && (
                                <div className="text-2xs text-ink-4 pl-2">
                                  <span>装饰信息：</span>{chain.decorative_info.join("；")}
                                </div>
                              )}
                            </div>

                            {/* 14.2 核心问题 */}
                            <div className="space-y-1 mb-2">
                              <div className="text-2xs text-vermilion-deep font-medium">核心问题</div>
                              <p className="text-2xs text-ink-2 leading-relaxed pl-2 font-medium">「{chain.core_question}」</p>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">问题针对：</span>{chain.question_target}
                              </div>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">问题结构：</span>{chain.question_structure}
                              </div>
                              {chain.subsequent_question_change && (
                                <div className="text-2xs text-ink-3 pl-2">
                                  <span className="text-vermilion-deep">后续变化：</span>{chain.subsequent_question_change}
                                </div>
                              )}
                            </div>

                            {/* 14.3 操作与观察 */}
                            <div className="space-y-1 mb-2">
                              <div className="text-2xs text-vermilion-deep font-medium">操作与观察</div>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">要求：</span>{chain.operation_required}
                              </div>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">对象：</span>{chain.operation_object}
                              </div>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-teal-2">暴露结构：</span>{chain.exposed_structure}
                              </div>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">后续使用：</span>{chain.operation_usage}
                              </div>
                            </div>

                            {/* 14.4 人物表达 */}
                            {chain.character_speeches.length > 0 && (
                              <div className="space-y-1 mb-2">
                                <div className="text-2xs text-vermilion-deep font-medium">人物表达</div>
                                {chain.character_speeches.map((sp, i) => (
                                  <div key={i} className="text-2xs text-ink-3 pl-2">
                                    <code className="text-ink-4 font-mono">{sp.character_id}</code>
                                    <span className="text-teal-2"> [{sp.speech_function}]</span>
                                    <span className="text-ink-2"> {sp.content}</span>
                                  </div>
                                ))}
                                <div className="text-2xs text-ink-3 pl-2">
                                  <span className="text-ink-4">关系：</span>{chain.speech_relations}
                                </div>
                              </div>
                            )}

                            {/* 14.5 数学表达 */}
                            <div className="space-y-1 mb-2">
                              <div className="text-2xs text-vermilion-deep font-medium">数学表达</div>
                              {chain.formulas.length > 0 && (
                                <div className="flex flex-wrap gap-1 pl-2">
                                  {chain.formulas.map((f, i) => (
                                    <code key={i} className="text-2xs px-1.5 py-0.5 bg-ink/5 text-ink font-mono rounded-sm">{f}</code>
                                  ))}
                                </div>
                              )}
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">算式含义：</span>{chain.formula_meaning}
                              </div>
                              <div className="text-2xs text-ink-3 pl-2">
                                <span className="text-ink-4">数字对应：</span>{chain.formula_number_mapping}
                              </div>
                              {chain.multiple_methods && (
                                <div className="text-2xs text-ink-3 pl-2">
                                  <span className="text-gold">多种方法：</span>{chain.multiple_methods}
                                </div>
                              )}
                              {chain.method_relation && (
                                <div className="text-2xs text-ink-3 pl-2">
                                  <span className="text-ink-4">方法关系：</span>{chain.method_relation}
                                </div>
                              )}
                            </div>

                            {/* 14.6 例题终点 */}
                            <div className="space-y-1 mb-2">
                              <div className="text-2xs text-vermilion-deep font-medium">例题终点</div>
                              <div className="flex items-center gap-1.5 pl-2">
                                <Badge tone="gold">{exampleEndpointCN[chain.endpoint_type] ?? chain.endpoint_type}</Badge>
                                <span className="text-2xs text-ink-2">{chain.endpoint_description}</span>
                              </div>
                            </div>

                            {/* 后续承接 */}
                            <div className="space-y-1">
                              <div className="text-2xs text-vermilion-deep font-medium">试一试及练习承接</div>
                              <p className="text-2xs text-ink-2 leading-relaxed pl-2">{chain.followup_connection}</p>
                              {chain.followup_object_ids.length > 0 && (
                                <div className="flex flex-wrap gap-1 pl-2">
                                  {chain.followup_object_ids.map((oid) => (
                                    <span key={oid} className="text-2xs px-1.5 py-0.5 bg-teal-tint/60 text-teal-2 rounded-sm">
                                      {objectName(oid)}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* 证据（审核模式） */}
                            {reviewMode && (
                              <div className="mt-2 pt-1.5 border-t border-ink-line flex items-center gap-1.5 flex-wrap">
                                <Badge tone={claimSourceTone[chain.source_type]}>
                                  {claimSourceCN[chain.source_type]}
                                </Badge>
                                {chain.evidence_ids.map((eid) => (
                                  <code key={eid} className="text-2xs text-teal-2 font-mono">{eid}</code>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                  <Card title="例题与试一试" accent="vermilion" bodyClassName="p-4">
                    <p className="text-sm text-ink-2 leading-relaxed">{analysis.example_try_relation}</p>
                  </Card>
                  <Card title="例题与练习" accent="vermilion" bodyClassName="p-4">
                    <p className="text-sm text-ink-2 leading-relaxed">{analysis.example_practice_relation}</p>
                  </Card>
                  <Card title="练习递进" accent="gold" bodyClassName="p-4">
                    <p className="text-sm text-ink-2 leading-relaxed">{analysis.practice_progression}</p>
                  </Card>

                  {/* 题目关系详情（审核模式） */}
                  {reviewMode && probRelations.length > 0 && (
                    <Card title="题目关系详情" subtitle={`${probRelations.length} 条`} bodyClassName="p-3">
                      <div className="space-y-2">
                        {probRelations.map((pr) => {
                          const retained = allRetained.filter((d) => d.problem_relation_id === pr.id);
                          const changed = allChanged.filter((d) => d.problem_relation_id === pr.id);
                          const reqChange = allReqChanges.filter((c) => c.problem_relation_id === pr.id);
                          return (
                            <div key={pr.id} className="px-2 py-2 bg-paper-2 rounded-sm">
                              <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
                                <code className="text-2xs text-ink-4 font-mono">{pr.src_object_id}</code>
                                <Badge tone="vermilion">{problemRelationCN[pr.relation_type]}</Badge>
                                <code className="text-2xs text-ink-4 font-mono">{pr.dst_object_id}</code>
                                {pr.position_in_sequence && (
                                  <Badge tone="gold">{problemSequenceRoleCN[pr.position_in_sequence]}</Badge>
                                )}
                              </div>
                              {pr.structural_relation && (
                                <p className="text-2xs text-ink-3 mb-1">结构关系：{pr.structural_relation}</p>
                              )}
                              {pr.representation_relation && (
                                <p className="text-2xs text-ink-3 mb-1">表征关系：{pr.representation_relation}</p>
                              )}
                              {retained.length > 0 && (
                                <div className="mb-1">
                                  <div className="text-2xs text-ok font-medium">保持项：</div>
                                  {retained.map((d) => (
                                    <div key={d.id} className="text-2xs text-ink-3 pl-2">· {d.dimension}: {d.retained_value}</div>
                                  ))}
                                </div>
                              )}
                              {changed.length > 0 && (
                                <div className="mb-1">
                                  <div className="text-2xs text-warn font-medium">变化项：</div>
                                  {changed.map((d) => (
                                    <div key={d.id} className="text-2xs text-ink-3 pl-2">· {d.dimension}: {d.source_value} → {d.target_value}</div>
                                  ))}
                                </div>
                              )}
                              {reqChange.length > 0 && (
                                <div>
                                  <div className="text-2xs text-vermilion-deep font-medium">任务要求变化：</div>
                                  {reqChange.map((c) => (
                                    <div key={c.id} className="text-2xs text-ink-3 pl-2">· {c.change_type}: {c.description}</div>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </Card>
                  )}
                </div>
              )}

              {/* 证据 */}
              {activeTab === "evidence" && (
                <div className="space-y-3">
                  <Card title="教师用书证据" accent="teal" bodyClassName="p-4">
                    <p className="text-sm text-ink-2 leading-relaxed">{analysis.tb_evidence_summary}</p>
                  </Card>
                  <Card title="系统推断" accent="vermilion" bodyClassName="p-4">
                    <p className="text-sm text-ink-2 leading-relaxed">{analysis.system_inferences}</p>
                  </Card>

                  {/* 结论列表 */}
                  <Card title="证据支持结论" subtitle={`${claims.length} 条`} bodyClassName="p-3">
                    <div className="space-y-2">
                      {claims.map((c) => (
                        <div key={c.id} className="px-3 py-2 bg-paper-2 rounded-sm">
                          <div className="flex items-center gap-1.5 mb-1.5">
                            <Badge tone={claimSourceTone[c.claim_source_type]}>
                              {claimSourceCN[c.claim_source_type]}
                            </Badge>
                            {reviewMode && (
                              <code className="text-2xs text-ink-4 font-mono">{c.id}</code>
                            )}
                          </div>
                          <p className="text-xs text-ink-2 leading-relaxed">{c.claim_text}</p>
                          {reviewMode && c.inference_basis && (
                            <p className="mt-1 text-2xs text-vermilion-deep">推断依据：{c.inference_basis}</p>
                          )}
                          {reviewMode && c.source_evidence_ids.length > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {c.source_evidence_ids.map((eid) => (
                                <div key={eid} className="group relative">
                                  <code className="text-2xs text-teal-2 font-mono cursor-help underline decoration-dotted">{eid}</code>
                                  {tbRefExcerpt(eid) && (
                                    <div className="hidden group-hover:block absolute z-10 left-0 top-full mt-1 w-72 p-2 bg-paper border border-ink-line rounded-sm shadow-card text-2xs text-ink-2 leading-relaxed">
                                      {tbRefExcerpt(eid)}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </Card>

                  {analysis.pending_issues.length > 0 && (
                    <Card title="待审核问题" accent="gold" bodyClassName="p-4">
                      <ul className="space-y-1">
                        {analysis.pending_issues.map((issue, i) => (
                          <li key={i} className="text-xs text-ink-2 flex items-start gap-1.5">
                            <AlertTriangle size={12} className="text-warn shrink-0 mt-0.5" /> {issue}
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}

                  {/* 任务四补充：浅层分析拦截检查（黄金课时） */}
                  {isGoldenLesson && reviewIssues.length > 0 && (
                    <Card
                      title="浅层分析拦截检查"
                      subtitle={`${reviewIssues.length} 项 · ${reviewIssues.filter((i) => i.resolution_status === "fixed").length} 已修复`}
                      accent="none"
                      className="border-l-2 border-l-ink"
                      bodyClassName="p-3"
                    >
                      <div className="space-y-2">
                        {reviewIssues.map((issue) => (
                          <div
                            key={issue.issue_id}
                            className={cn(
                              "px-3 py-2 bg-paper-2 rounded-sm border-l-2",
                              issue.severity === "blocking" ? "border-err" : "border-warn",
                            )}
                          >
                            <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                              <Badge tone={reviewIssueCategoryTone[issue.category]}>
                                {reviewIssueCategoryCN[issue.category]}
                              </Badge>
                              <Badge tone={issue.severity === "blocking" ? "err" : "warn"}>
                                {issue.severity === "blocking" ? "阻断" : "非阻断"}
                              </Badge>
                              <Badge
                                tone={
                                  issue.resolution_status === "fixed" ? "ok"
                                  : issue.resolution_status === "wontfix" ? "default"
                                  : "warn"
                                }
                              >
                                {issue.resolution_status === "fixed" ? "已修复"
                                  : issue.resolution_status === "wontfix" ? "不修复"
                                  : "待修复"}
                              </Badge>
                              {reviewMode && (
                                <code className="text-2xs text-ink-4 font-mono">{issue.issue_id}</code>
                              )}
                            </div>
                            <p className="text-xs text-ink-2 leading-relaxed">{issue.issue_description}</p>
                            <p className="text-2xs text-ink-4 mt-1 leading-relaxed">
                              <span className="text-ink-3 font-medium">检测模式：</span>{issue.detected_pattern}
                            </p>
                            <p className="text-2xs text-vermilion-deep mt-1 leading-relaxed">
                              <span className="font-medium">建议修复：</span>{issue.suggested_fix}
                            </p>
                            {issue.resolution_note && (
                              <p className="text-2xs text-ok mt-1 leading-relaxed">
                                <span className="font-medium">修复说明：</span>{issue.resolution_note}
                              </p>
                            )}
                            {reviewMode && issue.affected_data_ids.length > 0 && (
                              <div className="mt-1 flex flex-wrap gap-1">
                                <span className="text-2xs text-ink-4 font-medium">受影响：</span>
                                {issue.affected_data_ids.map((did) => (
                                  <code key={did} className="text-2xs text-ink-4 font-mono">{did}</code>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* 底部版本信息 */}
      <div className="mt-8 px-4 py-3 bg-paper-2 rounded-sm border border-ink-line text-2xs text-ink-4 font-mono flex items-center justify-between flex-wrap gap-2">
        <span>分析版本：{analysisVersion.version_id}</span>
        <span>关系模式：{analysisVersion.relation_schema_version}</span>
        <span>课时目录：{analysisVersion.lesson_catalog_version}</span>
        <span className="flex items-center gap-1">
          <CheckCircle2 size={11} className="text-ok" /> 全册课时：{analyzedLessons.length} 个（黄金{lessonAnalyses.length} + 扩展{lessonAnalysesExtra.length}）
        </span>
        <span className="flex items-center gap-1">
          <Network size={11} className="text-vermilion" /> 黄金深度：{lessonMainlines.length}主线 / {lessonMainlineNodes.length}节点 / {exampleAnalysisChains.length}例题链
        </span>
      </div>
    </div>
  );
}
