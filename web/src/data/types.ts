// ============================================================================
// 教材数字化系统 — 类型定义（对应 ER 设计 / DDL）
// 当前为前端原型类型化 mock 数据层，生产环境契约保持一致
// ============================================================================

export type ReviewStatus = "pending" | "confirmed" | "rejected";

export type TextbookObjectType = "example" | "try" | "think-do" | "exercise" | "operation";

export type BlockType =
  | "title"
  | "text"
  | "q_no"
  | "example_icon"
  | "section_icon"
  | "scene"
  | "table"
  | "chart"
  | "geometry"
  | "formula"
  | "character"
  | "speech_box"
  | "answer"
  | "answer_blank"
  | "decoration";

export type CoordinateKind = "pixel" | "normalized" | "polygon";

export type PixelRect = { x: number; y: number; w: number; h: number };
export type NormalizedRect = { nx: number; ny: number; nw: number; nh: number };
export type Polygon = { points: [number, number][] };

export type Coordinate = {
  id: string;
  block_id: string;
  kind: CoordinateKind;
  geometry: PixelRect | NormalizedRect | Polygon;
};

export type Textbook = {
  id: string;
  version: string; // 苏教版
  grade: string; // 三年级
  volume: string; // 上册
  edition: string;
  pdf_hash: string;
  page_count: number;
  created_at: string;
};

export type Page = {
  id: string;
  textbook_id: string;
  pdf_page_no: number;
  printed_page_no: number;
  width_px: number;
  height_px: number;
  rotation: number;
  // 派生页面图（对象存储引用）
  page_image: string; // 占位：实际为对象存储 key
};

export type ContentBlock = {
  id: string;
  page_id: string;
  type: BlockType;
  raw_text: string;
  normalized_text: string;
  confidence: number;
  review_status: ReviewStatus;
  read_order: number;
  // 来源（OCR / 规则 / 人工）
  source: "ocr" | "rule" | "manual";
};

export type TextbookObject = {
  id: string;
  type: TextbookObjectType;
  section_id: string;
  page_ids: string[]; // 支持跨页
  title: string;
};

export type ExampleComponent =
  | "anchor"
  | "scene"
  | "given"
  | "question"
  | "method"
  | "operation"
  | "formula"
  | "followup"
  | "conclusion"
  | "answer";

export type Example = {
  id: string;
  object_id: string;
  anchor_no: number; // 书本图标内数字
  components: ExampleComponent[];
  span_pages: boolean;
};

export type ExerciseSectionType = "try" | "think-do" | "practice";

export type Exercise = {
  id: string;
  object_id: string;
  section_type: ExerciseSectionType;
};

export type QuestionGroup = {
  id: string;
  exercise_id: string;
  label: string;
};

export type BigQuestion = {
  id: string;
  group_id: string | null;
  exercise_id: string;
  q_no: string;
  stem: string;
};

export type SmallQuestion = {
  id: string;
  big_question_id: string;
  q_no: string;
  stem: string;
};

export type SharedMaterialKind = "image" | "table" | "chart" | "geometry";

export type SharedMaterial = {
  id: string;
  kind: SharedMaterialKind;
  consumer_object_ids: string[];
  description: string;
};

export type CharacterRole = "student" | "teacher";

export type Character = {
  id: string;
  name: string; // 青椒/蘑菇/番茄/白菜/豌豆/茄子
  role: CharacterRole;
  // 默认教材姿态（与角色身份分开）
  default_pose: string;
  // 可编辑模式：教材中部分卡通形象与课本图案不100%一致，
  // 教师可在备课阶段修正角色名称/姿态以适配本班学情
  editable?: boolean;
  editor?: string | null;
  edited_at?: string | null;
  edit_note?: string | null;
};

export type SpeechFunction =
  | "ask-reason" // 追问理由
  | "give-method" // 给方法
  | "give-answer" // 给答案
  | "summarize" // 归纳
  | "prompt" // 提示
  | "operation"; // 操作说明

export type CharacterSpeech = {
  id: string;
  character_id: string;
  object_id: string;
  speech_function: SpeechFunction;
  content: string;
};

export type IconType = "example" | "try" | "think-do" | "section";

export type Icon = {
  id: string;
  name: string;
  type: IconType;
  semantic: string;
  default_role: string;
  // 录入原图（对象存储引用）
  source_image: string;
  // 可编辑模式：图标资源库中的标准图与课本图案可能不100%一致，
  // 允许教师修正名称/语义/默认角色身份以适配学情
  editable?: boolean;
  editor?: string | null;
  edited_at?: string | null;
  edit_note?: string | null;
};

export type IconVariantKind =
  | "gray"
  | "binary"
  | "scale"
  | "blur"
  | "jpeg"
  | "brightness"
  | "crop"
  | "screenshot";

export type IconVariant = {
  id: string;
  icon_id: string;
  variant: IconVariantKind;
  params: string;
  source_icon_id: string;
  for_training: boolean;
  for_match: boolean;
  for_test: boolean;
};

export type MathStructureKind = "quantity" | "chart" | "geometry";

