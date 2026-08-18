# Phase 12 / 1.0.3-rc.1 依赖与许可证登记

核心原生PDF文本提取已改为 `pypdf`。PyMuPDF只作为可选像素渲染器，
生产配置默认关闭，只有显式完成许可证证明后才能启用。

## 核心依赖

| 名称 | 已安装 | 版本 | 许可证 | 安装树SHA-256 |
|---|---|---|---|---|
| fastapi | True | 0.128.2 | MIT | 7a3d1d7d44bd33597669284b130057111dd3d7e29edbd20b841d05830960b80c |
| httpx | True | 0.28.1 | BSD-3-Clause | 2ab39e7e592599331023529a5d1348fc1fb3e15382e956efe337e861239cb26f |
| Pillow | True | 12.2.0 | MIT-CMU | 3bd6f3ff142c0c0b2fd83efb5861a9a0f2d838c0a914fe87c0d7e6eb2543dbd8 |
| pydantic | True | 2.13.4 | MIT | 2499a54a636eec4ececb4270d09dcd109c5915e40cdb07d34bcdbfe342dbbe0d |
| pydantic-settings | True | 2.14.1 | MIT | 6db5e7d6083182504c1239199c13b0e78a810d9982f29988313900b2c0b4a7c9 |
| pypdf | True | 5.9.0 | BSD-3-Clause | 99047eb292bb92803e1feeae740a371cbf001590da0626a55631f07155cdf8bc |
| numpy | True | 2.3.5 | Copyright (c) 2005-2025, NumPy Developers. | fc76c1f87a92a707a897c562cd75623a3c5381754b6ac2c944d6626d4ea1d903 |
| opencv-python-headless | True | 4.13.0.92 | Apache 2.0 | 718aff963694b590729e186dcde52b0254b4b14954ddb8f2ba82d7a45834b9ae |
| packaging | True | 25.0 | - | 56c4464a9d8313259aa6ffba91713fb7114c074c253e304064aff5de7e1823c4 |
| cryptography | True | 46.0.4 | Apache-2.0 OR BSD-3-Clause | 79fd506811755361e35747a461414f6dce8c64e5a5b94f0b640902624e718f5c |
| python-multipart | True | 0.0.29 | Apache-2.0 | 711ff1f5e02687f8fb577db1e4ca96e5b2f4d56dcc0069ea224f122ca7bb7e56 |
| PyYAML | True | 6.0.3 | MIT | 1ee7c0bfc54933c35c0b5b2c5f63ccbf2e0a78dd0956fbbd0b7ae417c3f27d10 |
| uvicorn | True | 0.48.0 | BSD-3-Clause | 3c1f5b4577e3568b8587d93ff107f292722d3ae19a38f3ec7325f23d3afee4ef |

## 正式质量工具状态

未安装的工具不会被描述为本地通过；正式CI必须执行Ruff、Mypy、
pip-audit、测试超时门禁和SBOM生成。

| 名称 | 当前环境已安装 | 版本 |
|---|---|---|
| pytest | True | 9.0.2 |
| coverage | True | 7.13.3 |
| ruff | False | - |
| mypy | False | - |
| cyclonedx-bom | False | - |
| pip-audit | False | - |
