# MorningBriefAgent 架构说明

## 定位

这是一个 Windows 优先的本地 Agent 工作流框架。代码负责读取、清洗、结构化和执行副作用；目标、偏好、计划和语义分析来自本地配置与 Agent。

## C4 容器视图

```text
用户 / Windows 计划任务
          |
          v
     main.py / Feishu WebSocket
          |
  +-------+------------------+
  |       |                  |
  v       v                  v
数据适配器  Agent Provider     输出适配器
微信/RSS/  AGY Bridge        飞书卡片/任务/
文件/行情  JSON 校验          日历/本地归档
  |       |                  |
  +-------+------------------+
          v
     本地运行状态与日志
```

## 边界

- `core/runtime/`：加载环境变量和运行诊断，不保存个人目录和秘密默认值。
- `core/agent/`：发现上下文、Agent Provider、AGY 桥接和数据契约。
- `core/integrations/feishu/`：卡片、任务、日历、幂等、重试和错误分类。
- `core/integrations/sync_outbox.py`：跨系统同步意图、失败状态和对账记录。
- `core/runtime/observability.py`：correlation ID、结构化事件和耗时记录。
- `core/parsers/`：邮件与本地内容解析。
- `services/`：按业务域组织用例，不应自行决定个人目标或硬编码外部数据源。
- `server/`：飞书事件入口、鉴权、异步调度和回复。

## 数据流规则

1. 外部资料先进入适配器，再进入 Agent；不直接拼接成工具指令。
2. Agent 结构化输出必须解析和校验后，才能创建任务、日历或归档。
3. 外部副作用应携带日期、任务类型和可追踪的计划状态。
4. 任务、日历事件和重复卡片发送使用统一的本地幂等存储；写入成功后才记录提供方 ID。
5. 业务服务通过 `FeishuTaskGateway` 和 `FeishuGateway` 调用飞书，适配器负责 URL、认证和请求格式。
6. 未配置路径时跳过本地写入，不推断 Vault 目录布局。

## 当前架构决策

- 交互式 Feishu 对话暂时继续使用一个 AGY 会话，保持现有体验。
- 批处理 Agent 调用通过 `agent_provider.py` 统一。
- 新闻源、邮件目录、计划文件和归档目录均由环境变量提供。
- 日历同步不再按天删除全部事件，只按稳定身份复用计划自身的事件。
- `RUN_LIVE_INTEGRATION=1` 才会启用只读真实飞书集成检查，默认测试保持离线。
- 旧版 JSON 幂等记录启动时自动迁移到 SQLite，不删除原始文件。
- 所有外部写入统一经过 `IdempotencyStore.execute_once`，不在业务服务重复实现“检查、执行、记录”。
- 规划同步拆分为 `task_sync.py` 和 `calendar_sync.py`，Server 回复与图片流程位于 `server/replies.py`。
- 所有内部代码统一使用包路径，避免同一实现被不同平铺模块名重复加载。
