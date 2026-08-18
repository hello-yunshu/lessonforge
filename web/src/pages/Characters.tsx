import { useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import ImageUpload from "@/components/ui/ImageUpload";
import { characters as initialChars, speeches, objects } from "@/data";
import type { Character, CharacterRole } from "@/data/types";
import { cn, objectTypeCN } from "@/lib/utils";
import {
  getCatalog,
  saveProfile,
  uploadTemplate,
  dataUrlToFile,
  loadLocal,
  saveLocal,
  characterNameToSemanticId,
} from "@/lib/visualCatalog";
import { GraduationCap, User, Pencil, Save, XCircle, RotateCcw, Check, UserPlus, Trash2 } from "lucide-react";

// 本地持久化键：编辑字段 + 自定义头像（后端不可用时的保底层）
const EDITS_KEY = "book3-chars-edits";
const AVATARS_KEY = "book3-chars-avatars";

const roleColor = {
  student: { tone: "teal" as const, label: "学生角色", bg: "bg-teal-tint", text: "text-teal-2", ring: "ring-teal/30" },
  teacher: { tone: "vermilion" as const, label: "教师角色", bg: "bg-vermilion-tint", text: "text-vermilion-deep", ring: "ring-vermilion/30" },
};

const speechFuncCN: Record<string, string> = {
  "ask-reason": "追问理由",
  "give-method": "给方法",
  "give-answer": "给答案",
  summarize: "归纳",
  prompt: "提示",
  operation: "操作说明",
};

// 角色头像（用 emoji + 色块表达教材卡通角色）
const avatar: Record<string, string> = {
  青椒: "🫑",
  蘑菇: "🍄",
  番茄: "🍅",
  白菜: "🥬",
  豌豆: "🫛",
  茄子: "🍆",
  小苗: "👧",
  豆豆: "👦",
  小青: "👧",
  芳芳: "👧",
  大志: "👦",
};

// 生成新角色 ID
let charIdSeq = 1000;
const genCharId = () => `ch-custom-${++charIdSeq}`;

// 新建角色草稿的初始值
const newCharDraft = (role: CharacterRole): Partial<Character> => ({
  name: "",
  role,
  default_pose: "",
  edit_note: "新增角色",
});

export default function Characters() {
  // 初始状态合并本地持久化的教师编辑（刷新后不丢失）
  const [characters, setCharacters] = useState<Character[]>(() => {
    const edits = loadLocal<Record<string, Partial<Character>>>(EDITS_KEY, {});
    return initialChars.map((c) =>
      edits[c.id] ? { ...c, ...edits[c.id] } : c,
    );
  });
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Partial<Character>>>({});
  const [filter, setFilter] = useState<"all" | "verified" | "placeholder">("all");
  // 自定义头像（character_id → DataURL），加载时从本地恢复
  const [customAvatars, setCustomAvatars] = useState<Record<string, string>>(() =>
    loadLocal<Record<string, string>>(AVATARS_KEY, {}),
  );
  // 新建角色草稿（role → draft），同时展示在列表最前
  const [newDrafts, setNewDrafts] = useState<Record<string, Partial<Character> & { _tempId: string }>>({});

  // 挂载时从后端拉取资源库目录（后端 var/visual-semantic/catalog.json 为解析真值）。
  // 后端角色名 / 说话人类型优先回填，保证「资源库作为解析依据」所见即所得。
  useEffect(() => {
    let cancelled = false;
    getCatalog()
      .then((cat) => {
        if (cancelled) return;
        const bySemantic = new Map(cat.profiles.map((p) => [p.semantic_id, p]));
        setCharacters((list) =>
          list.map((c) => {
            const sid = characterNameToSemanticId[c.name];
            const prof = sid ? bySemantic.get(sid) : undefined;
            if (!prof) return c;
            return {
              ...c,
              name: prof.role_name || c.name,
              role: prof.speaker_type === "teacher" ? "teacher" : "student",
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

  const students = characters.filter((c) => c.role === "student");
  const teachers = characters.filter((c) => c.role === "teacher");

  const filteredStudents = students.filter((c) => {
    if (filter === "all") return true;
    if (filter === "verified") return c.editor === "system-pdf-check";
    if (filter === "placeholder") return c.editor !== "system-pdf-check";
    return true;
  });
  const filteredTeachers = teachers.filter((c) => {
    if (filter === "all") return true;
    if (filter === "verified") return c.editor === "system-pdf-check";
    if (filter === "placeholder") return c.editor !== "system-pdf-check";
    return true;
  });

  const startEdit = (id: string) => {
    const c = characters.find((x) => x.id === id)!;
    setDrafts((d) => ({
      ...d,
      [id]: {
        name: c.name,
        role: c.role,
        default_pose: c.default_pose,
        edit_note: c.edit_note ?? "",
      },
    }));
    setEditingId(id);
  };

  const cancelEdit = (id: string) => {
    setDrafts((d) => {
      const next = { ...d };
      delete next[id];
      return next;
    });
    setEditingId(null);
  };

  const saveEdit = async (id: string) => {
    const draft = drafts[id];
    if (!draft) return;
    const now = new Date().toISOString();
    const edited: Character = {
      ...characters.find((x) => x.id === id)!,
      ...draft,
      editor: "当前教师",
      edited_at: now,
      editable: true,
    };
    setCharacters((list) =>
      list.map((it) => (it.id === id ? edited : it)),
    );
    setDrafts((d) => {
      const next = { ...d };
      delete next[id];
      return next;
    });
    setEditingId(null);

    // 1) 本地持久化（刷新不丢失的保底层）
    const edits = loadLocal<Record<string, Partial<Character>>>(EDITS_KEY, {});
    edits[id] = {
      name: edited.name,
      role: edited.role,
      default_pose: edited.default_pose,
      edit_note: edited.edit_note,
      editor: edited.editor,
      edited_at: edited.edited_at,
    };
    saveLocal(EDITS_KEY, edits);

    // 2) 后端持久化（教材内置 6 角色有后端 profile，作为解析依据）
    const semanticId = characterNameToSemanticId[edited.name];
    if (!semanticId) {
      // 自定义角色无后端 profile，仅本地保存
      return;
    }
    try {
      await saveProfile(semanticId, {
        role_name: edited.name,
        speaker_type: edited.role === "teacher" ? "teacher" : "student",
        review_status: "reviewed",
      });
      const avatarUrl = customAvatars[id];
      if (avatarUrl) {
        const file = await dataUrlToFile(
          avatarUrl,
          `${semanticId.replace(/\./g, "-")}.png`,
        );
        await uploadTemplate(semanticId, file);
      }
    } catch (e) {
      alert(`已保存到本地，但写入后端资源库失败（刷新后部分字段可能回退）：${(e as Error).message}`);
    }
  };

  const resetEdit = async (id: string) => {
    const original = initialChars.find((x) => x.id === id);
    setCharacters((list) =>
      list.map((it) =>
        it.id === id
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
    // 清除本地编辑与自定义头像
    const edits = loadLocal<Record<string, Partial<Character>>>(EDITS_KEY, {});
    delete edits[id];
    saveLocal(EDITS_KEY, edits);
    const avatars = loadLocal<Record<string, string>>(AVATARS_KEY, {});
    if (avatars[id]) {
      delete avatars[id];
      saveLocal(AVATARS_KEY, avatars);
    }
    setCustomAvatars((m) => {
      const next = { ...m };
      delete next[id];
      return next;
    });
    cancelEdit(id);
    // 回写后端默认角色名
    if (original) {
      const semanticId = characterNameToSemanticId[original.name];
      if (semanticId) {
        try {
          await saveProfile(semanticId, {
            role_name: original.name,
            speaker_type: original.role === "teacher" ? "teacher" : "student",
          });
        } catch {
          // 后端不可用时静默，本地已回滚
        }
      }
    }
  };

  const setDraft = (id: string, key: keyof Character, value: string) => {
    setDrafts((d) => ({
      ...d,
      [id]: { ...(d[id] ?? {}), [key]: value },
    }));
  };

  // ===== 新建角色 =====
  const startAdd = (role: CharacterRole) => {
    const tempId = `new-${role}-${Date.now()}`;
    setNewDrafts((d) => ({
      ...d,
      [tempId]: { ...newCharDraft(role), _tempId: tempId },
    }));
  };

  const setNewDraft = (tempId: string, key: keyof Character, value: string) => {
    setNewDrafts((d) => ({
      ...d,
      [tempId]: { ...(d[tempId] ?? {}), _tempId: tempId, [key]: value },
    }));
  };

  const saveNew = (tempId: string) => {
    const draft = newDrafts[tempId];
    if (!draft || !draft.name?.trim()) {
      alert("请填写角色名");
      return;
    }
    const newChar: Character = {
      id: genCharId(),
      name: draft.name.trim(),
      role: (draft.role as CharacterRole) ?? "student",
      default_pose: draft.default_pose ?? "",
      editable: true,
      editor: "当前教师",
      edited_at: new Date().toISOString(),
      edit_note: draft.edit_note ?? "新增角色",
    };
    setCharacters((list) => [...list, newChar]);
    // 如果有自定义头像，绑定到新 ID
    if (customAvatars[tempId]) {
      setCustomAvatars((m) => {
        const next = { ...m };
        next[newChar.id] = next[tempId];
        delete next[tempId];
        return next;
      });
    }
    // 持久化新角色
    const edits = loadLocal<Record<string, Partial<Character>>>(EDITS_KEY, {});
    edits[newChar.id] = { ...newChar };
    saveLocal(EDITS_KEY, edits);
    if (customAvatars[tempId]) {
      const avatars = loadLocal<Record<string, string>>(AVATARS_KEY, {});
      avatars[newChar.id] = customAvatars[tempId];
      delete avatars[tempId];
      saveLocal(AVATARS_KEY, avatars);
    }
    setNewDrafts((d) => {
      const next = { ...d };
      delete next[tempId];
      return next;
    });
  };

  const cancelNew = (tempId: string) => {
    setNewDrafts((d) => {
      const next = { ...d };
      delete next[tempId];
      return next;
    });
    setCustomAvatars((m) => {
      if (!m[tempId]) return m;
      const next = { ...m };
      delete next[tempId];
      return next;
    });
  };

  // ===== 删除角色 =====
  const deleteChar = (id: string) => {
    const c = characters.find((x) => x.id === id);
    if (!c) return;
    if (!confirm(`确认删除角色「${c.name}」？此操作不可撤销。`)) return;
    setCharacters((list) => list.filter((x) => x.id !== id));
    setCustomAvatars((m) => {
      if (!m[id]) return m;
      const next = { ...m };
      delete next[id];
      return next;
    });
    // 同步清除本地持久化记录
    const edits = loadLocal<Record<string, Partial<Character>>>(EDITS_KEY, {});
    delete edits[id];
    saveLocal(EDITS_KEY, edits);
    const avatars = loadLocal<Record<string, string>>(AVATARS_KEY, {});
    if (avatars[id]) {
      delete avatars[id];
      saveLocal(AVATARS_KEY, avatars);
    }
  };

  // ===== 更换头像（编辑态，同时本地持久化） =====
  const setAvatar = (id: string, dataUrl: string) => {
    setCustomAvatars((m) => ({ ...m, [id]: dataUrl }));
    const avatars = loadLocal<Record<string, string>>(AVATARS_KEY, {});
    avatars[id] = dataUrl;
    saveLocal(AVATARS_KEY, avatars);
  };

  const editedCount = characters.filter((c) => c.editor).length;
  const verifiedCount = characters.filter((c) => c.editor === "system-pdf-check").length;

  // 渲染单个角色卡片（学生 / 教师通用）
  const renderCharCard = (c: Character) => {
    const r = roleColor[c.role];
    const draft = drafts[c.id];
    const isEditing = editingId === c.id && editMode;
    const isVerified = c.editor === "system-pdf-check";
    const isEdited = !!c.editor && !isVerified;
    const customAvatar = customAvatars[c.id];

    return (
      <Card
        key={c.id}
        accent={r.tone === "teal" ? "teal" : "vermilion"}
        right={
          editMode ? (
            isEditing ? (
              <div className="flex gap-1.5">
                <button
                  onClick={() => saveEdit(c.id)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-ok text-paper rounded-sm hover:bg-ok/90"
                >
                  <Save size={11} /> 保存
                </button>
                <button
                  onClick={() => cancelEdit(c.id)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2"
                >
                  <XCircle size={11} /> 取消
                </button>
              </div>
            ) : (
              <div className="flex gap-1.5">
                <button
                  onClick={() => startEdit(c.id)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-vermilion text-paper rounded-sm hover:bg-vermilion-deep"
                >
                  <Pencil size={11} /> 编辑
                </button>
                {c.editor && (
                  <button
                    onClick={() => resetEdit(c.id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2"
                    title="恢复为系统初稿"
                  >
                    <RotateCcw size={11} /> 回滚
                  </button>
                )}
                <button
                  onClick={() => deleteChar(c.id)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-err-soft text-err rounded-sm hover:bg-err/20"
                  title="删除角色"
                >
                  <Trash2 size={11} /> 删除
                </button>
              </div>
            )
          ) : null
        }
      >
        {/* 头像 + 名称 */}
        <div className="flex items-center gap-3">
          {isEditing ? (
            // 编辑态：头像可上传
            <div className="shrink-0">
              <div className={cn("relative h-14 w-14 rounded-full overflow-hidden ring-2", r.bg, r.ring)}>
                {customAvatar ? (
                  <img src={customAvatar} alt="头像" className="h-full w-full object-cover" />
                ) : (
                  <div className="h-full w-full flex items-center justify-center text-3xl">
                    {avatar[c.name] ?? "👤"}
                  </div>
                )}
                {isVerified && (
                  <span className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-ok border-2 border-paper flex items-center justify-center">
                    <Check size={9} className="text-paper" />
                  </span>
                )}
              </div>
              <label className="mt-1 block text-center text-2xs text-vermilion-deep cursor-pointer hover:text-vermilion">
                更换头像
                <ImageUpload
                  className="py-2 text-2xs"
                  hint="点击或拖拽上传头像"
                  subHint="jpg / png · 自动裁剪为圆形"
                  onFileSelected={(_file, dataUrl) => setAvatar(c.id, dataUrl)}
                />
              </label>
            </div>
          ) : (
            <div className={cn("flex h-14 w-14 items-center justify-center rounded-full text-3xl ring-2 relative shrink-0 overflow-hidden", r.bg, r.ring)}>
              {customAvatar ? (
                <img src={customAvatar} alt="头像" className="h-full w-full object-cover" />
              ) : (
                avatar[c.name] ?? "👤"
              )}
              {isVerified && (
                <span className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-ok border-2 border-paper flex items-center justify-center">
                  <Check size={9} className="text-paper" />
                </span>
              )}
            </div>
          )}
          <div className="flex-1 min-w-0">
            {isEditing && draft ? (
              <input
                type="text"
                value={draft.name ?? ""}
                onChange={(e) => setDraft(c.id, "name", e.target.value)}
                className="w-full px-2 py-1 text-sm font-serif font-bold bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion"
              />
            ) : (
              <div className="font-serif text-lg font-bold text-ink">{c.name}</div>
            )}
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              {isEditing && draft ? (
                <select
                  value={draft.role ?? c.role}
                  onChange={(e) => setDraft(c.id, "role", e.target.value as CharacterRole)}
                  className="px-2 py-0.5 text-2xs bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion"
                >
                  <option value="student">学生角色</option>
                  <option value="teacher">教师角色</option>
                </select>
              ) : (
                <Badge tone={r.tone}>{r.label}</Badge>
              )}
              {isVerified && <Badge tone="ok">PDF 已核查</Badge>}
              {isEdited && <Badge tone="gold">教师已修订</Badge>}
              {!c.editor && c.editable && <Badge tone="teal">允许编辑</Badge>}
              {customAvatar && !isEditing && <Badge tone="default">自定义头像</Badge>}
            </div>
          </div>
        </div>

        {/* 默认姿态 */}
        <div className="mt-3 pt-3 border-t border-ink-line-2">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">默认教材姿态</div>
          {isEditing && draft ? (
            <textarea
              value={draft.default_pose ?? ""}
              onChange={(e) => setDraft(c.id, "default_pose", e.target.value)}
              rows={2}
              className="mt-1 w-full px-2 py-1 text-xs bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion resize-none"
            />
          ) : (
            <p className="text-xs text-ink-2 mt-1">{c.default_pose}</p>
          )}
          {/* 编辑原因 */}
          {isEditing && draft && (
            <div className="mt-2">
              <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">编辑原因</div>
              <input
                type="text"
                value={draft.edit_note ?? ""}
                onChange={(e) => setDraft(c.id, "edit_note", e.target.value)}
                placeholder="说明修订原因（如：与课本第10页插图略有差异）"
                className="mt-1 w-full px-2 py-1 text-xs bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
              />
            </div>
          )}
          {/* 修订记录 */}
          {c.editor && c.edited_at && !isEditing && (
            <div className="mt-2 text-[0.5rem] text-ink-4 font-mono flex items-center gap-1.5">
              <span className="text-ink-3">修订人</span>
              <span className="text-ink-2">{c.editor}</span>
              <span className="text-ink-4">·</span>
              <span>{new Date(c.edited_at).toLocaleString("zh-CN")}</span>
            </div>
          )}
          {c.edit_note && !isEditing && (
            <p className="mt-1 text-[0.65rem] text-ink-3 italic">"{c.edit_note}"</p>
          )}
        </div>
      </Card>
    );
  };

  // 渲染新建角色卡片
  const renderNewCharCard = (tempId: string, role: CharacterRole) => {
    const draft = newDrafts[tempId];
    if (!draft) return null;
    const r = roleColor[role];
    const customAvatar = customAvatars[tempId];

    return (
      <Card
        key={tempId}
        accent="gold"
        right={
          <div className="flex gap-1.5">
            <button
              onClick={() => saveNew(tempId)}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-ok text-paper rounded-sm hover:bg-ok/90"
            >
              <Save size={11} /> 保存
            </button>
            <button
              onClick={() => cancelNew(tempId)}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-paper-3 text-ink-2 rounded-sm hover:bg-paper-2"
            >
              <XCircle size={11} /> 取消
            </button>
          </div>
        }
      >
        {/* 头像上传 + 名称 */}
        <div className="flex items-center gap-3">
          <div className="shrink-0">
            <div className={cn("relative h-14 w-14 rounded-full overflow-hidden ring-2", r.bg, r.ring)}>
              {customAvatar ? (
                <img src={customAvatar} alt="头像" className="h-full w-full object-cover" />
              ) : (
                <div className="h-full w-full flex items-center justify-center text-3xl">👤</div>
              )}
            </div>
            <label className="mt-1 block text-center text-2xs text-vermilion-deep cursor-pointer hover:text-vermilion">
              上传头像
              <ImageUpload
                className="py-2 text-2xs"
                hint="点击或拖拽上传头像"
                subHint="jpg / png · 自动裁剪为圆形"
                onFileSelected={(_file, dataUrl) =>
                  setCustomAvatars((m) => ({ ...m, [tempId]: dataUrl }))
                }
              />
            </label>
          </div>
          <div className="flex-1 min-w-0">
            <input
              type="text"
              value={draft.name ?? ""}
              onChange={(e) => setNewDraft(tempId, "name", e.target.value)}
              placeholder="角色名称（如：小明）"
              className="w-full px-2 py-1 text-sm font-serif font-bold bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
              autoFocus
            />
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <select
                value={draft.role ?? role}
                onChange={(e) => setNewDraft(tempId, "role", e.target.value as CharacterRole)}
                className="px-2 py-0.5 text-2xs bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion"
              >
                <option value="student">学生角色</option>
                <option value="teacher">教师角色</option>
              </select>
              <Badge tone="gold">新建</Badge>
            </div>
          </div>
        </div>

        {/* 默认姿态 */}
        <div className="mt-3 pt-3 border-t border-ink-line-2">
          <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">默认教材姿态</div>
          <textarea
            value={draft.default_pose ?? ""}
            onChange={(e) => setNewDraft(tempId, "default_pose", e.target.value)}
            rows={2}
            placeholder="描述角色的默认教材姿态（如：举手发言、思考状）"
            className="mt-1 w-full px-2 py-1 text-xs bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion resize-none placeholder:text-ink-4"
          />
          <div className="mt-2">
            <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">编辑原因</div>
            <input
              type="text"
              value={draft.edit_note ?? ""}
              onChange={(e) => setNewDraft(tempId, "edit_note", e.target.value)}
              placeholder="新增角色原因（如：本班学生配图需要）"
              className="mt-1 w-full px-2 py-1 text-xs bg-paper-2 border border-ink-line rounded-sm focus:outline-none focus:border-vermilion placeholder:text-ink-4"
            />
          </div>
        </div>
      </Card>
    );
  };

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={4}
        eyebrow="CHARACTER RESOURCE LIBRARY"
        title="角色资源库"
        subtitle="苏教版三上卡通角色库。教材前 12 页核查已确认学生角色为小苗、豆豆、小青、芳芳、大志（PDF p.10/p.12/p.15）。原蔬菜占位角色保留并开启可编辑模式，教师可逐个修正以适配本班学情。角色身份与具体话语功能必须分开保存。"
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

      {/* 编辑模式说明条 + 过滤器 */}
      {editMode && (
        <div className="mb-6 p-3 bg-vermilion-tint/40 border border-vermilion/30 rounded-sm flex items-start gap-2.5">
          <Pencil size={14} className="text-vermilion-deep mt-0.5 shrink-0" />
          <div className="text-xs text-ink-2 leading-relaxed flex-1">
            <span className="font-medium text-vermilion-deep">可编辑模式已开启：</span>
            教材中部分卡通形象与课本图案不 100% 一致，教师可逐个修正
            <span className="text-ink"> 角色名 / 身份 / 默认姿态 / 头像 / 编辑原因</span>，
            也可<span className="text-ink">新增或删除角色</span>。系统将记录修改人、修改时间与原因。已通过 PDF 文本提取核查的角色会标"PDF 已核查"徽章。
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="flex gap-1.5">
              <Badge tone="gold">已修订 {editedCount}</Badge>
              <Badge tone="ok">PDF 核查 {verifiedCount}</Badge>
              <Badge tone="default">共 {characters.length}</Badge>
            </div>
            <div className="flex gap-1 mt-1">
              <FilterBtn label="全部" active={filter === "all"} onClick={() => setFilter("all")} />
              <FilterBtn label="PDF核查" active={filter === "verified"} onClick={() => setFilter("verified")} />
              <FilterBtn label="待修正" active={filter === "placeholder"} onClick={() => setFilter("placeholder")} />
            </div>
          </div>
        </div>
      )}

      {/* 学生角色 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <User size={18} className="text-teal" />
        <span className="chapter-num">一</span> 学生角色
        <Badge tone="teal">{filteredStudents.length}</Badge>
        {editMode && (
          <button
            onClick={() => startAdd("student")}
            className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-teal-tint text-teal-2 border border-teal/30 rounded-sm hover:bg-teal/10"
          >
            <UserPlus size={11} /> 添加学生角色
          </button>
        )}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-10">
        {/* 新建学生角色卡片（gold 边） */}
        {editMode && Object.values(newDrafts)
          .filter((d) => d.role === "student")
          .map((d) => renderNewCharCard(d._tempId, "student"))}
        {filteredStudents.map(renderCharCard)}
      </div>

      {/* 教师角色 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4 flex items-center gap-2">
        <GraduationCap size={18} className="text-vermilion" />
        <span className="chapter-num">二</span> 教师角色
        <Badge tone="vermilion">{filteredTeachers.length}</Badge>
        {editMode && (
          <button
            onClick={() => startAdd("teacher")}
            className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-vermilion-tint text-vermilion-deep border border-vermilion/30 rounded-sm hover:bg-vermilion/10"
          >
            <UserPlus size={11} /> 添加教师角色
          </button>
        )}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-10">
        {/* 新建教师角色卡片（gold 边） */}
        {editMode && Object.values(newDrafts)
          .filter((d) => d.role === "teacher")
          .map((d) => renderNewCharCard(d._tempId, "teacher"))}
        {filteredTeachers.map(renderCharCard)}
      </div>

      {/* 身份与话语功能分离 */}
      <h2 className="font-serif text-xl font-bold text-ink mb-4">
        <span className="chapter-num">三</span> 身份与话语功能分离
      </h2>
      <Card bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-line bg-paper-2">
                <th className="text-left px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">角色身份</th>
                <th className="text-left px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">教学身份</th>
                <th className="text-left px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">当前话语功能</th>
                <th className="text-left px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">话语内容</th>
                <th className="text-left px-4 py-2.5 text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">所属对象</th>
              </tr>
            </thead>
            <tbody>
              {speeches.map((sp) => {
                const ch = characters.find((c) => c.id === sp.character_id)!;
                const obj = objects.find((o) => o.id === sp.object_id);
                const r = roleColor[ch.role];
                return (
                  <tr key={sp.id} className="border-b border-ink-line-2 last:border-0 hover:bg-paper-2">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{avatar[ch.name] ?? "👤"}</span>
                        <span className="font-medium text-ink">{ch.name}</span>
                        {ch.editor === "system-pdf-check" && (
                          <span className="text-[0.5rem] px-1 py-0.5 bg-ok-soft text-ok rounded-sm">PDF</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3"><Badge tone={r.tone}>{r.label}</Badge></td>
                    <td className="px-4 py-3">
                      <span className="text-vermilion-deep font-medium text-xs">{speechFuncCN[sp.speech_function]}</span>
                      <code className="ml-1.5 text-2xs text-ink-4 font-mono">{sp.speech_function}</code>
                    </td>
                    <td className="px-4 py-3 text-ink-2 text-xs">"{sp.content}"</td>
                    <td className="px-4 py-3 text-xs text-ink-3">{obj ? objectTypeCN(obj.type) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-ink-line-2 bg-paper-2/50 text-2xs text-ink-3">
          示例：角色身份=白菜（教师）· 教学身份=教师 · 当前话语功能=追问运算顺序的理由。三者分开保存，避免身份与功能耦合。
        </div>
      </Card>
    </div>
  );
}

function FilterBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2 py-0.5 text-2xs rounded-sm border transition-colors",
        active
          ? "bg-ink text-paper border-ink"
          : "bg-paper text-ink-2 border-ink-line hover:border-ink",
      )}
    >
      {label}
    </button>
  );
}
