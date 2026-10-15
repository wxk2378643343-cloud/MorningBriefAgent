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
  const [activeSection, setActiveSection] = useState("工作台");
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
          <NavItem icon={<LayoutDashboard size={17} />} label="工作台" active={activeSection === "工作台"} onClick={() => setActiveSection("工作台")} />
          <NavItem icon={<FolderOpen size={17} />} label="文件与数据" active={activeSection === "文件与数据"} onClick={() => setActiveSection("文件与数据")} />
          <NavItem icon={<Workflow size={17} />} label="工作流" active={activeSection === "工作流"} onClick={() => setActiveSection("工作流")} />
          <NavItem icon={<Database size={17} />} label="数据库" active={activeSection === "数据库"} onClick={() => setActiveSection("数据库")} />
          <NavItem icon={<Bot size={17} />} label="Agent 运行" active={activeSection === "Agent 运行"} onClick={() => setActiveSection("Agent 运行")} />
        </nav>
        <div className="sidebar-bottom"><NavItem icon={<Settings2 size={17} />} label="设置" /><div className="local-only"><span /> 仅在本机运行</div></div>
      </aside>
      <main className="main">
        <header className="topbar"><div><span className="eyebrow">首次启动</span><h1>把你的工作流交给本地 Agent</h1></div><div className="connection"><span className="pulse" />{message}</div></header>
        {activeSection === "文件与数据" ? <FileWorkspace /> : activeSection === "数据库" ? <DatabaseWorkspace /> : activeSection !== "工作台" ? <SectionPlaceholder section={activeSection} /> : <><section className="hero">
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
function FileWorkspace() {
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
  const [live, setLive] = useState(false);

  const loadFiles = async () => {
    try {
      const sourcesResponse = await fetch("http://127.0.0.1:8765/api/v1/data-sources");
      const sourcesPayload = await sourcesResponse.json();
      const nextSource = sourcesPayload.sources?.[0];
      if (!nextSource) throw new Error("no source");
      const filesResponse = await fetch(`http://127.0.0.1:8765/api/v1/files?source_id=${encodeURIComponent(nextSource.id)}`);
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
      return;
    }
    fetch(`http://127.0.0.1:8765/api/v1/files?source_id=${encodeURIComponent(source.id)}&path=${encodeURIComponent(file[4] || file[2])}`)
      .then((response) => response.json())
      .then((payload) => setPreview(payload.file?.content ?? null))
      .catch(() => setPreview(null));
  }, [source, selected, files]);

  const selectedFile = files.find(([name]) => name === selected);
  return <section className="file-workspace"><div className="file-toolbar"><div><span className="eyebrow">Local data</span><h2>文件与数据</h2><p>查看本地文件、数据库、Agent 记录和附件，不复制原始数据。</p></div><div className="file-toolbar-actions"><button type="button" className="secondary" onClick={loadFiles}><RefreshCw size={15} />刷新索引</button><button type="button" className="primary"><FolderOpen size={15} />添加目录</button></div></div><div className="file-layout"><aside className="file-tree"><strong>数据源</strong><button className="tree-selected"><FolderOpen size={15} />{source?.name ?? "全部数据"}</button><button><FolderOpen size={15} />知识库</button><button><Database size={15} />数据库</button><button><MessageSquare size={15} />Agent 对话</button><button><Workflow size={15} />运行日志</button><div className="tree-note"><span className="pulse" /> {live ? "本地索引已连接" : "演示模式：本地 API 未启动"}</div></aside><div className="file-list"><div className="file-list-header"><span>名称</span><span>类型</span><span>更新时间</span></div>{files.map(([name, type, path, time]) => <button className={`file-row ${selected === name ? "selected" : ""}`} key={name} onClick={() => setSelected(name)}><span className="file-name"><FileGlyph type={type} /><span><strong>{name}</strong><small>{path}</small></span></span><span>{type}</span><span>{time}</span></button>)}</div><aside className="file-detail"><span className="eyebrow">Selected file</span><h3>{selected || "未选择文件"}</h3><p>这里会显示受大小限制的只读预览。原始文件仍然保存在你配置的本地目录中。</p><div className="preview-box">{preview !== null ? <pre>{preview}</pre> : selectedFile?.[1] === "markdown" || selectedFile?.[1] === "Markdown" ? <><strong># 今日晨间简报</strong><br /><br /><span>本地预览已准备就绪。启动本地 API 后会显示真实内容。</span></> : <span>此文件类型将使用专用查看器打开：{selectedFile?.[1] ?? "未知"}。</span>}</div><div className="detail-line"><span>访问方式</span><strong>只读预览</strong></div><div className="detail-line"><span>数据位置</span><strong>本地文件系统</strong></div><button type="button" className="secondary">打开原文件</button></aside></div></section>;
}
function FileGlyph({ type }) {
  if (type === "SQLite") return <Database size={17} />;
  if (type === "图片") return <FolderOpen size={17} />;
  if (type === "日志") return <Workflow size={17} />;
  return <FolderOpen size={17} />;
}
function DatabaseWorkspace() {
  const tables = ["agent_usage_records", "todo_records", "schedule_records", "news_items"];
  const [selected, setSelected] = useState(tables[0]);
  return <section className="file-workspace"><div className="file-toolbar"><div><span className="eyebrow">Read only</span><h2>数据库</h2><p>只读查看结构化事实、Agent 用量和同步状态。</p></div><div className="file-toolbar-actions"><span className="db-badge"><Database size={14} /> app.sqlite3</span></div></div><div className="file-layout database-layout"><aside className="file-tree"><strong>数据表</strong>{tables.map((table) => <button className={selected === table ? "tree-selected" : ""} key={table} onClick={() => setSelected(table)}><Database size={14} />{table}</button>)}<div className="tree-note">只读模式<br />修改请通过业务流程完成</div></aside><div className="db-content"><div className="db-title"><div><span className="eyebrow">Table</span><h3>{selected}</h3></div><span className="row-count">最近 50 条</span></div><table><thead><tr><th>id</th><th>status</th><th>provider</th><th>created_at</th></tr></thead><tbody><tr><td>1</td><td><span className="status-dot">success</span></td><td>deepseek</td><td>2026-10-16 09:12</td></tr><tr><td>2</td><td><span className="status-dot">success</span></td><td>agy</td><td>2026-10-16 07:45</td></tr></tbody></table></div><aside className="file-detail"><span className="eyebrow">Database guard</span><h3>只读查看器</h3><p>桌面端不会直接修改业务表，避免绕过校验、幂等和同步流程。</p><div className="detail-line"><span>数据库</span><strong>本地 SQLite</strong></div><div className="detail-line"><span>当前表</span><strong>{selected}</strong></div></aside></div></section>;
}
function WorkspaceStep({ onComplete }) { return <div className="step-panel"><div className="panel-icon blue"><FolderOpen size={21} /></div><div className="panel-copy"><h4>创建本地工作区</h4><p>应用会在本机创建数据库、知识库、日志、附件和对话目录，不会覆盖已有文件。</p><div className="path-row"><code>用户目录 / MorningBriefAgent</code><button className="secondary">选择位置</button></div><button className="primary" onClick={onComplete}>初始化本地工作区 <ChevronRight size={16} /></button></div></div>; }
function ProviderStep({ providers, selected, onSelect, onComplete }) { return <div className="step-panel"><div className="panel-icon violet"><Bot size={21} /></div><div className="panel-copy"><h4>选择你的 AI Provider</h4><p>可以使用 API，也可以使用本地 Agent 进程。密钥不会显示在界面或日志中。</p><div className="provider-grid">{providers.map((provider) => <button className={`provider-option ${selected === provider.name ? "selected" : ""}`} key={provider.name} onClick={() => onSelect(provider.name)}><span className="provider-dot" /><span><strong>{provider.name}</strong><small>{provider.available ? "已检测到" : provider.detail}</small></span>{selected === provider.name && <Check size={16} />}</button>)}</div><button className="primary" onClick={onComplete}>保存 Provider 选择 <ChevronRight size={16} /></button></div></div>; }
function ChannelStep({ channels, selected, onSelect, onComplete }) { const channel = channels.find((item) => item.name === selected); return <div className="step-panel"><div className="panel-icon orange"><MessageSquare size={21} /></div><div className="panel-copy"><h4>连接消息渠道</h4><p>第一阶段先支持飞书。后续可以增加 Telegram、企业微信、邮件或 Webhook。</p><button className={`channel-option ${selected === "feishu" ? "selected" : ""}`} onClick={() => onSelect("feishu")}><span className="feishu-mark">飞</span><span><strong>飞书 Feishu</strong><small>{channel?.configured ? "已配置" : "等待配置 App ID 和 Secret"}</small></span><Settings2 size={16} /></button><button className="primary" onClick={onComplete}>保存渠道设置 <ChevronRight size={16} /></button></div></div>; }
function ProfileStep({ onComplete }) { return <div className="step-panel"><div className="panel-icon green"><Sparkles size={21} /></div><div className="panel-copy"><h4>建立你的个人上下文</h4><p>告诉 Agent 你是谁、做什么、关注什么，以及你希望它如何帮助你。之后可以随时修改。</p><div className="profile-grid"><label>我的工作<textarea placeholder="例如：我负责……" /></label><label>当前目标<textarea placeholder="例如：近期重点是……" /></label></div><button className="primary" onClick={onComplete}>完成设置，进入工作台 <ChevronRight size={16} /></button></div></div>; }

createRoot(document.getElementById("root")).render(<App />);
