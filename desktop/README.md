# MorningBrief Desktop Prototype

这是 Tauri + React 桌面端的第一阶段 UI 原型，当前展示首次启动向导。

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

当前阶段尚未接入真实 Tauri 壳、系统密钥存储和飞书配置提交。

### Tauri 壳

`src-tauri/` 已提供最小桌面壳结构。开发环境需要 Rust、Cargo 和 Tauri
依赖；启动后会尝试运行仓库根目录的 `scripts/run_local_api.py`，退出时回收
Python 子进程。发布安装包前仍需把 Python 运行时和业务代码作为受控 sidecar
打包，这一步不会把个人数据库或 `.env` 打进仓库。
