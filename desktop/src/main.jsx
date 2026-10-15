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
import { apiUrl, probeLocalApi } from "./localApi";
import { open } from "@tauri-apps/plugin-dialog";
import WorkflowPage from "./pages/WorkflowPage";
import DatabasePage from "./pages/DatabasePage";
import FileTree from "./components/FileTree";

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
  const [activeSection, setActiveSection] = useState("工作台");
  const [serviceState, setServiceState] = useState("starting");
  const [status, setStatus] = useState(null);
  const [workspace, setWorkspace] = useState(null);
  const [discovery, setDiscovery] = useState(demoDiscovery);
  const [selectedProvider, setSelectedProvider] = useState("deepseek");
  const [selectedChannel, setSelectedChannel] = useState("feishu");
  const [message, setMessage] = useState("正在检查本地环境…");
  const [setupMode, setSetupMode] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const checkService = async () => {
      try {
        await probeLocalApi();
        if (!cancelled) setServiceState("ready");
      } catch {
        if (!cancelled) setServiceState("offline");
      }
    };
    checkService();
    const timer = window.setInterval(checkService, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      setServiceState("stopping");
    };
  }, []);

  useEffect(() => {
    if (serviceState !== "ready") return undefined;
    Promise.all([
      fetch(apiUrl("/api/v1/onboarding/status")).then((response) => response.json()),
      fetch(apiUrl("/api/v1/workspace")).then((response) => response.json()),
      fetch(apiUrl("/api/v1/providers/discovery")).then((response) => response.json()),
    ])
      .then(([nextStatus, nextWorkspace, nextDiscovery]) => {
        setStatus(nextStatus);
        setWorkspace(nextWorkspace);
        setDiscovery(nextDiscovery);
        const localProvider = nextDiscovery.providers?.find((provider) => provider.kind === "local_process" && provider.available);
        if (localProvider) setSelectedProvider(localProvider.name);
        setMessage("本地服务已连接");
      })
      .catch(() => {
        setMessage("本地配置状态读取失败");
      });
  }, [serviceState]);

  const currentStep = status?.current_step ?? "workspace";
  const serviceLabel = {
    starting: "本地服务启动中",
    ready: "本地服务已连接",
    offline: "演示模式：本地服务未连接",
    stopping: "本地服务正在停止",
  }[serviceState];
  const currentIndex = Math.max(0, steps.findIndex((step) => step.key === currentStep));
  const completeStep = async (stepKey, detail) => {
    try {
      const response = await fetch(apiUrl("/api/v1/onboarding/complete"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_key: stepKey, detail }),
      });
      if (!response.ok) throw new Error("request failed");
      const nextStatus = await response.json();
      setStatus(nextStatus);
      if (stepKey === "workspace") {
        setWorkspace(await fetch(apiUrl("/api/v1/workspace")).then((item) => item.json()));
      }
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

  if (serviceState !== "ready") {
    return <StartupScreen serviceState={serviceState} serviceLabel={serviceLabel} onRetry={() => window.location.reload()} />;
  }
  if (setupMode || !workspace?.configured || !status?.complete) {
    return (
      <SetupScreen
        serviceLabel={serviceLabel}
        serviceState={serviceState}
        status={status}
        currentStep={currentStep}
        currentIndex={currentIndex}
        discovery={discovery}
        selectedProvider={selectedProvider}
        selectedChannel={selectedChannel}
        setSelectedProvider={setSelectedProvider}
        setSelectedChannel={setSelectedChannel}
        completeStep={completeStep}
        message={message}
      />
    );
  }
  if (activeSection === "Agent 运行") return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div><div className="workspace-label">本地工作台</div><nav><NavItem icon={<LayoutDashboard size={17} />} label="工作台" active={false} onClick={() => setActiveSection("工作台")} /><NavItem icon={<FolderOpen size={17} />} label="文件与数据" active={false} onClick={() => setActiveSection("文件与数据")} /><NavItem icon={<Workflow size={17} />} label="工作流" active={false} onClick={() => setActiveSection("工作流")} /><NavItem icon={<Database size={17} />} label="数据库" active={false} onClick={() => setActiveSection("数据库")} /><NavItem icon={<Bot size={17} />} label="Agent 运行" active onClick={() => setActiveSection("Agent 运行")} /></nav></aside><main className="main"><header className="topbar"><div><span className="eyebrow">Runtime</span><h1>Agent 运行状态</h1></div><div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div></header><AgentRuntime serviceState={serviceState} /></main></div>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div>
        <div className="workspace-label">本地工作台</div>
        <nav>
          <NavItem icon={<LayoutDashboard size={17} />} label="工作台" active={activeSection === "工作台"} onClick={() => setActiveSection("工作台")} />
          <NavItem icon={<FolderOpen size={17} />} label="文件与数据" active={activeSection === "文件与数据"} onClick={() => setActiveSection("文件与数据")} />
          <NavItem icon={<Workflow size={17} />} label="工作流" active={activeSection === "工作流"} onClick={() => setActiveSection("工作流")} />
          <NavItem icon={<Database size={17} />} label="数据库" active={activeSection === "数据库"} onClick={() => setActiveSection("数据库")} />
          <NavItem icon={<Bot size={17} />} label="Agent 运行" active={activeSection === "Agent 运行"} onClick={() => setActiveSection("Agent 运行")} />
        </nav>
        <div className="sidebar-bottom"><NavItem icon={<Settings2 size={17} />} label="设置" active={activeSection === "设置"} onClick={() => setActiveSection("设置")} /><div className="local-only"><span /> 仅在本机运行</div></div>
      </aside>
      <main className="main">
        <header className="topbar"><div><span className="eyebrow">首次启动</span><h1>把你的工作流交给本地 Agent</h1></div><div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div></header>
        {activeSection === "文件与数据" ? <FileWorkspace serviceState={serviceState} /> : activeSection === "工作流" ? <WorkflowPage /> : activeSection === "数据库" ? <DatabasePage /> : activeSection === "设置" ? <SettingsPage onReconfigure={async () => { await fetch(apiUrl("/api/v1/onboarding/reset"), { method: "POST" }); setSetupMode(true); setActiveSection("工作台"); }} /> : activeSection !== "工作台" ? <SectionPlaceholder section={activeSection} /> : <><WorkbenchQuickNav onOpen={setActiveSection} /><section className="hero">
          <div><div className="hero-kicker"><KeyRound size={15} /> 你的数据不会自动上传</div><h2>先完成本地配置，<br /><em>再开始建立你的工作系统。</em></h2><p>MorningBrief 会把数据库、文件、Agent 和消息渠道留在你的电脑上。你可以随时修改或移除配置。</p></div>
          <div className="hero-orbit"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit-core"><Bot size={30} /></div><span className="orbit-label label-one">SQLite</span><span className="orbit-label label-two">Markdown</span><span className="orbit-label label-three">Agent</span></div>
        </section></>}
      </main>
    </div>
  );
}

