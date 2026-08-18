# Phase 1 运维说明

## 启动

```bash
python -m pip install -e .
PYTHONPATH=src uvicorn document_intelligence.api.main:app --host 0.0.0.0 --port 8080
```

## 数据目录

- `var/raw`：供应商或原生解析器原始输出；
- `var/runs`：成功运行和失败记录；
- `var/standard`：预留的标准结果库，本阶段解析事务无写权限。

## 外部解析器启用

1. 部署符合统一网关协议的服务；
2. 固定服务/模型产物 SHA-256；
3. 在 `configs/parsers.yaml` 中启用并填写摘要；
4. 设置对应 endpoint 环境变量；
5. 运行健康检查与黄金集；
6. 才允许进入路由。

## 降级

- Native PDF 失败：记录失败，不写标准库；
- 图片或扫描 PDF 无文本层：返回 `EMPTY_NATIVE_TEXT`，提示使用 OCR 解析器；
- 外部服务不可达、版本或摘要不一致：视为不可用；
- 所有候选失败：返回明确错误和独立失败记录。
