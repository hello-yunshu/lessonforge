# REST API Phase 2

## 1. 标准库访问认证

标准文档列表、注册和正文返回使用请求头：

```http
X-Standard-Token: <raw-token>
```

服务端只配置令牌的SHA-256：

```bash
DI_STANDARD_ACCESS_TOKEN_SHA256=<64位小写SHA-256>
```

未配置令牌、缺少请求头或令牌错误均返回：

```json
{"error":{"code":"STANDARD_ACCESS_DENIED","severity":"P0"}}
```

## 2. 标准文档列表

```http
GET /v1/standard
X-Standard-Token: <raw-token>
```

## 3. 注册标准文档

```http
POST /v1/standard/register
X-Standard-Token: <raw-token>
Content-Type: application/json
```

```json
{
  "run_id": "run_...",
  "reviewer": "reviewer-id",
  "approval_note": "reason and evidence",
  "approved": true
}
```

除令牌外，还必须显式设置：

```bash
DI_ENABLE_STANDARD_WRITES=true
```

写开关默认关闭。令牌不能替代人工批准和写开关。

## 4. 匹配

```http
POST /v1/match
Content-Type: multipart/form-data
```

字段：

- `file`：图片或PDF；
- `page_index`：PDF页序号，默认0；
- `query_text`：可选文本证据；
- `top_k`：候选数，1—20；
- `include_standard`：是否在安全匹配后返回标准结构全文。

普通匹配无需标准令牌。设置 `include_standard=true` 时必须提供 `X-Standard-Token`。

返回结论：

- `safe_standard_reuse`；
- `ambiguous`；
- `no_match`。
