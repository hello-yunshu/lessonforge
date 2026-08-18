# Phase 10 / 1.0.1 依赖与摘要登记

## 核心 Python 依赖

| 名称 | 已安装 | 版本 | 许可证元数据 | 安装树 SHA-256 |
|---|---|---|---|---|
| fastapi | True | 0.128.2 | MIT | 7a3d1d7d44bd33597669284b130057111dd3d7e29edbd20b841d05830960b80c |
| httpx | True | 0.28.1 | BSD-3-Clause | 2ab39e7e592599331023529a5d1348fc1fb3e15382e956efe337e861239cb26f |
| Pillow | True | 12.2.0 | MIT-CMU | 3bd6f3ff142c0c0b2fd83efb5861a9a0f2d838c0a914fe87c0d7e6eb2543dbd8 |
| pydantic | True | 2.13.4 | MIT | 2499a54a636eec4ececb4270d09dcd109c5915e40cdb07d34bcdbfe342dbbe0d |
| pydantic-settings | True | 2.14.1 | MIT | 6db5e7d6083182504c1239199c13b0e78a810d9982f29988313900b2c0b4a7c9 |
| PyMuPDF | True | 1.26.7 | Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License | 6ceaa7971ea1254eb4cc2cf02fad6f03de3bd3fdde25cb4621e28cc790ae40c3 |
| numpy | True | 2.3.5 | Copyright (c) 2005-2025, NumPy Developers. | fc76c1f87a92a707a897c562cd75623a3c5381754b6ac2c944d6626d4ea1d903 |
| opencv-python-headless | True | 4.13.0.92 | Apache 2.0 | 718aff963694b590729e186dcde52b0254b4b14954ddb8f2ba82d7a45834b9ae |
| packaging | True | 25.0 | - | 56c4464a9d8313259aa6ffba91713fb7114c074c253e304064aff5de7e1823c4 |
| cryptography | True | 46.0.4 | Apache-2.0 OR BSD-3-Clause | 79fd506811755361e35747a461414f6dce8c64e5a5b94f0b640902624e718f5c |
| python-multipart | True | 0.0.29 | Apache-2.0 | 711ff1f5e02687f8fb577db1e4ca96e5b2f4d56dcc0069ea224f122ca7bb7e56 |
| PyYAML | True | 6.0.3 | MIT | 1ee7c0bfc54933c35c0b5b2c5f63ccbf2e0a78dd0956fbbd0b7ae417c3f27d10 |
| uvicorn | True | 0.48.0 | BSD-3-Clause | 3c1f5b4577e3568b8587d93ff107f292722d3ae19a38f3ec7325f23d3afee4ef |
| pytest | True | 9.0.2 | MIT | 42d0a31aee7a2d13a6d038f9e725aa13c820ec4d83d8c92cd1bd775d0290fdd2 |
| coverage | True | 7.13.3 | Apache-2.0 | e9e0f45b04f6db8990605dba50fe111637a20c92ec72a9a4ffb40d3636fca6a0 |
| ruff | False | - | - | - |
| mypy | False | - | - | - |
| cyclonedx-bom | False | - | - | - |

## 外部解析引擎

| 名称 | 当前环境已安装 | 版本 | 安装树 SHA-256 |
|---|---|---|---|
| paddleocr | False | - | - |
| paddlepaddle | False | - | - |
| openocr-python | False | - | - |
| mineru | False | - | - |
| dvc | False | - | - |
| mlflow | False | - | - |

生产部署时，安装树摘要不能替代容器镜像和模型文件摘要。外部解析器只有同时固定服务版本与 `required_artifact_sha256` 才会通过健康检查。

> **许可证门禁：** 当前 Native PDF 路线依赖 PyMuPDF。其安装元数据声明为 AGPL-3.0 或 Artifex 商业许可证；非兼容产品在完成法务审查或取得商业许可证前不得作为生产发行结论。
