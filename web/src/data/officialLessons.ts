import type {
  OfficialLesson,
  LessonEvidence,
  ObjectLessonAssignment,
  LessonCatalog,
} from "./types";

// 教材版权数据（正式课时划分等）不随源码发布，保留类型与空结构。
export const officialLessons: OfficialLesson[] = [];
export const lessonEvidences: LessonEvidence[] = [];
export const objectLessonAssignments: ObjectLessonAssignment[] = [];
export const lessonCatalog: LessonCatalog = {
  catalog_id: "",
  edition_id: "tb-sjedu-3-1",
  version: "",
  source_data_version: "",
  teacher_guide_processing_version: "",
  textbook_parsing_version: "",
  created_at: "",
  reviewed_at: null,
  reviewer: null,
  status: "draft",
  change_log: [],
};