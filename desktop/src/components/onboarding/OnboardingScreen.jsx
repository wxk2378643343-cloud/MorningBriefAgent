import React, { useRef, useState } from "react";
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
import { apiUrl, fetchJson } from "../../localApi";

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

export function NameRegistrationScreen({ onComplete }) {
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    const normalizedName = displayName.trim();
    if (!normalizedName) {
      setError("请输入你希望使用的名字。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/profile"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: normalizedName }),
      });
      if (!response.ok) throw new Error("profile");
      onComplete(await response.json());
    } catch {
      setBusy(false);
      setError("名字保存失败，请检查本地服务后重试。");
    }
  };

  return (
    <div className="welcome-screen">
      <main className="name-registration-card">
        <div className="panel-icon green"><Sparkles size={23} /></div>
        <span className="eyebrow">WELCOME</span>
        <h1>你好，怎么称呼你？</h1>
        <p>这个名字只保存在本机，用于首页问候；之后可以在设置中修改。</p>
        <form onSubmit={submit}>
          <input
            autoFocus
            autoComplete="name"
            maxLength={40}
            placeholder="输入你的名字"
            value={displayName}
            onChange={(event) => {
              setDisplayName(event.target.value);
              setError("");
            }}
          />
          <button className="primary" disabled={busy} type="submit">
            {busy ? "保存中…" : "进入工作台"} <ChevronRight size={16} />
          </button>
        </form>
        {error && <div className="error-banner">{error}</div>}
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
  skipStep,
  onBack,
  onCancel,
  message,
}) {
  return (
    <div className="setup-screen">
      <main className="setup-main">
        <div className="setup-intro"><span className="eyebrow">FIRST RUN</span><h1>先配置本地工作区</h1><p>选择你的本地文件位置，再配置 AI 和飞书。完成后才进入工作台。</p></div>
        <section className="setup-card">
          <div className="setup-header"><div><span className="eyebrow">Setup</span><h3>本地初始化向导</h3></div></div>
          <div className="stepper">{ONBOARDING_STEPS.map((step, index) => { const Icon = step.icon; const done = index < currentIndex; const active = index === currentIndex; return <div className={`step ${active ? "active" : ""} ${done ? "done" : ""}`} key={step.key}><div className="step-icon">{done ? <Check size={15} /> : <Icon size={16} />}</div><span>{step.label}</span>{index < ONBOARDING_STEPS.length - 1 && <ChevronRight className="step-arrow" size={15} />}</div>; })}</div>
          <div className="setup-content">
            {currentStep === "workspace" && <WorkspaceStep initialRoot={workspace?.root_path ?? workspace?.default_root_path ?? ""} onComplete={() => completeStep("workspace", "local workspace initialized")} />}
            {currentStep === "provider" && <ProviderStep providers={discovery.providers} selected={selectedProvider} onSelect={setSelectedProvider} onComplete={() => completeStep("provider", selectedProvider)} onSkip={() => skipStep("provider")} />}
            {currentStep === "channel" && <ChannelStep channels={discovery.channels} selected={selectedChannel} onSelect={setSelectedChannel} onComplete={() => completeStep("channel", selectedChannel)} onSkip={() => skipStep("channel")} />}
            {currentStep === "profile" && <ProfileStep onComplete={() => completeStep("profile", "profile ready")} onSkip={() => skipStep("profile")} />}
          </div>
          <div className="setup-footer">
            <button className="secondary" type="button" onClick={onBack}><span>←</span>{currentIndex === 0 ? "返回欢迎页" : "上一步"}</button>
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
  return <div className="step-panel workspace-step"><div className="panel-icon blue"><FolderOpen size={21} /></div><div className="panel-copy"><h4>配置本地工作区</h4><p>选择你自己的本地目录。应用只会建立运行所需的数据库、附件、导出和日志目录；待办、日程与其他内容在首次真实写入时生成。</p><div className="workspace-preview"><span className="workspace-preview-title">初始化后会得到最小安全结构</span><div className="workspace-preview-grid"><span><b>▣</b>data/app.sqlite3</span><span><b>⌁</b>attachments</span><span><b>↗</b>exports</span><span><b>⋯</b>logs</span></div></div><div className="path-row"><input value={root} onChange={(event) => { setRoot(event.target.value); setError(""); }} placeholder="例如：D:\\MorningBriefWorkspace" /><button type="button" className="secondary" onClick={chooseDirectory}>选择目录</button></div><div className="setup-actions"><button className="primary" disabled={!root || busy} onClick={submit}>{busy ? "初始化中…" : "初始化本地工作区"} <ChevronRight size={16} /></button></div>{error && <div className="error-banner">{error}</div>}</div></div>;
}

function ProviderStep({ providers, selected, onSelect, onComplete, onSkip }) {
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const provider = providers.find((item) => item.name === selected);
      if (selected !== "deepseek" && !provider?.available && !provider?.configured) throw new Error("provider_unavailable");
      if (selected === "deepseek" && !apiKey && !provider?.configured) throw new Error("api_key_required");
      if (selected === "deepseek" && apiKey) {
        const response = await fetch(apiUrl(`/api/v1/providers/${selected}/credentials`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: apiKey }) });
        if (!response.ok) throw new Error("provider");
      }
      onComplete();
    } catch (caught) {
      setBusy(false);
      setError(caught.message === "provider_unavailable" ? "这个 Provider 当前不可用，请选择已检测到的本地 Agent 或填写可用 API Key。" : "请先完成 AI Provider 配置。");
    }
  };
  return <div className="step-panel"><div className="panel-icon violet"><Bot size={21} /></div><div className="panel-copy"><h4>选择 AI 运行方式</h4><p>优先检测本地 Agent 进程；也可以选择 API。密钥只保存到本机系统凭据。</p><div className="provider-grid">{providers.map((provider) => <button className={`provider-option ${selected === provider.name ? "selected" : ""}`} key={provider.name} onClick={() => { onSelect(provider.name); setError(""); }}><span className="provider-dot" /><span><strong>{provider.name}</strong><small>{provider.available ? "已检测到，可使用" : provider.detail}</small></span>{selected === provider.name && <Check size={16} />}</button>)}</div>{selected === "deepseek" && <label className="secret-field">DeepSeek API Key<input type="password" value={apiKey} onChange={(event) => { setApiKey(event.target.value); setError(""); }} placeholder="sk-…" /></label>}<div className="flex items-center gap-3 mt-4"><button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "使用此 Provider"} <ChevronRight size={16} /></button><button type="button" className="secondary" disabled={busy} onClick={async () => { setBusy(true); try { await onSkip(); } finally { setBusy(false); } }}>稍后配置</button></div>{error && <div className="error-banner">{error}</div>}</div></div>;
}

