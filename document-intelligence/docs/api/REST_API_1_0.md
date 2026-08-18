# REST API 1.0冻结补充

## 冻结查询

### `GET /v1/contracts/freeze`

返回：

- `manifest`：v1冻结清单；
- `verification`：实时实现相对冻结清单的验证结果。

该端点不返回密钥、令牌、运行态正文或模型参数，不需要管理令牌。

## 兼容规则

`docs/phase-9/FROZEN_CONTRACTS_V1.json`中登记的REST方法与路径在1.x内不得删除或改变含义。1.x可新增隔离端点，但不能借新增端点绕过既有权限、证据、Rill或MLOps门禁。

## 生产资格

返回的`status=engineering_frozen`仅说明契约稳定。`production_qualified=false`时，客户端不得把该响应解释为解析准确率、许可证或规模运行已经通过生产认证。
