import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  Check,
  ChevronRight,
  Database,
  FolderOpen,
  KeyRound,
  LayoutDashboard,
  MessageSquare,
  RefreshCw,
  Settings2,
  Sparkles,
  Workflow,
} from "lucide-react";
import "./styles.css";

const demoDiscovery = {
  providers: [
    { name: "deepseek", kind: "api", available: true, configured: true, detail: "deepseek-chat" },
    { name: "agy", kind: "local_process", available: false, configured: false, detail: "本地 Agent 未检测到" },
    { name: "claude", kind: "api", available: false, configured: false, detail: "API key 未配置" },
  ],
  channels: [
    { name: "feishu", kind: "channel", available: false, configured: false, detail: "应用凭据未配置" },
  ],
};

const steps = [
  { key: "workspace", label: "本地工作区", icon: FolderOpen },
  { key: "provider", label: "AI Provider", icon: Bot },
  { key: "channel", label: "消息渠道", icon: MessageSquare },
  { key: "profile", label: "个人上下文", icon: Sparkles },
];

function App() {
  const [status, setStatus] = useState(null);
  const [discovery, setDiscovery] = useState(demoDiscovery);
  const [selectedProvider, setSelectedProvider] = useState("deepseek");
  const [selectedChannel, setSelectedChannel] = useState("feishu");
  const [message, setMessage] = useState("正在检查本地环境…");

  useEffect(() => {
    Promise.all([
      fetch("http://127.0.0.1:8765/api/v1/onboarding/status").then((response) => response.json()),
      fetch("http://127.0.0.1:8765/api/v1/providers/discovery").then((response) => response.json()),
    ])
      .then(([nextStatus, nextDiscovery]) => {
        setStatus(nextStatus);
        setDiscovery(nextDiscovery);
        setMessage("本地服务已连接");
      })
      .catch(() => {
        setMessage("演示模式：本地 API 尚未启动");
      });
  }, []);

  const currentStep = status?.current_step ?? "workspace";
  const currentIndex = Math.max(0, steps.findIndex((step) => step.key === currentStep));
  const completeStep = async (stepKey, detail) => {
    try {
      const response = await fetch("http://127.0.0.1:8765/api/v1/onboarding/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_key: stepKey, detail }),
      });
      if (!response.ok) throw new Error("request failed");
      setStatus(await response.json());
      setMessage("配置已保存到本地");
    } catch {
      setMessage("演示模式：配置将在本地 API 启动后保存");
      setStatus((previous) => ({
        ...(previous ?? { steps: [], completed_count: 0, total_count: 4 }),
        current_step: steps[Math.min(currentIndex + 1, steps.length - 1)].key,
        completed_count: Math.min((previous?.completed_count ?? 0) + 1, 4),
      }));
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div>
        <div className="workspace-label">本地工作台</div>
        <nav>
          <NavItem icon={<LayoutDashboard size={17} />} label="工作台" active />
          <NavItem icon={<FolderOpen size={17} />} label="文件与数据" />
          <NavItem icon={<Workflow size={17} />} label="工作流" />
          <NavItem icon={<Database size={17} />} label="数据库" />
          <NavItem icon={<Bot size={17} />} label="Agent 运行" />
        </nav>
        <div className="sidebar-bottom"><NavItem icon={<Settings2 size={17} />} label="设置" /><div className="local-only"><span /> 仅在本机运行</div></div>
      </aside>
      <main className="main">
        <header className="topbar"><div><span className="eyebrow">首次启动</span><h1>把你的工作流交给本地 Agent</h1></div><div className="connection"><span className="pulse" />{message}</div></header>
        <section className="hero">
          <div><div className="hero-kicker"><KeyRound size={15} /> 你的数据不会自动上传</div><h2>先完成本地配置，<br /><em>再开始建立你的工作系统。</em></h2><p>MorningBrief 会把数据库、文件、Agent 和消息渠道留在你的电脑上。你可以随时修改或移除配置。</p></div>
          <div className="hero-orbit"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit-core"><Bot size={30} /></div><span className="orbit-label label-one">SQLite</span><span className="orbit-label label-two">Markdown</span><span className="orbit-label label-three">Agent</span></div>
        </section>
        <section className="setup-card">
          <div className="setup-header"><div><span className="eyebrow">Setup</span><h3>完成你的本地环境</h3></div><span className="progress-label">{status?.completed_count ?? 0} / 4 完成</span></div>
          <div className="stepper">{steps.map((step, index) => { const Icon = step.icon; const done = index < currentIndex; const active = index === currentIndex; return <div className={`step ${active ? "active" : ""} ${done ? "done" : ""}`} key={step.key}><div className="step-icon">{done ? <Check size={15} /> : <Icon size={16} />}</div><span>{step.label}</span>{index < steps.length - 1 && <ChevronRight className="step-arrow" size={15} />}</div>; })}</div>
          <div className="setup-content">
            {currentStep === "workspace" && <WorkspaceStep onComplete={() => completeStep("workspace", "local workspace initialized")} />}
            {currentStep === "provider" && <ProviderStep providers={discovery.providers} selected={selectedProvider} onSelect={setSelectedProvider} onComplete={() => completeStep("provider", selectedProvider)} />}
            {currentStep === "channel" && <ChannelStep channels={discovery.channels} selected={selectedChannel} onSelect={setSelectedChannel} onComplete={() => completeStep("channel", selectedChannel)} />}
            {currentStep === "profile" && <ProfileStep onComplete={() => completeStep("profile", "profile ready")} />}
          </div>
        </section>
      </main>
    </div>
  );
}

