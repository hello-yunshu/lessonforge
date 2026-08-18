# lessonforge

教材数字化解析与例题练习识别的**前端原型**与配套**文档智能解析服务**。

> 本仓库取的是"教（lesson）+ 锻造（forge）"之意，聚焦把教材内容解析为结构、可检索、可核验的数据底座。

## 项目定位

本仓库是"AI 助力教师备课"项目的**教材基础层**工作，包含两个独立组件：

| 目录 | 说明 | 技术栈 |
| --- | --- | --- |
| [`web/`](./web/) | 教材标准库 / 页面定位 / 例题练习识别 / 上传原图定位 / 人机协同纠错的前端原型 | React 18 · TypeScript · Vite · TailwindCSS · Zustand |
| [`document-intelligence/`](./document-intelligence/) | 通用复杂文档智能解析、多领域适配与受控 Rill Assist/MLOps 平台 | Python 3.11 · FastAPI · PyMuPDF |

两个组件独立开发、独立构建，可分开部署。

## 目录结构

```
lessonforge
├── web/                     # 前端原型
│   ├── src/data/            # 类型定义（TS mock 数据层，不含教材版权数据）
│   ├── src/pages/           # 14 个功能页面
│   ├── src/components/      # UI 组件
│   ├── api/                 # 服务端代理（DI 调用封装）
│   ├── scripts/             # 结果文件生成脚本
│   └── public/              # 静态资源
├── document-intelligence/   # 文档智能解析服务
│   ├── src/document_intelligence/   # 服务源码
│   ├── defaults/            # 领域包（解析规则 / 校验器 / 审核）
│   ├── configs/             # 解析器配置
│   ├── tests/               # 测试套件
│   └── scripts/             # 发布 / 校验 / SBOM 脚本
└── LICENSE                  # AGPL-3.0
```

## 快速开始

### 前端 web

```bash
cd web
npm install
npm run dev        # 开发服务器 http://localhost:5173
npm run check      # TypeScript 类型检查
npm run build      # 生产构建
npm run lint       # ESLint 检查
```

### 文档智能解析服务 document-intelligence

```bash
cd document-intelligence
python -m venv .venv
.venv/Scripts/activate        # Windows；macOS/Linux 用 .venv/bin/activate
pip install -e ".[dev]"
pytest                         # 运行测试
doc-intelligence --help        # 命令行入口
```

服务以 FastAPI 提供 REST API，详见 [`document-intelligence/docs/api/REST_API_1_0.md`](./document-intelligence/docs/api/REST_API_1_0.md)。

## 重要说明：版权与数据

- 本仓库**仅包含代码与文档**，不包含任何教材原文、扫描页图像、课时/例题/练习分析数据等版权内容。
- `web/src/data/` 通过类型定义与空结构占位，保证前端可构建，但不携带任何教材数据。
- 涉及教材解析的运行期资产（如图标、角色、指纹资产等）均不随源码发布。
- 使用或二次开发时，请自行获取具备授权/版权的教材数据，勿将受版权保护的教材内容并入公开分支。

## 开源协议

本项目采用 [GNU AGPL-3.0](./LICENSE)（Affero 通用公共许可证 3.0）——一种严格的强版权（copyleft）许可：任何人修改并对外提供基于本项目的网络服务时，必须开放其修改后的完整对应源码。

```
Copyright (c) 2026 lessonforge contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```