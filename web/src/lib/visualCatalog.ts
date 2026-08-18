/**
 * 视觉语义资源库 —— 前端读写后端目录的桥梁。
 *
 * 后端 document-intelligence 以 var/visual-semantic/catalog.json 为唯一真值，
 * 教材解析（_build_visual_semantic_annotations → catalog.match）直接基于它做
 * 图像匹配。前端「图标资源库 / 角色资源库」页面的编辑通过本模块写回后端目录，
 * 从而：
 *   1) 保存后刷新不丢失（后端持久化，刷新后从后端恢复）；
 *   2) 资源库真正成为解析教材的依据（后续解析立即使用新目录）。
 *
 * 经 Vite 代理 /api/di/* → http://localhost:8080/* 透传。
 */

const BASE = "/api/di/v1/visual-semantic";

export type CatalogProfile = {
  semantic_id: string;
  category: string;
  role_name: string | null;
  speaker_type: string | null;
  special_meaning: string;
  exact_sha256: string[];
  perceptual_hashes: string[];
  min_aspect_ratio: number;
  max_aspect_ratio: number;
  review_status: string;
};

export type VisualCatalog = {
  schema_version: number;
  matching: {
    max_dhash_distance: number;
    ambiguity_margin: number;
    min_information_score: number;
  };
  profiles: CatalogProfile[];
};

/** 获取完整资源库目录（后端唯一真值）。后端不可用时抛错。 */
export async function getCatalog(): Promise<VisualCatalog> {
  const resp = await fetch(`${BASE}/catalog`);
  if (!resp.ok) throw new Error(`GET 资源库失败 (HTTP ${resp.status})`);
  return resp.json();
}

/** 更新某个语义对象的可编辑元数据并持久化。 */
export async function saveProfile(
  semanticId: string,
  fields: Record<string, unknown>,
): Promise<CatalogProfile> {
  const resp = await fetch(
    `${BASE}/catalog/${encodeURIComponent(semanticId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    },
  );
  if (!resp.ok) throw new Error(`保存 ${semanticId} 失败 (HTTP ${resp.status})`);
  const data = await resp.json();
  return data.profile as CatalogProfile;
}

/** 上传某语义对象的图像作为匹配模板（更新哈希 → 解析真正按此图匹配）。 */
export async function uploadTemplate(
  semanticId: string,
  file: File,
): Promise<CatalogProfile> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(
    `${BASE}/templates/${encodeURIComponent(semanticId)}`,
    { method: "POST", body: form },
  );
  if (!resp.ok) throw new Error(`上传模板 ${semanticId} 失败 (HTTP ${resp.status})`);
  const data = await resp.json();
  return data.profile as CatalogProfile;
}

/** DataURL → File（用于把预览图回传为后端模板）。 */
export async function dataUrlToFile(
  dataUrl: string,
  filename: string,
): Promise<File> {
  const resp = await fetch(dataUrl);
  const blob = await resp.blob();
  return new File([blob], filename, { type: blob.type || "image/png" });
}

// ===== 图标类型 → 后端语义 id =====
export const iconTypeToSemanticId: Record<string, string> = {
  example: "sujiaoban.section.example-book-icon",
  try: "sujiaoban.section.try",
  "think-do": "sujiaoban.section.think-do",
  section: "sujiaoban.section.operation",
};

// ===== 角色名 → 后端语义 id（仅教材内置 6 角色有后端 profile） =====
export const characterNameToSemanticId: Record<string, string> = {
  青椒: "sujiaoban.character.qingjiao",
  蘑菇: "sujiaoban.character.mogu",
  番茄: "sujiaoban.character.fanqie",
  白菜: "sujiaoban.character.baicai",
  豌豆: "sujiaoban.character.wandou",
  茄子: "sujiaoban.character.qiezi",
};

// ===== 本地缓存（后端不可用时保底，避免刷新丢失） =====
export function loadLocal<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function saveLocal(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 超出 localStorage 配额时静默跳过（例如超大自定义图），不影响主流程
  }
}