function NavItem({ icon, label, active }) { return <button className={`nav-item ${active ? "active" : ""}`}><span>{icon}</span>{label}</button>; }
function WorkspaceStep({ onComplete }) { return <div className="step-panel"><div className="panel-icon blue"><FolderOpen size={21} /></div><div className="panel-copy"><h4>创建本地工作区</h4><p>应用会在本机创建数据库、知识库、日志、附件和对话目录，不会覆盖已有文件。</p><div className="path-row"><code>用户目录 / MorningBriefAgent</code><button className="secondary">选择位置</button></div><button className="primary" onClick={onComplete}>初始化本地工作区 <ChevronRight size={16} /></button></div></div>; }
function ProviderStep({ providers, selected, onSelect, onComplete }) { return <div className="step-panel"><div className="panel-icon violet"><Bot size={21} /></div><div className="panel-copy"><h4>选择你的 AI Provider</h4><p>可以使用 API，也可以使用本地 Agent 进程。密钥不会显示在界面或日志中。</p><div className="provider-grid">{providers.map((provider) => <button className={`provider-option ${selected === provider.name ? "selected" : ""}`} key={provider.name} onClick={() => onSelect(provider.name)}><span className="provider-dot" /><span><strong>{provider.name}</strong><small>{provider.available ? "已检测到" : provider.detail}</small></span>{selected === provider.name && <Check size={16} />}</button>)}</div><button className="primary" onClick={onComplete}>保存 Provider 选择 <ChevronRight size={16} /></button></div></div>; }
function ChannelStep({ channels, selected, onSelect, onComplete }) { const channel = channels.find((item) => item.name === selected); return <div className="step-panel"><div className="panel-icon orange"><MessageSquare size={21} /></div><div className="panel-copy"><h4>连接消息渠道</h4><p>第一阶段先支持飞书。后续可以增加 Telegram、企业微信、邮件或 Webhook。</p><button className={`channel-option ${selected === "feishu" ? "selected" : ""}`} onClick={() => onSelect("feishu")}><span className="feishu-mark">飞</span><span><strong>飞书 Feishu</strong><small>{channel?.configured ? "已配置" : "等待配置 App ID 和 Secret"}</small></span><Settings2 size={16} /></button><button className="primary" onClick={onComplete}>保存渠道设置 <ChevronRight size={16} /></button></div></div>; }
function ProfileStep({ onComplete }) { return <div className="step-panel"><div className="panel-icon green"><Sparkles size={21} /></div><div className="panel-copy"><h4>建立你的个人上下文</h4><p>告诉 Agent 你是谁、做什么、关注什么，以及你希望它如何帮助你。之后可以随时修改。</p><div className="profile-grid"><label>我的工作<textarea placeholder="例如：我负责……" /></label><label>当前目标<textarea placeholder="例如：近期重点是……" /></label></div><button className="primary" onClick={onComplete}>完成设置，进入工作台 <ChevronRight size={16} /></button></div></div>; }

createRoot(document.getElementById("root")).render(<App />);
