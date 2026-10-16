import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  ChevronRight,
  Database,
  FolderOpen,
  KeyRound,
  LayoutDashboard,
  RefreshCw,
  Settings2,
  Sparkles,
  Workflow,
} from "lucide-react";
import "./styles.css";
import { apiUrl, probeLocalApi } from "./localApi";
import WorkflowPage from "./pages/WorkflowPage";
import DatabasePage from "./pages/DatabasePage";
import FileTree from "./components/FileTree";
import { ONBOARDING_STEPS, SetupScreen, StartupScreen, WelcomeScreen } from "./components/onboarding/OnboardingScreen";

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
  const [setupStep, setSetupStep] = useState(null);
  const [showWelcome, setShowWelcome] = useState(false);
  const [firstRun, setFirstRun] = useState(false);

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
        if (!nextStatus.complete) {
          setFirstRun(true);
          setShowWelcome(true);
        }
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
  const currentIndex = Math.max(0, ONBOARDING_STEPS.findIndex((step) => step.key === (setupStep ?? currentStep)));
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
      setSetupStep(null);
      if (nextStatus.complete && (setupMode || firstRun)) {
        setSetupMode(false);
        setActiveSection("工作台");
        setFirstRun(false);
      }
      if (stepKey === "workspace") {
        setWorkspace(await fetch(apiUrl("/api/v1/workspace")).then((item) => item.json()));
      }
      setMessage("配置已保存到本地");
    } catch {
      setMessage("演示模式：配置将在本地 API 启动后保存");
      setStatus((previous) => ({
        ...(previous ?? { steps: [], completed_count: 0, total_count: 4 }),
        current_step: ONBOARDING_STEPS[Math.min(currentIndex + 1, ONBOARDING_STEPS.length - 1)].key,
        completed_count: Math.min((previous?.completed_count ?? 0) + 1, 4),
      }));
    }
  };
  const skipRemainingSetup = async () => {
    const pending = (status?.steps ?? []).filter((item) => item.status !== "completed" && item.step_key !== "workspace");
    let nextStatus = status;
    for (const item of pending) {
      const response = await fetch(apiUrl("/api/v1/onboarding/complete"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_key: item.step_key, skipped: true, detail: "skipped; can be configured later" }),
      });
      if (response.ok) nextStatus = await response.json();
    }
    setStatus(nextStatus);
    setSetupStep(null);
    setMessage("已跳过后续配置，可在设置中重新配置");
  };

  if (serviceState !== "ready") {
    return <StartupScreen serviceState={serviceState} serviceLabel={serviceLabel} onRetry={() => window.location.reload()} />;
  }
  if (showWelcome) {
    return <WelcomeScreen onEnter={() => setShowWelcome(false)} />;
  }
  if (setupMode || !workspace?.configured || !status?.complete) {
    return (
      <SetupScreen
        serviceLabel={serviceLabel}
        serviceState={serviceState}
        status={status}
        workspace={workspace}
        currentStep={setupStep ?? currentStep}
        currentIndex={currentIndex}
        discovery={discovery}
        selectedProvider={selectedProvider}
        selectedChannel={selectedChannel}
        setSelectedProvider={setSelectedProvider}
        setSelectedChannel={setSelectedChannel}
        completeStep={completeStep}
        onBack={() => {
          const index = ONBOARDING_STEPS.findIndex((step) => step.key === (setupStep ?? currentStep));
          if (index === 0) {
            setSetupMode(false);
            setSetupStep(null);
            setShowWelcome(true);
          } else {
            setSetupStep(ONBOARDING_STEPS[index - 1].key);
          }
        }}
        onSkip={currentStep === "workspace" ? null : skipRemainingSetup}
        onCancel={() => {
          setSetupMode(false);
          setSetupStep(null);
          if (firstRun || !status?.complete) {
            setShowWelcome(true);
          } else {
            setActiveSection("工作台");
          }
        }}
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
        <header className="topbar"><div><span className="eyebrow">{activeSection === "设置" ? "LOCAL SETTINGS" : activeSection === "工作台" ? "LOCAL WORKBENCH" : "MORNINGBRIEF AGENT"}</span><h1>{activeSection === "设置" ? "设置" : activeSection === "工作台" ? "你的本地 Agent 工作台" : activeSection}</h1></div><div className={`connection connection-${serviceState}`}><span className="pulse" />{serviceLabel}</div></header>
        {activeSection === "文件与数据" ? <FileWorkspace serviceState={serviceState} /> : activeSection === "工作流" ? <WorkflowPage /> : activeSection === "数据库" ? <DatabasePage /> : activeSection === "设置" ? <SettingsPage status={status} onOpenSetup={(stepKey) => {
          setSetupStep(stepKey);
          setSetupMode(true);
        }} onReconfigure={async () => { await fetch(apiUrl("/api/v1/onboarding/reset"), { method: "POST" }); setSetupStep(null); setSetupMode(true); setActiveSection("工作台"); }} /> : activeSection !== "工作台" ? <SectionPlaceholder section={activeSection} /> : <><WorkbenchQuickNav onOpen={setActiveSection} /><section className="hero">
          <div><div className="hero-kicker"><KeyRound size={15} /> 你的数据不会自动上传</div><h2>先完成本地配置，<br /><em>再开始建立你的工作系统。</em></h2><p>MorningBrief 会把数据库、文件、Agent 和消息渠道留在你的电脑上。你可以随时修改或移除配置。</p></div>
          <div className="hero-orbit"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit-core"><Bot size={30} /></div><span className="orbit-label label-one">SQLite</span><span className="orbit-label label-two">Markdown</span><span className="orbit-label label-three">Agent</span></div>
        </section></>}
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
function SettingsPage({ status, onOpenSetup, onReconfigure }) {
  const [selectedKey, setSelectedKey] = useState("workspace");
  const selectedStep = ONBOARDING_STEPS.find((step) => step.key === selectedKey) ?? ONBOARDING_STEPS[0];
  const SelectedIcon = selectedStep.icon;
  const selectedState = status?.steps?.find((item) => item.step_key === selectedStep.key)?.status ?? "pending";
  const stateLabel = { completed: "已连接", skipped: "稍后配置", pending: "未配置" }[selectedState] ?? "未配置";
  const stateTone = { completed: "success", skipped: "muted", pending: "warning" }[selectedState] ?? "warning";
  const stepDescriptions = {
    workspace: "管理本地工作区、知识库文件和运行数据的位置。",
    provider: "选择本地 Agent 或 API，并管理模型连接方式。",
    channel: "配置飞书等消息渠道，让业务工作流可以主动通知你。",
    profile: "告诉 Agent 你的工作重点和当前目标，形成可编辑的本地记忆。",
  };
  const completed = status?.completed_count ?? 0;
  const skipped = status?.skipped_count ?? 0;
  return (
    <section className="settings-page mx-auto max-w-[1120px] !pt-2">
      <div className="settings-hero !items-center !border-0 !pb-8">
        <div>
          <span className="eyebrow !text-[10px] !tracking-[.18em]">LOCAL SETTINGS</span>
          <h2 className="!mt-3 !text-[36px] !font-semibold !tracking-[-.06em]">设置</h2>
          <p className="!mt-2 !text-[13px]">让本地 Agent 更贴合你的工作方式。</p>
        </div>
        <div className="settings-summary !min-w-[154px] !rounded-2xl !border-black/[.08] !bg-white/80 !shadow-[0_12px_40px_rgba(0,0,0,.06)]">
          <strong className="!text-[26px] !text-[#171717]">{completed}/{ONBOARDING_STEPS.length}</strong><span>配置项已完成</span>{skipped > 0 && <small>{skipped} 项稍后配置</small>}
        </div>
      </div>
      <div className="settings-shell !grid-cols-[250px_minmax(0,1fr)] !rounded-[24px] !border-black/[.08] !shadow-[0_22px_70px_rgba(0,0,0,.07)]">
        <nav className="settings-nav !gap-1 !bg-[#fafafa] !p-3" aria-label="设置分类">
          <div className="settings-nav-title !px-3 !pb-3 !text-[10px]">设置</div>
          {ONBOARDING_STEPS.map((step) => {
            const Icon = step.icon;
            const stepState = status?.steps?.find((item) => item.step_key === step.key)?.status ?? "pending";
            return <button type="button" className={`settings-nav-item !rounded-xl !px-3 !py-3 ${selectedKey === step.key ? "active !border-black/[.08] !bg-white !text-black !shadow-[0_4px_14px_rgba(0,0,0,.06)]" : "!text-[#737373]"}`} key={step.key} onClick={() => setSelectedKey(step.key)}><span className={`settings-nav-icon !h-8 !w-8 !rounded-[10px] ${selectedKey === step.key ? "!bg-black !text-white" : "!bg-[#ededed] !text-[#737373]"}`}><Icon size={15} /></span><span><strong className="!text-[12px]">{step.label}</strong><small>{stepState === "completed" ? "已连接" : stepState === "skipped" ? "稍后配置" : "未配置"}</small></span><ChevronRight size={14} /></button>;
          })}
          <div className="settings-nav-foot !text-[#a3a3a3]"><span className="local-dot !bg-black !shadow-none" />数据仅保存在本机</div>
        </nav>
        <div className="settings-detail !bg-white">
          <div className="settings-detail-head !gap-4 !border-black/[.06] !px-9 !py-8">
            <div className="settings-detail-icon settings-icon-float !h-12 !w-12 !rounded-2xl !bg-black !text-white"><SelectedIcon size={21} /></div>
            <div><div className="settings-detail-title"><h3 className="!text-[21px] !font-semibold !tracking-[-.03em]">{selectedStep.label}</h3><span className={`settings-status ${stateTone} !rounded-full !border !border-black/[.06]`}>{stateLabel}</span></div><p>{stepDescriptions[selectedStep.key]}</p></div>
          </div>
          <div className="settings-detail-body !gap-6 !px-9 !py-8">
            <div className="settings-state-row settings-state-row-hover !rounded-2xl !border-black/[.08] !bg-[#fafafa] !p-5"><div><strong className="!text-[14px]">{selectedState === "completed" ? "配置已生效" : selectedState === "skipped" ? "这项配置可以稍后补充" : "这项配置还没有完成"}</strong><span>{selectedState === "completed" ? "你可以随时进入向导修改。" : "进入配置向导完成后，状态会在这里更新。"}</span></div><button className="primary !rounded-full !bg-black !px-5 !py-3 hover:!bg-[#333]" type="button" onClick={() => onOpenSetup(selectedStep.key)}>{selectedState === "completed" ? "修改设置" : "开始配置"} <ChevronRight size={15} /></button></div>
            <div className="settings-note !text-[#a3a3a3]"><Sparkles size={16} /><span>首次启动向导只负责建立基础配置；这里是日常修改入口。</span></div>
          </div>
        </div>
      </div>
      <div className="settings-danger-zone !mt-5 !rounded-2xl !border-black/[.07] !bg-white/70"><div><strong>重新运行初始化向导</strong><p>保留本地文件，只重置配置进度。适合更换工作区或重新选择 Agent。</p></div><button className="secondary !rounded-full !border-black/[.1]" type="button" onClick={onReconfigure}>重新配置</button></div>
    </section>
  );
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
createRoot(document.getElementById("root")).render(<App />);