export type QuantityStructure = {
  kind: "quantity";
  objects: { name: string; quantity: number | null; unit: string }[];
  known: string[];
  unknown: string[];
  relation: "add" | "sub" | "mul" | "div" | "compare" | "multiple" | "total-part";
  parts: { per: number | null; count: number | null; total: number | null } | null;
  unused_info: string[];
};

export type ChartCell = {
  row: number;
  col: number;
  value: number | null;
  blank_meaning: "value-zero" | "intentional-blank" | "ocr-missed" | "not-applicable";
};

export type ChartStructure = {
  kind: "chart";
  chart_type: "table" | "bar" | "line" | "pictograph";
  row_titles: string[];
  col_titles: string[];
  cells: ChartCell[];
  unit: string;
  // 仅统计图
  x_axis?: string;
  y_axis?: string;
  scale?: string;
  per_grid?: string;
  shared_with_questions: string[];
};

export type GeometryStructure = {
  kind: "geometry";
  objects: (
    | { type: "point" | "line" | "plane"; label: string }
    | {
        type: "polygon";
        label: string;
        sides: number;
        edges: string[];
        angles: string[];
        vertices: string[];
      }
  )[];
  marks: ("parallel" | "perpendicular" | "equal" | "symmetry")[];
  units: string;
  operations: ("translate" | "rotate" | "axis-symmetry" | "assemble" | "split")[];
  states: ("before" | "during" | "after")[];
};

export type MathStructure = {
  id: string;
  object_id: string;
  kind: MathStructureKind;
  structure: QuantityStructure | ChartStructure | GeometryStructure;
};

export type RelationType =
  | "icon-marks"
  | "scene-provides"
  | "character-says"
  | "explains-formula"
  | "shared-table"
  | "shared-chart"
  | "spans-page"
  | "try-follows-example";

export type Relation = {
  id: string;
  src_object_id: string;
  rel_type: RelationType;
  dst_object_id: string | null;
  dst_block_id: string | null;
  note: string;
};

export type Correction = {
  id: string;
  textbook_id: string;
  page_id: string;
  block_id: string;
  original: string;
  revised: string;
  error_type: string;
  rule_version: string;
  model_version: string;
  original_confidence: number;
  editor: string;
  edited_at: string;
  is_universal: boolean;
  iteration: 1 | 2 | 3; // 三级迭代
};

export type Version = {
  id: string;
  version_no: string;
  released_at: string;
  changeset: string[];
  regression_passed: boolean;
  notes: string;
};

export type ReviewReason =
  | "new-icon"
  | "role-conflict"
  | "bubble-unclear"
  | "multi-owner"
  | "span-page"
  | "blank-ambiguous"
  | "scale-unclear"
  | "no-vs-example"
  | "parse-conflict"
  | "multi-candidate"
  | "decoration-adjacent";

export type ReviewTask = {
  id: string;
  block_id: string;
  reason: ReviewReason;
  priority: number;
  status: ReviewStatus;
  detail: string;
};

export type GoldenSampleCategory =
  | "example-icon"
  | "student-roles"
  | "teacher-roles"
  | "multi-method"
  | "teacher-followup"
  | "hidden-condition"
  | "one-image-multi-q"
  | "multi-image-one-q"
  | "table-blank"
  | "chart-scale"
  | "geometry-mark"
  | "span-page-example"
  | "span-page-exercise"
  | "decoration-adjacent"
  | "photo-tilted-bw";

export type GoldenSample = {
  id: string;
  category: GoldenSampleCategory;
  object_id: string | null;
  description: string;
  expected: string;
};

export type RegressionTest = {
  id: string;
  sample_id: string;
  passed: boolean;
  detail: string;
  ran_at: string;
};

export type UploadType =
  | "full"
  | "half"
  | "local"
  | "scene"
  | "chart"
  | "tilted"
  | "bw"
  | "annotated";

export type CoordinateTransformKind = "similarity" | "homography" | "local-grid";

export type CoordinateTransform = {
  id: string;
  upload_id: string;
  transform_kind: CoordinateTransformKind;
  matrix: number[]; // 3x3 单应矩阵或参数
  residual: number; // 配准残差（像素）
};

export type UserUpload = {
  id: string;
  upload_type: UploadType;
  located_object_id: string | null;
  located_page_id: string | null;
  confidence: number;
  uploaded_at: string;
  // 8 步定位流程状态
  pipeline: { step: number; name: string; done: boolean; note?: string }[];
};

// ---- 统计聚合（用于工作台/验收指标） ----
export type Metric = {
  key: string;
  name: string;
  current: number; // 0..1
  target: number; // 0..1
  priority: 1 | 2 | 3 | 4 | 5; // 1 最高
  category: "object" | "image" | "shared" | "crosspage" | "locate" | "character" | "table";
};

export type PhaseStatus = "done" | "in-progress" | "pending";

export type Phase = {
  no: number;
  name: string;
  status: PhaseStatus;
  detail: string;
};

// ============================================================================
// 教师教学用书结构化资料库类型（任务二）
// 分层保存：教材原页事实 / 教师用书原文 / 系统推断 三者独立存储，不互相覆盖
// ============================================================================

