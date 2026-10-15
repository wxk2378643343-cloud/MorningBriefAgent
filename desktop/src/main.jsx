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
  const [discovery, setDiscovery] = useState(demoDiscovery);
  const [selectedProvider, setSelectedProvider] = useState("deepseek");
  const [selectedChannel, setSelectedChannel] = useState("feishu");
  const [message, setMessage] = useState("正在检查本地环境…");

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
    Promise.all([
      fetch(apiUrl("/api/v1/onboarding/status")).then((response) => response.json()),
      fetch(apiUrl("/api/v1/providers/discovery")).then((response) => response.json()),
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
  const serviceLabel = {
    starting: "本地服务启动中",
    ready: "本地服务已连接",
    offline: "演示模式：本地服务未连接",
    stopping: "本地服务正在停止",
  }[serviceState];
  if (activeSection === "Agent 运行") return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark"><Sparkles size={17} /></span><span>MorningBrief</span></div><div className="workspace-label">本地工作台</div><nav><NavItem icon={<LayoutDashboard size={17} />} label="工作台" active={false} onClick={() => setActiveSection("工作台")} /><NavItem icon={<FolderOpen size={17} />} label="文件与数据" active={false} onClick={() => setActiveSection("文件与数据")} /><NavItem icon={<Workflow size={17} />} label="工作流" active={false} onClick={() => setActiveSection("工作流")} /><NavItem icon={<Database size={17} />} label="数据库" active={false} onClick={() => setActiveSection("数据库")} /><NavItem icon={<Bot size={17} />} label="Agent 运行" active onClick={() => setActiveSection("Agent 运行")} /></nav></aside><main className="main"><header className="topbar"><div><span className="eyebrow">Runtime</span><h1>Agent 运行状态</h1></div><div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div></header><AgentRuntime serviceState={serviceState} /></main></div>;
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
          <NavItem icon={<LayoutDashboard size={17} />} label="工作台" active={activeSection === "工作台"} onClick={() => setActiveSection("工作台")} />
          <NavItem icon={<FolderOpen size={17} />} label="文件与数据" active={activeSection === "文件与数据"} onClick={() => setActiveSection("文件与数据")} />
          <NavItem icon={<Workflow size={17} />} label="工作流" active={activeSection === "工作流"} onClick={() => setActiveSection("工作流")} />
          <NavItem icon={<Database size={17} />} label="数据库" active={activeSection === "数据库"} onClick={() => setActiveSection("数据库")} />
          <NavItem icon={<Bot size={17} />} label="Agent 运行" active={activeSection === "Agent 运行"} onClick={() => setActiveSection("Agent 运行")} />
        </nav>
        <div className="sidebar-bottom"><NavItem icon={<Settings2 size={17} />} label="设置" /><div className="local-only"><span /> 仅在本机运行</div></div>
      </aside>
      <main className="main">
        <header className="topbar"><div><span className="eyebrow">首次启动</span><h1>把你的工作流交给本地 Agent</h1></div><div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div></header>
        {activeSection === "文件与数据" ? <FileWorkspace serviceState={serviceState} /> : activeSection === "数据库" ? <DatabaseWorkspace serviceState={serviceState} /> : activeSection !== "工作台" ? <SectionPlaceholder section={activeSection} /> : <><section className="hero">
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
        </section></>}
      </main>
    </div>
  );
}

