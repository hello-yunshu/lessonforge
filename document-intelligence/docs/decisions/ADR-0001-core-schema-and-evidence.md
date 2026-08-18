# ADR-0001：核心 Schema 与证据强制关联

- 状态：Accepted
- 日期：2026-08-02

## 决策

核心层固定使用 `Document → Page → Element / Relation → Evidence → ParseRun`。每个 Element 和 Relation 至少关联一条 Evidence；坐标使用归一化 `[0,1]`，可附带像素坐标。

## 原因

纯 Markdown 或纯文本不能满足定位、复核、跨解析器比较和后续持续学习要求。

## 后果

- 外部解析器必须经过标准化网关；
- 缺少证据的输出视为 P0；
- 领域语义通过扩展字段接入，不修改核心对象含义。
