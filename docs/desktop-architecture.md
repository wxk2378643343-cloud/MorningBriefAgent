# Windows 桌面端架构决策

## 决策

桌面端采用 Tauri 2 + React。业务规则继续位于 Python 应用服务中，Tauri 只负责
窗口、生命周期和启动本地 API。发布构建使用 PyInstaller 将本地 API 打包为
sidecar，并由 NSIS/MSI 安装器一同安装；用户不需要单独安装 Python。

发布版数据库位于 `%LOCALAPPDATA%\\MorningBrief\\app.sqlite3`，不会写入安装目录。
开发模式仍可通过 `MORNINGBRIEF_PYTHON` 指定 Python，并直接运行仓库中的本地 API。

## 稳定边界

- `core.agent.runtime.AgentProvider`：Provider 请求、响应、能力和分类错误。
- `core.integrations.channel.ChannelAdapter`：消息、附件、动作和渠道能力。
- `services.subtasks`：父任务、子任务、深度、并发、取消、幂等和持久化状态。
- `services.knowledge.folder_sync.KnowledgeStore`：普通文件夹知识库和安全同步。
- `core.application.local_api`：桌面端和脚本共用的 loopback API。

## 发布验证

`.github/workflows/windows-desktop.yml` 在 Windows runner 上执行：

1. Python 依赖和 PyInstaller sidecar 构建；
2. 前端依赖安装与测试；
3. Tauri MSI/NSIS 构建；
4. 安装包 artifact 上传。

本地开发使用 `cargo check` 验证 Rust 壳；发布配置单独保存在
`src-tauri/tauri.release.conf.json`，避免开发构建依赖预先存在的 sidecar。
