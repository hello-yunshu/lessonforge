/** @type {import('tailwindcss').Config} */

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        // 宣纸暖白底
        paper: "#FAF7F0",
        "paper-2": "#F3EEE2",
        "paper-3": "#EDE6D5",
        // 墨黑系
        ink: "#1F1B16",
        "ink-2": "#4A4239",
        "ink-3": "#6B6258",
        "ink-4": "#8A8174",
        "ink-line": "#D9CFB8",
        "ink-line-2": "#E8E0D0",
        // 朱砂红（印章）
        vermilion: "#B33A3A",
        "vermilion-deep": "#8B2C2C",
        "vermilion-soft": "#E8D4D0",
        "vermilion-tint": "#F5E6E3",
        // 墨青（数据/图表）
        teal: "#3A5A5A",
        "teal-2": "#2C4545",
        "teal-soft": "#D5DDDB",
        "teal-tint": "#E8EEED",
        // 印章金
        gold: "#B8923A",
        "gold-soft": "#E8D9B0",
        // 审核状态
        ok: "#3F7A4E",
        "ok-soft": "#D7E6DC",
        warn: "#C2862A",
        "warn-soft": "#F0E2C8",
        err: "#A83333",
        "err-soft": "#EFD6D4",
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', "Songti SC", "SimSun", "serif"],
        sans: ['"Noto Sans SC"', "PingFang SC", "Microsoft YaHei", "sans-serif"],
        mono: ['"JetBrains Mono"', "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        seal: "0 1px 0 rgba(31,27,22,0.04), 0 0 0 1px rgba(179,58,58,0.15)",
        card: "0 1px 2px rgba(31,27,22,0.04), 0 0 0 1px #E8E0D0",
        "card-hover": "0 4px 16px rgba(31,27,22,0.08), 0 0 0 1px #D9CFB8",
        ink: "0 1px 3px rgba(31,27,22,0.06)",
      },
      letterSpacing: {
        seal: "0.12em",
      },
    },
  },
  plugins: [],
};