// 教师用书元信息
export type TeacherBook = {
  id: string;
  version: string; // 苏教版
  grade: string; // 三年级
  volume: string; // 上册
  edition: string; // 版次
  isbn: string;
  cip: string;
  pdf_file: string; // PDF 文件名
  pdf_page_count: number; // PDF 总页数（含二年级上册部分）
  pdf_page_start: number; // 三年级上册部分在 PDF 中的起始页
  pdf_page_end: number; // 三年级上册部分在 PDF 中的结束页
  printed_page_start: number; // 三年级上册部分教师用书印刷页起始
  printed_page_end: number; // 三年级上册部分教师用书印刷页结束
  publisher: string;
  compiled_by: string;
};

// 教师用书印刷页 ↔ PDF 页 映射
export type TeacherBookPage = {
  id: string;
  teacher_book_id: string;
  pdf_page_no: number; // 教师用书 PDF 页码
  printed_page_no: number | null; // 教师用书印刷页码（封面/版权页无印刷页码）
  section: string; // 所属部分（总说明/各单元教材说明与教学建议/参考资料）
  summary: string; // 该页内容摘要
};

// 教师用书单元说明（对应教材单元）
export type TeacherBookUnit = {
  id: string;
  teacher_book_id: string;
  no: number; // 单元号
  name: string; // 单元名
  is_comprehensive_practice: boolean; // 是否为综合实践/探索规律
  lesson_count: number; // 课时数
  // 教师用书印刷页范围
  tb_printed_start: number;
  tb_printed_end: number;
  // 对应的教材单元 ID（映射）
  textbook_unit_id: string | null;
  // 教材印刷页范围
  textbook_printed_start: number;
  textbook_printed_end: number;
  // 教学目标原文片段
  objectives_excerpt: string;
};

// 教师用书课时划分（教师用书明确给出的课时范围）
export type TeacherBookLesson = {
  id: string;
  unit_id: string; // 教师用书单元 ID
  no: number; // 课时号（单元内编号）
  title: string; // 课时标题
  // 该课时覆盖的教材印刷页范围（用于跨页调取验证）
  textbook_printed_pages: number[];
  // 该课时对应的教材 PDF 页 ID 列表
  textbook_page_ids: string[];
  // 该课时引用的教材对象 ID 列表（例题/试一试/想想做做/练习）
  textbook_object_ids: string[];
  // 教师用书对该课时的教学建议原文片段
  teaching_suggestion: string;
  // 教师用书印刷页（该课时建议所在页）
  tb_printed_pages: number[];
};

// 教师用书对教材对象的引用（原文引用，不覆盖教材原页事实）
export type TeacherBookReference = {
  id: string;
  lesson_id: string;
  // 引用类型
  ref_kind: "example" | "try" | "think-do" | "exercise" | "operation" | "scene" | "formula";
  // 教师用书原文中提到的教材对象描述
  tb_description: string;
  // 教师用书原文页码
  tb_printed_page: number;
  // 对应的教材对象 ID（映射，可为 null 表示教师用书提到但系统尚未识别）
  textbook_object_id: string | null;
  // 对应的教材印刷页
  textbook_printed_page: number;
  // 教师用书原文片段（可返回原文）
  excerpt: string;
};

// ============================================================================
// 教材解析验证类型（任务二 — 验证现有教材解析结果）
// 教师用书是参照和证据来源，不直接覆盖教材原页事实
// ============================================================================

export type VerifyCheckType =
  | "question-complete" // 题目完整性（隐藏条件/气泡/表格/相邻区域是否遗漏）
  | "lesson-retrieval" // 课时调取（跨页完整调取，不遗漏不重复不混入）
  | "exercise-set" // 练习集合（同一课时多道练习独立完整且建立联系）
  | "binding-accuracy"; // 绑定准确性（教材对象与页面/单元绑定）

export type VerifyStatus = "pass" | "warn" | "fail" | "pending";

// 单条验证项
export type VerifyItem = {
  id: string;
  check_type: VerifyCheckType;
  // 验证目标名称
  target_name: string;
  // 关联的课时 ID（若适用）
  lesson_id: string | null;
  // 关联的教材对象 ID（若适用）
  textbook_object_id: string | null;
  // 教师用书给出的预期（原文依据）
  expected_from_tb: string;
  // 教师用书原文页码（证据来源）
  tb_printed_page: number;
  // 系统当前解析结果
  actual_in_system: string;
  // 验证状态
  status: VerifyStatus;
  // 差异说明（若 warn/fail）
  diff_note: string;
  // 三层证据标记：教材原页 / 教师用书原文 / 系统推断
  evidence_layers: ("textbook-page" | "tb-text" | "system-infer")[];
};

// 验证汇总（按验证类型）
export type VerifySummary = {
  check_type: VerifyCheckType;
  total: number;
  pass: number;
  warn: number;
  fail: number;
  pending: number;
  // 该类型验证说明
  description: string;
};

// ============================================================================
// 正式教材课时划分与内容归属（任务三）
// 建立"正式教材课时"对象：经过教材原页、完整教材对象、教师用书证据和人工审核
// 共同确认的教材内容范围。这是后续教材分析的唯一课时边界基准。
// ============================================================================

// 课时名称来源
export type LessonNameSource =
  | "teacher-book-official" // 教师用书正式名称
  | "publisher-material" // 出版社/教材编写组正式资料
  | "textbook-heading" // 教材显性标题
  | "normalized"; // 根据教材内容建立的规范名称