function NavItem({ icon, label, active, onClick }) { return <button type="button" className={`nav-item ${active ? "active" : ""}`} onClick={onClick}><span>{icon}</span>{label}</button>; }
function SectionPlaceholder({ section }) {
  const descriptions = {
    "文件与数据": "这里将查看你的 Markdown、JSON、SQLite、日志、图片和附件。当前原型先展示导航状态。",
    "工作流": "这里将展示待办、日程、新闻、知识库和其他业务工作流。",
    "数据库": "这里将提供 SQLite 表的分页只读查看，不直接修改业务事实。",
    "Agent 运行": "这里将展示 Provider、Token、耗时、输入输出和同步结果。",
  };
  return <section className="placeholder-page"><div className="placeholder-icon"><FolderOpen size={25} /></div><span className="eyebrow">Preview</span><h2>{section}</h2><p>{descriptions[section]}</p><button className="primary" type="button" onClick={() => window.location.reload()}>返回工作台</button></section>;
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
    ["2026-10-15-晨间简报.md", "Markdown", "知识库 / briefings", "今天 07:45"],
    ["app.sqlite3", "SQLite", "data / database", "今天 09:12"],
    ["conversation-20261015.json", "JSON", "Agent 对话 / archive", "今天 10:26"],
    ["nutrition_20261015.jpg", "图片", "图片附件 / nutrition", "今天 12:18"],
    ["agent-20261015.log", "日志", "运行日志", "今天 14:03"],
  ];
  const [source, setSource] = useState(null);
  const [files, setFiles] = useState(demoFiles);
  const [selected, setSelected] = useState(demoFiles[0][0]);
  const [preview, setPreview] = useState(null);
  const [binaryPreview, setBinaryPreview] = useState(null);
  const [live, setLive] = useState(false);
  const [folderFilter, setFolderFilter] = useState("");

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
      setSelected(nextFiles[0]?.[0] ?? "");
      setLive(true);
    } catch {
      setLive(false);
    }
  };

  useEffect(() => { loadFiles(); }, []);

  useEffect(() => {
    if (!source || !selected) return;
    const file = files.find(([name]) => name === selected);
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
      .then((payload) => setPreview(payload.file?.content ?? null))
      .catch(() => setPreview(null));
  }, [source, selected, files]);

  const selectedFile = files.find(([name]) => name === selected);
  const visibleFiles = files.filter(([, , path]) => !folderFilter || path.startsWith(`${folderFilter}/`) || path === folderFilter);
  const binaryUrl = binaryPreview ? `data:${binaryPreview.content_type};base64,${binaryPreview.content_base64}` : null;
  const folders = ["00-首页.md", "01-今日计划", "02-待办", "03-日程", "04-新闻简报", "05-知识库", "06-聊天复盘", "07-饮食记录", "08-运动记录", "09-基金投资", "99-归档"];
  return <section className="file-workspace"><div className="file-toolbar"><div><span className="eyebrow">Demo Obsidian</span><h2>文件与数据</h2><p>所有内容按照本地 Obsidian 目录展示，点击左侧文件夹切换数据。</p></div><div className="file-toolbar-actions"><button type="button" className="secondary" onClick={loadFiles}><RefreshCw size={15} />刷新索引</button></div></div><div className="file-layout"><aside className="file-tree"><strong>{source?.name ?? "Demo Obsidian"}</strong><button className={!folderFilter ? "tree-selected" : ""} onClick={() => setFolderFilter("")}><FolderOpen size={15} />全部文件</button>{folders.map((folder) => <button key={folder} className={folderFilter === folder ? "tree-selected" : ""} onClick={() => { setFolderFilter(folder); const first = files.find(([, , path]) => path === folder || path.startsWith(`${folder}/`)); if (first) setSelected(first[0]); }}>{folder.endsWith(".md") ? <FileGlyph type="markdown" /> : <FolderOpen size={15} />}{folder}</button>)}<div className="tree-note"><span className="pulse" /> {serviceState === "ready" && live ? "已连接 demo/obsidian" : "演示模式：本地 API 未启动"}</div></aside><div className="file-list"><div className="file-list-header"><span>名称</span><span>类型</span><span>更新时间</span></div>{visibleFiles.map(([name, type, path, time]) => <button className={`file-row ${selected === name ? "selected" : ""}`} key={name} onClick={() => setSelected(name)}><span className="file-name"><FileGlyph type={type} /><span><strong>{name}</strong><small>{path}</small></span></span><span>{type}</span><span>{time}</span></button>)}</div><aside className="file-detail"><span className="eyebrow">Selected file</span><h3>{selected || "未选择文件"}</h3><p>这里显示 demo/obsidian 中选中文件的只读内容。</p><div className="preview-box">{preview !== null ? <pre>{preview}</pre> : binaryUrl && selectedFile?.[1] === "image" ? <img className="binary-preview" src={binaryUrl} alt={selected} /> : binaryUrl && selectedFile?.[1] === "pdf" ? <iframe className="binary-preview pdf-preview" src={binaryUrl} title={selected} /> : selectedFile?.[1] === "markdown" || selectedFile?.[1] === "Markdown" ? <><strong>{selected}</strong><br /><br /><span>正在读取本地 Markdown…</span></> : <span>此文件类型暂不支持预览：{selectedFile?.[1] ?? "未知"}。</span>}</div><div className="detail-line"><span>访问方式</span><strong>只读预览</strong></div><div className="detail-line"><span>数据位置</span><strong>demo/obsidian</strong></div></aside></div></section>;
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
  const submit = async () => {
    setBusy(true);
    try {
      const response = await fetch(apiUrl("/api/v1/workspace/initialize"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ root_path: root }) });
      if (!response.ok) throw new Error("workspace");
      onComplete();
    } catch { setBusy(false); }
  };
  const chooseDirectory = async () => {
    try {
      const selected = await open({ directory: true, multiple: false, title: "选择 MorningBrief 工作区" });
      if (typeof selected === "string") setRoot(selected);
    } catch { /* Browser preview keeps the manual path field available. */ }
  };
  return <div className="step-panel"><div className="panel-icon blue"><FolderOpen size={21} /></div><div className="panel-copy"><h4>创建本地工作区</h4><p>选择一个本地目录，应用会创建数据库、知识库、日志、附件和对话目录。</p><div className="path-row"><input value={root} onChange={(event) => setRoot(event.target.value)} placeholder="例如：D:\\MorningBriefWorkspace" /><button type="button" className="secondary" onClick={chooseDirectory}>选择目录</button></div><button className="primary" disabled={!root || busy} onClick={submit}>{busy ? "初始化中…" : "初始化本地工作区"} <ChevronRight size={16} /></button></div></div>;
}
function ProviderStep({ providers, selected, onSelect, onComplete }) {
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      if (selected === "deepseek" && apiKey) {
        const response = await fetch(apiUrl(`/api/v1/providers/${selected}/credentials`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: apiKey }) });
        if (!response.ok) throw new Error("provider");
      }
      onComplete();
    } catch { setBusy(false); }
  };
  return <div className="step-panel"><div className="panel-icon violet"><Bot size={21} /></div><div className="panel-copy"><h4>选择你的 AI Provider</h4><p>密钥只保存到本机系统凭据，不会写入 SQLite 或日志。</p><div className="provider-grid">{providers.map((provider) => <button className={`provider-option ${selected === provider.name ? "selected" : ""}`} key={provider.name} onClick={() => onSelect(provider.name)}><span className="provider-dot" /><span><strong>{provider.name}</strong><small>{provider.available ? "已检测到" : provider.detail}</small></span>{selected === provider.name && <Check size={16} />}</button>)}</div>{selected === "deepseek" && <label className="secret-field">DeepSeek API Key<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-…" /></label>}<button className="primary" disabled={busy} onClick={submit}>{busy ? "保存中…" : "保存 Provider 选择"} <ChevronRight size={16} /></button></div></div>;
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
