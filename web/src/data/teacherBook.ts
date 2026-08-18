import type {
  TeacherBook,
  TeacherBookPage,
  TeacherBookUnit,
  TeacherBookLesson,
  TeacherBookReference,
} from "./types";

// 教材版权数据（教师用书内容等）不随源码发布，保留类型与空结构。
export const teacherBook: TeacherBook = {
  id: "tbk-sjedu-3-1",
  version: "苏教版",
  grade: "三年级",
  volume: "上册",
  edition: "（教材版权数据未随源码发布）",
  isbn: "",
  cip: "",
  pdf_file: "",
  pdf_page_count: 0,
  pdf_page_start: 0,
  pdf_page_end: 0,
  printed_page_start: 0,
  printed_page_end: 0,
  publisher: "",
  compiled_by: "",
};

export const teacherBookPages: TeacherBookPage[] = [];
export const teacherBookUnits: TeacherBookUnit[] = [];
export const teacherBookLessons: TeacherBookLesson[] = [];
export const teacherBookReferences: TeacherBookReference[] = [];

export const tbPagesBySection = (section: string): TeacherBookPage[] => [];
export const tbLessonsByUnit = (unitId: string): TeacherBookLesson[] => [];
export const tbRefsByLesson = (lessonId: string): TeacherBookReference[] => [];