import React, { useState } from "react";
import {
  Bot,
  Check,
  ChevronRight,
  FolderOpen,
  MessageSquare,
  RefreshCw,
  Settings2,
  Sparkles,
} from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";
import { apiUrl } from "../../localApi";

export const ONBOARDING_STEPS = [
  { key: "workspace", label: "本地工作区", icon: FolderOpen },
  { key: "provider", label: "AI Provider", icon: Bot },
  { key: "channel", label: "消息渠道", icon: MessageSquare },
  { key: "profile", label: "个人上下文", icon: Sparkles },
];

export function StartupScreen({ serviceState, serviceLabel, onRetry }) {
  const isOffline = serviceState === "offline";
  return (
    <div className="startup-screen">
      <div className="startup-card">
        <div className="brand startup-brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div>
        <span className="eyebrow">LOCAL DESKTOP</span>
        <h1>{isOffline ? "本地服务没有启动" : "正在准备本地工作台"}</h1>
        <p>{isOffline ? "请启动本地 API 后重试。你的文件和配置不会上传到云端。" : "正在检查 Python 服务和本机数据环境，请稍候。"}</p>
        <div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div>
        {isOffline && <button className="primary startup-action" type="button" onClick={onRetry}><RefreshCw size={15} />重新检查</button>}
      </div>
    </div>
  );
}

export function WelcomeScreen({ onEnter }) {
  const features = [
    { icon: "⌁", label: "LOCAL FIRST", title: "你的数据留在本机", copy: "Markdown、SQLite 和运行记录都由你掌控，不依赖云端存储。" },
    { icon: "✦", label: "ONE CONTEXT", title: "把信息放在一起", copy: "知识库、待办、日程和工作内容共享一套清晰的个人上下文。" },
    { icon: "↗", label: "ACTIONABLE", title: "从信息到行动", copy: "让 Agent 帮你提炼结论、安排下一步，并减少重复整理。" },
    { icon: "◌", label: "EXTENSIBLE", title: "按你的方式成长", copy: "先从本地工作台开始，之后再接入更多模型和消息渠道。" },
  ];
  return (
    <div className="welcome-screen">
      <header className="setup-topbar">
        <div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div>
        <div className="welcome-local"><span className="pulse" />所有数据仅保存在本机</div>
      </header>
      <main className="welcome-main">
        <div className="welcome-badge"><Sparkles size={15} /> YOUR LOCAL AI WORKSPACE</div>
        <h1>欢迎使用<br /><em>MorningBriefAgent</em></h1>
        <p className="welcome-lead">把信息整理、工作复盘和行动规划交给一个真正属于你的本地 Agent。</p>
        <div className="welcome-features">
          {features.map((feature) => <article className="welcome-feature-card" key={feature.label}>
            <div className="welcome-feature-top"><span className="welcome-feature-icon">{feature.icon}</span><span className="welcome-feature-label">{feature.label}</span></div>
            <strong>{feature.title}</strong>
            <p>{feature.copy}</p>
          </article>)}
        </div>
        <button className="primary welcome-enter" type="button" onClick={onEnter}>开始配置我的工作台 <ChevronRight size={16} /></button>
        <small className="welcome-footnote">本地文件由你掌控，之后可以在设置中随时修改。</small>
      </main>
    </div>
  );
}

