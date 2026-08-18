# Phase 7 REST API

所有MLOps端点使用`X-MLOps-Token`，服务端只保存令牌SHA-256。普通登记要求`DI_ENABLE_MLOPS_WRITES=true`；Shadow/Champion切换和回滚还要求独立的`DI_ENABLE_MLOPS_RELEASE=true`。

## 端点

- `POST /v1/mlops/active-learning/select`：生成不可变主动学习批次；
- `POST /v1/mlops/datasets`：登记DVC数据快照；
- `POST /v1/mlops/mlflow-runs`：登记MLflow运行证明；
- `POST /v1/mlops/candidates`：注册Candidate；
- `POST /v1/mlops/evaluations`：登记黄金集和挑战集评测；
- `POST /v1/mlops/shadow-validations`：登记Shadow灰度证明；
- `POST /v1/mlops/approvals`：登记人工批准；
- `POST /v1/mlops/promote/shadow`：将通过离线门禁的Candidate设为Shadow；
- `POST /v1/mlops/promote/champion`：将通过Shadow门禁并重新批准的Candidate设为Champion；
- `POST /v1/mlops/rollback`：将Champion切回Rollback；
- `GET /v1/mlops/lineage/{candidate_id}`：读取完整模型血缘；
- `GET /v1/mlops/inspect`：查看数量、别名和安全状态。

## 安全语义

API只接受摘要、修订号、运行ID和度量，不接收或执行训练代码。发布端点即使拥有访问令牌，在发布开关关闭时仍返回`MLOPS_RELEASE_DISABLED`。业务门禁失败返回`MLOPS_GATE_BLOCKED`。
