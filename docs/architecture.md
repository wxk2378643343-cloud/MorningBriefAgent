# MorningBriefAgent 架构说明

## 定位

这是一个 Windows 优先、面向个人业务流程的本地 Agent 工作流平台。代码负责读取、清洗、结构化和执行副作用；目标、偏好、计划和语义分析来自本地配置与 Agent。

产品化方向不是把项目改造成一个通用聊天机器人，而是逐步形成：

```text
本地事实与知识库
        ↓
Agent 理解与编排
        ↓
业务质量门禁
        ↓
SQLite 结构化事实与运行状态
        ↓
Markdown 知识文档 / 飞书 / 桌面端视图
```

当前采用模块化单体。后续即使增加桌面端、API、更多 Provider 和更多渠道，也应优先通过应用服务层和适配器扩展，而不是拆成多个相互复制逻辑的服务。

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
- `services/knowledge/`：知识库应用服务和 Markdown 投影；业务代码依赖 `KnowledgeStore`，不直接依赖 Obsidian 路径或 API。
- `server/`：飞书事件入口、鉴权、异步调度和回复。
- `desktop/`（规划中）：只负责界面、配置、查询和用户操作，不承载业务规则。
- `api/`（规划中）：为桌面端、脚本和未来客户端提供本地应用服务入口。

## 产品化后的核心边界

### 1. SQLite 与 Markdown

SQLite 是可计算、可查询、可追踪的结构化事实来源：

- 待办状态；
- 日程时间和外部同步状态；
- 饮食、热量和基金数据；
- Agent 运行记录、Token、耗时和错误；
- 幂等键、Outbox 和同步状态。

Markdown 是可读内容和知识投影：

- 晨报、新闻和复盘；
- 学习计划和工作记录；
- 知识库文档；
- Agent 生成的解释性内容。

图片、PDF 和其他大附件保存在文件系统，SQLite 只保存元数据和路径。不能让同一个业务字段同时在 SQLite 和 Markdown 中成为两个独立事实来源。

### 2. KnowledgeStore

Obsidian 不再作为产品的强制依赖，而是一种兼容的文件夹使用方式。知识库应该通过统一接口访问：

```text
KnowledgeStore
  ├── LocalMarkdownStore
  ├── Obsidian-compatible folder
  └── Future remote store
```

业务模块只调用读取、保存、搜索和更新文档的能力，不直接拼接个人路径。桌面端内置文件管理器也通过同一应用服务访问知识库。

### 3. 桌面端与应用服务

桌面端不能直接同时连接 SQLite、模型、飞书和文件系统。目标调用链是：

```text
Windows Desktop UI
        ↓
Application Service / Local API
        ↓
Workflow Orchestrator
        ├── Agent Runtime / Provider
        ├── Domain Storage
        ├── KnowledgeStore
        └── Channel Adapter
```

这样桌面端只是产品入口，飞书机器人、Windows 任务计划和未来 API 也可以复用同一套应用服务。

### 4. Agent Runtime 与 Provider

模型和 Agent 运行方式分为三层：

```text
Workflow Orchestrator
        ↓
Agent Runtime
        ↓
Provider Adapter
```

- Workflow Orchestrator 决定业务步骤和副作用顺序；
- Agent Runtime 管理上下文、结构化输出、流式事件、父子任务和运行状态；
- Provider Adapter 对接 AGY、DeepSeek、Claude、Codex 或本地模型。

新增 Provider 时不应修改新闻、待办、饮食或基金工作流。Provider 需要声明是否支持流式输出、图片、工具调用、结构化输出和子任务。

### 5. 子任务

子任务先采用轻量模型，不引入复杂的多 Agent 框架。每个子任务至少记录：

```text
parent_task_id / child_task_id / status / provider
input / output / started_at / finished_at / error
```

第一阶段只解决并行分析、超时、取消、失败和结果汇总；必须限制并发数、递归深度和运行时间。

## 数据流规则

