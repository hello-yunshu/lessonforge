import { useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/ui/PageHeader";
import Card from "@/components/ui/Card";
import { ConfBadge } from "@/components/ui/Badge";
import ImageUpload from "@/components/ui/ImageUpload";
import { userUploads, coordinateTransforms, objects, pages } from "@/data";
import { cn, fmtDate } from "@/lib/utils";
import {
  ScanSearch,
  CheckCircle2,
  Circle,
  ArrowRight,
  Camera,
  FileImage,
  Smartphone,
  Printer,
  AlertTriangle,
} from "lucide-react";

const uploadTypeMap: Record<string, { label: string; icon: typeof Camera }> = {
  full: { label: "完整页面", icon: FileImage },
  half: { label: "半页", icon: FileImage },
  local: { label: "局部情境图", icon: FileImage },
  scene: { label: "情境图", icon: FileImage },
  chart: { label: "统计图", icon: FileImage },
  tilted: { label: "手机倾斜拍摄", icon: Smartphone },
  bw: { label: "黑白打印页", icon: Printer },
  annotated: { label: "带批注页面", icon: FileImage },
};

export default function Locate() {
  const [sel, setSel] = useState(userUploads[0].id);
  const [uploadHint, setUploadHint] = useState<string | null>(null);
  const upload = userUploads.find((u) => u.id === sel)!;
  const transform = coordinateTransforms.find((t) => t.upload_id === upload.id);
  const obj = objects.find((o) => o.id === upload.located_object_id);
  const page = pages.find((p) => p.id === upload.located_page_id);
  const lowConf = upload.confidence < 0.85;

  return (
    <div className="animate-ink-rise">
      <PageHeader
        no={8}
        eyebrow="UPLOAD LOCATE"
        title="上传定位"
        subtitle="完整教材资源库是标准答案，用户上传图片只是查询条件。先在已选择的'苏教版三上'标准库中检索，不虚构课时，仅返回版本/年级册次/单元/PDF页/印刷页/栏目/例题或练习/大题小题号。"
      />

      {/* 上传区 */}
      <Card className="mb-8" bodyClassName="p-6">
        <ImageUpload
          hint="拖拽上传图片或点击选择"
          subHint="支持完整页 / 半页 / 局部 / 手机倾斜 / 黑白打印 / 带批注"
          onFileSelected={(file) => setUploadHint(`已选择：${file.name}（${(file.size / 1024).toFixed(1)} KB）· 实际项目中此步骤会进入 8 步定位流程`)}
        />
        {uploadHint && (
          <div className="mt-3 px-3 py-2 bg-teal-tint/40 border border-teal/30 rounded-sm text-xs text-teal-2">
            {uploadHint}
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(uploadTypeMap).map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1.5 px-2.5 py-1 text-2xs bg-paper-2 border border-ink-line rounded-sm text-ink-2">
              <v.icon size={11} /> {v.label}
            </span>
          ))}
        </div>
      </Card>

      {/* 上传记录 */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3">上传记录</h2>
          <div className="space-y-2">
            {userUploads.map((u) => {
              const m = uploadTypeMap[u.upload_type];
              const isSel = u.id === sel;
              return (
                <button
                  key={u.id}
                  onClick={() => setSel(u.id)}
                  className={cn(
                    "w-full text-left p-3 bg-paper border rounded-sm transition-all",
                    isSel ? "border-vermilion ring-2 ring-vermilion/30" : "border-ink-line hover:shadow-card",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <m.icon size={14} className="text-ink-2 shrink-0" />
                    <span className="text-xs font-medium text-ink flex-1 truncate">{m.label}</span>
                    <ConfBadge value={u.confidence} />
                  </div>
                  <div className="mt-1 text-2xs text-ink-4 font-mono">{fmtDate(u.uploaded_at)}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 详情：8步流程 */}
        <div>
          <h2 className="font-serif text-base font-bold text-ink mb-3 flex items-center gap-2">
            <ScanSearch size={16} className="text-vermilion" />
            8 步定位流程
          </h2>

          {lowConf && (
            <div className="mb-4 p-3 bg-warn-soft/40 border border-warn/30 rounded-sm flex items-start gap-2">
              <AlertTriangle size={16} className="text-warn mt-0.5 shrink-0" />
              <div className="text-xs text-ink-2">
                <span className="font-medium text-warn">置信度偏低（{upload.confidence.toFixed(2)}）</span>
                ：信息严重缺失时建议重新拍摄。系统已降低置信度并提示。
              </div>
            </div>
          )}

          <Card bodyClassName="p-0">
            <ol className="divide-y divide-ink-line-2">
              {upload.pipeline.map((step) => (
                <li key={step.step} className="flex items-start gap-3 px-4 py-3">
                  {step.done ? (
                    <CheckCircle2 size={16} className="text-ok mt-0.5 shrink-0" />
                  ) : (
                    <Circle size={16} className="text-ink-4 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-2xs font-mono text-ink-4">步骤 {step.step}</span>
                      <span className={cn("text-sm", step.done ? "text-ink" : "text-ink-3")}>{step.name}</span>
                    </div>
                    {step.note && (
                      <p className="text-xs text-ink-3 mt-0.5 ml-1">{step.note}</p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          {/* 定位结果 */}
          {obj && page && (
            <Card title="定位结果" accent="vermilion" className="mt-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Result label="教材版本" value="苏教版" />
                <Result label="年级 · 册次" value="三年级 · 上册" />
                <Result label="PDF 页码" value={`第 ${page.pdf_page_no} 页`} />
                <Result label="印刷页码" value={`第 ${page.printed_page_no} 页`} />
                <Result label="栏目" value={obj.type === "example" ? "例题" : obj.type === "try" ? "试一试" : obj.type === "think-do" ? "想想做做" : "练习"} />
                <Result label="对象" value={obj.title} />
              </div>
              <div className="mt-4 pt-3 border-t border-ink-line-2 flex items-center justify-between">
                <ConfBadge value={upload.confidence} />
                <Link
                  to={`/library/page/${page.id}`}
                  className="text-xs text-teal hover:underline flex items-center gap-1"
                >
                  查看原页证据 <ArrowRight size={11} />
                </Link>
              </div>
            </Card>
          )}

          {/* 坐标变换 */}
          {transform && (
            <Card title="坐标配准与映射" className="mt-4" accent="teal">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Result label="变换类型" value={
                  transform.transform_kind === "similarity" ? "相似变换（缩放旋转）" :
                  transform.transform_kind === "homography" ? "单应性（透视倾斜）" :
                  "局部网格（页面弯曲）"
                } />
                <Result label="配准残差" value={`${transform.residual} px`} />
              </div>
              <div className="mt-3">
                <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono mb-1.5">变换矩阵（3×3 单应性）</div>
                <div className="bg-ink text-paper font-mono text-2xs p-3 rounded-sm overflow-x-auto">
                  [{transform.matrix.map((v) => v.toFixed(4)).join(", ")}]
                </div>
              </div>
              <div className="mt-3 text-2xs text-ink-4 leading-relaxed">
                用户照片中的批注和教材标准内容分开保存，不污染教材标准库。
                大小变化→归一化坐标；旋转/透视→单应性配准；局部截图→局部特征配准；页面弯曲→局部网格变换。
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Result({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-[0.15em] text-ink-3 font-mono">{label}</div>
      <div className="text-sm text-ink mt-0.5">{value}</div>
    </div>
  );
}