// 审核状态
export type LessonReviewStatus =
  | "pending" // 待审核
  | "under-review" // 审核中
  | "approved" // 已审核通过
  | "disputed"; // 存在争议

// 边界置信度
export type SegmentationConfidence = "high" | "medium" | "low";

// 划分依据类型
export type SegmentationBasis =
  | "teacher-book-evidence" // 教师用书明确证据
  | "textbook-structure" // 教材显性结构（标题/栏目）
  | "object-continuity" // 教材对象连续性
  | "manual-review"; // 人工审核裁定

// 正式教材课时
export type OfficialLesson = {
  // 基础标识
  lesson_id: string;
  edition_id: string; // 教材版本 ID
  unit_id: string; // 所属单元 ID（对应 textbook.ts 的 Unit.id）

  // 顺序
  lesson_sequence_in_book: number; // 全册顺序（1-based）
  lesson_sequence_in_unit: number; // 单元内顺序（1-based）

  // 名称
  official_lesson_name: string; // 正式名称（优先取自教师用书）
  normalized_lesson_name: string; // 规范名称（便于检索）
  lesson_name_source: LessonNameSource;

  // 边界 — 页面级
  start_page_id: string;
  end_page_id: string;
  // 边界 — 对象级（精确到教材对象）
  start_object_id: string | null; // 起始教材对象 ID（未对象化时为 null）
  end_object_id: string | null; // 结束教材对象 ID

  // 包含范围
  included_page_ids: string[]; // 包含的页面 ID 列表
  included_region_ids: string[]; // 包含的页面区域 ID（预留，当前为空）
  included_problem_ids: string[]; // 包含的完整题目 ID（大题/小题）
  included_object_ids: string[]; // 包含的教材对象 ID 列表

  // 排除范围（同页切分时，明确排除的区域/对象）
  excluded_region_ids: string[];
  excluded_problem_ids: string[];
  excluded_object_ids: string[];

  // 分类对象归属
  main_example_ids: string[]; // 主要例题
  try_it_ids: string[]; // 试一试
  practice_section_ids: string[]; // 想想做做
  exercise_item_ids: string[]; // 独立练习题
  review_object_ids: string[]; // 复习内容
  activity_object_ids: string[]; // 综合与实践内容
  character_ids: string[]; // 人物
  speech_bubble_ids: string[]; // 气泡

  // 跨页与共享标记
  cross_page_flag: boolean; // 是否跨页
  shared_page_flag: boolean; // 是否与其它课时共享同一页

  // 教师用书建议
  recommended_school_periods: number; // 建议教学课时数
  recommended_period_source_id: string | null; // 建议来源（教师用书课时 ID）

  // 划分证据
  segmentation_basis: SegmentationBasis[];
  source_evidence_ids: string[]; // 证据 ID 列表（对应 LessonEvidence）
  segmentation_confidence: SegmentationConfidence;

  // 备选方案与争议
  alternative_segmentation: string | null; // 备选划分方案描述
  segmentation_dispute: string | null; // 争议说明

  // 审核
  review_status: LessonReviewStatus;
  reviewer: string | null;
  reviewed_at: string | null;
  review_note: string | null;

  // 版本
  lesson_catalog_version: string; // 课时目录版本号
};

// 课时划分证据
export type LessonEvidence = {
  id: string;
  lesson_id: string;
  // 证据类型
  evidence_kind:
    | "textbook-page" // 教材原页依据
    | "tb-text" // 教师用书原文依据
    | "object-range" // 教材对象范围
    | "system-infer" // 系统判断说明
    | "manual-review"; // 人工审核记录
  // 证据内容
  description: string;
  // 证据来源页码/位置
  textbook_printed_page: number | null;
  tb_printed_page: number | null;
  // 原文片段（如适用）
  excerpt: string | null;
};

// 教材对象正式归属
export type ObjectLessonAssignment = {
  id: string;
  object_id: string; // 教材对象 ID
  object_type: string; // 对象类型（example/try/think-do/exercise/operation）
  primary_lesson_id: string; // 主要归属课时 ID
  secondary_lesson_ids: string[]; // 辅助关联课时 ID
  // 归属依据
  assignment_basis: SegmentationBasis[];
  assignment_confidence: SegmentationConfidence;
  // 审核
  review_status: LessonReviewStatus;
  review_note: string | null;
};

// 课时目录版本信息
export type LessonCatalog = {
  catalog_id: string;
  edition_id: string;
  version: string; // 目录版本号
  source_data_version: string; // 源数据版本
  teacher_guide_processing_version: string; // 教师用书处理版本
  textbook_parsing_version: string; // 教材解析版本
  created_at: string;
  reviewed_at: string | null;
  reviewer: string | null;
  status: "draft" | "frozen"; // 草稿/已冻结
  change_log: string[];
};

// ============================================================================
// 任务四：课时内部教材内容关系与练习结构分析
// 在正式课时边界和完整教材对象基础上，建立可检索、可核验、可回溯的
// 课时内部教材内容关系与练习结构数据。
// ============================================================================