1. 外部资料先进入适配器，再进入 Agent；不直接拼接成工具指令。
2. Agent 结构化输出必须解析和校验后，才能创建任务、日历或归档。
3. 外部副作用应携带日期、任务类型和可追踪的计划状态。
4. 任务、日历事件和重复卡片发送使用统一的本地幂等存储；写入成功后才记录提供方 ID。
5. 业务服务通过 `FeishuTaskGateway` 和 `FeishuGateway` 调用飞书，适配器负责 URL、认证和请求格式。
6. 未配置路径时跳过本地写入，不推断 Vault 目录布局。

## 当前架构决策

- 交互式 Feishu 对话暂时继续使用一个 AGY 会话，保持现有体验；所有进程通过同一会话锁串行访问，防止 transcript 串答。
- 批处理 Agent 调用通过 `agent_provider.py` 统一。
- 新闻源、邮件目录、计划文件和归档目录均由环境变量提供。
- 日历同步不再按天删除全部事件，只按稳定身份复用计划自身的事件。
- `RUN_LIVE_INTEGRATION=1` 才会启用只读真实飞书集成检查，默认测试保持离线。
- 旧版 JSON 幂等记录启动时自动迁移到 SQLite，不删除原始文件。
- 所有外部写入统一经过 `IdempotencyStore.execute_once`，同一幂等 key 使用跨进程锁串行执行，不在业务服务重复实现“检查、执行、记录”。
- Outbox 对账先通过 SQLite 短事务原子领取记录，并使用带过期时间的 lease 恢复崩溃中的 worker；每次真实重放都会增加 attempts。
- 持久日志统一脱敏并轮转，第三方 SDK 不以 INFO 级别记录包含临时凭证的连接 URL。
- 规划同步拆分为 `task_sync.py` 和 `calendar_sync.py`，Server 回复与图片流程位于 `server/replies.py`。
- 所有内部代码统一使用包路径，避免同一实现被不同平铺模块名重复加载。
- 桌面端和本地 API 规划为应用服务的不同入口，不复制业务流程。
- Obsidian 降级为可选兼容方式；默认产品体验由本地 Markdown 存储和内置文件管理器提供。
- 新增 Provider 或消息渠道只能增加适配器和能力声明，不应把具体模型或平台判断扩散到业务工作流。

## 桌面端技术路线评估

### 推荐结论

第一阶段推荐：

```text
Python 业务核心 + 本地 API
        +
PySide6 桌面端
        +
SQLite / Markdown 本地存储
```

理由是现有项目已经使用 Python，业务、测试、数据库和飞书集成无需迁移；PySide6 能提供原生 Windows 界面、托盘、文件选择器和后台线程，适合先做稳定的本地产品。

### Tauri + TypeScript

Tauri 适合第二阶段或需要更现代复杂界面的版本。TypeScript 在 Agent 生态中确实很强，尤其是 Web UI、流式界面、MCP 和部分 Agent SDK，但这不意味着业务核心必须迁移到 TypeScript。

可行形态是：

```text
TypeScript/Tauri UI
        ↓
Python Local API
        ↓
现有业务核心
```

这样利用 TypeScript 的界面和 Agent 生态，同时避免重写当前 Python 业务。代价是要维护两个运行时、进程通信、打包和升级链路。

### Electron + TypeScript

开发体验好、生态丰富，但体积和内存占用较高。对于本地优先、数据和 Agent 运行在 Windows 上的个人工具，除非后期需要复杂 Web 生态，否则不作为首选。

### Rust 重写核心

暂不推荐。Rust 适合高性能、强隔离和长期桌面基础设施，但当前瓶颈是业务边界和产品验证，不是 Python 性能。过早重写会提高开发成本，并破坏现有测试和 Provider 集成速度。

### 分阶段决策

1. 先用现有 Python 核心定义 `Application Service` 和 `KnowledgeStore`；
2. 使用 PySide6 做最小桌面原型，验证文件管理、任务查看和日志展示；
3. 如果 UI 复杂度明显提升，再评估 Tauri + TypeScript；
4. 保持 Python 核心通过本地 API 被调用，不因更换 UI 重写业务；
5. 最后再做 PyInstaller 或 Tauri 安装包、升级和数据迁移。

因此，TypeScript 是值得保留的桌面端候选技术，但不是当前必须迁移的 Agent 核心语言。当前最重要的是先稳定应用服务和领域边界。