function ChannelStep({ channels, selected, onSelect, onComplete, onSkip }) {
  const [values, setValues] = useState({ app_id: "", app_secret: "", user_open_id: "", chat_id: "" });
  const formRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      // Password managers and native WebView autofill can update the DOM
      // without firing React's onChange. Read the form at submit time so a
      // visibly filled credential is never treated as empty.
      const submittedValues = Object.fromEntries(new FormData(formRef.current).entries());
      if (Object.values(submittedValues).some((value) => !String(value).trim())) throw new Error("required");
      await fetchJson("/api/v1/channels/feishu/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(submittedValues),
      });
      setValues(submittedValues);
      onComplete();
    } catch (caught) {
      setBusy(false);
      const messages = {
        app_id_required: "请填写飞书 App ID 后继续。",
        app_secret_required: "请填写飞书 App Secret 后继续。",
        user_open_id_required: "请填写飞书 User Open ID 后继续。",
        chat_id_required: "请填写飞书 Chat ID 后继续。",
        keyring_dependency_missing: "系统凭据存储组件未安装。请安装项目依赖后重试。",
        system_credential_store_unavailable: "系统凭据存储暂不可用，请检查 Windows Credential Manager 后重试。",
      };
      setError(messages[caught.message] || "保存飞书配置失败，请检查本地服务后重试。");
    }
  };
  const labels = { app_id: "App ID", app_secret: "App Secret", user_open_id: "User Open ID", chat_id: "Chat ID" };
  return <div className="step-panel"><div className="panel-icon orange"><MessageSquare size={21} /></div><div className="panel-copy"><h4>连接消息渠道</h4><p>配置飞书后，待办、日程、新闻和简报仍由 Python 工作流统一处理。</p><button className={`channel-option ${selected === "feishu" ? "selected" : ""}`} onClick={() => { onSelect("feishu"); setError(""); }}><span className="feishu-mark">飞</span><span><strong>飞书 Feishu</strong><small>{channels.find((item) => item.name === "feishu")?.detail ?? "本地配置"}</small></span><Settings2 size={16} /></button><form ref={formRef} className="channel-fields" onSubmit={(event) => { event.preventDefault(); submit(); }}>{["app_id", "app_secret", "user_open_id", "chat_id"].map((key) => <label key={key}>{labels[key]}<input name={key} type={key === "app_secret" ? "password" : "text"} autoComplete={key === "app_secret" ? "current-password" : "off"} placeholder={labels[key]} value={values[key]} onChange={(event) => { setValues({ ...values, [key]: event.target.value }); setError(""); }} /></label>)}</form><div className="flex items-center gap-3 mt-4"><button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "保存渠道设置"} <ChevronRight size={16} /></button><button type="button" className="secondary" disabled={busy} onClick={async () => { setBusy(true); try { await onSkip(); } finally { setBusy(false); } }}>稍后配置</button></div>{error && <div className="error-banner">{error}</div>}</div></div>;
}

function ProfileStep({ onComplete, onSkip }) {
  const [values, setValues] = useState({ display_name: "", "我的工作": "", "当前目标": "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      if (Object.values(values).some((value) => !value.trim())) throw new Error("required");
      const response = await fetch(apiUrl("/api/v1/profile"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
      if (!response.ok) throw new Error("profile");
      onComplete();
    } catch { setBusy(false); setError("请填写你的名字、工作内容和当前目标后继续。"); }
  };
  return <div className="step-panel"><div className="panel-icon green"><Sparkles size={21} /></div><div className="panel-copy"><h4>建立你的个人上下文</h4><p>先告诉我该怎么称呼你；名字和个人上下文之后都可以在设置中修改。</p><div className="profile-grid"><label className="profile-name-field">你的名字<input value={values.display_name} onChange={(event) => { setValues({ ...values, display_name: event.target.value }); setError(""); }} placeholder="例如：小王" maxLength={40} autoComplete="name" /></label><label>我的工作<textarea value={values["我的工作"]} onChange={(event) => { setValues({ ...values, "我的工作": event.target.value }); setError(""); }} placeholder="例如：我负责……" /></label><label>当前目标<textarea value={values["当前目标"]} onChange={(event) => { setValues({ ...values, "当前目标": event.target.value }); setError(""); }} placeholder="例如：近期重点是……" /></label></div><div className="flex items-center gap-3 mt-4"><button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "完成设置，进入桌面端"} <ChevronRight size={16} /></button><button type="button" className="secondary" disabled={busy} onClick={async () => { setBusy(true); try { await onSkip(); } finally { setBusy(false); } }}>稍后设置</button></div>{error && <div className="error-banner">{error}</div>}</div></div>;
}
