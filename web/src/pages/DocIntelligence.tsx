import { useCallback, useEffect, useMemo, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import {
  BrainCircuit,
  HeartPulse,
  Loader2,
  FileText,
  Network,
  Layers,
  Boxes,
  GitMerge,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Upload,
  History,
  FlaskConical,
  Trash2,
  MapPin,
  Save,
  ChevronDown,
  Sparkles,
} from "lucide-react";

type ChapterListItem = {
  chapter_id: string;
  chapter_name?: string;
  page_range?: string;
  created_at?: string;
  metrics?: Record<string, unknown>;
  iteration_count?: number;
};

type AnnotationItem = {
  annotation_id: string;
  element_id: string;
  domain_type: string;
  confidence?: number;
  properties?: Record<string, unknown>;
  content?: string | null;
  page_index?: number | null;
  // 识别对象在页面中的归一化区域（0~1，相对整页），供「页面标注视图」定位高亮
  bbox?: { x1: number; y1: number; x2: number; y2: number } | null;
};

type RelationItem = {
  relation_id?: string;
  source_id: string;
  target_id: string;
  domain_type: string;
  confidence?: number;
};

// 板块切割后的完整板块（标题 + 其后归组内容，边界精确到下一个板块标题）
type BoardItem = {
  title_element_id: string;
  board_type: string;
  title: string;
  page_index?: number | null;
  element_ids?: string[];
  content?: string;
  // 引擎自动生成的原文字（人工提交标准文字后，content 会被覆盖为修正文字，原文保留在此）
  engine_content?: string;
  // 该板块涉及到的页面（章节内页序），用于逐页展示裁剪图
  pages?: number[];
};

// 板块文字标注（自迭代）：每个板块的用户标准文字 + 学习样本状态
type BoardDetail = {
  boards: BoardItem[];
  board_texts: Record<string, string>;
  // AI 自迭代生成的文字草稿（board_index -> 草稿），供人工审核修改
  board_drafts?: Record<string, string>;
  learning_samples: Record<string, unknown>;
};

type ChapterDetail = {
  chapter_id: string;
  chapter_name?: string;
  page_range?: string;
  created_at?: string;
  annotations: AnnotationItem[];
  relations: RelationItem[];
  boards?: BoardItem[];
  metrics?: Record<string, unknown>;
  iterations?: Array<Record<string, unknown>>;
};

// 板块类型 → 中文标签（education-content 领域包 0.4.0）
const DOMAIN_TYPE_LABELS: Record<string, string> = {
  example: "例题",
  try: "试一试",
  "think-do": "想想做做",
  exercise: "练习",
  operation: "动手做",
  "thinking-question": "思考题",
  reflection_prompt: "思考提示",
  learner_character: "角色",
  speech: "对话气泡",
  worked_example: "示例",
  practice: "练习",
};

// 板块类型 → 高亮描边颜色（用于页面标注视图区域定位）
const DOMAIN_TYPE_COLORS: Record<string, string> = {
  example: "#0f766e", // teal-700
  try: "#b45309", // amber-700
  "think-do": "#7c3aed", // violet-700
  exercise: "#1d4ed8", // blue-700
  operation: "#be123c", // rose-700
  "thinking-question": "#c2410c", // orange-700
};

type Choice = "correct" | "wrong" | null;

// 可修正的板块类型选项（education-content 领域包 0.4.0 六类）
const DOMAIN_TYPE_OPTIONS = [
  "example",
  "try",
  "think-do",
  "exercise",
  "operation",
  "thinking-question",
];

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

export default function DocIntelligence() {
  const [serviceStatus, setServiceStatus] = useState<"unknown" | "up" | "down">("unknown");
  const [checking, setChecking] = useState(false);

  // 解析
  const [analyzing, setAnalyzing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [pageRange, setPageRange] = useState("0-15");
  const [chapterName, setChapterName] = useState("第一单元");

  // 章节列表 & 详情
  const [chapters, setChapters] = useState<ChapterListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ChapterDetail | null>(null);

  // 标注
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  // 用户修正的板块类型（annotation_id -> domain_type）
  const [labelEdits, setLabelEdits] = useState<Record<string, string>>({});
  // 用户解释说明（annotation_id -> 说明，供模型/引擎学习）
  const [noteEdits, setNoteEdits] = useState<Record<string, string>>({});
  const [reviewer, setReviewer] = useState("教师");
  const [submitting, setSubmitting] = useState(false);

  // 「页面标注视图」：当前查看页 + 被选中的识别对象
  const [activePage, setActivePage] = useState<number | null>(null);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);

  // 删除
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // 板块文字标注（自迭代）：标准文字内容 / 加载状态 / 保存状态 / 每板块当前查看页
  const [boardDetail, setBoardDetail] = useState<BoardDetail | null>(null);
  const [boardLoading, setBoardLoading] = useState(false);
  const [boardSaving, setBoardSaving] = useState(false);
  const [boardDrafts, setBoardDrafts] = useState<Record<string, string>>({});
  const [boardActivePages, setBoardActivePages] = useState<Record<string, number>>({});
  const [boardCollapsed, setBoardCollapsed] = useState<Record<string, boolean>>({});
  const [boardSavedAt, setBoardSavedAt] = useState<Record<string, string>>({});
  const [rillNotice, setRillNotice] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const loadChapters = useCallback(async () => {
    try {
      const resp = await fetch("/api/di/v1/textbook/chapters/list");
      if (!resp.ok) return;
      const data = (await resp.json()) as { chapters: ChapterListItem[] };
      setChapters(data.chapters ?? []);
    } catch {
      /* 服务未启动时静默 */
    }
  }, []);

  const checkHealth = useCallback(async () => {
    setChecking(true);
    try {
      const resp = await fetch("/api/di/health");
      setServiceStatus(resp.ok ? "up" : "down");
      if (resp.ok) await loadChapters();
    } catch {
      setServiceStatus("down");
    } finally {
      setChecking(false);
    }
  }, [loadChapters]);

  useEffect(() => {
    void checkHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 加载板块列表 + 已保存的标准文字（供「板块文字标注（自迭代）」视图使用）
  const loadBoardDetail = useCallback(async (id: string) => {
    setBoardLoading(true);
    try {
      const resp = await fetch(`/api/di/v1/textbook/chapters/${id}/boards`);
      if (!resp.ok) return;
      const data = (await resp.json()) as BoardDetail;
      setBoardDetail(data);
      // 回填草稿：人工已提交的标准文字优先；未提交的板块回填 AI 自迭代草稿供审核
      const drafts: Record<string, string> = {};
      const savedAt: Record<string, string> = {};
      for (const [k, v] of Object.entries(data.board_texts ?? {})) {
        if (v) drafts[k] = v;
      }
      for (const [k, v] of Object.entries(data.board_drafts ?? {})) {
        if (!drafts[k] && v) drafts[k] = v;
      }
      for (const [k, v] of Object.entries(data.learning_samples ?? {})) {
        const entry = v as { corrected_at?: string };
        if (entry?.corrected_at) savedAt[k] = entry.corrected_at;
      }
      setBoardDrafts(drafts);
      setBoardSavedAt(savedAt);
    } catch {
      /* 板块接口异常时静默，不阻断主视图 */
    } finally {
      setBoardLoading(false);
    }
  }, []);

  // 提交标准文字（board_index -> 标准文字），落盘到学习样本库
  const saveBoardTexts = useCallback(async () => {
    if (!detail || !selectedId) return;
    // 仅提交有内容的草稿（避免覆盖已有标准文字）
    const texts: Record<string, string> = {};
    for (const [k, v] of Object.entries(boardDrafts)) {
      if (v && v.trim() !== "") texts[k] = v.trim();
    }
    if (Object.keys(texts).length === 0) {
      setError("请先在板块中输入标准文字后再提交");
      return;
    }
    setBoardSaving(true);
    setError(null);
    try {
      const resp = await fetch(`/api/di/v1/textbook/chapters/${selectedId}/board-texts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(texts),
      });
      const data = (await resp.json()) as {
        success?: boolean;
        error?: string;
        rill?: { evaluated?: boolean; iteration?: Record<string, unknown> };
      };
      if (!resp.ok || data.success === false) {
        setError(data.error || `标准文字提交失败 (HTTP ${resp.status})`);
        return;
      }
      // 更新已保存时间戳
      const now = new Date().toISOString();
      setBoardSavedAt((p) => {
        const next = { ...p };
        for (const k of Object.keys(texts)) next[k] = now;
        return next;
      });
      // rill 回灌状态提示
      if (data.rill?.evaluated) {
        setRillNotice("本次提交已回灌 rill 自学习评估");
      } else {
        setRillNotice("板块文字已保存，但 rill 回灌未完成（可查看迭代历史中的降级原因）");
      }
      // 刷新板块详情（含裁剪图/草稿）；同步刷新章节详情使「自学习迭代历史」展示本次 rill 回灌
      const [boardData] = await Promise.all([
        fetch(`/api/di/v1/textbook/chapters/${selectedId}/boards`).then((r) =>
          r.ok ? (r.json() as Promise<BoardDetail>) : null,
        ),
      ]);
      if (boardData) setBoardDetail(boardData);
      const chapterResp = await fetch(`/api/di/v1/textbook/chapters/${selectedId}`);
      if (chapterResp.ok) {
        const chapterData = (await chapterResp.json()) as { chapter?: ChapterDetail };
        if (chapterData.chapter) setDetail(chapterData.chapter);
      }
      await loadChapters();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBoardSaving(false);
    }
  }, [detail, selectedId, boardDrafts, loadBoardDetail, loadChapters]);

  const runAnalyze = useCallback(async () => {
    if (!file) {
      setError("请先选择教材 PDF 文件");
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("page_range", pageRange);
      form.append("chapter_name", chapterName);
      const resp = await fetch("/api/di/v1/textbook/chapters/analyze", {
        method: "POST",
        body: form,
      });
      const data = (await resp.json()) as {
        success?: boolean;
        error?: string;
        chapter?: ChapterDetail;
      };
      if (!resp.ok || data.success === false) {
        setError(data.error || `解析失败 (HTTP ${resp.status})`);
        // 兜底：即使响应异常，引擎可能已在后台完成解析并落盘，刷新列表让新章节可见
        await loadChapters();
        return;
      }
      if (data.chapter) {
        setDetail(data.chapter);
        setSelectedId(data.chapter.chapter_id);
        setChoices({});
        setLabelEdits({});
        setNoteEdits({});
        setActivePage(null);
        setSelectedAnnotationId(null);
        void loadBoardDetail(data.chapter.chapter_id);
      }
      await loadChapters();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      // 兜底：请求中断/超时后，主动刷新列表，避免后端已完成解析却看不到结果
      await loadChapters();
    } finally {
      setAnalyzing(false);
    }
  }, [file, pageRange, chapterName, loadChapters, loadBoardDetail]);

  const deleteChapter = useCallback(
    async (id: string, name?: string) => {
      if (!window.confirm(`确认删除章节「${name || id}」？\n将同时删除其解析结果、标注历史与自学习数据，且不可恢复。`)) {
        return;
      }
      setDeletingId(id);
      setError(null);
      try {
        const resp = await fetch(`/api/di/v1/textbook/chapters/${id}`, { method: "DELETE" });
        if (!resp.ok) {
          const data = (await resp.json().catch(() => ({}))) as { detail?: string };
          setError(data.detail || `删除失败 (HTTP ${resp.status})`);
          return;
        }
        if (selectedId === id) {
          setSelectedId(null);
          setDetail(null);
          setChoices({});
          setLabelEdits({});
          setNoteEdits({});
          setActivePage(null);
          setSelectedAnnotationId(null);
        }
        await loadChapters();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setDeletingId(null);
      }
    },
    [selectedId, loadChapters],
  );

  const openChapter = useCallback(async (id: string) => {
    setSelectedId(id);
    setError(null);
    // 切换章节时清空板块标注状态
    setBoardDetail(null);
    setBoardDrafts({});
    setBoardSavedAt({});
    setBoardActivePages({});
    setBoardCollapsed({});
    try {
      const resp = await fetch(`/api/di/v1/textbook/chapters/${id}`);
      const data = (await resp.json()) as { chapter?: ChapterDetail };
      if (resp.ok && data.chapter) {
        setDetail(data.chapter);
        setChoices({});
        setLabelEdits({});
        setNoteEdits({});
        setActivePage(null);
        setSelectedAnnotationId(null);
        void loadBoardDetail(id);
      } else {
        setError("无法加载章节详情");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [loadBoardDetail]);

  const submitAnnotation = useCallback(async () => {
    if (!detail || !selectedId) return;
    const correct = Object.entries(choices)
      .filter(([, c]) => c === "correct")
      .map(([id]) => id);
    const wrong = Object.entries(choices)
      .filter(([, c]) => c === "wrong")
      .map(([id]) => id);
    // 仅提交被用户改动过的板块类型（与引擎识别不一致的）
    const originalTypes = Object.fromEntries(
      (detail.annotations ?? []).map((a) => [a.annotation_id, a.domain_type]),
    );
    const labels = Object.fromEntries(
      Object.entries(labelEdits).filter(
        ([id, v]) => v && v !== originalTypes[id],
      ),
    );
    // 仅提交非空的解释说明
    const notes = Object.fromEntries(
      Object.entries(noteEdits).filter(([, v]) => v && v.trim() !== ""),
    );
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch("/api/di/v1/textbook/chapters/annotate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chapter_id: selectedId,
          reviewer,
          correct,
          wrong,
          labels,
          notes,
          reason: "人工审核教材章节对象标注",
        }),
      });
      const data = (await resp.json()) as {
        success?: boolean;
        error?: string;
        chapter?: ChapterDetail;
      };
      if (!resp.ok || data.success === false) {
        setError(data.error || `标注提交失败 (HTTP ${resp.status})`);
        return;
      }
      if (data.chapter) {
        setDetail(data.chapter);
        setChoices({});
        setLabelEdits({});
        setNoteEdits({});
      }
      await loadChapters();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, [detail, selectedId, choices, reviewer, labelEdits, noteEdits, loadChapters]);

  const annotations = detail?.annotations ?? [];
  const boards = detail?.boards ?? [];
  // 暂时隐藏「板块结构（板块切割）」卡片（用户要求，后续可恢复）
  const SHOW_BOARD_STRUCTURE = false;
  // 当前标注项选中的板块类型（优先用户修正值，否则引擎识别值）
  const effectiveType = (a: AnnotationItem) => labelEdits[a.annotation_id] ?? a.domain_type;
  const relations = detail?.relations ?? [];
  const iterations = detail?.iterations ?? [];
  const metrics = detail?.metrics ?? {};

  // 页面标注视图：按章节内页序分组，仅保留带 bbox 的识别对象
  const pageAnnotations = useMemo(() => {
    const map = new Map<number, AnnotationItem[]>();
    for (const a of annotations) {
      if (typeof a.page_index !== "number" || !a.bbox) continue;
      const arr = map.get(a.page_index) ?? [];
      arr.push(a);
      map.set(a.page_index, arr);
    }
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
  }, [annotations]);

  // 定位到某页并把某个对象设为选中（页面视图与列表双向联动）
  const focusAnnotation = useCallback((annotationId: string, pageIndex: number) => {
    setActivePage(pageIndex);
    setSelectedAnnotationId(annotationId);
    document.getElementById(`anno-${annotationId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, []);

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={14}
        eyebrow="DOCUMENT INTELLIGENCE"
        title="教材智能解析与标注"
        subtitle="编排下沉到引擎：按章节解析 → 结构恢复 → education-content 教育对象识别 → 人工标注 → 自学习回灌。需先运行「启动文档智能解析服务.bat」启动 FastAPI 服务。"
        right={
          <div className="flex items-center gap-2">
            <button
              onClick={checkHealth}
              disabled={checking}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-sm border border-ink-line bg-paper hover:bg-paper-2 transition-colors disabled:opacity-60"
            >
              <HeartPulse size={13} className="text-teal" />
              {checking ? "检测中..." : "检测服务"}
            </button>
          </div>
        }
      />

      {/* 服务状态 */}
      <Card accent="teal" className="mb-6">
        <div className="flex items-center gap-3">
          <BrainCircuit size={18} className="text-teal" />
          <div className="flex-1">
            <div className="text-sm font-medium text-ink">document-intelligence 服务</div>
            <div className="text-xs text-ink-3 mt-0.5">
              默认地址 http://localhost:8080 · 通过 /api/di/* 纯透传 · 编排在引擎 textbook 模块内
            </div>
          </div>
          <Badge tone={serviceStatus === "up" ? "ok" : serviceStatus === "down" ? "err" : "default"}>
            {serviceStatus === "up" ? "已连接" : serviceStatus === "down" ? "未连接" : "未检测"}
          </Badge>
        </div>
      </Card>

      {error && (
        <Card accent="vermilion" className="mb-6">
          <div className="flex items-start gap-3 text-err">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div className="text-sm leading-relaxed break-all">{error}</div>
          </div>
        </Card>
      )}

      {/* 一、按章节解析 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <Network size={18} className="text-vermilion" />
        <span className="chapter-num">一</span> 按章节解析
      </h2>
      <Card className="mb-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-3">
            <label className="block text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">
              教材 PDF 文件
            </label>
            <label className="flex items-center gap-2 border border-ink-line rounded-sm px-3 py-2.5 cursor-pointer hover:bg-paper-2 transition-colors">
              <Upload size={15} className="text-teal shrink-0" />
              <span className={cn("text-sm truncate", file ? "text-ink" : "text-ink-3")}>
                {file ? file.name : "选择扫描版教材 PDF（建议先只解析第一章）"}
              </span>
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
          <div>
            <label className="block text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">
              PDF 页序 page_range（0 起，含端点）
            </label>
            <input
              value={pageRange}
              onChange={(e) => setPageRange(e.target.value)}
              placeholder="如 0-15"
              className="w-full border border-ink-line rounded-sm px-3 py-2 text-sm bg-paper focus:outline-none focus:border-teal"
            />
            <p className="text-2xs text-ink-3 mt-1.5 leading-relaxed">
              ⚠ 这是 <span className="text-vermilion font-medium">PDF 文件内的物理页序</span>（第 1 页 = 0），
              不是书本上印刷的页码。扫描件里两者常有错位。
            </p>
          </div>
          <div>
            <label className="block text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">
              书本印刷页码（可选参考）
            </label>
            <input
              value={chapterName}
              onChange={(e) => setChapterName(e.target.value)}
              placeholder="仅用于命名，不影响切页"
              className="w-full border border-ink-line rounded-sm px-3 py-2 text-sm bg-paper focus:outline-none focus:border-teal"
            />
            <p className="text-2xs text-ink-3 mt-1.5 leading-relaxed">
              例如：若书本第 1 页在 PDF 里是第 3 页，则 PDF 页序从 2 开始。
            </p>
          </div>
          <div className="flex items-end">
            <button
              onClick={runAnalyze}
              disabled={analyzing || !file}
              className={cn(
                "inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-sm transition-colors disabled:opacity-60 w-full justify-center",
                analyzing ? "bg-ink-3 text-paper cursor-wait" : "bg-vermilion text-paper hover:bg-vermilion-deep",
              )}
            >
              {analyzing ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> 解析中...
                </>
              ) : (
                <>
                  <FlaskConical size={14} /> 解析该章节
                </>
              )}
            </button>
          </div>
        </div>
      </Card>

      {/* 板块结构：板块切割结果（标题 + 归组内容，边界精确到下一个板块标题） */}
      {SHOW_BOARD_STRUCTURE && detail && (
        <Card
          title="板块结构（板块切割）"
          subtitle="按阅读顺序将「板块标题 + 其后内容」归并为完整板块，边界精确到下一个板块标题"
          accent="teal"
          right={<Badge tone="teal">{boards.length}</Badge>}
          bodyClassName="p-0"
          className="mb-8"
        >
          {boards.length === 0 ? (
            <div className="p-5 text-sm text-ink-3">
              未切割到板块。若该章节为旧数据（不含板块结构），请删除后重新解析。
            </div>
          ) : (
            <ul className="divide-y divide-ink-line-2">
              {boards.map((b, i) => (
                <li key={b.title_element_id ?? i} className="px-5 py-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge tone="teal">{DOMAIN_TYPE_LABELS[b.board_type] ?? b.board_type}</Badge>
                    <span className="text-sm font-medium text-ink">{b.title || "（无标题文本）"}</span>
                    {typeof b.page_index === "number" && (
                      <span className="text-2xs text-ink-3 font-mono">第 {b.page_index} 页</span>
                    )}
                    <span className="text-2xs text-ink-3 font-mono">
                      {b.element_ids?.length ?? 0} 个元素
                    </span>
                    {b.engine_content && (
                      <span className="text-2xs text-teal inline-flex items-center gap-1">
                        <CheckCircle2 size={11} /> 已用标准文字修正
                      </span>
                    )}
                  </div>
                  {b.content ? (
                    <p className="text-sm text-ink mt-1.5 leading-relaxed whitespace-pre-wrap break-words">
                      {b.content}
                    </p>
                  ) : (
                    <p className="text-2xs text-ink-3 mt-1">（板块无正文内容）</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* 板块文字标注（自迭代）：裁剪图 + 用户撰写标准文字 + 提交学习 */}
      {detail && boardDetail && selectedId && (
        <Card
          title="板块文字标注（自迭代）"
          subtitle="引擎自动切割出的板块裁剪图，供撰写「标准文字」。当前为人工撰写阶段：请按图撰写通顺、完整的标准文字并提交；后续将由引擎尝试自动生成，再由你审核修改"
          accent="vermilion"
          right={
            <div className="flex items-center gap-2">
              <Badge tone="vermilion">
                {boardDetail.boards.length} 板块 · {Object.keys(boardDetail.board_texts ?? {}).length} 已标注
              </Badge>
              <button
                onClick={saveBoardTexts}
                disabled={boardSaving}
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-sm transition-colors disabled:opacity-60",
                  boardSaving ? "bg-ink-3 text-paper cursor-wait" : "bg-teal text-paper hover:bg-teal-deep",
                )}
              >
                {boardSaving ? (
                  <>
                    <Loader2 size={13} className="animate-spin" /> 保存中...
                  </>
                ) : (
                  <>
                    <Save size={13} /> 保存全部已填写文字
                  </>
                )}
              </button>
            </div>
          }
          bodyClassName="p-0"
          className="mb-8"
        >
          {rillNotice && (
            <div className="px-5 py-2 text-xs bg-ink-line-2/40 text-ink-2 border-b border-ink-line-2">
              {rillNotice}
            </div>
          )}
          {boardLoading ? (
            <div className="p-6 text-sm text-ink-3 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-teal" /> 加载板块裁剪图...
            </div>
          ) : (
            <ul className="divide-y divide-ink-line-2">
              {boardDetail.boards.map((b, i) => {
                const idx = String(i);
                const pages = b.pages && b.pages.length > 0 ? b.pages : [b.page_index ?? 0];
                const activePage =
                  boardActivePages[idx] ?? pages[0] ?? 0;
                const isCollapsed = boardCollapsed[idx];
                const savedAt = boardSavedAt[idx];
                const hasSaved = !!savedAt;
                return (
                  <li key={b.title_element_id ?? i} className="px-5 py-4">
                    {/* 板块头 */}
                    <button
                      onClick={() =>
                        setBoardCollapsed((p) => ({ ...p, [idx]: !p[idx] }))
                      }
                      className="w-full text-left flex items-center gap-2 flex-wrap"
                    >
                      <span className="text-ink-3 text-xs transition-transform">
                        <ChevronDown
                          size={14}
                          className={cn("transition-transform", isCollapsed && "-rotate-90")}
                        />
                      </span>
                      <Badge tone="vermilion">{DOMAIN_TYPE_LABELS[b.board_type] ?? b.board_type}</Badge>
                      <span className="text-sm font-medium text-ink">{b.title || "（无标题文本）"}</span>
                      <span className="text-2xs text-ink-3 font-mono">
                        第 {i} 板块
                      </span>
                      {pages.length > 0 && (
                        <span className="text-2xs text-ink-3 font-mono">
                          {pages.map((p) => `第 ${p} 页`).join(" · ")}
                        </span>
                      )}
                      <span className="text-2xs text-ink-3 font-mono">
                        {b.element_ids?.length ?? 0} 个元素
                      </span>
                      {hasSaved && (
                        <span className="text-2xs text-teal inline-flex items-center gap-1">
                          <CheckCircle2 size={11} /> 已提交 {new Date(savedAt!).toLocaleString()}
                        </span>
                      )}
                      {!hasSaved && boardDetail.board_drafts?.[idx] && (
                        <span className="text-2xs text-vermilion inline-flex items-center gap-1">
                          <Sparkles size={11} /> AI 自迭代草稿（待审核）
                        </span>
                      )}
                    </button>

                    {!isCollapsed && (
                      <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {/* 左：裁剪图（多页时可切换） */}
                        <div className="border border-ink-line rounded-sm overflow-hidden bg-paper">
                          {pages.length > 1 && (
                            <div className="flex items-center gap-1.5 px-3 py-2 bg-paper-2 border-b border-ink-line-2">
                              <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">
                                裁剪页
                              </span>
                              {pages.map((p) => (
                                <button
                                  key={p}
                                  onClick={() =>
                                    setBoardActivePages((s) => ({ ...s, [idx]: p }))
                                  }
                                  className={cn(
                                    "px-2 py-0.5 text-2xs rounded-sm border transition-colors",
                                    activePage === p
                                      ? "bg-vermilion text-paper border-vermilion"
                                      : "border-ink-line text-ink-3 hover:border-vermilion hover:text-vermilion",
                                  )}
                                >
                                  第 {p} 页
                                </button>
                              ))}
                            </div>
                          )}
                          <img
                            src={`/api/di/v1/textbook/chapters/${selectedId}/boards/${i}/crop?page_index=${activePage}`}
                            alt={`板块 ${i} 裁剪图（第 ${activePage} 页）`}
                            className="w-full h-auto block"
                            loading="lazy"
                          />
                          <div className="px-3 py-1.5 bg-paper-2 border-t border-ink-line-2 text-2xs text-ink-3">
                            板块裁剪区域（页序为章节内页序，非印刷页码）
                          </div>
                        </div>

                        {/* 右：引擎生成文字 + 标准文字输入 */}
                        <div className="flex flex-col gap-2.5">
                          <div>
                            {hasSaved ? (
                              <>
                                <label className="block text-2xs uppercase tracking-[0.15em] text-teal font-mono mb-1">
                                  已提交标准文字（人工修正已生效）
                                </label>
                                <div className="text-xs text-ink leading-relaxed whitespace-pre-wrap break-words bg-paper-2 rounded-sm p-2 max-h-40 overflow-y-auto">
                                  {boardDrafts[idx] ?? b.content ?? "（已保存标准文字）"}
                                </div>
                              </>
                            ) : (
                              <>
                                <label className="block text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1">
                                  引擎当前生成（仅参考，勿直接作为标准文字）
                                </label>
                                <div className="text-xs text-ink-3 leading-relaxed whitespace-pre-wrap break-words bg-paper-2 rounded-sm p-2 max-h-40 overflow-y-auto">
                                  {(b.engine_content ?? b.content) || "（引擎未生成文字）"}
                                </div>
                              </>
                            )}
                          </div>
                          <div className="flex-1">
                            <label className="block text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1">
                              标准文字（请按图撰写通顺完整文字，空位用（ ））
                            </label>
                            <textarea
                              value={boardDrafts[idx] ?? ""}
                              onChange={(e) =>
                                setBoardDrafts((p) => ({ ...p, [idx]: e.target.value }))
                              }
                              placeholder="例如：已知条件：…… 问题：…… 学生：…… 教师：……"
                              rows={6}
                              className="w-full border border-ink-line rounded-sm px-2.5 py-2 text-sm bg-paper focus:outline-none focus:border-vermilion leading-relaxed resize-y"
                            />
                          </div>
                          <div className="flex items-center justify-end">
                            <button
                              onClick={() => {
                                const v = (boardDrafts[idx] ?? "").trim();
                                if (!v) {
                                  setError("请先填写该板块的标准文字");
                                  return;
                                }
                                void saveBoardTexts();
                              }}
                              disabled={boardSaving || !(boardDrafts[idx] ?? "").trim()}
                              className={cn(
                                "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-sm transition-colors disabled:opacity-50",
                                "bg-vermilion text-paper hover:bg-vermilion-deep",
                              )}
                            >
                              <Save size={12} />
                              提交此板块
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}

      {/* 页面标注视图：整页原图 + 识别对象区域高亮，点击区域选择对象 */}
      {detail && pageAnnotations.length > 0 && selectedId && (
        <Card
          title="页面标注视图（板切割 + 区域定位）"
          subtitle="把识别对象按其在页面中的真实区域（bbox）高亮到原页图上，点击高亮框直接选中对应对象，避免整页一张图无法点选"
          accent="vermilion"
          right={<Badge tone="vermilion">{pageAnnotations.length} 页有对象</Badge>}
          className="mb-8"
        >
          {/* 页选择器 */}
          <div className="flex items-center gap-2 flex-wrap mb-4">
            <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">选择页</span>
            {pageAnnotations.map(([pageIndex]) => (
              <button
                key={pageIndex}
                onClick={() => setActivePage(pageIndex)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded-sm border transition-colors",
                  activePage === pageIndex
                    ? "bg-vermilion text-paper border-vermilion"
                    : "border-ink-line text-ink-3 hover:border-vermilion hover:text-vermilion",
                )}
              >
                第 {pageIndex} 页
              </button>
            ))}
          </div>

          {typeof activePage === "number" && selectedId && (
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
              {/* 原页图 + bbox 高亮层 */}
              <div className="lg:col-span-3 relative border border-ink-line rounded-sm overflow-hidden bg-paper">
                <img
                  src={`/api/di/v1/textbook/chapters/${selectedId}/pages/${activePage}/image`}
                  alt={`章节内页 ${activePage}`}
                  className="w-full h-auto block"
                  loading="lazy"
                />
                {pageAnnotations
                  .find(([p]) => p === activePage)?.[1]
                  .map((a) => {
                    if (!a.bbox) return null;
                    const color = DOMAIN_TYPE_COLORS[effectiveType(a)] ?? "#334155";
                    const isSelected = selectedAnnotationId === a.annotation_id;
                    return (
                      <button
                        key={a.annotation_id}
                        title={`${DOMAIN_TYPE_LABELS[effectiveType(a)] ?? effectiveType(a)} · ${a.content || "（无文本）"}`}
                        onClick={() => setSelectedAnnotationId(a.annotation_id)}
                        className="absolute"
                        style={{
                          left: `${a.bbox.x1 * 100}%`,
                          top: `${a.bbox.y1 * 100}%`,
                          width: `${(a.bbox.x2 - a.bbox.x1) * 100}%`,
                          height: `${(a.bbox.y2 - a.bbox.y1) * 100}%`,
                          border: `${isSelected ? 3 : 1.5}px solid ${color}`,
                          background: isSelected ? `${color}33` : "transparent",
                          boxShadow: isSelected ? `0 0 0 2px ${color}55` : "none",
                        }}
                      />
                    );
                  })}
              </div>

              {/* 该页对象清单 */}
              <div className="lg:col-span-2 border border-ink-line rounded-sm overflow-hidden">
                <div className="px-3 py-2 bg-paper-2 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">
                  第 {activePage} 页识别对象
                </div>
                <ul className="divide-y divide-ink-line-2 max-h-96 overflow-y-auto">
                  {pageAnnotations
                    .find(([p]) => p === activePage)?.[1]
                    .map((a) => {
                      const isSelected = selectedAnnotationId === a.annotation_id;
                      return (
                        <li key={a.annotation_id}>
                          <button
                            onClick={() => focusAnnotation(a.annotation_id, activePage)}
                            className={cn(
                              "w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-paper-2 transition-colors",
                              isSelected && "bg-paper-2",
                            )}
                          >
                            <span
                              className="w-2 h-2 rounded-full shrink-0"
                              style={{ background: DOMAIN_TYPE_COLORS[effectiveType(a)] ?? "#334155" }}
                            />
                            <span className="text-xs font-medium text-ink truncate">
                              {DOMAIN_TYPE_LABELS[effectiveType(a)] ?? effectiveType(a)}
                            </span>
                            <span className="text-2xs text-ink-3 truncate flex-1">
                              {a.content || "（无文本）"}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                </ul>
              </div>
            </div>
          )}
          {typeof activePage !== "number" && (
            <div className="p-4 text-sm text-ink-3">点击上方某一页，查看该页识别对象在原图中的位置。</div>
          )}
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* 已分析章节列表 */}
        <Card
          title="已分析章节"
          subtitle="点击查看结果与迭代历史"
          accent="teal"
          right={<Badge tone="teal">{chapters.length}</Badge>}
          bodyClassName="p-0"
        >
          <div className="max-h-[26rem] overflow-y-auto">
            {chapters.length === 0 ? (
              <div className="p-5 text-sm text-ink-3">暂无分析记录。</div>
            ) : (
              <ul className="divide-y divide-ink-line-2">
                {chapters.map((c) => (
                  <li key={c.chapter_id} className="group flex items-stretch">
                    <button
                      onClick={() => openChapter(c.chapter_id)}
                      className={cn(
                        "flex-1 text-left px-5 py-3 flex items-start gap-3 hover:bg-paper-2 transition-colors",
                        selectedId === c.chapter_id && "bg-paper-2",
                      )}
                    >
                      <FileText size={14} className="text-teal mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-ink truncate">
                          {c.chapter_name || "未命名章节"}
                        </div>
                        <div className="text-2xs text-ink-3 mt-0.5 font-mono break-all">
                          {c.page_range || "整册"}
                        </div>
                        <div className="text-2xs text-ink-3 mt-0.5">
                          迭代 {c.iteration_count ?? 0} 次 · {c.created_at ? new Date(c.created_at).toLocaleString() : ""}
                        </div>
                      </div>
                    </button>
                    <button
                      title="删除该章节解析记录"
                      disabled={deletingId === c.chapter_id}
                      onClick={() => deleteChapter(c.chapter_id, c.chapter_name)}
                      className={cn(
                        "shrink-0 px-3 flex items-center justify-center border-l border-ink-line-2 text-ink-3 transition-colors",
                        "hover:text-vermilion hover:bg-vermilion/5",
                        deletingId === c.chapter_id && "opacity-50 cursor-wait",
                      )}
                    >
                      {deletingId === c.chapter_id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Trash2 size={14} />
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        {/* 章节详情：识别对象 + 关系 */}
        <Card
          title="识别对象（可标注）"
          subtitle="education-content 识别出的教材对象，请逐条判定正确/错误"
          accent="vermilion"
          right={<Badge tone="vermilion">{annotations.length}</Badge>}
          bodyClassName="p-0"
          className="lg:col-span-2"
        >
          {!detail ? (
            <div className="p-5 text-sm text-ink-3">
              解析后在此展示并标注。选中左侧章节可复看历史结果。
            </div>
          ) : annotations.length === 0 ? (
            <div className="p-5 text-sm text-ink-3">未识别到对象。</div>
          ) : (
            <>
              <ul className="divide-y divide-ink-line-2 max-h-72 overflow-y-auto">
                {annotations.map((a) => {
                  const choice = choices[a.annotation_id] ?? null;
                  const isSelected = selectedAnnotationId === a.annotation_id;
                  return (
                    <li
                      key={a.annotation_id}
                      id={`anno-${a.annotation_id}`}
                      onClick={() => setSelectedAnnotationId(a.annotation_id)}
                      className={cn(
                        "px-5 py-3 flex items-start gap-3 cursor-pointer transition-colors",
                        isSelected && "bg-paper-2 ring-1 ring-inset ring-teal/30",
                      )}
                    >
                      <Boxes size={14} className="text-vermilion mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge tone={effectiveType(a) !== a.domain_type ? "warn" : "vermilion"}>
                            {DOMAIN_TYPE_LABELS[effectiveType(a)] ?? effectiveType(a)}
                          </Badge>
                          {effectiveType(a) !== a.domain_type && (
                            <span className="text-2xs text-vermilion font-medium">
                              已修正（原 {DOMAIN_TYPE_LABELS[a.domain_type] ?? a.domain_type}）
                            </span>
                          )}
                          {typeof a.confidence === "number" && (
                            <span className="text-2xs text-ink-3 font-mono">
                              置信 {(a.confidence * 100).toFixed(0)}%
                            </span>
                          )}
                          {typeof a.page_index === "number" && (
                            <span className="text-2xs text-ink-3 font-mono">
                              第 {a.page_index} 页（章节内页序）
                            </span>
                          )}
                        </div>
                        {/* 用户标注：修正板块类型 */}
                        <div className="mt-2 flex items-center gap-2">
                          <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono shrink-0">
                            标注板块
                          </label>
                          <select
                            value={effectiveType(a)}
                            onChange={(e) =>
                              setLabelEdits((p) => ({ ...p, [a.annotation_id]: e.target.value }))
                            }
                            className="border border-ink-line rounded-sm px-2 py-1 text-xs bg-paper focus:outline-none focus:border-teal"
                          >
                            {DOMAIN_TYPE_OPTIONS.map((t) => (
                              <option key={t} value={t}>
                                {DOMAIN_TYPE_LABELS[t] ?? t}
                              </option>
                            ))}
                          </select>
                        </div>
                        {/* 用户标注：解释说明（供模型/引擎学习） */}
                        <div className="mt-1.5">
                          <input
                            value={noteEdits[a.annotation_id] ?? ""}
                            onChange={(e) =>
                              setNoteEdits((p) => ({ ...p, [a.annotation_id]: e.target.value }))
                            }
                            placeholder="补充判断依据 / 说明（可选，帮助模型/引擎学习迭代）"
                            className="w-full border border-ink-line rounded-sm px-2 py-1 text-xs bg-paper focus:outline-none focus:border-teal"
                          />
                        </div>
                        {a.content ? (
                          <p className="text-sm text-ink mt-1.5 leading-relaxed whitespace-pre-wrap break-words">
                            {a.content}
                          </p>
                        ) : (
                          <p className="text-2xs text-ink-3 mt-1">（无原文文本）</p>
                        )}
                        {typeof a.page_index === "number" && selectedId && (
                          <button
                            onClick={() => focusAnnotation(a.annotation_id, a.page_index!)}
                            className="mt-2 inline-flex items-center gap-1.5 text-2xs px-2 py-1 rounded-sm border border-ink-line text-ink-3 hover:border-teal hover:text-teal transition-colors"
                          >
                            <MapPin size={12} className="text-teal" />
                            在页面区域中定位（点击高亮框）
                          </button>
                        )}
                        <div className="text-2xs text-ink-3 mt-1 font-mono break-all">
                          {a.annotation_id}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          title="判定为正确"
                          onClick={() => setChoices((p) => ({ ...p, [a.annotation_id]: choice === "correct" ? null : "correct" }))}
                          className={cn(
                            "inline-flex items-center gap-1 px-2 py-1 text-2xs rounded-sm border transition-colors",
                            choice === "correct"
                              ? "bg-teal text-paper border-teal"
                              : "border-ink-line text-ink-3 hover:border-teal hover:text-teal",
                          )}
                        >
                          <CheckCircle2 size={12} /> 正确
                        </button>
                        <button
                          title="判定为错误（作为反例回灌自学习）"
                          onClick={() => setChoices((p) => ({ ...p, [a.annotation_id]: choice === "wrong" ? null : "wrong" }))}
                          className={cn(
                            "inline-flex items-center gap-1 px-2 py-1 text-2xs rounded-sm border transition-colors",
                            choice === "wrong"
                              ? "bg-vermilion text-paper border-vermilion"
                              : "border-ink-line text-ink-3 hover:border-vermilion hover:text-vermilion",
                          )}
                        >
                          <XCircle size={12} /> 错误
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="px-5 py-4 border-t border-ink-line-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">审核人</span>
                  <input
                    value={reviewer}
                    onChange={(e) => setReviewer(e.target.value)}
                    className="border border-ink-line rounded-sm px-2 py-1 text-sm bg-paper focus:outline-none focus:border-teal"
                  />
                </div>
                <div className="flex-1" />
                <button
                  onClick={submitAnnotation}
                  disabled={submitting}
                  className={cn(
                    "inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-sm transition-colors disabled:opacity-60",
                    submitting ? "bg-ink-3 text-paper cursor-wait" : "bg-teal text-paper hover:bg-teal-deep",
                  )}
                >
                  {submitting ? (
                    <>
                      <Loader2 size={14} className="animate-spin" /> 提交并回灌...
                    </>
                  ) : (
                    <>
                      <RefreshCw size={14} /> 提交标注 · 触发自学习
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </Card>
      </div>

      {/* 二、对象关系 */}
      {detail && (
        <>
          <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
            <Layers size={18} className="text-teal" />
            <span className="chapter-num">二</span> 对象关系与指标
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <Card
              title="对象关系"
              subtitle="领域包识别出的对象间关系（练习关联例题等）"
              accent="teal"
              right={<Badge tone="teal">{relations.length}</Badge>}
              bodyClassName="p-0"
            >
              {relations.length === 0 ? (
                <div className="p-5 text-sm text-ink-3">未识别到关系。</div>
              ) : (
                <ul className="divide-y divide-ink-line-2 max-h-72 overflow-y-auto">
                  {relations.map((r, i) => (
                    <li key={i} className="px-5 py-3 flex items-start gap-3">
                      <GitMerge size={14} className="text-teal mt-0.5 shrink-0" />
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-ink">{r.domain_type}</div>
                        <div className="text-2xs text-ink-3 mt-0.5 font-mono break-all">
                          {r.source_id} → {r.target_id}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="解析指标" subtitle="本次解析与标注的统计" accent="vermilion" bodyClassName="p-0">
              <dl className="divide-y divide-ink-line-2">
                {[
                  { label: "章节名称", value: detail.chapter_name },
                  { label: "页码范围", value: detail.page_range },
                  { label: "创建时间", value: detail.created_at ? new Date(detail.created_at).toLocaleString() : "—" },
                  { label: "识别对象", value: metrics.annotations },
                  { label: "领域关系", value: metrics.domain_relations },
                  { label: "校验发现", value: metrics.validation_findings },
                  { label: "错误发现", value: metrics.error_findings },
                  { label: "回退", value: metrics.fallback_used },
                ].map((it) => (
                  <div key={it.label} className="px-5 py-3 flex items-center gap-3">
                    <dt className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono flex-1">
                      {it.label}
                    </dt>
                    <dd className="text-sm font-mono text-ink">{fmt(it.value)}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>

          {/* 三、自学习迭代历史 */}
          <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
            <History size={18} className="text-vermilion" />
            <span className="chapter-num">三</span> 自学习迭代历史（rill-ml）
          </h2>
          <Card className="mb-10" bodyClassName="p-0">
            {iterations.length === 0 ? (
              <div className="p-5 text-sm text-ink-3">
                尚无迭代。提交一次标注后，引擎会将人工判定回灌给 rill 自学习评估。
              </div>
            ) : (
              <ul className="divide-y divide-ink-line-2">
                {iterations.map((it, i) => (
                  <li key={i} className="px-5 py-4 flex items-start gap-3">
                    <RefreshCw size={14} className="text-teal mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-ink">迭代 #{fmt(it.iteration)}</span>
                        {it.source === "board_text" && <Badge tone="teal">板块文字</Badge>}
                        <Badge tone={Number(it.correct_count ?? 0) > 0 ? "ok" : "default"}>
                          正确 {fmt(it.correct_count)}
                        </Badge>
                        {Number(it.wrong_count ?? 0) > 0 && <Badge tone="err">错误 {fmt(it.wrong_count)}</Badge>}
                        {it.feedback_error && <Badge tone="warn">回灌降级</Badge>}
                      </div>
                      <div className="text-2xs text-ink-3 mt-1">
                        审核人 {fmt(it.reviewer)} · {it.reviewed_at ? new Date(String(it.reviewed_at)).toLocaleString() : ""}
                      </div>
                      {it.feedback && (
                        <pre className="mt-2 text-2xs font-mono text-ink-3 bg-paper-2 rounded-sm p-2 overflow-x-auto">
                          {JSON.stringify(it.feedback, null, 2)}
                        </pre>
                      )}
                      {it.feedback_error && (
                        <div className="mt-2 text-2xs text-err">{fmt(it.feedback_error)}</div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}