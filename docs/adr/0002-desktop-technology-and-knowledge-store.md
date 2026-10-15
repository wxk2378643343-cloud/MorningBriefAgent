# ADR-0002：产品化桌面端与知识库存储路线

## 状态

Proposed

## 背景

产品化后不应要求用户安装 Obsidian，也不应让桌面界面直接连接所有业务模块。项目需要同时支持本地 Markdown、SQLite、Agent Provider、飞书和未来的桌面端。

## 决策

短期采用 Python 模块化单体作为业务核心，增加应用服务边界和 `KnowledgeStore` 抽象。桌面端第一阶段优先评估 PySide6；Tauri + TypeScript 作为后续 UI 复杂化时的候选方案。

知识库默认使用本地 Markdown 文件夹，Obsidian 作为可选兼容方式。SQLite 保存结构化事实和运行状态，Markdown 保存可读知识文档，附件保存在文件系统。

## 原因

- 现有核心、测试、SQLite 和飞书集成均为 Python；
- PySide6 可以减少迁移成本并提供 Windows 原生能力；
- TypeScript/Agent 生态强，但可以先用于未来的 Tauri UI，不必立即重写 Python 业务；
- `KnowledgeStore` 可以隔离内置文件管理器、Obsidian 和未来云端存储；
- 应用服务层可以让桌面端、飞书机器人、计划任务和 API 复用同一套业务流程。

## 约束

- UI 不得承载领域规则；
- 业务模块不得直接依赖 Obsidian 路径；
- 不允许为桌面端复制一套 SQLite、Agent 或飞书逻辑；
- 新 Provider 和新渠道通过适配器接入；
- 个人数据、demo 数据、密钥和真实知识库不得进入安装包或仓库。

## 后果

短期可以保留现有 Python 投资并快速验证桌面产品。后续若选择 Tauri，需要维护 TypeScript UI、Python 本地 API、进程通信和双运行时打包；因此必须先稳定应用服务契约，再决定是否迁移 UI。
