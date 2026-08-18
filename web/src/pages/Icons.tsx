import { useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import ImageUpload from "@/components/ui/ImageUpload";
import { icons as initialIcons, iconVariants } from "@/data";
import type { Icon, IconType } from "@/data/types";
import { cn } from "@/lib/utils";
import {
  getCatalog,
  saveProfile,
  uploadTemplate,
  dataUrlToFile,
  loadLocal,
  saveLocal,
  iconTypeToSemanticId,
} from "@/lib/visualCatalog";
import { BookOpen, FlaskConical, Lightbulb, ClipboardList, Check, X, Plus, Pencil, Save, XCircle, RotateCcw, Trash2 } from "lucide-react";

// 本地持久化键：编辑字段 + 自定义图标图（后端不可用时的保底层）
const EDITS_KEY = "book3-icons-edits";
const IMAGES_KEY = "book3-icons-images";

const iconTypeMap = {
  example: { label: "例题书本图标", icon: BookOpen, tone: "vermilion" as const },
  try: { label: "试一试图标", icon: FlaskConical, tone: "teal" as const },
  "think-do": { label: "想想做做图标", icon: Lightbulb, tone: "teal" as const },
  section: { label: "栏目图标", icon: ClipboardList, tone: "default" as const },
};

const variantLabels: Record<string, string> = {
  gray: "灰度版",
  binary: "黑白二值版",
  scale: "多尺度版",
  blur: "轻度模糊版",
  jpeg: "JPEG 压缩版",
  brightness: "亮度对比度版",
  crop: "适度裁剪版",
  screenshot: "截图质量版",
};

const allowed = [
  "灰度版", "黑白二值版", "多尺度版本", "轻度模糊版本",
  "JPEG压缩版本", "亮度和对比度变化版本", "适度裁剪版本", "常见截图质量版本",
];
const disallowed = [
  "严重大角度旋转", "镜像翻转", "明显形变",
  "改变角色颜色", "生成教材中不存在的姿态", "改变角色五官或身体结构",
];

// 类型选项（用于编辑表单的下拉）
const typeOptions: { value: IconType; label: string }[] = [
  { value: "example", label: "example · 例题书本图标" },
  { value: "try", label: "try · 试一试图标" },
  { value: "think-do", label: "think-do · 想想做做图标" },
  { value: "section", label: "section · 栏目图标" },
];

// 生成新图标 ID
let iconIdSeq = 1000;
const genIconId = () => `ic-custom-${++iconIdSeq}`;

// 新图标录入草稿的初始值
const newIconDraftInit = (): {
  name: string;
  type: IconType;
  semantic: string;
  default_role: string;
  source_image: string;
  edit_note: string;
} => ({
  name: "",
  type: "example",
  semantic: "",
  default_role: "",
  source_image: "",
  edit_note: "新增图标",
});

export default function Icons() {
  // 初始状态合并本地持久化的教师编辑（刷新后不丢失）
  const [icons, setIcons] = useState<Icon[]>(() => {
    const edits = loadLocal<Record<string, Partial<Icon>>>(EDITS_KEY, {});
    return initialIcons.map((it) =>
      edits[it.id] ? { ...it, ...edits[it.id] } : it,
    );
  });
  const [selected, setSelected] = useState(icons[0].id);
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  // 编辑草稿：每个图标一份独立草稿
  const [drafts, setDrafts] = useState<Record<string, Partial<Icon>>>({});
  // 自定义图标图（icon_id → DataURL），加载时从本地恢复
  const [customIconImages, setCustomIconImages] = useState<Record<string, string>>(() =>
    loadLocal<Record<string, string>>(IMAGES_KEY, {}),
  );
  // 新图标录入表单
  const [newDraft, setNewDraft] = useState(newIconDraftInit());
  // 新图标原图预览
  const [newIconPreview, setNewIconPreview] = useState<string | null>(null);

  // 挂载时从后端拉取资源库目录（后端 var/visual-semantic/catalog.json 为解析真值）。
  // 后端特殊语义 / 角色名优先回填，保证「资源库作为解析依据」所见即所得。
  useEffect(() => {
    let cancelled = false;
    getCatalog()
      .then((cat) => {
        if (cancelled) return;
        const bySemantic = new Map(cat.profiles.map((p) => [p.semantic_id, p]));
        setIcons((list) =>
          list.map((it) => {
            const sid = iconTypeToSemanticId[it.type];
            const prof = sid ? bySemantic.get(sid) : undefined;
            if (!prof) return it;
            return {
              ...it,
              semantic: prof.special_meaning || it.semantic,
              default_role: prof.role_name || it.default_role,
            };
          }),
        );
      })
      .catch(() => {
        // 后端不可用时保留本地数据，不阻塞页面
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const icon = icons.find((i) => i.id === selected)!;
  const variants = iconVariants.filter((v) => v.icon_id === icon.id);
  const IconComp = iconTypeMap[icon.type].icon;
  const draft = drafts[icon.id];
  const isEditing = editingId === icon.id && editMode;

  // 进入编辑：把当前图标字段复制到草稿
  const startEdit = () => {
    setDrafts((d) => ({
      ...d,
      [icon.id]: {
        name: icon.name,
        type: icon.type,
        semantic: icon.semantic,
        default_role: icon.default_role,
        edit_note: icon.edit_note ?? "",
      },
    }));
    setEditingId(icon.id);
  };

  const cancelEdit = () => {
    setDrafts((d) => {
      const next = { ...d };
      delete next[icon.id];
      return next;
    });
    setEditingId(null);
  };

  const saveEdit = async () => {
    if (!draft) return;
    const now = new Date().toISOString();
    const editedIcon: Icon = {
      ...icon,
      ...draft,
      editor: "当前教师",
      edited_at: now,
      editable: true,
    };
    setIcons((list) =>
      list.map((it) => (it.id === icon.id ? editedIcon : it)),
    );
    setDrafts((d) => {
      const next = { ...d };
      delete next[icon.id];
      return next;
    });
    setEditingId(null);

    // 1) 本地持久化（刷新不丢失的保底层）
    const edits = loadLocal<Record<string, Partial<Icon>>>(EDITS_KEY, {});
    edits[icon.id] = {
      name: editedIcon.name,
      type: editedIcon.type,
      semantic: editedIcon.semantic,
      default_role: editedIcon.default_role,
      edit_note: editedIcon.edit_note,
      editor: editedIcon.editor,
      edited_at: editedIcon.edited_at,
    };
    saveLocal(EDITS_KEY, edits);

    // 2) 后端持久化（写入 var/visual-semantic/catalog.json，作为后续解析依据）
    const semanticId = iconTypeToSemanticId[editedIcon.type];
    if (!semanticId) {
      alert("该图标类型无后端语义对象，已仅保存到本地。");
      return;
    }
    try {
      await saveProfile(semanticId, {
        special_meaning: editedIcon.semantic,
        role_name: editedIcon.default_role || null,
        review_status: "reviewed",
      });
      const img = customIconImages[icon.id];
      if (img) {
        const file = await dataUrlToFile(
          img,
          `${semanticId.replace(/\./g, "-")}.png`,
        );
        await uploadTemplate(semanticId, file);
      }
    } catch (e) {
      alert(`已保存到本地，但写入后端资源库失败（刷新后部分字段可能回退）：${(e as Error).message}`);
    }
  };

  // 恢复为系统初稿（清除教师修改）
  const resetEdit = async () => {
    const original = initialIcons.find((x) => x.id === icon.id);
    setIcons((list) =>
      list.map((it) =>
        it.id === icon.id
          ? {
              ...it,
              ...(original ?? {}),
              editor: null,
              edited_at: null,
              edit_note: null,
            }
          : it,
      ),
    );
    // 清除本地编辑与自定义图
    const edits = loadLocal<Record<string, Partial<Icon>>>(EDITS_KEY, {});
    delete edits[icon.id];
    saveLocal(EDITS_KEY, edits);
    const imgs = loadLocal<Record<string, string>>(IMAGES_KEY, {});
    if (imgs[icon.id]) {
      delete imgs[icon.id];
      saveLocal(IMAGES_KEY, imgs);
    }
    setCustomIconImages((m) => {
      const next = { ...m };
      delete next[icon.id];
      return next;
    });
    cancelEdit();
    // 回写后端默认语义（资源库恢复默认值）
    const semanticId = iconTypeToSemanticId[icon.type];
    if (semanticId && original) {
      try {
        await saveProfile(semanticId, {
          special_meaning: original.semantic,
          role_name: original.default_role || null,
        });
      } catch {
        // 后端不可用时静默，本地已回滚
      }
    }
  };

  const setDraft = (key: keyof Icon, value: string) => {
    setDrafts((d) => ({
      ...d,
      [icon.id]: { ...(d[icon.id] ?? {}), [key]: value },
    }));
  };

  // ===== 更换图标图（编辑态） =====
  const setIconImage = (iconId: string, dataUrl: string) => {
    setCustomIconImages((m) => ({ ...m, [iconId]: dataUrl }));
    const imgs = loadLocal<Record<string, string>>(IMAGES_KEY, {});
    imgs[iconId] = dataUrl;
    saveLocal(IMAGES_KEY, imgs);
  };

  // ===== 删除图标 =====
  const deleteIcon = (id: string) => {
    const ic = icons.find((x) => x.id === id);
    if (!ic) return;
    if (!confirm(`确认删除图标「${ic.name}」？此操作不可撤销。`)) return;
    setIcons((list) => list.filter((x) => x.id !== id));
    setCustomIconImages((m) => {
      if (!m[id]) return m;
      const next = { ...m };
      delete next[id];
      return next;
    });
    // 同步清除本地持久化记录
    const edits = loadLocal<Record<string, Partial<Icon>>>(EDITS_KEY, {});
    delete edits[id];
    saveLocal(EDITS_KEY, edits);
    const imgs = loadLocal<Record<string, string>>(IMAGES_KEY, {});
    if (imgs[id]) {
      delete imgs[id];
      saveLocal(IMAGES_KEY, imgs);
    }
    // 如果删除的是当前选中的，切换到第一个
    if (selected === id) {
      const remaining = icons.filter((x) => x.id !== id);
      if (remaining.length > 0) setSelected(remaining[0].id);
    }
    setEditingId(null);
  };

  // ===== 录入新图标 =====
  const setNewField = (key: keyof typeof newDraft, value: string) => {
    setNewDraft((d) => ({ ...d, [key]: value }));
  };

  const addIcon = () => {
    if (!newDraft.name.trim()) {
      alert("请填写图标名称");
      return;
    }
    if (!newDraft.semantic.trim()) {
      alert("请填写教材语义");
      return;
    }
    const newId = genIconId();
    const now = new Date().toISOString();
    const newIcon: Icon = {
      id: newId,
      name: newDraft.name.trim(),
      type: newDraft.type,
      semantic: newDraft.semantic.trim(),
      default_role: newDraft.default_role.trim() || "自定义",
      source_image: newDraft.source_image.trim() || `upload/${newId}.png`,
      editable: true,
      editor: "当前教师",
      edited_at: now,
      edit_note: newDraft.edit_note || "新增图标",
    };
    setIcons((list) => [...list, newIcon]);
    // 绑定预览图到新 ID
    if (newIconPreview) {
      setCustomIconImages((m) => ({ ...m, [newId]: newIconPreview }));
    }
    // 持久化新图标到本地（新增图标为前端自定义对象，无后端 profile）
    const edits = loadLocal<Record<string, Partial<Icon>>>(EDITS_KEY, {});
    edits[newId] = { ...newIcon };
    saveLocal(EDITS_KEY, edits);
    if (newIconPreview) {
      const imgs = loadLocal<Record<string, string>>(IMAGES_KEY, {});
      imgs[newId] = newIconPreview;
      saveLocal(IMAGES_KEY, imgs);
    }
    // 清空表单
    setNewDraft(newIconDraftInit());
    setNewIconPreview(null);
    // 选中新图标
    setSelected(newId);
    alert(`已录入图标「${newIcon.name}」，已选为当前查看项。`);
  };

  const cancelNewIcon = () => {
    setNewDraft(newIconDraftInit());
    setNewIconPreview(null);
  };

  const editedCount = icons.filter((i) => i.editor).length;

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={3}
        eyebrow="ICON RESOURCE LIBRARY"
        title="图标资源库"
        subtitle="苏教版专属图标库。用户上传一张清晰彩色标准图并填写名称/类型/教材语义/默认角色/适用范围，系统自动生成 8 类变体。所有派生图必须记录来源原图，不得作为新的人工真值。"
        right={
          <div className="flex items-center gap-2">
            <Badge tone={editMode ? "vermilion" : "default"}>
              {editMode ? "可编辑模式 · ON" : "只读模式"}
            </Badge>
            <button
              onClick={() => {
                if (editMode) setEditingId(null);
                setEditMode((v) => !v);
              }}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-sm border transition-colors",
                editMode
                  ? "bg-vermilion text-paper border-vermilion hover:bg-vermilion-deep"
                  : "bg-paper text-ink-2 border-ink-line hover:border-vermilion hover:text-vermilion",
              )}
            >
              <Pencil size={12} />
              {editMode ? "退出可编辑" : "开启可编辑模式"}
            </button>
          </div>
        }
      />

      {/* 编辑模式说明条 */}
      {editMode && (
        <div className="mb-6 p-3 bg-vermilion-tint/40 border border-vermilion/30 rounded-sm flex items-start gap-2.5 animate-ink-rise">
          <Pencil size={14} className="text-vermilion-deep mt-0.5 shrink-0" />
          <div className="text-xs text-ink-2 leading-relaxed flex-1">
            <span className="font-medium text-vermilion-deep">可编辑模式已开启：</span>
            部分标准图标与课本实际图案可能不 100% 一致。点击下方任意图标卡片进入编辑状态，
            可修正<span className="text-ink"> 名称 / 类型 / 教材语义 / 默认角色身份 / 编辑原因 / 图标图</span>，
            也可<span className="text-ink">新增或删除图标</span>。系统将记录修改人、修改时间与原因。原系统初稿永久保留，可随时回滚。
          </div>
          <Badge tone="gold">{editedCount} / {icons.length} 已修订</Badge>
        </div>
      )}

      {/* 图标网格 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <span className="chapter-num">一</span> 标准图标
        <Badge tone="default">{icons.length}</Badge>
        {editMode && (
          <button
            onClick={() => {
              document.getElementById("new-icon-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-vermilion-tint text-vermilion-deep border border-vermilion/30 rounded-sm hover:bg-vermilion/10"
          >
            <Plus size={11} /> 添加图标
          </button>
        )}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
        {icons.map((ic) => {
          const m = iconTypeMap[ic.type];
          const M = m.icon;
          const isSel = ic.id === selected;
          const isEdited = !!ic.editor;
          const customImg = customIconImages[ic.id];
          return (
            <button
              key={ic.id}
              onClick={() => setSelected(ic.id)}
              className={cn(
                "relative p-4 bg-paper border rounded-sm text-left transition-all",
                isSel ? "border-vermilion ring-2 ring-vermilion/30" : "border-ink-line hover:border-ink-line-2 hover:shadow-card-hover",
                editMode && "ring-1 ring-dashed ring-ink-3/40",
              )}
            >
              {isEdited && (
                <span className="absolute top-2 right-2 inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[0.5rem] font-mono bg-gold-soft text-ink rounded-sm border border-gold/30">
                  已修订
                </span>
              )}
              <div className={cn(
                "flex h-14 w-14 items-center justify-center rounded-sm mb-3 overflow-hidden",
                m.tone === "vermilion" ? "bg-vermilion-tint" : m.tone === "teal" ? "bg-teal-tint" : "bg-paper-3",
              )}>
                {customImg ? (
                  <img src={customImg} alt={ic.name} className="h-full w-full object-contain" />
                ) : (
                  <M size={26} className={m.tone === "vermilion" ? "text-vermilion-deep" : m.tone === "teal" ? "text-teal-2" : "text-ink-2"} />
                )}
              </div>
              <div className="text-sm font-medium text-ink">{ic.name}</div>
              <div className="mt-1 flex items-center gap-1">
                <Badge tone={m.tone}>{m.label}</Badge>
                {customImg && <Badge tone="default">自定义图</Badge>}
              </div>
              <div className="mt-2 text-2xs text-ink-4 font-mono truncate">{ic.source_image}</div>
              {isEdited && ic.edited_at && (
                <div className="mt-1 text-[0.5rem] text-ink-4 font-mono">
                  {ic.editor} · {new Date(ic.edited_at).toLocaleDateString("zh-CN")}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* 选中图标的详情 + 变体 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10">
        <Card
          title="图标档案"
          accent="vermilion"
          right={
            editMode ? (
              isEditing ? (
                <div className="flex gap-1.5">
                  <button
                    onClick={saveEdit}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-ok text-paper rounded-sm hover:bg-ok/90"
                  >
                    <Save size={11} /> 保存
                  </button>
                  <button
                    onClick={cancelEdit}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2"
                  >
                    <XCircle size={11} /> 取消
                  </button>
                  <button
                    onClick={() => deleteIcon(icon.id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-err-soft text-err rounded-sm hover:bg-err/20"
                    title="删除图标"
                  >
                    <Trash2 size={11} /> 删除
                  </button>
                </div>
              ) : (
                <div className="flex gap-1.5">
                  <button
                    onClick={startEdit}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-vermilion text-paper rounded-sm hover:bg-vermilion-deep"
                  >
                    <Pencil size={11} /> 编辑此图标
                  </button>
                  {icon.editor && (
                    <button
                      onClick={resetEdit}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2"
                      title="恢复为系统初稿"
                    >
                      <RotateCcw size={11} /> 回滚
                    </button>
                  )}
                  <button
                    onClick={() => deleteIcon(icon.id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-err-soft text-err rounded-sm hover:bg-err/20"
                    title="删除图标"
                  >
                    <Trash2 size={11} /> 删除
                  </button>
                </div>
              )
            ) : null
          }
        >
          {/* 编辑态：更换图标图上传区 */}
          {isEditing && (
            <div className="mb-4 pb-4 border-b border-ink-line-2">
              <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">图标图</div>
              <div className="flex items-center gap-3">
                <div className={cn(
                  "flex h-16 w-16 items-center justify-center rounded-sm overflow-hidden shrink-0",
                  iconTypeMap[icon.type].tone === "vermilion" ? "bg-vermilion-tint" : iconTypeMap[icon.type].tone === "teal" ? "bg-teal-tint" : "bg-paper-3",
                )}>
                  {customIconImages[icon.id] ? (
                    <img src={customIconImages[icon.id]} alt={icon.name} className="h-full w-full object-contain" />
                  ) : (
                    <IconComp size={28} className={iconTypeMap[icon.type].tone === "vermilion" ? "text-vermilion-deep" : iconTypeMap[icon.type].tone === "teal" ? "text-teal-2" : "text-ink-2"} />
                  )}
                </div>
                <div className="flex-1">
                  <ImageUpload
                    className="py-3"
                    hint="点击或拖拽上传新图标图"
                    subHint="jpg / png / svg · 将替换当前显示"
                    onFileSelected={(_file, dataUrl) => setIconImage(icon.id, dataUrl)}
                  />
                </div>
              </div>
            </div>
          )}
          <div className="space-y-3 text-sm">
            {/* 编辑模式：行内表单；只读模式：纯展示 */}
            {isEditing && draft ? (
              <>
                <EditField label="名称" value={draft.name ?? ""} onChange={(v) => setDraft("name", v)} />
                <div className="flex items-start gap-3">
                  <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono w-20 shrink-0 pt-1.5">类型</span>
                  <select
                    value={draft.type ?? icon.type}
                    onChange={(e) => setDraft("type", e.target.value)}
                    className="flex-1 px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion"
                  >
                    {typeOptions.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <EditField label="教材语义" value={draft.semantic ?? ""} onChange={(v) => setDraft("semantic", v)} multiline />
                <EditField label="默认角色身份" value={draft.default_role ?? ""} onChange={(v) => setDraft("default_role", v)} />
                <EditField label="编辑原因" value={draft.edit_note ?? ""} onChange={(v) => setDraft("edit_note", v)} multiline placeholder="说明本次修订原因（如：图标与课本第10页图案略有差异）" />
              </>
            ) : (
              <>
                <Row label="名称" value={icon.name} />
                <Row label="类型" value={iconTypeMap[icon.type].label} />
                <Row label="教材语义" value={icon.semantic} />
                <Row label="默认角色" value={icon.default_role} />
                <Row label="录入原图" value={<code className="text-xs font-mono text-ink-3">{icon.source_image}</code>} />
                <Row label="适用范围" value={<Badge tone="default">苏教版三上</Badge>} />
                {icon.editable && (
                  <Row
                    label="可编辑"
                    value={<Badge tone={icon.editor ? "gold" : "teal"}>{icon.editor ? "教师已修订" : "允许编辑"}</Badge>}
                  />
                )}
                {icon.editor && (
                  <>
                    <Row label="修订人" value={<span className="text-ink-2 text-xs">{icon.editor}</span>} />
                    {icon.edited_at && (
                      <Row
                        label="修订时间"
                        value={<span className="text-ink-3 text-xs font-mono">{new Date(icon.edited_at).toLocaleString("zh-CN")}</span>}
                      />
                    )}
                    {icon.edit_note && (
                      <Row label="修订原因" value={<span className="text-ink-2 text-xs italic">"{icon.edit_note}"</span>} />
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </Card>

        <Card title="自动生成变体 (8)" subtitle="系统据一张彩色原图自动生成" className="lg:col-span-2">
          <div className="grid grid-cols-4 gap-2.5">
            {Object.entries(variantLabels).map(([k, label], idx) => {
              const v = variants.find((x) => x.variant === k);
              return (
                <div key={k} className="bg-paper-2 border border-ink-line rounded-sm p-2 text-center">
                  <div className="aspect-square bg-paper border border-ink-line-2 rounded-sm flex items-center justify-center mb-1.5">
                    <IconComp
                      size={28}
                      className={cn(
                        idx % 2 === 0 ? "text-ink-2" : "text-ink-3",
                        k === "binary" && "opacity-100 text-ink",
                        k === "blur" && "blur-[1px]",
                        k === "jpeg" && "opacity-70",
                        k === "brightness" && "opacity-80",
                        k === "crop" && "scale-90",
                        k === "scale" && "scale-75",
                      )}
                    />
                  </div>
                  <div className="text-2xs text-ink-2 font-medium">{label}</div>
                  {v && (
                    <div className="mt-1 flex flex-wrap gap-0.5 justify-center">
                      {v.for_match && <span className="text-[0.5rem] text-teal">匹配</span>}
                      {v.for_training && <span className="text-[0.5rem] text-vermilion">训练</span>}
                      {v.for_test && <span className="text-[0.5rem] text-ink-3">测试</span>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3 border-t border-ink-line-2 text-2xs text-ink-3 leading-relaxed">
            派生图均记录：来源原图 · 生成参数 · 资源版本 · 是否用于训练/匹配/测试。派生图不得作为新的人工真值。
          </div>
        </Card>
      </div>

      {/* 允许 vs 禁止 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
        <Card title="允许的增强" accent="teal">
          <ul className="space-y-2">
            {allowed.map((a) => (
              <li key={a} className="flex items-start gap-2 text-sm text-ink-2">
                <Check size={14} className="text-ok mt-0.5 shrink-0" /> {a}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="禁止的增强" accent="vermilion">
          <ul className="space-y-2">
            {disallowed.map((a) => (
              <li key={a} className="flex items-start gap-2 text-sm text-ink-2">
                <X size={14} className="text-err mt-0.5 shrink-0" /> {a}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* 录入表单 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <span className="chapter-num">二</span> 录入新图标
        <Badge tone="default">{editMode ? "可录入" : "需开启可编辑模式"}</Badge>
      </h2>
      <Card>
        <div id="new-icon-form" className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">上传一张清晰彩色标准图</label>
            <div className="mt-1.5">
              <ImageUpload
                hint="拖拽或点击上传（仅需一张彩色原图）"
                subHint="系统将基于此原图自动生成 8 类变体（灰度/二值/多尺度/模糊/JPEG/亮度/裁剪/截图）"
                className="py-8"
                onFileSelected={(_file, dataUrl) => setNewIconPreview(dataUrl)}
              />
            </div>
          </div>
          <div>
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">名称 *</label>
            <input
              type="text"
              value={newDraft.name}
              onChange={(e) => setNewField("name", e.target.value)}
              placeholder="例：例题书本图标"
              className="mt-1.5 w-full px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
            />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">类型</label>
            <select
              value={newDraft.type}
              onChange={(e) => setNewField("type", e.target.value)}
              className="mt-1.5 w-full px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion"
            >
              {typeOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">教材语义 *</label>
            <input
              type="text"
              value={newDraft.semantic}
              onChange={(e) => setNewField("semantic", e.target.value)}
              placeholder="书本形状图标+图标内数字，是例题开始的强锚点"
              className="mt-1.5 w-full px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
            />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">默认角色身份</label>
            <input
              type="text"
              value={newDraft.default_role}
              onChange={(e) => setNewField("default_role", e.target.value)}
              placeholder="anchor / section-marker"
              className="mt-1.5 w-full px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
            />
          </div>
          <div>
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">原图文件名（可选）</label>
            <input
              type="text"
              value={newDraft.source_image}
              onChange={(e) => setNewField("source_image", e.target.value)}
              placeholder="留空将自动生成"
              className="mt-1.5 w-full px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">编辑原因</label>
            <input
              type="text"
              value={newDraft.edit_note}
              onChange={(e) => setNewField("edit_note", e.target.value)}
              placeholder="新增图标原因（如：本版教材新增栏目图标）"
              className="mt-1.5 w-full px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
            />
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-ink-line-2 flex items-center justify-between">
          <span className="text-2xs text-ink-4">
            {newIconPreview ? "✓ 已上传原图，" : "未上传原图也可录入（将使用默认占位图），"}
            提交后自动生成 8 类变体并写入资源库
          </span>
          <div className="flex gap-2">
            <button
              onClick={cancelNewIcon}
              className="px-3 py-1.5 bg-paper-3 text-ink-2 text-sm rounded-sm hover:bg-paper-2 transition-colors"
            >
              清空
            </button>
            <button
              onClick={addIcon}
              className="px-4 py-1.5 bg-vermilion text-paper text-sm rounded-sm hover:bg-vermilion-deep transition-colors"
            >
              录入并生成变体
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono w-20 shrink-0 pt-0.5">{label}</span>
      <span className="text-ink-2 flex-1">{value}</span>
    </div>
  );
}

function EditField({
  label,
  value,
  onChange,
  multiline,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono w-20 shrink-0 pt-1.5">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={2}
          className="flex-1 px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion resize-none"
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 px-3 py-1.5 text-sm bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion"
        />
      )}
    </div>
  );
}
