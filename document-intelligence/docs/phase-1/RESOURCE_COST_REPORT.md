# Phase 1 资源与成本报告

## 当前实测范围

当前执行环境真实安装并运行的是 `NativePdfParser / PyMuPDF 1.26.7`。每个夹具重复运行五次，完整数据位于 `benchmark_results.json`。

| 文档 | 大小 | 页数 | 中位耗时 | 输出元素 | 计费调用 |
|---|---:|---:|---:|---:|---:|
| `native_text.pdf` | 约 3.9 KB | 1 | 见自动报告 | 7 | 0 |
| `scanned_image.pdf` | 约 19 KB | 1 | 见自动报告 | 1 | 0 |
| `mixed_layout.pdf` | 约 6.5 KB | 2 | 见自动报告 | 6 | 0 |

Native PDF 路线没有云端API费用；`ParseRun.resource_usage`记录耗时、输入字节、输出元素和进程最大常驻内存观测值。

## 外部解析器

PaddleOCR、OpenDoc、MinerU 在本次离线环境中没有安装模型产物，因此：

- 不填写虚构吞吐量；
- 不填写宣传指标作为自有准确率；
- 不将合约测试当作模型效果测试；
- 由 `scripts/qualify_external_parser.py` 在固定服务和摘要就绪后生成真实报告。

只有完成相同黄金集的准确率、延迟、内存、显存和许可证复核后，外部解析器才可以进入生产路由。