// 学习任务动作类型（受控词表）
export type ActionType =
  | "OBSERVE" | "OPERATE" | "COUNT" | "COMPARE" | "CLASSIFY"
  | "CALCULATE" | "FILL_IN" | "DRAW" | "EXPRESS" | "EXPLAIN"
  | "CHOOSE" | "ESTIMATE" | "DISCOVER" | "VERIFY" | "GENERALIZE"
  | "APPLY" | "SOLVE_PROBLEM" | "REFLECT";

// 表征类型（受控词表）
export type RepresentationType =
  | "REAL_OBJECT" | "REAL_CONTEXT" | "PICTURE" | "OPERATION_DIAGRAM"
  | "GEOMETRIC_DIAGRAM" | "NUMBER_LINE" | "TABLE" | "VERTICAL_FORM"
  | "HORIZONTAL_EXPRESSION" | "MATHEMATICAL_EXPRESSION" | "VERBAL_EXPRESSION"
  | "SYMBOLIC_EXPRESSION" | "CHARACTER_SPEECH";

// 表征关系类型
export type RepresentationRelationType =
  | "REPRESENTS" | "TRANSFORMS_TO" | "EXPLAINS" | "CORRESPONDS_TO"
  | "ABSTRACTS_FROM" | "MAKES_VISIBLE" | "REPLACES" | "COMBINES_WITH";

// 题目结构关系类型
export type ProblemRelationType =
  // 结构事实关系
  | "SAME_LESSON" | "SAME_SECTION" | "FOLLOWS" | "PRECEDES"
  | "SHARED_STEM" | "SHARED_CONTEXT" | "SHARED_IMAGE" | "SHARED_TABLE"
  | "SUBPROBLEM_OF" | "CONTINUES"
  // 教材内容关系
  | "DIRECTLY_CORRESPONDS_TO" | "PRACTICES_SAME_STRUCTURE"
  | "CHANGES_DATA_FROM" | "CHANGES_CONTEXT_FROM" | "CHANGES_REPRESENTATION_FROM"
  | "CHANGES_QUESTION_FROM" | "REVERSES_RELATION_FROM"
  | "REMOVES_EXPLICIT_SUPPORT_FROM" | "ADDS_CONDITION_TO"
  | "COMBINES_ELEMENTS_FROM" | "APPLIES_IN_NEW_CONTEXT";

// 保持项维度（受控）
export type RetainedDimension =
  | "MATHEMATICAL_OBJECT" | "QUANTITY_RELATION" | "OPERATION"
  | "PROBLEM_STRUCTURE" | "REPRESENTATION" | "QUESTION_DIRECTION"
  | "UNIT_STRUCTURE" | "GEOMETRIC_STRUCTURE" | "SOLUTION_STEP" | "CONTEXT_TYPE";

// 变化项维度（受控）
export type ChangedDimension =
  | "NUMBER_VALUE" | "CONTEXT" | "CONDITION_COUNT" | "CONDITION_ORDER"
  | "QUESTION" | "QUESTION_DIRECTION" | "REPRESENTATION" | "KNOWN_UNKNOWN"
  | "UNIT" | "OPERATION_STEP_COUNT" | "INFORMATION_RELEVANCE"
  | "SUPPORT_LEVEL" | "RESPONSE_FORM" | "OPENNESS";

// 任务要求变化类型（受控）
export type RequirementChangeType =
  | "IMITATE" | "COMPLETE" | "INDEPENDENT_CALCULATION"
  | "INDEPENDENT_REPRESENTATION" | "SELECT_INFORMATION" | "SELECT_METHOD"
  | "EXPLAIN_REASON" | "CONVERT_REPRESENTATION" | "SOLVE_MULTI_STEP"
  | "COMPARE_METHODS" | "CREATE_EXAMPLE" | "OPEN_RESPONSE";

// 结论来源类型
export type ClaimSourceType =
  | "TEXTBOOK_FACT" // 教材直接事实
  | "TEACHER_GUIDE_EXPLICIT" // 教师用书明确说明
  | "OTHER_AUTHORITY_EXPLICIT" // 其他权威资料明确说明
  | "SYSTEM_STRUCTURAL_INFERENCE" // 系统结构推断
  | "HUMAN_REVIEWED_INFERENCE"; // 人工审核后的解释

// 教师用书证据类型
export type TbEvidenceKind =
  | "CONTENT_DESCRIPTION" | "ARRANGEMENT_EXPLANATION" | "EXAMPLE_EXPLANATION"
  | "PRACTICE_EXPLANATION" | "REPRESENTATION_EXPLANATION"
  | "TEACHING_SUGGESTION" | "OTHER";

// 置信度（复用 SegmentationConfidence）
// 审核状态（复用 LessonReviewStatus）

// 第一层：教材内容顺序
export type LessonContentSequence = {
  id: string;
  lesson_id: string;
  sequence_index: number; // 1-based
  object_id: string;
  object_role: string; // 该对象在课时中的角色描述
  sequence_basis: string; // 顺序依据
};

// 第二层：教材对象直接关系
export type LessonContentRelation = {
  id: string;
  lesson_id: string;
  src_object_id: string;
  dst_object_id: string | null;
  relation_type: string; // 直接观察到的关系类型描述
  evidence_note: string; // 关系依据
  confidence: SegmentationConfidence;
};

