# Phase 12 / 1.0.3-rc.1 依赖与许可证登记

核心原生PDF文本提取已改为 `pypdf`。PyMuPDF只作为可选像素渲染器，
生产配置默认关闭，只有显式完成许可证证明后才能启用。

## 核心依赖

| 名称 | 已安装 | 版本 | 许可证 | 安装树SHA-256 |
|---|---|---|---|---|
| fastapi | True | 0.141.1 | MIT | 8d7a12059bbdba76b56708c46aa2baac88070bc1e92581dfcb5b8061edb48f8c |
| httpx | True | 0.28.1 | BSD-3-Clause | cc97810abed172201f226eb2203b6a61b6427a73e5cd9a1da17d5a98e2068244 |
| Pillow | True | 12.3.0 | MIT-CMU | 47f78ad45f3f47ae5d1f690ae8e11197804d83967715c7d424cbd224c1093263 |
| pydantic | True | 2.13.4 | MIT | 18bfb6365033f14d3ff59c90400862582c16e2603df8cd18f2600ab9c0cd5fbb |
| pydantic-settings | True | 2.14.2 | MIT | 80b56c4c2d053d60661c5d29650ad58f3dbe8f7597d50bf120497b9488a554df |
| pypdf | True | 6.16.1 | BSD-3-Clause | d161912a3262c71fb8bd19cbf1756c007c367aa3ffed41049d8d9b1f823bbde0 |
| numpy | True | 2.3.5 | Copyright (c) 2005-2025, NumPy Developers. | 475dab6577904b27a258b794f44ce2be4117b5528ed9d244688a6cfd5d98d5df |
| opencv-python-headless | True | 4.13.0.92 | Apache 2.0 | 5ee710ab2311c0d95bdbe68e4e0d27d05493e06bec4f2e739096d4c84414f876 |
| packaging | True | 25.0 | - | 73984dee0806cc6d675af3103c88b0b6baf73113b20bcb039187594eb2776a0f |
| cryptography | True | 50.0.0 | Apache-2.0 OR BSD-3-Clause | 5328ba527ad2dddad9c7b29e2705161b64ab9d11fc01a8001c1f5253761bd1fc |
| python-multipart | True | 0.0.31 | Apache-2.0 | 05925e5a17137a4e7da82b32ab1477567d13673667ef3b4bccffaba92640c097 |
| PyYAML | True | 6.0.3 | MIT | 9da406cb92a9797b330fb58cb2ce29c541ed42f48838c5ce9d410f4c87eb279e |
| uvicorn | True | 0.48.0 | BSD-3-Clause | 9a38196597aa5dd0b0f619c313b489883634c7d955081ab4676d3d448c230768 |

## 正式质量工具状态

未安装的工具不会被描述为本地通过；正式CI必须执行Ruff、Mypy、
pip-audit、测试超时门禁和SBOM生成。

| 名称 | 当前环境已安装 | 版本 |
|---|---|---|
| pytest | True | 9.0.2 |
| coverage | True | 7.13.3 |
| ruff | True | 0.14.14 |
| mypy | True | 1.19.1 |
| cyclonedx-bom | True | 7.2.1 |
| pip-audit | True | 2.9.0 |
