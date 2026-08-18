import { useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import {
  ScrollText,
  FolderTree,
  Database,
  Map,
  Stamp,
  Users,
  BookOpenCheck,
  Share2,
  Sigma,
  ScanSearch,
  GitCommitVertical,
  History,
  Target,
  FlaskConical,
  ListChecks,
  Gauge,
  FileText,
  ChevronRight,
} from "lucide-react";

type Deliverable = {
  no: number;
  name: string;
  desc: string;
  icon: typeof FolderTree;
  group: "范围" | "数据" | "资源" | "识别" | "结构" | "流程" | "质量";
  status: "done" | "in-progress" | "planned";
  detail?: React.ReactNode;
};

const fieldDict: { field: string; type: string; desc: string }[] = [
  { field: "textbook.version", type: "TEXT", desc: "苏教版（固定）" },
  { field: "content_block.confidence", type: "REAL ∈ [0,1]", desc: "低于0.8入审核队列" },
  { field: "content_block.review_status", type: "ENUM", desc: "pending/confirmed/rejected，仅confirmed进正式库" },
  { field: "textbook_object.page_ids[]", type: "TEXT[]", desc: "支持跨页对象" },
  { field: "character.role", type: "ENUM", desc: "student/teacher，与话语功能分开存储" },
  { field: "character_speech.speech_function", type: "ENUM", desc: "ask-reason/give-method/…，与角色身份分开" },
  { field: "icon_variant.source_icon_id", type: "TEXT FK", desc: "所有派生图必须记录来源原图" },
  { field: "math_structure.kind", type: "ENUM", desc: "quantity/chart/geometry" },
  { field: "relation.rel_type", type: "ENUM", desc: "显式关系，不依赖空间距离" },
  { field: "coordinate.kind", type: "ENUM", desc: "pixel/normalized/polygon" },
  { field: "coordinate_transform.transform_kind", type: "ENUM", desc: "similarity/homography/local-grid" },
  { field: "correction.iteration", type: "INT 1-3", desc: "三级迭代：即时/资源库/正式" },
];

const deliverables: Deliverable[] = [
  { no: 1, name: "项目范围与边界说明", desc: "苏教版三上专用；禁止课时/教学设计/学情/素养映射", icon: FileText, group: "范围", status: "done" },
  { no: 2, name: "教材数字包目录结构", desc: "原始PDF/页面图/区域图/上传图/解析器输出/变体", icon: FolderTree, group: "范围", status: "done" },
  { no: 3, name: "数据库实体关系设计", desc: "ER图含25+实体，见下方", icon: Database, group: "数据", status: "done" },
  { no: 4, name: "字段字典", desc: "关键字段类型与含义，见下方", icon: Database, group: "数据", status: "done" },
  { no: 5, name: "坐标与页面配准规范", desc: "三类坐标+三种变换策略", icon: Map, group: "数据", status: "done" },
  { no: 6, name: "图标资源库格式", desc: "原图+8变体+来源记录+用途标记", icon: Stamp, group: "资源", status: "done" },
  { no: 7, name: "角色资源库格式", desc: "6角色，身份与话语功能分离", icon: Users, group: "资源", status: "done" },
  { no: 8, name: "例题与练习识别规则", desc: "书本图标强锚点+对象封装+边界判断", icon: BookOpenCheck, group: "识别", status: "in-progress" },
  { no: 9, name: "图片及共享材料归属规则", desc: "不按距离绑定，综合7项判据", icon: Share2, group: "识别", status: "in-progress" },
  { no: 10, name: "数量关系结构规范", desc: "对象/数量/单位/已知未知/加减乘除/比较倍总分", icon: Sigma, group: "结构", status: "in-progress" },
  { no: 11, name: "表格与统计图结构规范", desc: "行列/数据/空白含义/轴/刻度/每格代表", icon: Sigma, group: "结构", status: "in-progress" },
  { no: 12, name: "空间与几何图结构规范", desc: "点线面/边角顶点/标记/拼合分割/平移旋转轴对称", icon: Sigma, group: "结构", status: "in-progress" },
  { no: 13, name: "用户上传图片定位流程", desc: "8步定位+坐标配准+置信度", icon: ScanSearch, group: "流程", status: "in-progress" },
  { no: 14, name: "用户纠错数据规范", desc: "12字段记录+三级迭代", icon: GitCommitVertical, group: "流程", status: "done" },
  { no: 15, name: "资源库、规则和模型版本机制", desc: "版本号/审计/回滚/旧结果保留/回归测试", icon: History, group: "流程", status: "done" },
  { no: 16, name: "黄金样本标注规范", desc: "15类覆盖样本", icon: Target, group: "质量", status: "done" },
  { no: 17, name: "自动化测试和回归测试", desc: "用例+通过率+失败明细", icon: FlaskConical, group: "质量", status: "in-progress" },
  { no: 18, name: "识别结果人工审核界面", desc: "三栏审核+原页证据并排", icon: ListChecks, group: "质量", status: "done" },
  { no: 19, name: "当前完成情况、遗留问题和下一步建议", desc: "见完成情况页", icon: Gauge, group: "质量", status: "in-progress" },
];

const groupOrder: Deliverable["group"][] = ["范围", "数据", "资源", "识别", "结构", "流程", "质量"];

export default function Specs() {
  const [expanded, setExpanded] = useState<number | null>(3);

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={12}
        eyebrow="SPECIFICATION CENTER"
        title="规范文档中心"
        subtitle="十六·最终交付物。19 项交付物覆盖范围/数据/资源/识别/结构/流程/质量。所有结论必须能够回到原教材 PDF 页、印刷页和精确区域。"
        right={<Badge tone="vermilion">19 项交付物</Badge>}
      />

      {/* 交付物索引（按分组） */}
      {groupOrder.map((g) => {
        const items = deliverables.filter((d) => d.group === g);
        if (items.length === 0) return null;
        return (
          <div key={g} className="mb-8">
            <h2 className="font-serif text-lg font-bold text-ink mb-3 flex items-center gap-2">
              <span className="chapter-num">{g}</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {items.map((d) => {
                const isOpen = expanded === d.no;
                return (
                  <Card key={d.no} noPad bodyClassName="p-0">
                    <button
                      onClick={() => setExpanded(isOpen ? null : d.no)}
                      className="w-full text-left p-4 hover:bg-paper-2 transition-colors"
                    >
                      <div className="flex items-start gap-3">
                        <span className="font-serif text-sm font-bold text-vermilion w-6 shrink-0">
                          {d.no.toString().padStart(2, "0")}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <d.icon size={14} className="text-ink-2 shrink-0" />
                            <span className="text-sm font-medium text-ink">{d.name}</span>
                          </div>
                          <p className="mt-1 text-xs text-ink-3">{d.desc}</p>
                          <div className="mt-2 flex items-center gap-2">
                            <Badge tone={d.status === "done" ? "ok" : d.status === "in-progress" ? "warn" : "default"}>
                              {d.status === "done" ? "已完成" : d.status === "in-progress" ? "进行中" : "计划中"}
                            </Badge>
                            <ChevronRight
                              size={12}
                              className={cn("text-ink-4 transition-transform", isOpen && "rotate-90")}
                            />
                          </div>
                        </div>
                      </div>
                    </button>

                    {/* 展开详情：ER & 字段字典 */}
                    {isOpen && d.no === 3 && (
                      <div className="px-4 pb-4 border-t border-ink-line-2 pt-3 bg-paper-2/50">
                        <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-2">ER 关系（核心实体）</div>
                        <pre className="text-2xs font-mono text-ink-2 bg-ink text-paper p-3 rounded-sm overflow-x-auto leading-relaxed">
{`TEXTBOOK ─┬─ PAGE ─── CONTENT_BLOCK ─── COORDINATE
          ├─ UNIT ─ SECTION ─┐
          └─ CORRECTION       └─ TEXTBOOK_OBJECT ─┬─ EXAMPLE
                                                  ├─ EXERCISE ─ QUESTION_GROUP
                                                  │           └─ BIG_QUESTION ─ SMALL_QUESTION
                                                  ├─ SHARED_MATERIAL
                                                  ├─ CHARACTER_SPEECH ─ CHARACTER
                                                  ├─ MATH_STRUCTURE
                                                  └─ RELATION
USER_UPLOAD ─ COORDINATE_TRANSFORM
ICON ─ ICON_VARIANT       VERSION
REVIEW_TASK               GOLDEN_SAMPLE ─ REGRESSION_TEST`}
                        </pre>
                        <div className="mt-2 text-2xs text-ink-4">
                          完整 ER 图与 DDL 详见 <code className="font-mono text-teal">.trae/documents/TechnicalArchitecture.md</code>
                        </div>
                      </div>
                    )}
                    {isOpen && d.no === 4 && (
                      <div className="px-4 pb-4 border-t border-ink-line-2 pt-3 bg-paper-2/50">
                        <div className="overflow-x-auto">
                          <table className="w-full text-2xs">
                            <thead>
                              <tr className="text-left text-ink-3 font-mono border-b border-ink-line">
                                <th className="py-1.5 pr-3">字段</th>
                                <th className="py-1.5 pr-3">类型</th>
                                <th className="py-1.5">说明</th>
                              </tr>
                            </thead>
                            <tbody>
                              {fieldDict.map((f) => (
                                <tr key={f.field} className="border-b border-ink-line-2">
                                  <td className="py-1.5 pr-3 font-mono text-vermilion-deep">{f.field}</td>
                                  <td className="py-1.5 pr-3 font-mono text-teal-2">{f.type}</td>
                                  <td className="py-1.5 text-ink-2">{f.desc}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {isOpen && d.no === 5 && (
                      <div className="px-4 pb-4 border-t border-ink-line-2 pt-3 bg-paper-2/50 text-xs space-y-2">
                        <div>
                          <span className="text-ink-3">标准页像素坐标</span>：基于教材标准页面宽高的像素坐标
                        </div>
                        <div>
                          <span className="text-ink-3">归一化坐标</span>：所有坐标转换到 0–1 范围
                        </div>
                        <div>
                          <span className="text-ink-3">多边形区域</span>：除矩形外支持四边形和不规则多边形
                        </div>
                        <div>
                          <span className="text-ink-3">用户照片坐标</span>：每次上传单独保存实际像素坐标
                        </div>
                        <div>
                          <span className="text-ink-3">坐标变换</span>：similarity（缩放旋转）/ homography（透视）/ local-grid（弯曲）
                        </div>
                        <div className="mt-2 text-2xs text-ink-4">
                          批注与教材标准内容分开保存，不污染教材标准库
                        </div>
                      </div>
                    )}
                    {isOpen && d.no === 9 && (
                      <div className="px-4 pb-4 border-t border-ink-line-2 pt-3 bg-paper-2/50 text-xs">
                        <div className="text-ink-3 mb-1.5">综合 7 项判据（不按距离绑定）：</div>
                        <ul className="space-y-1 text-ink-2">
                          <li>· 版面边界</li>
                          <li>· 题号</li>
                          <li>· 栏目</li>
                          <li>· 引线和箭头</li>
                          <li>· 题干中的"看图""根据下图"</li>
                          <li>· 图中编号</li>
                          <li>· 前后页连续关系 + 是否为解题必要条件</li>
                        </ul>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          </div>
        );
      })}

      <Card className="mt-6" bodyClassName="p-4 flex items-center gap-3">
        <ScrollText size={18} className="text-vermilion shrink-0" />
        <div className="flex-1 text-xs text-ink-2">
          所有结论必须能够回到原教材 PDF 页、印刷页和精确区域。任何无法确认的内容必须标记为不确定并进入人工审核，不得猜测填充。
        </div>
      </Card>
    </div>
  );
}