// 第三层：学习任务
export type LessonLearningTask = {
  id: string;
  lesson_id: string;
  action_type: ActionType;
  target_object_ids: string[];
  instruction_source_object_id: string | null;
  expected_output_type: string;
  evidence_id: string | null; // 教师用书证据 ID
  review_status: LessonReviewStatus;
};

// 表征作用词表（任务四补充 13.2）
export type RepresentationFunction =
  | "PROVIDES_INFORMATION" // 提供条件
  | "FOCUSES_STRUCTURE" // 突出结构
  | "SUPPORTS_COUNTING" // 支持计数
  | "SHOWS_GROUPING" // 呈现分组
  | "SHOWS_CORRESPONDENCE" // 呈现对应
  | "SHOWS_CHANGE" // 呈现变化
  | "MAKES_RELATION_VISIBLE" // 使数量关系可见
  | "RECORDS_PROCESS" // 记录过程
  | "SUPPORTS_CALCULATION" // 支持计算
  | "ABSTRACTS_RELATION" // 抽象数学关系
  | "VERIFIES_RESULT" // 验证结果
  | "COMMUNICATES_REASONING" // 表达思考
  | "ORGANIZES_INFORMATION" // 组织信息
  | "REDUCES_CONTEXT_DETAIL"; // 减少情境细节

// 表征转换动作
export type TransformationAction =
  | "ABSTRACT" // 抽象
  | "TRANSLATE" // 翻译
  | "REPRESENT" // 表征
  | "DECOMPOSE" // 分解
  | "COMPOSE" // 组合
  | "TRANSFORM" // 转换
  | "RECODE"; // 重新编码

// 第四层：表征关系（任务四补充 13.3 扩展字段）
export type RepresentationRelation = {
  id: string;
  lesson_id: string;
  src_representation: RepresentationType;
  dst_representation: RepresentationType;
  relation_type: RepresentationRelationType;
  mathematical_content: string; // 共同表达的数学内容（向后兼容）
  src_object_id: string;
  dst_object_id: string | null;
  textbook_evidence: string;
  tb_evidence: string | null;
  is_system_inference: boolean;
  // 任务四补充 13.3 详细字段（可选，黄金课时必填）
  shared_mathematical_meaning?: string; // 共同数学含义
  retained_information?: string; // 保持的信息
  highlighted_information?: string; // 突出的信息
  omitted_information?: string; // 省略的信息
  newly_added_information?: string; // 新增的信息
  transformation_action?: TransformationAction; // 转换动作
  representation_function?: RepresentationFunction; // 表征作用
  mainline_role?: string; // 在本课内容主线中的作用
  teacher_guide_evidence_ids?: string[]; // 教师用书证据 ID
  source_type?: ClaimSourceType; // 来源类型
  confidence?: SegmentationConfidence;
  review_status?: LessonReviewStatus;
};

// 表征功能独立记录（用于表征作用分析）
export type RepresentationFunctionRecord = {
  id: string;
  lesson_id: string;
  representation_relation_id: string;
  function: RepresentationFunction;
  function_description: string; // 具体说明该作用在本课中如何体现
  evidence_object_ids: string[];
  teacher_guide_evidence_ids: string[];
  source_type: ClaimSourceType;
  confidence: SegmentationConfidence;
  review_status: LessonReviewStatus;
};

// 练习序列位置词表（任务四补充 16.6）
export type ProblemSequenceRole =
  | "FIRST_DIRECT_APPLICATION" // 首次直接运用
  | "SAME_STRUCTURE_REPETITION" // 同结构重复
  | "DATA_VARIATION" // 数据变化
  | "CONTEXT_VARIATION" // 情境变化
  | "REPRESENTATION_VARIATION" // 表征变化
  | "QUESTION_VARIATION" // 问题变化
  | "RELATION_DIRECTION_VARIATION" // 关系方向变化
  | "SUPPORT_REDUCTION" // 显性支撑减少
  | "MULTI_ELEMENT_COMBINATION" // 综合多个前置要素
  | "NEW_CONTEXT_APPLICATION"; // 新情境应用

// 教师用书核验状态（任务四补充 步骤7）
export type GuideSupportStatus =
  | "SUPPORTED_BY_GUIDE" // 教师用书明确支持
  | "PARTIALLY_SUPPORTED_BY_GUIDE" // 部分支持
  | "NOT_MENTIONED_IN_GUIDE" // 教师用书未提及
  | "CONFLICTS_WITH_GUIDE"; // 与教师用书冲突

// 第五层-1：题目关系
export type ProblemRelation = {
  id: string;
  lesson_id: string;
  src_object_id: string; // 比较源（如练习）
  dst_object_id: string; // 比较目标（如例题或前题）
  relation_type: ProblemRelationType;
  evidence_object_ids: string[];
  confidence: SegmentationConfidence;
  // 任务四补充 16.1 扩展字段（可选，黄金课时必填）
  primary_reference_object_id?: string; // 主要承接对象
  secondary_reference_object_id?: string | null; // 次要承接对象
  position_in_sequence?: ProblemSequenceRole; // 在练习序列中的位置
  structural_relation?: string; // 结构关系说明
  representation_relation?: string; // 表征关系说明
  teacher_guide_evidence_ids?: string[]; // 教师用书证据 ID
  source_type?: ClaimSourceType;
  review_status?: LessonReviewStatus;
};

