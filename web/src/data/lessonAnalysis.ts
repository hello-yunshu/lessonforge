import type {
  LessonContentSequence,
  LessonContentRelation,
  LessonLearningTask,
  RepresentationRelation,
  RepresentationFunctionRecord,
  ProblemRelation,
  ProblemRetainedDimension,
  ProblemChangedDimension,
  ProblemRequirementChange,
  LessonKeyNode,
  EvidenceBackedClaim,
  LessonAnalysis,
  UpstreamCorrectionRequest,
  LessonMainline,
  LessonMainlineNode,
  LessonMainlineTransition,
  LessonMainlineEvidence,
  LessonMainlineAlternative,
  ExampleAnalysisChain,
  AnalysisReviewIssue,
  AnalysisVersion,
} from "./types";

// 教材版权数据不随源码发布，保留类型与空结构。
export const lessonContentSequences: LessonContentSequence[] = [];
export const lessonContentRelations: LessonContentRelation[] = [];
export const lessonLearningTasks: LessonLearningTask[] = [];
export const representationRelations: RepresentationRelation[] = [];
export const representationFunctionRecords: RepresentationFunctionRecord[] = [];
export const problemRelations: ProblemRelation[] = [];
export const problemRetainedDimensions: ProblemRetainedDimension[] = [];
export const problemChangedDimensions: ProblemChangedDimension[] = [];
export const problemRequirementChanges: ProblemRequirementChange[] = [];
export const lessonKeyNodes: LessonKeyNode[] = [];
export const evidenceBackedClaims: EvidenceBackedClaim[] = [];
export const lessonAnalyses: LessonAnalysis[] = [];
export const upstreamCorrectionRequests: UpstreamCorrectionRequest[] = [];
export const lessonMainlines: LessonMainline[] = [];
export const lessonMainlineNodes: LessonMainlineNode[] = [];
export const lessonMainlineTransitions: LessonMainlineTransition[] = [];
export const lessonMainlineEvidence: LessonMainlineEvidence[] = [];
export const lessonMainlineAlternatives: LessonMainlineAlternative[] = [];
export const exampleAnalysisChains: ExampleAnalysisChain[] = [];
export const analysisReviewIssues: AnalysisReviewIssue[] = [];
export const analysisVersion: AnalysisVersion = {
  version_id: "",
  lesson_catalog_version: "",
  textbook_parsing_version: "",
  teacher_guide_processing_version: "",
  relation_schema_version: "",
  created_at: "",
  reviewed_at: null,
  reviewer: null,
  status: "draft",
  change_log: [],
};