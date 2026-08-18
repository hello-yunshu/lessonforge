# Phase 4 运维说明

## 默认策略

- Domain Pack 写入关闭；
- 管理访问令牌为空时拒绝访问；
- 签名强制默认关闭，生产应根据密钥治理方案显式打开；
- Rill 仅 Shadow；
- 适配失败默认回退通用结果；
- 运行时目录不得进入发布包。

## 运行时目录

- `var/domain-packs`：已安装包和启用状态；
- `var/domain-results`：不可变领域结果；
- `var/domain-reviews`：审核导出和回传。

备份和恢复必须保持三者、通用解析结果及结构结果的一致时间点。不得单独删除被结果引用的
Domain Pack 版本。

## 签名

使用 `scripts/build_domain_pack.py` 生成摘要并可选签名。生产可信公钥通过
`DI_DOMAIN_PACK_TRUSTED_KEYS_JSON` 提供。旧结果仍依赖对应包的内容和签名验证，因此密钥
轮换不能直接删除历史验证公钥。

## 故障处置

- `DOMAIN_PACK_ARCHIVE_INVALID`：拒绝安装，检查来源和压缩包限制；
- `DOMAIN_PACK_INCOMPATIBLE`：不得强制激活，制作兼容新版本；
- `DOMAIN_PACK_SIGNATURE_INVALID`：隔离包并核查密钥；
- `DOMAIN_PACK_STORE_CORRUPT`：停止领域执行并从可信备份恢复；
- `DOMAIN_RESULT_STORE_CORRUPT`：停止读取该结果并进行血缘审计；
- `DOMAIN_EXECUTION_ERROR`：通用结果继续可用，领域结果进入复核；
- `DOMAIN_REVIEW_INVALID`：拒绝回传并保留原始导出。