// 第五层-2：保持项
export type ProblemRetainedDimension = {
  id: string;
  problem_relation_id: string;
  dimension: RetainedDimension;
  retained_value: string;
  evidence_object_ids: string[];
  confidence: SegmentationConfidence;
};

// 第五层-3：变化项
export type ProblemChangedDimension = {
  id: string;
  problem_relation_id: string;
  dimension: ChangedDimension;
  source_value: string;
  target_value: string;
  evidence_object_ids: string[];
  confidence: SegmentationConfidence;
};

// 第五层-4：任务要求变化
export type ProblemRequirementChange = {
  id: string;
  problem_relation_id: string;
  change_type: RequirementChangeType;
  description: string;
  evidence_object_ids: string[];
};

// 关键教材节点
export type LessonKeyNode = {
  id: string;
  lesson_id: string;
  object_id: string;
  key_node_basis: string; // 为何是关键节点
  affected_relation_ids: string[];
  evidence_ids: string[];
  confidence: SegmentationConfidence;
  review_status: LessonReviewStatus;
};

// ============================================================================
// 任务四补充：内容主线证据化结构（节点-转换-证据-备选）
// ============================================================================

// 主线变化类型（任务四补充 步骤5）
export type MainlineChangeType =
  | "MATHEMATICAL_OBJECT_CHANGE"
  | "QUESTION_CHANGE"
  | "TASK_CHANGE"
  | "REPRESENTATION_CHANGE"
  | "SUPPORT_CHANGE"
  | "CONTEXT_CHANGE"
  | "RESPONSE_REQUIREMENT_CHANGE";

// 主线基本信息（任务四补充 18.1）
export type LessonMainline = {
  mainline_id: string;
  lesson_id: string;
  main_mathematical_object: string; // 核心数学对象
  initial_object_state: string; // 起始状态
  developed_object_state: string; // 发展状态
  object_change_description: string; // 对象变化描述
  mainline_summary: string; // 主线摘要（教师可读文字）
  source_type: ClaimSourceType;
  evidence_ids: string[]; // 教师用书证据 ID
  evidence_object_ids: string[]; // 教材对象 ID
  guide_support_status: GuideSupportStatus; // 教师用书核验状态
  confidence: SegmentationConfidence;
  review_status: LessonReviewStatus;
  analysis_version: string;
};

// 主线节点（任务四补充 18.2）
export type LessonMainlineNode = {
  mainline_node_id: string;
  mainline_id: string;
  lesson_id: string;
  sequence_index: number;
  node_title: string; // 节点标题（如"起点"、"关键变化"、"表征转化"、"独立运用"、"练习扩展"）
  node_description: string; // 节点描述
  main_object_ids: string[]; // 主要教材对象
  mathematical_object_state: string; // 数学对象状态
  question_state: string; // 问题状态
  task_state: string; // 任务状态
  representation_state: string; // 表征状态
  source_type: ClaimSourceType;
  evidence_ids: string[];
  review_status: LessonReviewStatus;
};

// 主线转换（任务四补充 18.3）
export type LessonMainlineTransition = {
  transition_id: string;
  mainline_id: string;
  lesson_id: string;
  from_node_id: string;
  to_node_id: string;
  mathematical_change: string; // 数学对象变化
  question_change: string; // 问题变化
  task_change: string; // 任务变化
  representation_change: string; // 表征变化
  support_change: string; // 支撑变化
  context_change: string; // 情境变化
  response_requirement_change: string; // 应答要求变化
  transition_basis: string; // 转换依据
  change_types: MainlineChangeType[]; // 变化类型集合
  source_type: ClaimSourceType;
  evidence_ids: string[];
  guide_support_status: GuideSupportStatus;
  confidence: SegmentationConfidence;
  review_status: LessonReviewStatus;
};

// 主线证据（任务四补充 18.4）
export type LessonMainlineEvidence = {
  mainline_evidence_id: string;
  mainline_id: string;
  lesson_id: string;
  node_id: string | null; // 关联节点
  transition_id: string | null; // 关联转换
  evidence_type: ClaimSourceType;
  textbook_object_ids: string[];
  teacher_guide_evidence_ids: string[];
  evidence_description: string;
  support_status: GuideSupportStatus;
};

// 备选主线（任务四补充 18.5）
export type LessonMainlineAlternative = {
  alternative_mainline_id: string;
  lesson_id: string;
  alternative_description: string; // 备选主线描述
  supporting_evidence_ids: string[]; // 支持证据
  conflicting_evidence_ids: string[]; // 冲突证据
  reason_not_selected: string; // 未选用原因
  review_status: LessonReviewStatus;
};

// ============================================================================
// 任务四补充：例题深度分析链（第十四条）
// ============================================================================

// 例题分析链的环节标识
export type ExampleChainComponent =
  | "scene_info" // 情境信息
  | "conditions" // 条件
  | "core_question" // 核心问题
  | "operation_observation" // 操作或观察
  | "representation_change" // 表征变化
  | "mathematical_expression" // 数学表达
  | "method_conclusion" // 方法、结论或结果
  | "followup_connection"; // 试一试及练习承接