export function SetupScreen({
  serviceLabel,
  serviceState,
  status,
  workspace,
  currentStep,
  currentIndex,
  discovery,
  selectedProvider,
  selectedChannel,
  setSelectedProvider,
  setSelectedChannel,
  completeStep,
  onBack,
  onSkip,
  onCancel,
  message,
}) {
  return (
    <div className="setup-screen">
      <header className="setup-topbar">
        <div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div>
        <div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div>
      </header>
      <main className="setup-main">
        <div className="setup-intro"><span className="eyebrow">FIRST RUN</span><h1>先配置本地工作区</h1><p>选择你的本地文件位置，再配置 AI 和飞书。完成后才进入工作台。</p></div>
        <section className="setup-card">
          <div className="setup-header"><div><span className="eyebrow">Setup</span><h3>本地初始化向导</h3></div><span className="progress-label">{status?.completed_count ?? 0} / 4 已配置{status?.skipped_count ? ` · ${status.skipped_count} 项稍后配置` : ""}</span></div>
          <div className="stepper">{ONBOARDING_STEPS.map((step, index) => { const Icon = step.icon; const done = index < currentIndex; const active = index === currentIndex; return <div className={`step ${active ? "active" : ""} ${done ? "done" : ""}`} key={step.key}><div className="step-icon">{done ? <Check size={15} /> : <Icon size={16} />}</div><span>{step.label}</span>{index < ONBOARDING_STEPS.length - 1 && <ChevronRight className="step-arrow" size={15} />}</div>; })}</div>
          <div className="setup-content">
            {currentStep === "workspace" && <WorkspaceStep initialRoot={workspace?.root_path ?? workspace?.default_root_path ?? ""} onComplete={() => completeStep("workspace", "local workspace initialized")} />}
            {currentStep === "provider" && <ProviderStep providers={discovery.providers} selected={selectedProvider} onSelect={setSelectedProvider} onComplete={() => completeStep("provider", selectedProvider)} />}
            {currentStep === "channel" && <ChannelStep channels={discovery.channels} selected={selectedChannel} onSelect={setSelectedChannel} onComplete={() => completeStep("channel", selectedChannel)} />}
            {currentStep === "profile" && <ProfileStep onComplete={() => completeStep("profile", "profile ready")} />}
          </div>
          <div className="setup-footer">
            <button className="secondary" type="button" onClick={onBack}><span>←</span>{currentIndex === 0 ? "返回欢迎页" : "上一步"}</button>
            {onSkip && <button className="text-button" type="button" onClick={onSkip}>稍后配置</button>}
            <button className="text-button setup-cancel" type="button" onClick={onCancel}>取消</button>
          </div>
          {message && <div className="setup-message">{message}</div>}
        </section>
      </main>
    </div>
  );
}

function WorkspaceStep({ initialRoot, onComplete }) {
  const [root, setRoot] = useState(initialRoot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    try {
      const response = await fetch(apiUrl("/api/v1/workspace/initialize"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ root_path: root }) });
      if (!response.ok) throw new Error(await response.text());
      onComplete();
    } catch { setBusy(false); setError("工作区初始化失败，请确认目录可写且本地 API 已启动。"); }
  };
  const chooseDirectory = async () => {
    if (!window.__TAURI_INTERNALS__) {
      setError("当前是浏览器预览，不能打开系统文件夹选择器；请直接输入本地路径，或运行 Tauri 桌面版。");
      return;
    }
    try {
      const selected = await open({ directory: true, multiple: false, title: "选择 MorningBrief 工作区" });
      if (typeof selected === "string") setRoot(selected);
    } catch { setError("系统文件夹选择器打开失败，请直接输入本地路径。"); }
  };
  return <div className="step-panel workspace-step"><div className="panel-icon blue"><FolderOpen size={21} /></div><div className="panel-copy"><h4>配置本地工作区</h4><p>选择你自己的本地目录。应用会在这里建立数据库、日志、附件和完整的 Obsidian 知识库结构，不上传任何内容。</p><div className="workspace-preview"><span className="workspace-preview-title">初始化后会得到</span><div className="workspace-preview-grid"><span><b>⌂</b>00-首页.md</span><span><b>✓</b>02-待办</span><span><b>◷</b>03-日程</span><span><b>◌</b>04-新闻简报</span><span><b>✦</b>05-知识库</span><span><b>＋</b>07-饮食记录</span></div></div><div className="path-row"><input value={root} onChange={(event) => { setRoot(event.target.value); setError(""); }} placeholder="例如：D:\\MorningBriefWorkspace" /><button type="button" className="secondary" onClick={chooseDirectory}>选择目录</button></div><div className="setup-actions"><button className="primary" disabled={!root || busy} onClick={submit}>{busy ? "初始化中…" : "初始化本地工作区"} <ChevronRight size={16} /></button></div>{error && <div className="error-banner">{error}</div>}</div></div>;
}

