# MorningBrief Desktop Prototype

这是 Tauri + React 桌面端的第一版本地工作台。首次启动可以初始化本地工作区、
保存 Provider/飞书凭据并建立个人上下文。

## 运行

```powershell
cd desktop
npm install
npm run dev
```

原型会优先调用本地 API：

- `http://127.0.0.1:8765/api/v1/onboarding/status`
- `http://127.0.0.1:8765/api/v1/providers/discovery`
- `http://127.0.0.1:8765/api/v1/onboarding/complete`

如果本地 API 尚未启动，界面会进入演示模式，不会访问云服务。

可以在仓库根目录启动本地 API：

```powershell
python scripts/run_local_api.py --port 8765
```

API 只监听 `127.0.0.1`，默认使用本地 SQLite 配置。桌面端可以通过
`GET /api/v1/health` 判断服务是否可用。后续接入 Tauri 时，由桌面壳启动和回收
这个 Python 子进程，不把业务逻辑复制到 TypeScript 中。

### 通用文件夹同步

文件工作台可把当前知识库同步到任意本地文件夹。同步始终先调用
`POST /api/v1/folder-sync` 预览，再由用户确认应用；只复制目标中不存在的文件，
同名但内容不同的文件报告为冲突，不覆盖、不删除。隐藏运行目录、符号链接和本地
回收区不会进入同步清单。该能力基于普通文件夹和 `KnowledgeStore` 契约，不依赖
任何编辑器的私有 API。

文件工作台通过
`GET /api/v1/files?source_id=<id>&sort=recent` 读取稳定的文件元数据契约。
更新时间来自文件系统并以 UTC ISO 8601 返回；来源来自 `data_sources`；
同步状态由存储层比较 SQLite 索引快照与当前文件元数据后确定。桌面端只负责将
`synced`、`stale`、`missing` 和 `unknown` 展示为用户可读状态。

密钥通过 Python 的系统凭据存储边界保存，不写入 SQLite；非敏感的工作区状态和
向导进度保存在本地 SQLite。桌面端不会把原始文件上传到云端。

### 文件删除与恢复

知识库中的 Markdown 和文本文件默认采用可恢复删除。文件会被原子移动到知识库
内部的隐藏回收区，操作状态保存在本地 SQLite；桌面端可通过“恢复最近删除”
恢复文件。若原路径已经存在新文件，恢复会返回冲突且不会覆盖现有内容。

本地 API 启动时会对账中断的删除或恢复操作并刷新文件索引。相同
`request_id` 的删除请求只执行一次。文件移动和重命名由 Issue #65 单独实现，
本恢复流程不复制其路径变更逻辑。

### Tauri 壳

`src-tauri/` 已提供最小桌面壳结构。开发环境需要 Rust、Cargo 和 Tauri
依赖；启动后会尝试运行仓库根目录的 `scripts/run_local_api.py`，退出时回收
Python 子进程。发布安装包前仍需把 Python 运行时和业务代码作为受控 sidecar
打包，这一步不会把个人数据库或 `.env` 打进仓库。