// 例题深度分析链（任务四补充 第十四条）
export type ExampleAnalysisChain = {
  chain_id: string;
  lesson_id: string;
  example_object_id: string; // 例题对象 ID
  // 14.1 情境与条件
  scene_info: string; // 情境由哪些教材对象构成
  scene_objects: string[]; // 情境教材对象 ID
  conditions_location: string; // 条件位于文字/图/表/气泡
  direct_conditions: string[]; // 直接给出的条件
  inferred_conditions: string[]; // 需从图中读取的条件
  shared_conditions: string[]; // 共用条件
  decorative_info: string[]; // 与解题无关的装饰信息
  // 14.2 核心问题
  core_question: string; // 核心问题文本
  question_object_id: string | null; // 问题由哪个对象提出
  question_target: string; // 问题针对什么数学对象
  question_structure: string; // 问题与条件形成的结构
  subsequent_question_change: string | null; // 后续问题改变了什么
  // 14.3 操作与观察
  operation_required: string; // 教材要求学生做什么
  operation_object: string; // 操作或观察对象
  exposed_structure: string; // 该操作暴露了什么结构
  operation_usage: string; // 操作结果怎样被后续使用
  // 14.4 人物表达
  character_speeches: { character_id: string; speech_function: string; content: string; bound_object_id: string }[];
  speech_relations: string; // 多个人物表达之间的关系
  // 14.5 数学表达
  formulas: string[]; // 算式列表
  formula_meaning: string; // 算式对应哪些条件和问题
  formula_number_mapping: string; // 算式中数字/符号对应什么
  multiple_methods: string | null; // 是否存在多种方法
  method_relation: string | null; // 多种方法保持什么、改变什么
  // 14.6 例题终点
  endpoint_type: "textbook_conclusion" | "character_method" | "fill_in_completion" | "concrete_instance" | "student_generalization";
  endpoint_description: string;
  // 试一试及练习承接
  followup_connection: string; // 与试一试和练习的承接关系
  followup_object_ids: string[];
  // 证据
  evidence_ids: string[];
  evidence_object_ids: string[];
  source_type: ClaimSourceType;
  confidence: SegmentationConfidence;
  review_status: LessonReviewStatus;
};

// ============================================================================
// 任务四补充：浅层分析拦截（第二十条）
// ============================================================================

// 浅层分析拦截问题类别
export type AnalysisReviewIssueCategory =
  | "MAINLINE_SHALLOW" // 内容主线问题
  | "REPRESENTATION_GENERIC" // 表征分析问题
  | "EXAMPLE_ANALYSIS_INCOMPLETE" // 例题分析问题
  | "PRACTICE_ANALYSIS_INCOMPLETE" // 练习分析问题
  | "EVIDENCE_MISSING" // 证据缺失
  | "INFERENCE_OVERREACH"; // 推断越界

// 浅层分析拦截结果
export type AnalysisReviewIssue = {
  issue_id: string;
  lesson_id: string;
  category: AnalysisReviewIssueCategory;
  issue_description: string;
  detected_pattern: string; // 检测到的具体模式
  affected_data_ids: string[]; // 受影响的数据 ID
  severity: "blocking" | "non-blocking"; // 阻断/非阻断
  suggested_fix: string; // 建议修复
  resolution_status: "pending" | "fixed" | "wontfix";
  resolution_note: string | null;
};

// 证据支持的结论
export type EvidenceBackedClaim = {
  id: string;
  lesson_id: string;
  claim_type: string;
  claim_text: string;
  related_object_ids: string[];
  related_relation_ids: string[];
  claim_source_type: ClaimSourceType;
  source_evidence_ids: string[]; // 教师用书证据 ID
  inference_basis: string | null; // 系统推断依据
  confidence: SegmentationConfidence;
  review_status: LessonReviewStatus;
  reviewer: string | null;
};

// 课时分析卡
export type LessonAnalysis = {
  id: string;
  lesson_id: string;
  content_sequence_summary: string; // 教材内容主线
  representation_summary: string; // 表征关系摘要
  example_try_relation: string; // 例题与试一试关系摘要
  example_practice_relation: string; // 例题与练习关系摘要
  practice_progression: string; // 练习之间的保持与变化摘要
  key_nodes_summary: string; // 关键节点摘要
  tb_evidence_summary: string; // 教师用书证据摘要
  system_inferences: string; // 系统推断摘要
  pending_issues: string[]; // 待审核问题
  analysis_version: string;
  review_status: LessonReviewStatus;
};

// 前序数据回流请求
export type UpstreamCorrectionRequest = {
  id: string;
  detected_in_task: "task-4";
  target_task: "task-1" | "task-2" | "task-3";
  affected_object_ids: string[];
  issue_type: string;
  issue_description: string;
  evidence_ids: string[];
  suggested_action: string;
  blocking_status: "blocking" | "non-blocking";
  review_status: LessonReviewStatus;
  resolution_note: string | null;
  resolved_at: string | null;
};

// 分析版本
export type AnalysisVersion = {
  version_id: string;
  lesson_catalog_version: string;
  textbook_parsing_version: string;
  teacher_guide_processing_version: string;
  relation_schema_version: string;
  created_at: string;
  reviewed_at: string | null;
  reviewer: string | null;
  status: "draft" | "frozen";
  change_log: string[];
};
