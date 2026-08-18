import { cn } from "@/lib/utils";

type SealProps = {
  text: string; // 印面文字（竖排或横排）
  size?: "sm" | "md" | "lg" | "xl";
  shape?: "square" | "round";
  rotate?: number;
  className?: string;
};

/** 印章徽记 — 朱砂红方印，带印泥纹理 */
export default function SealStamp({
  text,
  size = "md",
  shape = "square",
  rotate = -2,
  className,
}: SealProps) {
  const sizes = {
    sm: "h-10 w-10 text-[0.6rem]",
    md: "h-16 w-16 text-xs",
    lg: "h-24 w-24 text-sm",
    xl: "h-32 w-32 text-base",
  };
  return (
    <div
      className={cn(
        "seal relative flex items-center justify-center font-serif font-bold tracking-seal select-none animate-seal",
        shape === "round" ? "rounded-full" : "rounded-[3px]",
        sizes[size],
        className,
      )}
      style={{ transform: `rotate(${rotate}deg)` }}
    >
      <span className="relative z-10 leading-tight text-center">{text}</span>
    </div>
  );
}