function StartupScreen({ serviceState, serviceLabel, onRetry }) {
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

function SetupScreen({
  serviceLabel,
  serviceState,
  status,
  currentStep,
  currentIndex,
  discovery,
  selectedProvider,
  selectedChannel,
  setSelectedProvider,
  setSelectedChannel,
  completeStep,
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
          <div className="setup-header"><div><span className="eyebrow">Setup</span><h3>本地初始化向导</h3></div><span className="progress-label">{status?.completed_count ?? 0} / 4 完成</span></div>
          <div className="stepper">{steps.map((step, index) => { const Icon = step.icon; const done = index < currentIndex; const active = index === currentIndex; return <div className={`step ${active ? "active" : ""} ${done ? "done" : ""}`} key={step.key}><div className="step-icon">{done ? <Check size={15} /> : <Icon size={16} />}</div><span>{step.label}</span>{index < steps.length - 1 && <ChevronRight className="step-arrow" size={15} />}</div>; })}</div>
          <div className="setup-content">
            {currentStep === "workspace" && <WorkspaceStep onComplete={() => completeStep("workspace", "local workspace initialized")} />}
            {currentStep === "provider" && <ProviderStep providers={discovery.providers} selected={selectedProvider} onSelect={setSelectedProvider} onComplete={() => completeStep("provider", selectedProvider)} />}
            {currentStep === "channel" && <ChannelStep channels={discovery.channels} selected={selectedChannel} onSelect={setSelectedChannel} onComplete={() => completeStep("channel", selectedChannel)} />}
            {currentStep === "profile" && <ProfileStep onComplete={() => completeStep("profile", "profile ready")} />}
          </div>
          {message && <div className="setup-message">{message}</div>}
        </section>
      </main>
    </div>
  );
}

function NavItem({ icon, label, active, onClick }) { return <button type="button" className={`nav-item ${active ? "active" : ""}`} onClick={onClick}><span>{icon}</span>{label}</button>; }
function WorkbenchQuickNav({ onOpen }) {
  const items = [
    ["文件与数据", "查看 Demo Obsidian 文件树", FolderOpen],
    ["工作流", "查看和运行本地工作流", Workflow],
    ["数据库", "查看和管理业务记录", Database],
    ["Agent 运行", "查看运行、Token 和同步状态", Bot],
  ];
  return <section className="quick-nav"><div><span className="eyebrow">LOCAL WORKBENCH</span><h2>你的本地 Agent 工作台</h2><p>Demo Obsidian 已作为默认本地数据源，选择一个入口开始使用。</p></div><div className="quick-nav-grid">{items.map(([label, description, Icon]) => <button type="button" className="quick-nav-card" key={label} onClick={() => onOpen(label)}><span className="quick-nav-icon"><Icon size={18} /></span><strong>{label}</strong><span>{description}</span><ChevronRight size={16} /></button>)}</div></section>;
}
function SectionPlaceholder({ section }) {
  const descriptions = {
    "文件与数据": "这里将查看你的 Markdown、JSON、SQLite、日志、图片和附件。当前原型先展示导航状态。",
    "工作流": "这里将展示待办、日程、新闻、知识库和其他业务工作流。",
    "数据库": "这里将提供 SQLite 表的分页只读查看，不直接修改业务事实。",
    "Agent 运行": "这里将展示 Provider、Token、耗时、输入输出和同步结果。",
  };
  return <section className="placeholder-page"><div className="placeholder-icon"><FolderOpen size={25} /></div><span className="eyebrow">Preview</span><h2>{section}</h2><p>{descriptions[section]}</p><button className="primary" type="button" onClick={() => window.location.reload()}>返回工作台</button></section>;
}
function SettingsPage({ onReconfigure }) {
  return <section className="placeholder-page"><div className="placeholder-icon"><Settings2 size={25} /></div><span className="eyebrow">Local settings</span><h2>设置</h2><p>所有配置只保存在本机。重新配置不会删除工作区文件，只会重新打开首次启动向导。</p><button className="primary" type="button" onClick={onReconfigure}>重新配置本地工作区</button></section>;
}
function AgentRuntime({ serviceState }) {
  const [status, setStatus] = useState({ latest: null, recent: [], sync: { pending: 0, failed: 0 } });
  const [live, setLive] = useState(false);
  const load = () => fetch(apiUrl("/api/v1/agent/status")).then((response) => response.json()).then((payload) => { setStatus(payload); setLive(true); }).catch(() => setLive(false));
  useEffect(() => { load(); const timer = window.setInterval(load, 5000); return () => window.clearInterval(timer); }, []);
  const latest = status.latest;
  return <section className="runtime-page"><div className="runtime-cards"><RuntimeCard label="当前 Provider" value={latest?.provider ?? "暂无记录"} /><RuntimeCard label="最近任务" value={latest?.task ?? "暂无运行"} /><RuntimeCard label="总 Token" value={latest?.total_tokens ?? "—"} /><RuntimeCard label="耗时" value={latest?.duration_ms ? `${latest.duration_ms} ms` : "—"} /></div><div className="runtime-grid"><div className="runtime-panel"><div className="db-title"><div><span className="eyebrow">Recent runs</span><h3>最近 Agent 运行</h3></div><span className={`status-pill ${live && serviceState === "ready" ? "ok" : ""}`}>{live ? "已连接" : "演示模式"}</span></div><table><thead><tr><th>任务</th><th>Provider</th><th>Token</th><th>状态</th><th>时间</th></tr></thead><tbody>{status.recent.map((run, index) => <tr key={`${run.created_at}-${index}`}><td>{run.task}</td><td>{run.provider}</td><td>{run.total_tokens ?? "—"}</td><td>{run.status}</td><td>{run.created_at}</td></tr>)}{!status.recent.length && <tr><td colSpan="5">暂无 Agent 运行记录</td></tr>}</tbody></table></div><aside className="runtime-panel"><span className="eyebrow">Feishu sync</span><h3>同步状态</h3><div className="detail-line"><span>待处理</span><strong>{status.sync.pending}</strong></div><div className="detail-line"><span>失败待重试</span><strong>{status.sync.failed}</strong></div><button className="secondary" onClick={load}><RefreshCw size={15} />刷新状态</button></aside></div></section>;
}
function RuntimeCard({ label, value }) { return <div className="runtime-card"><span>{label}</span><strong>{value}</strong></div>; }
function FileWorkspace({ serviceState }) {
  const demoFiles = [
    ["2026-10-15-晨间简报.md", "Markdown", "知识库 / briefings", "今天 07:45", "2026-10-15-晨间简报.md"],
    ["app.sqlite3", "SQLite", "data / database", "今天 09:12", "app.sqlite3"],
    ["conversation-20261015.json", "JSON", "Agent 对话 / archive", "今天 10:26", "conversation-20261015.json"],
    ["nutrition_20261015.jpg", "图片", "图片附件 / nutrition", "今天 12:18", "nutrition_20261015.jpg"],
    ["agent-20261015.log", "日志", "运行日志", "今天 14:03", "agent-20261015.log"],
  ];
  const [source, setSource] = useState(null);
  const [files, setFiles] = useState(demoFiles);
  const [selected, setSelected] = useState(demoFiles[0][4] || demoFiles[0][0]);
  const [preview, setPreview] = useState(null);
  const [binaryPreview, setBinaryPreview] = useState(null);
  const [live, setLive] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [fileMessage, setFileMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const loadFiles = async () => {
    try {
      const sourcesResponse = await fetch(apiUrl("/api/v1/data-sources"));
      const sourcesPayload = await sourcesResponse.json();
      const nextSource = sourcesPayload.sources?.[0];
      if (!nextSource) throw new Error("no source");
      const filesResponse = await fetch(apiUrl(`/api/v1/files?source_id=${encodeURIComponent(nextSource.id)}`));
      const filesPayload = await filesResponse.json();
      const nextFiles = (filesPayload.files ?? []).map((file) => [
        file.file_name,
        file.file_type,
        file.relative_path,
        file.modified_at ? new Date(Number(file.modified_at) * 1000).toLocaleString() : "本地文件",
        file.relative_path,
      ]);
      setSource(nextSource);
      setFiles(nextFiles);
      setSelected(nextFiles[0]?.[4] ?? "");
      setLive(true);
    } catch {
      setLive(false);
    }
  };

  useEffect(() => { loadFiles(); }, []);

  useEffect(() => {
    if (!source || !selected) return;
    const file = files.find(([, , , , path]) => path === selected);
    if (!file || !["markdown", "json", "log", "file"].includes(file[1])) {
      setPreview(null);
      if (file && ["image", "pdf"].includes(file[1])) {
        fetch(apiUrl(`/api/v1/file-binary?source_id=${encodeURIComponent(source.id)}&path=${encodeURIComponent(file[4] || file[2])}`))
          .then((response) => response.json())
          .then((payload) => setBinaryPreview(payload.file ?? null))
          .catch(() => setBinaryPreview(null));
      } else {
        setBinaryPreview(null);
      }
      return;
    }
    setBinaryPreview(null);
    fetch(apiUrl(`/api/v1/files?source_id=${encodeURIComponent(source.id)}&path=${encodeURIComponent(file[4] || file[2])}`))
      .then((response) => response.json())
      .then((payload) => { const content = payload.file?.content ?? null; setPreview(content); if (!editing) setDraft(content ?? ""); })
      .catch(() => setPreview(null));
  }, [source, selected, files]);

  const selectedFile = files.find(([, , , , path]) => path === selected);
  const binaryUrl = binaryPreview ? `data:${binaryPreview.content_type};base64,${binaryPreview.content_base64}` : null;
  const saveFile = async () => { if (!source || !selectedFile) return; setSaving(true); setFileMessage(""); try { const response = await fetch(apiUrl("/api/v1/files"), { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ source_id: source.id, path: selectedFile[4], content: draft }) }); if (!response.ok) throw new Error(); setPreview(draft); setEditing(false); setFileMessage("已保存"); await loadFiles(); } catch { setFileMessage("保存失败"); } finally { setSaving(false); } };
  const deleteSelectedFile = async () => { if (!source || !selectedFile || !window.confirm(`确定删除 ${selectedFile[0]} 吗？`)) return; const response = await fetch(apiUrl("/api/v1/files"), { method: "DELETE", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ source_id: source.id, path: selectedFile[4] }) }); if (response.ok) { setSelected(""); setPreview(null); setFileMessage("已删除"); await loadFiles(); } else setFileMessage("删除失败"); };
  const createFile = async () => { if (!source) return; const path = window.prompt("请输入 Markdown 路径，例如：05-知识库/新文件.md"); if (!path) return; const response = await fetch(apiUrl("/api/v1/files"), { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ source_id: source.id, path, content: "# 新文件\n\n" }) }); if (response.ok) { await loadFiles(); setSelected(path); setFileMessage("已创建"); } else setFileMessage("创建失败：只能创建 Markdown 或文本文件"); };
  return <section className="file-workspace"><div className="file-toolbar"><div><span className="eyebrow">Demo Obsidian</span><h2>文件与数据</h2><p>左侧文件树，中间文件列表，右侧可以查看、编辑、保存和删除 Markdown。</p></div><div className="file-toolbar-actions"><button type="button" className="secondary" onClick={createFile}>新建 Markdown</button><button type="button" className="secondary" onClick={loadFiles}><RefreshCw size={15} />刷新索引</button></div></div><div className="file-layout"><aside className="file-tree"><strong>{source?.name ?? "Demo Obsidian"}</strong><FileTree files={files} selected={selected} onSelect={(path) => { setSelected(path); setEditing(false); setFileMessage(""); }} /><div className="tree-note"><span className="pulse" /> {serviceState === "ready" && live ? "已连接 demo/obsidian" : "演示模式：本地 API 未启动"}</div></aside><div className="file-list"><div className="file-list-header"><span>名称</span><span>类型</span><span>更新时间</span></div>{files.map(([name, type, path, time, filePath]) => <button className={`file-row ${selected === filePath ? "selected" : ""}`} key={filePath} onClick={() => { setSelected(filePath); setEditing(false); }}><span className="file-name"><FileGlyph type={type} /><span><strong>{name}</strong><small>{path}</small></span></span><span>{type}</span><span>{time}</span></button>)}</div><aside className="file-detail"><span className="eyebrow">Selected file</span><h3>{selectedFile?.[0] || "未选择文件"}</h3>{selectedFile?.[1] === "markdown" || selectedFile?.[1] === "Markdown" ? <div className="file-actions"><button className="secondary" onClick={() => setEditing((value) => !value)}>{editing ? "取消编辑" : "编辑"}</button><button className="primary compact" disabled={!editing || saving} onClick={saveFile}>{saving ? "保存中…" : "保存"}</button><button className="danger-button" onClick={deleteSelectedFile}>删除</button></div> : null}{fileMessage && <div className="file-message">{fileMessage}</div>}<p>内容保存在本机 Obsidian 目录中。</p><div className="preview-box">{editing ? <textarea className="markdown-editor" value={draft} onChange={(event) => setDraft(event.target.value)} /> : preview !== null ? <pre>{preview}</pre> : binaryUrl && selectedFile?.[1] === "image" ? <img className="binary-preview" src={binaryUrl} alt={selectedFile?.[0]} /> : binaryUrl && selectedFile?.[1] === "pdf" ? <iframe className="binary-preview pdf-preview" src={binaryUrl} title={selectedFile?.[0]} /> : <span>此文件类型暂不支持预览：{selectedFile?.[1] ?? "未知"}。</span>}</div><div className="detail-line"><span>访问方式</span><strong>{editing ? "本地编辑" : "只读预览"}</strong></div><div className="detail-line"><span>数据位置</span><strong>demo/obsidian</strong></div></aside></div></section>;
}
function FileGlyph({ type }) {
  if (type === "SQLite") return <Database size={17} />;
  if (type === "图片") return <FolderOpen size={17} />;
  if (type === "日志") return <Workflow size={17} />;
  return <FolderOpen size={17} />;
}
function DatabaseWorkspace() {
  const demoTables = ["agent_usage_records", "todo_records", "schedule_records", "news_items"];
  const [source, setSource] = useState(null);
  const [databaseFile, setDatabaseFile] = useState(null);
  const [tables, setTables] = useState(demoTables);
  const [selected, setSelected] = useState(demoTables[0]);
  const [database, setDatabase] = useState(null);
  const [live, setLive] = useState(false);

  const loadDatabase = async () => {
    try {
      const sourcesPayload = await fetch(apiUrl("/api/v1/data-sources")).then((response) => response.json());
      const nextSource = sourcesPayload.sources?.[0];
      if (!nextSource) throw new Error("no source");
      const filesPayload = await fetch(apiUrl(`/api/v1/files?source_id=${encodeURIComponent(nextSource.id)}`)).then((response) => response.json());
      const nextFile = filesPayload.files?.find((file) => file.file_type === "sqlite");
      if (!nextFile) throw new Error("no sqlite");
      const schema = await fetch(apiUrl(`/api/v1/sqlite?source_id=${encodeURIComponent(nextSource.id)}&path=${encodeURIComponent(nextFile.relative_path)}`)).then((response) => response.json());
      const nextTables = schema.database?.tables ?? [];
      setSource(nextSource);
      setDatabaseFile(nextFile);
      setTables(nextTables);
      setSelected(nextTables[0] ?? "");
      setLive(true);
    } catch {
      setLive(false);
    }
  };

  useEffect(() => { loadDatabase(); }, []);

  useEffect(() => {
    if (!source || !databaseFile || !selected) return;
    fetch(apiUrl(`/api/v1/sqlite?source_id=${encodeURIComponent(source.id)}&path=${encodeURIComponent(databaseFile.relative_path)}&table=${encodeURIComponent(selected)}`))
      .then((response) => response.json())
      .then((payload) => setDatabase(payload.database ?? null))
      .catch(() => setDatabase(null));
  }, [source, databaseFile, selected]);

  const columns = database?.columns ?? ["id", "status", "provider", "created_at"];
  const rows = database?.rows ?? [
    { id: 1, status: "success", provider: "deepseek", created_at: "演示数据" },
    { id: 2, status: "success", provider: "agy", created_at: "演示数据" },
  ];
  return <section className="file-workspace"><div className="file-toolbar"><div><span className="eyebrow">Read only</span><h2>数据库</h2><p>只读查看结构化事实、Agent 用量和同步状态。</p></div><div className="file-toolbar-actions"><button type="button" className="secondary" onClick={loadDatabase}><RefreshCw size={15} />刷新</button><span className="db-badge"><Database size={14} /> {databaseFile?.file_name ?? "app.sqlite3"}</span></div></div><div className="file-layout database-layout"><aside className="file-tree"><strong>数据表</strong>{tables.map((table) => <button className={selected === table ? "tree-selected" : ""} key={table} onClick={() => setSelected(table)}><Database size={14} />{table}</button>)}<div className="tree-note"><span className="pulse" /> {live ? "已读取本地 SQLite" : "演示模式：未连接本地数据库"}<br />只读模式</div></aside><div className="db-content"><div className="db-title"><div><span className="eyebrow">Table</span><h3>{selected || "未选择数据表"}</h3></div><span className="row-count">最近 50 条</span></div><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id ?? index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}</tr>)}</tbody></table></div><aside className="file-detail"><span className="eyebrow">Database guard</span><h3>只读查看器</h3><p>桌面端不会直接修改业务表，避免绕过校验、幂等和同步流程。</p><div className="detail-line"><span>数据库</span><strong>{databaseFile?.file_name ?? "本地 SQLite"}</strong></div><div className="detail-line"><span>当前表</span><strong>{selected || "—"}</strong></div></aside></div></section>;
}
function WorkspaceStep({ onComplete }) {
  const [root, setRoot] = useState("");
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
  return <div className="step-panel"><div className="panel-icon blue"><FolderOpen size={21} /></div><div className="panel-copy"><h4>配置本地工作区</h4><p>选择你自己的本地目录。应用只会在该目录建立必要的本地目录和 SQLite，不上传任何内容。</p><div className="path-row"><input value={root} onChange={(event) => { setRoot(event.target.value); setError(""); }} placeholder="例如：D:\\MorningBriefWorkspace" /><button type="button" className="secondary" onClick={chooseDirectory}>选择目录</button></div><div className="setup-actions"><button className="primary" disabled={!root || busy} onClick={submit}>{busy ? "初始化中…" : "初始化本地工作区"} <ChevronRight size={16} /></button></div>{error && <div className="error-banner">{error}</div>}</div></div>;
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

createRoot(document.getElementById("root")).render(<App />);