function ProviderStep({ providers, selected, onSelect, onComplete }) {
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const provider = providers.find((item) => item.name === selected);
      if (selected === "deepseek" && !apiKey && !provider?.configured) throw new Error("api_key_required");
      if (selected === "deepseek" && apiKey) {
        const response = await fetch(apiUrl(`/api/v1/providers/${selected}/credentials`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: apiKey }) });
        if (!response.ok) throw new Error("provider");
      }
      onComplete();
    } catch { setBusy(false); }
  };
  return <div className="step-panel"><div className="panel-icon violet"><Bot size={21} /></div><div className="panel-copy"><h4>选择 AI 运行方式</h4><p>优先检测本地 Agent 进程；也可以选择 API。密钥只保存到本机系统凭据。</p><div className="provider-grid">{providers.map((provider) => <button className={`provider-option ${selected === provider.name ? "selected" : ""}`} key={provider.name} onClick={() => onSelect(provider.name)}><span className="provider-dot" /><span><strong>{provider.name}</strong><small>{provider.available ? "已检测到，可使用" : provider.detail}</small></span>{selected === provider.name && <Check size={16} />}</button>)}</div>{selected === "deepseek" && <label className="secret-field">DeepSeek API Key<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-…" /></label>}<button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "使用此 Provider"} <ChevronRight size={16} /></button></div></div>;
}

function ChannelStep({ channels, selected, onSelect, onComplete }) {
  const [values, setValues] = useState({ app_id: "", app_secret: "", user_open_id: "", chat_id: "" });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const response = await fetch(apiUrl("/api/v1/channels/feishu/credentials"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
      if (!response.ok) throw new Error("channel");
      onComplete();
    } catch { setBusy(false); }
  };
  return <div className="step-panel"><div className="panel-icon orange"><MessageSquare size={21} /></div><div className="panel-copy"><h4>连接消息渠道</h4><p>配置飞书后，待办、日程、新闻和简报仍由 Python 工作流统一处理。</p><button className={`channel-option ${selected === "feishu" ? "selected" : ""}`} onClick={() => onSelect("feishu")}><span className="feishu-mark">飞</span><span><strong>飞书 Feishu</strong><small>{channels.find((item) => item.name === "feishu")?.detail ?? "本地配置"}</small></span><Settings2 size={16} /></button><div className="channel-fields">{["app_id", "app_secret", "user_open_id", "chat_id"].map((key) => <input key={key} type={key === "app_secret" ? "password" : "text"} placeholder={key} value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />)}</div><button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "保存渠道设置"} <ChevronRight size={16} /></button></div></div>;
}

function ProfileStep({ onComplete }) {
  const [values, setValues] = useState({ "我的工作": "", "当前目标": "" });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const response = await fetch(apiUrl("/api/v1/profile"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
      if (!response.ok) throw new Error("profile");
      onComplete();
    } catch { setBusy(false); }
  };
  return <div className="step-panel"><div className="panel-icon green"><Sparkles size={21} /></div><div className="panel-copy"><h4>建立你的个人上下文</h4><p>内容会保存为工作区内的 Markdown 文件，之后可以随时修改。</p><div className="profile-grid"><label>我的工作<textarea value={values["我的工作"]} onChange={(event) => setValues({ ...values, "我的工作": event.target.value })} placeholder="例如：我负责……" /></label><label>当前目标<textarea value={values["当前目标"]} onChange={(event) => setValues({ ...values, "当前目标": event.target.value })} placeholder="例如：近期重点是……" /></label></div><button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "完成设置，进入工作台"} <ChevronRight size={16} /></button></div></div>;
}
