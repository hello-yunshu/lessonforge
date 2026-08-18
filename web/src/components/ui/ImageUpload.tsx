import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Upload, ImageIcon, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ImageUploadProps = {
  /** 顶层提示文字（如"拖拽上传图片或点击选择"） */
  hint?: string;
  /** 辅助说明（如"支持完整页 / 半页 / 局部"） */
  subHint?: string;
  /** 已选文件变化时的回调，传入 DataURL（base64）和 File 信息 */
  onFileSelected?: (file: File, dataUrl: string) => void;
  /** 容器高度类（默认 py-10） */
  className?: string;
};

/**
 * 图片上传区组件 —— 支持「点击选择」与「拖拽放下」两种交互。
 * 仅在前端内存中预览（生成 ObjectURL / DataURL），不会上传到服务器。
 */
export function ImageUpload({
  hint = "拖拽上传图片或点击选择",
  subHint,
  onFileSelected,
  className,
}: ImageUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      alert("请选择图片文件（jpg/png/webp 等）");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setPreview(dataUrl);
      setFileName(file.name);
      onFileSelected?.(file, dataUrl);
    };
    reader.readAsDataURL(file);
  };

  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFile(e.target.files?.[0]);
    // 清空 input 的 value 以便重复选择同一文件
    e.target.value = "";
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const clearPreview = (e: React.MouseEvent) => {
    e.stopPropagation();
    setPreview(null);
    setFileName("");
  };

  // 有预览图时显示预览态
  if (preview) {
    return (
      <div className={cn("relative border border-ink-line rounded-sm overflow-hidden bg-paper-2", className)}>
        <img src={preview} alt="预览" className="w-full max-h-72 object-contain bg-paper" />
        <div className="absolute top-2 right-2 flex items-center gap-2">
          <span className="text-2xs px-2 py-0.5 bg-ink/70 text-paper rounded-sm font-mono truncate max-w-[200px]">
            {fileName}
          </span>
          <button
            type="button"
            onClick={clearPreview}
            className="p-1 bg-ink/70 text-paper rounded-sm hover:bg-vermilion transition-colors"
            title="清除预览"
          >
            <X size={12} />
          </button>
        </div>
        <div className="px-3 py-1.5 text-2xs text-ink-3 border-t border-ink-line-2 flex items-center gap-1.5">
          <ImageIcon size={11} />
          已预览 · 点击右侧 X 可清除，再次拖拽或点击下方按钮可重新选择
        </div>
      </div>
    );
  }

  // 无预览时显示上传区
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      className={cn(
        "border-2 border-dashed rounded-sm text-center cursor-pointer transition-colors outline-none",
        "hover:border-vermilion hover:text-vermilion focus:border-vermilion focus:text-vermilion",
        isDragOver ? "border-vermilion bg-vermilion-tint/30 text-vermilion" : "border-ink-line",
        className ?? "py-10",
      )}
    >
      <Upload size={28} className="mx-auto text-ink-3 mb-2" />
      <div className="text-sm text-ink-2 font-medium">{hint}</div>
      {subHint && <div className="mt-1 text-2xs text-ink-4">{subHint}</div>}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onInputChange}
        className="hidden"
      />
    </div>
  );
}

export default ImageUpload;
