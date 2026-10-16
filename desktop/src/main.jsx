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
  Workflow,
  Play,
  Clock,
  Calendar,
  CheckCircle2,
  TrendingUp,
  ShieldCheck,
  Zap,
  Sparkles,
} from "lucide-react";
import "./styles.css";
import "./components/onboarding/onboarding.css";
import { apiUrl, fetchJson, probeLocalApi } from "./localApi";
import WorkflowPage from "./pages/WorkflowPage";
import DatabasePage from "./pages/DatabasePage";
import FileTree from "./components/FileTree";
import AppTopbar from "./components/AppTopbar";
import ApplicationShell from "./components/ApplicationShell";
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

const DesktopFileWorkspace = React.lazy(
  () => import("./components/file-workspace/FileWorkspace"),
);

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an unhandled error:", error, errorInfo);
  }

  resetError = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <section className="placeholder-page mx-auto max-w-xl my-12 p-8 text-center bg-white/90 backdrop-blur-md rounded-2xl border border-red-200 shadow-xl">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-red-100 text-red-600">
            <Zap size={22} />
          </div>
          <span className="eyebrow !text-red-500 font-semibold tracking-wider text-[11px]">PAGE RENDER ERROR</span>
          <h2 className="mt-2 text-xl font-bold text-slate-800">页面渲染遇到异常</h2>
          <p className="mt-2 text-sm text-slate-500">
            {this.state.error?.message || "组件在渲染时遇到未捕获错误，本地数据未受损。"}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              className="primary !rounded-full !bg-black !px-6 !py-2.5 !text-white hover:!bg-slate-800"
              type="button"
              onClick={this.resetError}
            >
              返回工作台首页
            </button>
            <button
              className="secondary !rounded-full !border-slate-300 !px-5 !py-2.5 text-slate-600 hover:!bg-slate-100"
              type="button"
              onClick={() => window.location.reload()}
            >
              刷新应用
            </button>
          </div>
        </section>
      );
    }
    return this.props.children;
  }
}

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
      fetchJson("/api/v1/onboarding/status"),
      fetchJson("/api/v1/workspace"),
      fetchJson("/api/v1/providers/discovery"),
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
      const nextStatus = await fetchJson("/api/v1/onboarding/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_key: stepKey, detail }),
      });
      setStatus(nextStatus);
      setSetupStep(null);
      if (nextStatus.complete && (setupMode || firstRun)) {
        setSetupMode(false);
        setActiveSection("工作台");
        setFirstRun(false);
      }
      if (stepKey === "workspace") {
        setWorkspace(await fetchJson("/api/v1/workspace"));
      }
      if (stepKey === "provider" || stepKey === "channel") {
        setDiscovery(await fetchJson("/api/v1/providers/discovery"));
      }
      setMessage("配置已保存到本地");
    } catch (error) {
      setMessage(`配置未保存：${error.message || "请检查本地服务和输入内容"}`);
    }
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
  return (
    <ApplicationShell activeSection={activeSection} onNavigate={setActiveSection}>
      <main className="main">
        <AppTopbar
          eyebrow={activeSection === "设置" ? "LOCAL SETTINGS" : activeSection === "工作台" ? "LOCAL WORKBENCH" : "MORNINGBRIEF AGENT"}
          title={activeSection === "设置" ? "设置" : activeSection === "工作台" ? "工作台" : activeSection}
          activeSection={activeSection}
          onNavigate={setActiveSection}
          serviceState={serviceState}
          serviceLabel={serviceLabel}
          workspace={workspace}
          onQuickRun={() => setActiveSection("工作流")}
        />
        <ErrorBoundary onReset={() => setActiveSection("工作台")}>
          {activeSection === "文件与数据" ? (
            <React.Suspense fallback={<section className="placeholder-page"><p>正在打开本地文件工作台…</p></section>}>
              <DesktopFileWorkspace serviceState={serviceState} />
            </React.Suspense>
          ) : activeSection === "工作流" ? (
            <WorkflowPage />
          ) : activeSection === "数据库" ? (
            <DatabasePage />
          ) : activeSection === "设置" ? (
            <SettingsPage
              status={status}
              onOpenSetup={(stepKey) => {
                setSetupStep(stepKey);
                setSetupMode(true);
              }}
              onReconfigure={async () => {
                await fetch(apiUrl("/api/v1/onboarding/reset"), { method: "POST" });
                setSetupStep(null);
                setSetupMode(true);
                setActiveSection("工作台");
              }}
            />
          ) : activeSection !== "工作台" ? (
            <SectionPlaceholder section={activeSection} />
          ) : (
            <WorkbenchHome onNavigate={setActiveSection} workspace={workspace} status={status} />
          )}
        </ErrorBoundary>
      </main>
    </ApplicationShell>
  );
}

