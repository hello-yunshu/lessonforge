import type { Textbook, Page } from "./types";

// 注意：教材版权数据（具体单元/页面/内容）不随源码发布，这里仅保留类型与空结构。
// 私有的真实教材数据存放于本地 .private/ 目录，不纳入公开仓库。

export type Unit = {
  id: string;
  no: number;
  name: string;
  start_page: number;
  end_page: number;
  parent_id?: string;
};

export type Section = {
  id: string;
  unit_id: string;
  no: number;
  name: string;
  pages: string[];
};

export const textbook: Textbook = {
  id: "tb-sjedu-3-1",
  version: "苏教版",
  grade: "三年级",
  volume: "上册",
  edition: "（教材版权数据未随源码发布）",
  pdf_hash: "",
  page_count: 0,
  created_at: "",
};

export const pages: Page[] = [];
export const units: Unit[] = [];
export const sections: Section[] = [];