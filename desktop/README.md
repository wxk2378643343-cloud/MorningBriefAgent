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

当前阶段只实现界面原型，尚未接入真实 Tauri 壳、系统密钥存储和飞书配置提交。