function WorkbenchHome({ onNavigate, workspace, status }) {
  const [runningKey, setRunningKey] = useState("");
  const [actionNotice, setActionNotice] = useState("");

  const currentHour = new Date().getHours();
  const greeting =
    currentHour >= 5 && currentHour < 12
      ? "早上好，站长 🌅"
      : currentHour >= 12 && currentHour < 14
      ? "中午好，站长 ☀️"
      : currentHour >= 14 && currentHour < 18
      ? "下午好，站长 ☕"
      : "夜深了，站长 🌙";

  const todayStr = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());

  const quickRun = async (key, name) => {
    setRunningKey(key);
    setActionNotice(`正在触发 [${name}] 智能体...`);
    try {
      await fetch(apiUrl(`/api/v1/workflows/${key}/run`), { method: "POST" });
      setActionNotice(`已成功启动 [${name}]，全流程后台静默执行中`);
      setTimeout(() => setActionNotice(""), 3500);
    } catch {
      setActionNotice(`触发 [${name}] 失败，请检查本地后端服务`);
      setTimeout(() => setActionNotice(""), 3500);
    } finally {
      setRunningKey("");
    }
  };

  return (
    <div className="workbench-home-container">
      {/* Executive Greeting & Spring Festival Goal Banner */}
      <section className="executive-hero-banner">
        <div className="executive-hero-left">
          <div className="executive-date-pill">
            <Calendar size={13} className="text-indigo-600" />
            <span>{todayStr}</span>
            <span className="dot-sep">·</span>
            <span className="goal-tag">🎯 距2027春节目标剩 82 天</span>
          </div>

          <h2 className="executive-greeting-title">{greeting}</h2>
          <p className="executive-subtitle">
            你的本地全双工智能体总控中心已就绪。所有业务数据、知识库、行情与日程均保留在本机。
          </p>

          <div className="executive-fast-actions">
            <button
              type="button"
              className="executive-action-btn primary"
              onClick={() => quickRun("todo-morning", "早间行动与日程")}
              disabled={Boolean(runningKey)}
            >
              <Play size={13} />
              <span>{runningKey === "todo-morning" ? "正在执行晨报..." : "运行今日晨报"}</span>
            </button>
            <button
              type="button"
              className="executive-action-btn secondary"
              onClick={() => quickRun("fund", "基金量化投顾")}
              disabled={Boolean(runningKey)}
            >
              <TrendingUp size={13} className="text-emerald-600" />
              <span>{runningKey === "fund" ? "计算行情中..." : "评估基金持仓"}</span>
            </button>
            <button
              type="button"
              className="executive-action-btn secondary"
              onClick={() => quickRun("todo-evening", "晚间复盘总结")}
              disabled={Boolean(runningKey)}
            >
              <Clock size={13} className="text-indigo-600" />
              <span>{runningKey === "todo-evening" ? "正在复盘..." : "触发晚间复盘"}</span>
            </button>
            <button
              type="button"
              className="executive-action-btn secondary"
              onClick={() => onNavigate("文件与数据")}
            >
              <FolderOpen size={13} className="text-slate-600" />
              <span>浏览知识库</span>
            </button>
          </div>

          {actionNotice && (
            <div className="executive-notice-toast animate-fade-in">
              <CheckCircle2 size={13} className="text-emerald-500" />
              <span>{actionNotice}</span>
            </div>
          )}
        </div>

        <div className="executive-hero-right">
          <div className="executive-radar-box">
            <div className="radar-circle circle-1" />
            <div className="radar-circle circle-2" />
            <div className="radar-core">
              <Bot size={28} className="text-white" />
            </div>
            <span className="radar-badge badge-obsidian">Obsidian 知识库</span>
            <span className="radar-badge badge-sqlite">SQLite WAL</span>
            <span className="radar-badge badge-feishu">飞书全双工 Bot</span>
          </div>
        </div>
      </section>

      {/* 4-Grid Bento Live Cards */}
      <section className="workbench-bento-grid">
        {/* Card 1: Knowledge Base */}
        <div className="wb-bento-card" onClick={() => onNavigate("文件与数据")}>
          <div className="wb-card-head">
            <div className="wb-icon-box indigo">
              <FolderOpen size={18} />
            </div>
            <span className="wb-badge">本地知识库</span>
          </div>
          <strong className="wb-title">文件与本地数据</strong>
          <p className="wb-desc">双向链接 Markdown 文档、任务清单与离线附件存储库。</p>
          <div className="wb-foot">
            <span className="wb-foot-meta truncate max-w-[200px]">
              📁 {workspace?.name || "wxk2378643343-cloud"}
            </span>
            <ChevronRight size={14} className="wb-arrow" />
          </div>
        </div>

        {/* Card 2: Workflows */}
        <div className="wb-bento-card" onClick={() => onNavigate("工作流")}>
          <div className="wb-card-head">
            <div className="wb-icon-box emerald">
              <Clock size={18} />
            </div>
            <span className="wb-badge active">系统托管中</span>
          </div>
          <strong className="wb-title">自动化与定时调度</strong>
          <p className="wb-desc">早间行动派发、考研早报、全球资讯、基金投顾与晚间总结。</p>
          <div className="wb-foot">
            <span className="wb-foot-meta text-emerald-700 font-medium">
              ⚡ 7 个专属智能体就绪
            </span>
            <ChevronRight size={14} className="wb-arrow" />
          </div>
        </div>

        {/* Card 3: Database */}
        <div className="wb-bento-card" onClick={() => onNavigate("数据库")}>
          <div className="wb-card-head">
            <div className="wb-icon-box amber">
              <Database size={18} />
            </div>
            <span className="wb-badge">ACID 事务</span>
          </div>
          <strong className="wb-title">持久化业务数据库</strong>
          <p className="wb-desc">待办事实、飞书日程、基金持仓、大盘实时快照与新闻库。</p>
          <div className="wb-foot">
            <span className="wb-foot-meta">7 张核心表 · 零外网泄露</span>
            <ChevronRight size={14} className="wb-arrow" />
          </div>
        </div>

        {/* Card 4: Agent Runtime */}
        <div className="wb-bento-card" onClick={() => onNavigate("Agent 运行")}>
          <div className="wb-card-head">
            <div className="wb-icon-box purple">
              <Bot size={18} />
            </div>
            <span className="wb-badge">在线响应</span>
          </div>
          <strong className="wb-title">智能体态势与飞书</strong>
          <p className="wb-desc">多模态图片识别、DeepSeek 推理执行、富文本卡片即时推送。</p>
          <div className="wb-foot">
            <span className="wb-foot-meta">飞书长连接守护进程活跃</span>
            <ChevronRight size={14} className="wb-arrow" />
          </div>
        </div>
      </section>

      {/* Pipeline Schedule & Fast Launchpad */}
      <section className="workbench-pipeline-section">
        <div className="pipeline-card">
          <div className="pipeline-header">
            <div>
              <span className="eyebrow">DAILY TIMELINE</span>
              <h3>今日自动化流水线时刻表</h3>
            </div>
            <button
              type="button"
              className="secondary compact text-xs"
              onClick={() => onNavigate("工作流")}
            >
              配置时刻
            </button>
          </div>

          <div className="pipeline-timeline">
            {[
              { time: "06:00", title: "🌅 早间待办与行动派发", desc: "整理昨天新增信息，智能生成今日行动与飞书日程", cat: "规划" },
              { time: "06:30", title: "📖 本地知识库考研早报", desc: "从本地 Obsidian 提炼重点考研与备考知识卡片", cat: "知识" },
              { time: "07:45", title: "🌐 全球热点晨报智能去重", desc: "抓取权威公开新闻源，去重筛选并生成早报", cat: "资讯" },
              { time: "14:00", title: "📈 基金持仓与大盘实时投顾", desc: "新浪全球实时行情评估，82天目标收益跟踪", cat: "金融" },
              { time: "23:00", title: "🌙 晚间复盘与级联同步", desc: "完成今日待办结算，级联写回日/周/月周期复盘", cat: "总结" },
            ].map((step, idx) => (
              <div key={idx} className="timeline-item">
                <span className="timeline-time">{step.time}</span>
                <div className="timeline-dot-line">
                  <span className="timeline-dot" />
                  {idx < 4 && <span className="timeline-line" />}
                </div>
                <div className="timeline-content">
                  <div className="flex items-center gap-2">
                    <strong className="text-xs text-slate-800">{step.title}</strong>
                    <span className="pipeline-tag">{step.cat}</span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="quick-launchpad-card">
          <div className="pipeline-header">
            <div>
              <span className="eyebrow">INSTANT LAUNCHPAD</span>
              <h3>高频动作快捷启动</h3>
            </div>
          </div>
          <p className="text-xs text-slate-500 mb-4">
            点击直接呼出对应工作流或功能，无需翻找层级菜单。
          </p>

          <div className="launchpad-grid">
            <button
              type="button"
              className="launchpad-btn"
              onClick={() => quickRun("todo-morning", "早间待办与日程")}
            >
              <div className="launchpad-icon blue">
                <Play size={15} />
              </div>
              <div className="launchpad-text">
                <strong>生成今日待办</strong>
                <small>智能规划并同步日历</small>
              </div>
            </button>

            <button
              type="button"
              className="launchpad-btn"
              onClick={() => quickRun("fund", "基金量化投顾")}
            >
              <div className="launchpad-icon emerald">
                <TrendingUp size={15} />
              </div>
              <div className="launchpad-text">
                <strong>基金行情评估</strong>
                <small>计算持仓盈亏与建议</small>
              </div>
            </button>

            <button
              type="button"
              className="launchpad-btn"
              onClick={() => quickRun("news", "全球热点晨报")}
            >
              <div className="launchpad-icon amber">
                <Zap size={15} />
              </div>
              <div className="launchpad-text">
                <strong>抓取全球新闻</strong>
                <small>多源快讯聚合生成</small>
              </div>
            </button>

            <button
              type="button"
              className="launchpad-btn"
              onClick={() => onNavigate("设置")}
            >
              <div className="launchpad-icon purple">
                <ShieldCheck size={15} />
              </div>
              <div className="launchpad-text">
                <strong>模型与渠道配置</strong>
                <small>DeepSeek / 飞书配置</small>
              </div>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
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
      const sourcesPayload = await fetchJson("/api/v1/data-sources");
      const nextSource = sourcesPayload.sources?.find(
        (item) => item.id === sourcesPayload.active_source_id,
      ) ?? sourcesPayload.sources?.[0];
      if (!nextSource) throw new Error("no source");
      const filesPayload = await fetchJson(`/api/v1/files?source_id=${encodeURIComponent(nextSource.id)}`);
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
  return <section className="file-workspace"><div className="file-toolbar"><div><span className="eyebrow">LOCAL OBSIDIAN</span><h2>文件与数据</h2><p>左侧文件树，中间文件列表，右侧可以查看、编辑、保存和删除 Markdown。</p></div><div className="file-toolbar-actions"><button type="button" className="secondary" onClick={createFile}>新建 Markdown</button><button type="button" className="secondary" onClick={loadFiles}><RefreshCw size={15} />刷新索引</button></div></div><div className="file-layout"><aside className="file-tree"><strong>{source?.name ?? "本地 Obsidian"}</strong><FileTree files={files} selected={selected} onSelect={(path) => { setSelected(path); setEditing(false); setFileMessage(""); }} /><div className="tree-note"><span className="pulse" /> {serviceState === "ready" && live ? "已连接本地工作区" : "本地 API 未启动"}</div></aside><div className="file-list"><div className="file-list-header"><span>名称</span><span>类型</span><span>更新时间</span></div>{files.map(([name, type, path, time, filePath]) => <button className={`file-row ${selected === filePath ? "selected" : ""}`} key={filePath} onClick={() => { setSelected(filePath); setEditing(false); }}><span className="file-name"><FileGlyph type={type} /><span><strong>{name}</strong><small>{path}</small></span></span><span>{type}</span><span>{time}</span></button>)}</div><aside className="file-detail"><span className="eyebrow">Selected file</span><h3>{selectedFile?.[0] || "未选择文件"}</h3>{selectedFile?.[1] === "markdown" || selectedFile?.[1] === "Markdown" ? <div className="file-actions"><button className="secondary" onClick={() => setEditing((value) => !value)}>{editing ? "取消编辑" : "编辑"}</button><button className="primary compact" disabled={!editing || saving} onClick={saveFile}>{saving ? "保存中…" : "保存"}</button><button className="danger-button" onClick={deleteSelectedFile}>删除</button></div> : null}{fileMessage && <div className="file-message">{fileMessage}</div>}<p>内容保存在本机 Obsidian 目录中。</p><div className="preview-box">{editing ? <textarea className="markdown-editor" value={draft} onChange={(event) => setDraft(event.target.value)} /> : preview !== null ? <pre>{preview}</pre> : binaryUrl && selectedFile?.[1] === "image" ? <img className="binary-preview" src={binaryUrl} alt={selectedFile?.[0]} /> : binaryUrl && selectedFile?.[1] === "pdf" ? <iframe className="binary-preview pdf-preview" src={binaryUrl} title={selectedFile?.[0]} /> : <span>此文件类型暂不支持预览：{selectedFile?.[1] ?? "未知"}。</span>}</div><div className="detail-line"><span>访问方式</span><strong>{editing ? "本地编辑" : "只读预览"}</strong></div><div className="detail-line"><span>数据位置</span><strong>{source?.root_path ?? "未连接"}</strong></div></aside></div></section>;
}
function FileGlyph({ type }) {
  if (type === "SQLite") return <Database size={17} />;
  if (type === "图片") return <FolderOpen size={17} />;
  if (type === "日志") return <Workflow size={17} />;
  return <FolderOpen size={17} />;
}
createRoot(document.getElementById("root")).render(<App />);
