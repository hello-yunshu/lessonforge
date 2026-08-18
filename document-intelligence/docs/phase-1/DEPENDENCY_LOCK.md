# Phase 1 依赖与摘要登记

## 核心 Python 依赖

| 名称 | 已安装 | 版本 | 安装树 SHA-256 |
|---|---|---|---|
| fastapi | True | 0.128.2 | 7a3d1d7d44bd33597669284b130057111dd3d7e29edbd20b841d05830960b80c |
| httpx | True | 0.28.1 | 2ab39e7e592599331023529a5d1348fc1fb3e15382e956efe337e861239cb26f |
| Pillow | True | 12.2.0 | 3bd6f3ff142c0c0b2fd83efb5861a9a0f2d838c0a914fe87c0d7e6eb2543dbd8 |
| pydantic | True | 2.13.4 | 2499a54a636eec4ececb4270d09dcd109c5915e40cdb07d34bcdbfe342dbbe0d |
| pydantic-settings | True | 2.14.1 | 6db5e7d6083182504c1239199c13b0e78a810d9982f29988313900b2c0b4a7c9 |
| PyMuPDF | True | 1.26.7 | 6ceaa7971ea1254eb4cc2cf02fad6f03de3bd3fdde25cb4621e28cc790ae40c3 |
| python-multipart | True | 0.0.29 | 711ff1f5e02687f8fb577db1e4ca96e5b2f4d56dcc0069ea224f122ca7bb7e56 |
| PyYAML | True | 6.0.3 | 1ee7c0bfc54933c35c0b5b2c5f63ccbf2e0a78dd0956fbbd0b7ae417c3f27d10 |
| uvicorn | True | 0.48.0 | 3c1f5b4577e3568b8587d93ff107f292722d3ae19a38f3ec7325f23d3afee4ef |
| pytest | True | 9.0.2 | 42d0a31aee7a2d13a6d038f9e725aa13c820ec4d83d8c92cd1bd775d0290fdd2 |
| coverage | True | 7.13.3 | e9e0f45b04f6db8990605dba50fe111637a20c92ec72a9a4ffb40d3636fca6a0 |

## 外部解析引擎

| 名称 | 当前环境已安装 | 版本 | 安装树 SHA-256 |
|---|---|---|---|
| paddleocr | False | - | - |
| paddlepaddle | False | - | - |
| openocr-python | False | - | - |
| mineru | False | - | - |

生产部署时，安装树摘要不能替代容器镜像和模型文件摘要。外部解析器只有同时固定服务版本与 `required_artifact_sha256` 才会通过健康检查。
