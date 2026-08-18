import { useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { mathStructures, objects } from "@/data";
import { cn } from "@/lib/utils";
import type {
  QuantityStructure,
  ChartStructure,
  GeometryStructure,
  MathStructureKind,
} from "@/data";
import { Sigma, BarChart3, Triangle, ImageIcon } from "lucide-react";

const tabs: { key: MathStructureKind; label: string; icon: typeof Sigma }[] = [
  { key: "quantity", label: "数量关系图", icon: Sigma },
  { key: "chart", label: "表格与统计图", icon: BarChart3 },
  { key: "geometry", label: "空间与几何图", icon: Triangle },
];

const relationCN: Record<string, string> = {
  add: "加法关系",
  sub: "减法关系",
  mul: "乘法关系",
  div: "除法关系",
  compare: "比较关系",
  multiple: "倍数关系",
  "total-part": "总分关系",
};

const blankCN: Record<string, string> = {
  "value-zero": "数值0",
  "intentional-blank": "教材有意留空",
  "ocr-missed": "OCR漏识别",
  "not-applicable": "不适用单元格",
};

export default function MathStructure() {
  const [tab, setTab] = useState<MathStructureKind>("quantity");
  const filtered = mathStructures.filter((m) => m.kind === tab);

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={7}
        eyebrow="IMAGE MATH STRUCTURE"
        title="图片数学结构抽取"
        subtitle="图片不只生成自然语言描述，按类型生成专门结构化结果。原图必须始终保留，结构化结果不能替代原图证据。"
      />

      {/* Tab */}
      <div className="flex gap-1 mb-8 border-b border-ink-line">
        {tabs.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors",
                active
                  ? "border-vermilion text-vermilion-deep font-medium"
                  : "border-transparent text-ink-3 hover:text-ink",
              )}
            >
              <t.icon size={16} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="space-y-6">
        {filtered.map((m) => {
          const obj = objects.find((o) => o.id === m.object_id);
          return (
            <Card
              key={m.id}
              title={obj?.title ?? "—"}
              subtitle={`结构 ID: ${m.id} · 对象 ID: ${m.object_id}`}
              accent={tab === "geometry" ? "teal" : "vermilion"}
              right={<Badge tone="default">{tabs.find((t) => t.key === m.kind)?.label}</Badge>}
            >
              <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-5">
                {/* 原图占位 */}
                <div className="bg-paper-2 border border-ink-line rounded-sm p-3">
                  <div className="aspect-[4/3] bg-paper border border-ink-line-2 rounded-sm flex flex-col items-center justify-center text-ink-3 relative overflow-hidden">
                    <div className="absolute inset-0 grid-paper-fine opacity-30" />
                    <ImageIcon size={32} className="relative mb-2 opacity-40" />
                    <span className="text-2xs relative">原图证据（始终保留）</span>
                  </div>
                  <div className="mt-2 text-2xs text-ink-4 text-center">
                    结构化结果不能替代原图证据
                  </div>
                </div>

                {/* 结构化字段 */}
                <div>
                  {m.kind === "quantity" && <QuantityView s={m.structure as QuantityStructure} />}
                  {m.kind === "chart" && <ChartView s={m.structure as ChartStructure} />}
                  {m.kind === "geometry" && <GeometryView s={m.structure as GeometryStructure} />}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function QuantityView({ s }: { s: QuantityStructure }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">数学对象</div>
        <div className="flex flex-wrap gap-2">
          {s.objects.map((o, i) => (
            <div key={i} className="px-3 py-1.5 bg-paper-2 border border-ink-line rounded-sm">
              <div className="text-xs font-medium text-ink">{o.name}</div>
              <div className="text-2xs text-ink-3 font-mono">
                {o.quantity ?? "?"} {o.unit}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-ok-soft/50 border border-ok/20 rounded-sm p-3">
          <div className="text-2xs uppercase text-ok font-mono mb-1">已知量</div>
          {s.known.map((k) => (
            <div key={k} className="text-xs text-ink-2">{k}</div>
          ))}
        </div>
        <div className="bg-vermilion-tint/50 border border-vermilion/20 rounded-sm p-3">
          <div className="text-2xs uppercase text-vermilion-deep font-mono mb-1">未知量</div>
          {s.unknown.map((k) => (
            <div key={k} className="text-xs text-ink-2">{k}</div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Badge tone="vermilion">{relationCN[s.relation]}</Badge>
        {s.parts && (
          <div className="text-xs text-ink-2 font-mono">
            每份 {s.parts.per ?? "?"} · 份数 {s.parts.count ?? "?"} · 总数 {s.parts.total ?? "?"}
          </div>
        )}
      </div>
      {s.unused_info.length > 0 && (
        <div className="bg-warn-soft/40 border border-warn/20 rounded-sm p-3">
          <div className="text-2xs uppercase text-warn font-mono mb-1">图中存在但当前题目未使用的信息</div>
          {s.unused_info.map((u) => (
            <div key={u} className="text-xs text-ink-2">{u}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function ChartView({ s }: { s: ChartStructure }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Badge tone="teal">
          {s.chart_type === "table" ? "表格" : s.chart_type === "bar" ? "条形统计图" : s.chart_type === "line" ? "折线统计图" : "象形统计图"}
        </Badge>
        <span className="text-xs text-ink-3">单位：{s.unit}</span>
        {s.per_grid && <Badge tone="gold">每格代表 {s.per_grid}</Badge>}
      </div>

      {/* 表格渲染 */}
      {s.chart_type === "table" && (
        <div className="overflow-x-auto">
          <table className="text-xs border-collapse">
            <thead>
              <tr>
                <th className="border border-ink-line bg-paper-2 px-3 py-1.5"></th>
                {s.col_titles.map((c) => (
                  <th key={c} className="border border-ink-line bg-paper-2 px-3 py-1.5 font-medium text-ink">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {s.row_titles.map((r, ri) => (
                <tr key={r}>
                  <td className="border border-ink-line bg-paper-2 px-3 py-1.5 font-medium text-ink">{r}</td>
                  {s.col_titles.map((_, ci) => {
                    const cell = s.cells.find((x) => x.row === ri && x.col === ci);
                    return (
                      <td
                        key={ci}
                        className={cn(
                          "border border-ink-line px-3 py-1.5 text-center",
                          cell?.blank_meaning === "intentional-blank" && "bg-warn-soft/40",
                          cell?.blank_meaning === "ocr-missed" && "bg-err-soft/40",
                        )}
                      >
                        {cell ? (cell.value ?? "—") : ""}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 象形统计图渲染 */}
      {s.chart_type === "pictograph" && (
        <div className="bg-paper-2 border border-ink-line rounded-sm p-4">
          <div className="space-y-2">
            {s.col_titles.map((c, ci) => {
              const cell = s.cells.find((x) => x.row === 0 && x.col === ci);
              const v = cell?.value ?? 0;
              const per = 20;
              const full = Math.floor(v / per);
              return (
                <div key={c} className="flex items-center gap-3">
                  <div className="w-12 text-xs text-ink-2">{c}</div>
                  <div className="flex-1 flex items-center gap-1">
                    {Array.from({ length: full }).map((_, i) => (
                      <span key={i} className="text-lg">📦</span>
                    ))}
                    {cell?.value === null && <span className="text-xs text-warn font-mono">?</span>}
                  </div>
                  <div className="w-12 text-xs font-mono text-ink-3 text-right">{cell?.value ?? "?"} {s.unit}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 空白含义区分 */}
      <div className="bg-paper-2 border border-ink-line rounded-sm p-3">
        <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">空白含义区分</div>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(blankCN).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-2xs">
              <span className={cn(
                "h-2 w-2 rounded-full",
                k === "value-zero" && "bg-ink",
                k === "intentional-blank" && "bg-warn",
                k === "ocr-missed" && "bg-err",
                k === "not-applicable" && "bg-ink-4",
              )} />
              <span className="text-ink-2">{v}</span>
            </div>
          ))}
        </div>
      </div>

      {s.shared_with_questions.length > 0 && (
        <div className="text-xs text-ink-3">
          <ShareIcon /> 图表与题目共用关系：{s.shared_with_questions.join("、")}
        </div>
      )}
    </div>
  );
}

function GeometryView({ s }: { s: GeometryStructure }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">图形对象</div>
        <div className="space-y-2">
          {s.objects.map((o, i) => (
            <div key={i} className="bg-paper-2 border border-ink-line rounded-sm p-3">
              <div className="flex items-center gap-2 mb-2">
                <Badge tone="teal">{o.type === "point" ? "点" : o.type === "line" ? "线" : o.type === "plane" ? "面" : "多边形"}</Badge>
                <span className="text-sm font-medium text-ink">{o.label}</span>
              </div>
              {"sides" in o && (
                <div className="grid grid-cols-3 gap-2 text-2xs">
                  <div>
                    <div className="text-ink-4 uppercase font-mono">边</div>
                    <div className="text-ink-2">{o.edges.join("、")}</div>
                  </div>
                  <div>
                    <div className="text-ink-4 uppercase font-mono">角</div>
                    <div className="text-ink-2">{o.angles.join("、")}</div>
                  </div>
                  <div>
                    <div className="text-ink-4 uppercase font-mono">顶点</div>
                    <div className="text-ink-2">{o.vertices.join("、")}</div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Info label="标记" items={s.marks.map((m) => ({ parallel: "平行", perpendicular: "垂直", equal: "相等", symmetry: "对称" }[m] ?? m))} tone="teal" />
        <Info label="单位" items={[s.units]} tone="default" />
        <Info label="操作" items={s.operations.map((o) => ({ translate: "平移", rotate: "旋转", "axis-symmetry": "轴对称", assemble: "拼合", split: "分割" }[o] ?? o))} tone="vermilion" />
        <Info label="状态" items={s.states.map((st) => ({ before: "操作前", during: "操作过程", after: "操作后" }[st] ?? st))} tone="gold" />
      </div>
    </div>
  );
}

function Info({ label, items, tone }: { label: string; items: string[]; tone: "teal" | "vermilion" | "gold" | "default" }) {
  const bg = { teal: "bg-teal-tint", vermilion: "bg-vermilion-tint", gold: "bg-gold-soft", default: "bg-paper-3" }[tone];
  return (
    <div className={cn("rounded-sm p-3", bg)}>
      <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">{label}</div>
      <div className="space-y-0.5">
        {items.map((it, i) => (
          <div key={i} className="text-xs text-ink-2">{it}</div>
        ))}
      </div>
    </div>
  );
}

function ShareIcon() {
  return <span className="text-gold">⇄</span>;
}
