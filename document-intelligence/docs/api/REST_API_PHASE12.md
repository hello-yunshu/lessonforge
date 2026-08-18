# Phase 12 REST API与生产安全边界

## 生产身份头

生产档所有 `/v1/*` 请求必须同时提供：

- `X-API-Token`
- `X-Tenant-ID`
- `X-Subject-ID`

服务端配置 `DI_API_TENANT_TOKENS_SHA256_JSON`，只保存令牌SHA-256。开发档保持历史
兼容，但不得用于公网生产。

## 公共探针

- `GET /livez`：进程存活；
- `GET /readyz`：工作区、解析器和安全配置就绪；
- `GET /healthz`：非敏感能力状态；
- `GET /metrics`：生产档默认404，配置独立摘要令牌后才可访问。

## 新增受保护接口

`GET /v1/capabilities` 返回候选版能力矩阵，明确：扫描OCR未资格、标准PDF视觉匹配可能
关闭、Rill Shadow只建议、Tier 1 Assist需资格、`boundedAuto=false`、多节点不支持。

## 核心资源授权

创建解析结果时，当前租户获得对应run和document entitlement。结构恢复、领域执行、
文档族检测和Rill评估会继续生成衍生entitlement。读取接口在查询底层内容前检查租户
授权，未授权与不存在统一返回404。

## 附加管理权限

标准库、Domain Pack、Family Detection、Rill、MLOps、生产资格和活动编排继续使用各自
独立管理令牌与写入开关。租户API令牌不能替代这些高权限门禁。
