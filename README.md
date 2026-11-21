# MorningBriefAgent 晨报智能体

MorningBriefAgent 正在重构为一个由飞书任务和日程驱动的个人计划助手。产品设计覆盖日计划生成、用户确认、执行跟踪，以及本地记录与飞书状态对账。

## 当前版本

`main` 目前维护产品需求和交付流程，处于产品设计阶段。运行入口会随实现发布。历史实现见 [backup/full-history-v1](https://github.com/wxk2378643343-cloud/morning-brief-agent/tree/backup/full-history-v1)。

## 从哪里开始

| 资料 | 内容 |
| --- | --- |
| [产品文档索引](docs/product/README.md) | 当前版本、读取顺序和维护规则 |
| [产品需求文档](docs/product/prd.md) | 需求、工作流、同步规则、验收和里程碑 |
| [交付流程](docs/process/delivery.md) | 从需求评审、技术方案到上线和复盘 |

提出变更时，先对照 PRD 的需求与验收条目，再按交付流程记录影响和验证结果。


## 自动检查

[测试工作流](.github/workflows/tests.yml)和 [AI Review 工作流](.github/workflows/ai-review.yml)位于仓库中。AI Review 面向符合工作流条件的本仓库 Pull Request，模型调用需要配置 `AI_API_KEY`。
