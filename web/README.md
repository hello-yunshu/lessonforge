# 新版苏教版小学数学三年级上册教材数字化解析与例题练习识别系统

"AI 助力教师备课"项目的**教材基础层**。严格限定新版苏教版小学数学三年级上册，提供完整教材标准库、教材对象识别、上传图片原文定位、人机协同纠错的基础系统。

## 任务边界

- ✅ 当前完成：教材入库、页面/区域结构、图标/角色资源库、例题锚点识别、试一试/想想做做/练习对象识别、图片数学结构抽取、上传图片定位、坐标配准、纠错与版本、黄金样本与回归
- 🚫 当前禁止：课时划分、教学设计、学情分析、核心素养/课程标准映射、引入教辅/题库/AI 变式题、扩展人教版/北师大版

## 技术栈

React 18 + TypeScript + Vite + TailwindCSS 3 + Zustand + React Router v6 + lucide-react。
当前为**前端原型**，类型化 TypeScript mock 数据层严格模拟关系型数据库（对应 ER 设计）；生产环境预留 Express + PostgreSQL + 对象存储 + 全文检索 + 向量索引契约。

## 设计语言

宣纸暖白底 + 墨黑正文 + 朱砂红强调（印章意象）+ 墨青辅助。Noto Serif SC 标题 + Noto Sans SC 正文 + JetBrains Mono 数据。编辑型栅格 + 编号章节 + 印章徽记。

## 快速开始

```bash
npm install      # 安装依赖
npm run dev      # 启动开发服务器 (http://localhost:5173)
npm run check     # TypeScript 类型检查
npm run build     # 生产构建
```

## 路由总览（14 个页面）

| 路由 | 页面 |
|------|------|
| `/` | 工作台 |
| `/library` | 教材标准库（五层数字模型） |
| `/library/page/:pageId` | 页面与内容块（坐标体系） |
| `/icons` | 图标资源库 |
| `/characters` | 角色资源库 |
| `/examples` | 例题识别 |
| `/exercises` | 练习识别 |
| `/math-structure` | 图片数学结构抽取 |
| `/locate` | 上传定位（8 步流程） |
| `/corrections` | 纠错与版本 |
| `/review` | 审核队列 |
| `/golden-samples` | 黄金样本与回归 |
| `/specs` | 规范文档中心（19 项交付物） |
| `/status` | 完成情况 |

## 数据层

`src/data/` 下类型化 mock，对应 ER 设计（25+ 实体）：
`textbook / page / content_block / textbook_object / example / exercise / question_group / big_question / small_question / shared_material / character / character_speech / icon / icon_variant / coordinate / math_structure / relation / correction / version / review_task / golden_sample / regression_test / user_upload / coordinate_transform`

完整 ER 图与 DDL 见 `.trae/documents/TechnicalArchitecture.md`，产品需求见 `.trae/documents/PRD.md`。

## 数据存储原则

- 正式主数据不得只存在向量库或 Markdown 中
- 向量索引只作辅助（页面/区域定位、题目语义、数量关系、数据结构、几何关系描述向量）
- 任何无法确认的内容标记不确定并进入人工审核，不得猜测填充
- 原始 PDF 不得被修改或覆盖；派生图不得作为新的人工真值
