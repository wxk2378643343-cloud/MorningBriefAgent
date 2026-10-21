import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  Calendar,
  CheckCircle2,
  CheckSquare,
  ChevronRight,
  Clock,
  History,
  LayoutDashboard,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  Trash2,
  Zap,
} from "lucide-react";
import "./styles.css";
import "./components/onboarding/onboarding.css";
import { apiUrl, fetchJson, probeLocalApi } from "./localApi";
import AppTopbar from "./components/AppTopbar";
import ApplicationShell from "./components/ApplicationShell";
import SettingsPage from "./components/SettingsPage";
import {
  NameRegistrationScreen,
  ONBOARDING_STEPS,
  SetupScreen,
  StartupScreen,
  WelcomeScreen,
} from "./components/onboarding/OnboardingScreen";

const EMPTY_DISCOVERY = { providers: [], channels: [] };

function getLocalDateString(d = new Date()) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

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
              返回今天首页
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
  const [activeSection, setActiveSection] = useState("今天");
  const [serviceState, setServiceState] = useState("starting");
  const [status, setStatus] = useState(null);
  const [workspace, setWorkspace] = useState(null);
  const [profile, setProfile] = useState({ display_name: "" });
  const [discovery, setDiscovery] = useState(EMPTY_DISCOVERY);
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
      fetchJson("/api/v1/profile"),
    ])
      .then(([nextStatus, nextWorkspace, nextDiscovery, nextProfile]) => {
        setStatus(nextStatus);
        if (!nextStatus.complete) {
          setFirstRun(true);
          setShowWelcome(true);
        }
        setWorkspace(nextWorkspace);
        setDiscovery(nextDiscovery);
        setProfile(nextProfile);
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
    offline: "本地服务未连接",
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
        setActiveSection("今天");
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
            setActiveSection("今天");
          }
        }}
        message={message}
      />
    );
  }
  if (!profile.display_name) {
    return <NameRegistrationScreen onComplete={setProfile} />;
  }
  return (
    <ApplicationShell
      activeSection={activeSection}
      onNavigate={setActiveSection}
      workspace={workspace}
      onQuickRun={() => setActiveSection("今天")}
    >
      <main className="main">
        <AppTopbar
          eyebrow={activeSection === "设置" ? "LOCAL SETTINGS" : activeSection === "今天" ? "TODAY" : "MORNINGBRIEF"}
          title={activeSection}
          activeSection={activeSection}
          onNavigate={setActiveSection}
          workspace={workspace}
          onQuickRun={() => setActiveSection("今天")}
        />
        <ErrorBoundary onReset={() => setActiveSection("今天")}>
          {activeSection === "待办" ? (
            <TodosView />
          ) : activeSection === "日程" ? (
            <ScheduleView />
          ) : activeSection === "复盘" ? (
            <ReviewView />
          ) : activeSection === "设置" ? (
            <SettingsPage
              profile={profile}
              status={status}
              onProfileUpdated={setProfile}
              onOpenSetup={(stepKey) => {
                setSetupStep(stepKey);
                setSetupMode(true);
              }}
              onReconfigure={async () => {
                await fetch(apiUrl("/api/v1/onboarding/reset"), { method: "POST" });
                setSetupStep(null);
                setSetupMode(true);
                setActiveSection("今天");
              }}
            />
          ) : (
            <TodayView
              displayName={profile.display_name}
              onNavigate={setActiveSection}
              workspace={workspace}
            />
          )}
        </ErrorBoundary>
      </main>
    </ApplicationShell>
  );
}

function TodayView({ displayName, onNavigate, workspace }) {
  const [todos, setTodos] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [newTodoTitle, setNewTodoTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [runningKey, setRunningKey] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState("success");

  const todayIso = getLocalDateString();
  const tomorrowIso = getLocalDateString(new Date(Date.now() + 86400000));

  const loadData = async () => {
    try {
      // Query today's todos (due_date = today or open tasks)
      const todoRes = await fetchJson(`/api/v1/todos?due_date=${todayIso}`);
      setTodos(todoRes.todos || []);
      // Query schedules strictly within today [todayT00:00:00, tomorrowT00:00:00)
      const schedRes = await fetchJson(`/api/v1/schedules?start_date=${todayIso}T00:00:00&end_date=${tomorrowIso}T00:00:00`);
      setSchedules(schedRes.schedules || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAddTodo = async (e) => {
    e?.preventDefault();
    if (!newTodoTitle.trim() || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiUrl("/api/v1/todos"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTodoTitle.trim(),
          due_date: todayIso,
        }),
      });
      if (!res.ok) throw new Error("添加失败");
      setNewTodoTitle("");
      await loadData();
    } catch (err) {
      setActionNotice(err.message || "添加待办失败");
      setNoticeTone("error");
      setTimeout(() => setActionNotice(""), 3500);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateTodoStatus = async (todo, nextStatus) => {
    try {
      const res = await fetch(apiUrl(`/api/v1/todos/${todo.id}/status`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!res.ok) throw new Error("状态更新失败");
      await loadData();
    } catch (e) {
      console.error(e);
    }
  };

  const quickRun = async (key, name) => {
    setRunningKey(key);
    setActionNotice(`正在触发 [${name}]...`);
    setNoticeTone("info");
    try {
      const res = await fetch(apiUrl(`/api/v1/workflows/${key}/run`), { method: "POST" });
      if (!res.ok) {
        throw new Error(`后端拒绝执行 (HTTP ${res.status})`);
      }
      setActionNotice(`已成功启动 [${name}]，全流程后台执行中`);
      setNoticeTone("success");
      setTimeout(() => setActionNotice(""), 3500);
      await loadData();
    } catch (err) {
      setActionNotice(`触发 [${name}] 失败：${err.message || "请检查本地后端服务"}`);
      setNoticeTone("error");
      setTimeout(() => setActionNotice(""), 3500);
    } finally {
      setRunningKey("");
    }
  };

  const todayStr = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());

  const salutation = displayName?.trim() ? `，${displayName.trim()}` : "";

  return (
    <div className="workbench-home-container !p-6 max-w-5xl mx-auto space-y-6">
      {/* Hero Header */}
      <section className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 text-indigo-600 text-xs font-semibold uppercase tracking-wider mb-1">
            <Calendar size={14} />
            <span>{todayStr}</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-800">你好{salutation} 👋</h2>
          <p className="text-sm text-slate-500 mt-1">
            这里是今日核心日程与待办事实。离线记录，随时复盘。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="primary flex items-center gap-1.5 !rounded-full !px-4 !py-2 text-sm"
            onClick={() => quickRun("todo-morning", "早间计划与日程")}
            disabled={Boolean(runningKey)}
          >
            <Play size={13} />
            <span>{runningKey === "todo-morning" ? "正在执行..." : "运行早间计划"}</span>
          </button>
          <button
            type="button"
            className="secondary flex items-center gap-1.5 !rounded-full !px-4 !py-2 text-sm"
            onClick={() => quickRun("todo-evening", "晚间复盘总结")}
            disabled={Boolean(runningKey)}
          >
            <Clock size={13} />
            <span>{runningKey === "todo-evening" ? "正在复盘..." : "触发晚间复盘"}</span>
          </button>
        </div>
      </section>

      {actionNotice && (
        <div className={`p-3 rounded-xl text-sm flex items-center gap-2 ${
          noticeTone === "error"
            ? "bg-red-50 border border-red-200 text-red-700"
            : noticeTone === "info"
            ? "bg-indigo-50 border border-indigo-200 text-indigo-700"
            : "bg-emerald-50 border border-emerald-200 text-emerald-700"
        }`}>
          <CheckCircle2 size={16} />
          <span>{actionNotice}</span>
        </div>
      )}

      {/* Quick Add */}
      <form onSubmit={handleAddTodo} className="flex gap-2">
        <input
          type="text"
          className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black"
          placeholder="快速添加一条今日要做的事，例如：下午三点交周报..."
          value={newTodoTitle}
          onChange={(e) => setNewTodoTitle(e.target.value)}
        />
        <button
          type="submit"
          className="primary !rounded-xl !px-5 !py-2.5 flex items-center gap-1.5 text-sm"
          disabled={!newTodoTitle.trim() || submitting}
        >
          <Plus size={16} />
          <span>添加待办</span>
        </button>
      </form>

      {/* Main Grid: Today Todos & Today Schedules */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Today Todos */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-sm flex flex-col">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
            <div className="flex items-center gap-2">
              <CheckSquare size={16} className="text-emerald-600" />
              <strong className="text-slate-800 text-sm">今日待办</strong>
              <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">
                {todos.filter((t) => t.status === "open").length} 项待处理
              </span>
            </div>
            <button
              type="button"
              className="text-xs text-indigo-600 hover:underline"
              onClick={() => onNavigate("待办")}
            >
              查看待办管理
            </button>
          </div>
          <div className="space-y-2 flex-1 overflow-y-auto max-h-[360px]">
            {todos.length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-xs">
                今日暂无计划待办，输入上方内容即可添加。
              </div>
            ) : (
              todos.map((todo) => (
                <div
                  key={todo.id}
                  className={`flex items-center justify-between p-2.5 rounded-xl border transition ${
                    todo.status === "completed"
                      ? "bg-slate-50/60 border-slate-100 text-slate-400"
                      : todo.status === "postponed"
                      ? "bg-amber-50/40 border-amber-100 text-amber-700"
                      : todo.status === "cancelled"
                      ? "bg-red-50/30 border-red-100 text-red-500 line-through"
                      : "bg-white border-slate-100 hover:border-slate-300 text-slate-700"
                  }`}
                >
                  <div
                    className="flex items-center gap-2.5 flex-1 cursor-pointer"
                    onClick={() => handleUpdateTodoStatus(todo, todo.status === "completed" ? "open" : "completed")}
                  >
                    <input
                      type="checkbox"
                      checked={todo.status === "completed"}
                      readOnly
                      className="rounded text-indigo-600 cursor-pointer"
                    />
                    <span className={`text-xs ${todo.status === "completed" ? "line-through text-slate-400" : "font-medium"}`}>
                      {todo.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px]">
                    {todo.status === "open" && (
                      <>
                        <button
                          type="button"
                          className="text-amber-600 hover:underline px-1.5 py-0.5"
                          onClick={() => handleUpdateTodoStatus(todo, "postponed")}
                        >
                          延期
                        </button>
                        <button
                          type="button"
                          className="text-slate-400 hover:text-red-500 px-1.5 py-0.5"
                          onClick={() => handleUpdateTodoStatus(todo, "cancelled")}
                        >
                          取消
                        </button>
                      </>
                    )}
                    {todo.status !== "open" && (
                      <span className="text-slate-400">
                        {todo.status === "completed" ? "已完成" : todo.status === "postponed" ? "已延期" : "已取消"}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Today Schedules */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-sm flex flex-col">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
            <div className="flex items-center gap-2">
              <Calendar size={16} className="text-indigo-600" />
              <strong className="text-slate-800 text-sm">今日日程</strong>
              <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">
                {schedules.length} 项日程
              </span>
            </div>
            <button
              type="button"
              className="text-xs text-indigo-600 hover:underline"
              onClick={() => onNavigate("日程")}
            >
              查看日程中心
            </button>
          </div>
          <div className="space-y-2 flex-1 overflow-y-auto max-h-[360px]">
            {schedules.length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-xs">
                今日暂无计划日程。
              </div>
            ) : (
              schedules.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start gap-3 p-2.5 rounded-xl border border-slate-100 bg-slate-50/50"
                >
                  <Clock size={14} className="mt-0.5 text-indigo-500" />
                  <div className="flex-1 text-xs">
                    <strong className="text-slate-800 font-medium">{item.title}</strong>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {item.start_at?.split("T")[1]?.slice(0, 5) || item.start_at} - {item.end_at?.split("T")[1]?.slice(0, 5) || item.end_at}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TodosView() {
  const [todos, setTodos] = useState([]);
  const [filter, setFilter] = useState("all");
  const [title, setTitle] = useState("");
  const todayIso = getLocalDateString();

  const load = async () => {
    const res = await fetchJson("/api/v1/todos");
    setTodos(res.todos || []);
  };

  useEffect(() => {
    load();
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    await fetchJson("/api/v1/todos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim(), due_date: todayIso }),
    });
    setTitle("");
    await load();
  };

  const updateStatus = async (todo, nextStatus) => {
    await fetchJson(`/api/v1/todos/${todo.id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: nextStatus }),
    });
    await load();
  };

  const filtered = todos.filter((t) => {
    if (filter === "completed") return t.status === "completed";
    if (filter === "postponed") return t.status === "postponed";
    if (filter === "cancelled") return t.status === "cancelled";
    if (filter === "open") return t.status === "open";
    return true;
  });

  return (
    <section className="p-8 max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <span className="eyebrow">TODOS MANAGEMENT</span>
          <h2 className="text-2xl font-bold text-slate-800">待办事项</h2>
          <p className="text-sm text-slate-500 mt-1">管理你的全部待办、完成状态、延期与取消留痕。</p>
        </div>
        <div className="flex gap-2">
          {[
            { key: "all", label: "全部" },
            { key: "open", label: "待完成" },
            { key: "completed", label: "已完成" },
            { key: "postponed", label: "已延期" },
            { key: "cancelled", label: "已取消" },
          ].map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition ${
                filter === key ? "bg-black text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="添加一条新待办..."
          className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-black"
        />
        <button type="submit" className="primary !rounded-xl !px-5 !py-2.5 text-sm">
          添加待办
        </button>
      </form>

      <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-100 shadow-sm">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">暂无符合条件的待办</div>
        ) : (
          filtered.map((todo) => (
            <div
              key={todo.id}
              className="flex items-center justify-between p-4 hover:bg-slate-50/50"
            >
              <div
                className="flex items-center gap-3 flex-1 cursor-pointer"
                onClick={() => updateStatus(todo, todo.status === "completed" ? "open" : "completed")}
              >
                <input type="checkbox" checked={todo.status === "completed"} readOnly className="rounded" />
                <div className="text-sm">
                  <span className={todo.status === "completed" ? "line-through text-slate-400" : "text-slate-800"}>
                    {todo.title}
                  </span>
                  {todo.due_date && <small className="ml-3 text-xs text-slate-400">截止: {todo.due_date}</small>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-medium ${
                  todo.status === "completed"
                    ? "bg-emerald-50 text-emerald-600"
                    : todo.status === "postponed"
                    ? "bg-amber-50 text-amber-600"
                    : todo.status === "cancelled"
                    ? "bg-red-50 text-red-500"
                    : "bg-indigo-50 text-indigo-600"
                }`}>
                  {todo.status === "completed"
                    ? "已完成"
                    : todo.status === "postponed"
                    ? "已延期"
                    : todo.status === "cancelled"
                    ? "已取消"
                    : "待完成"}
                </span>
                {todo.status === "open" && (
                  <>
                    <button
                      type="button"
                      className="text-xs text-amber-600 hover:underline px-1.5 py-0.5"
                      onClick={() => updateStatus(todo, "postponed")}
                    >
                      延期
                    </button>
                    <button
                      type="button"
                      className="text-xs text-slate-400 hover:text-red-500 px-1.5 py-0.5"
                      onClick={() => updateStatus(todo, "cancelled")}
                    >
                      取消
                    </button>
                  </>
                )}
                {todo.status !== "open" && (
                  <button
                    type="button"
                    className="text-xs text-slate-400 hover:underline px-1.5 py-0.5"
                    onClick={() => updateStatus(todo, "open")}
                  >
                    重开
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function ScheduleView() {
  const [schedules, setSchedules] = useState([]);

  useEffect(() => {
    fetchJson("/api/v1/schedules")
      .then((res) => setSchedules(res.schedules || []))
      .catch(console.error);
  }, []);

  return (
    <section className="p-8 max-w-4xl mx-auto space-y-6">
      <div>
        <span className="eyebrow">SCHEDULE MANAGEMENT</span>
        <h2 className="text-2xl font-bold text-slate-800">日程规划</h2>
        <p className="text-sm text-slate-500 mt-1">查看由智能规划确认后写入本地事实库的日程列表。</p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-100 shadow-sm">
        {schedules.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">暂无日程安排</div>
        ) : (
          schedules.map((item) => (
            <div key={item.id} className="p-4 flex items-center justify-between">
              <div>
                <strong className="text-sm text-slate-800">{item.title}</strong>
                <div className="text-xs text-slate-500 mt-1 flex items-center gap-1.5">
                  <Clock size={12} />
                  <span>{item.start_at} - {item.end_at}</span>
                </div>
              </div>
              <span className="text-[11px] bg-slate-100 text-slate-600 px-2.5 py-1 rounded-full">
                {item.sync_status || "planned"}
              </span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function ReviewView() {
  const [todos, setTodos] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const todayIso = getLocalDateString();

  useEffect(() => {
    Promise.all([
      fetchJson(`/api/v1/todos?due_date=${todayIso}`),
      fetchJson("/api/v1/audit-logs?entity_type=todo&limit=30"),
    ])
      .then(([todoData, auditData]) => {
        setTodos(todoData.todos || []);
        setAuditLogs(auditData.logs || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const completedCount = todos.filter((t) => t.status === "completed").length;
  const postponedCount = todos.filter((t) => t.status === "postponed").length;
  const cancelledCount = todos.filter((t) => t.status === "cancelled").length;
  const openCount = todos.filter((t) => t.status === "open").length;

  return (
    <section className="p-8 max-w-4xl mx-auto space-y-6">
      <div>
        <span className="eyebrow">ACTION REVIEW & AUDIT</span>
        <h2 className="text-2xl font-bold text-slate-800">今日复盘与行动留痕</h2>
        <p className="text-sm text-slate-500 mt-1">
          真实统计今日待办完成率、延期与取消变动，并提供可追溯的审计审计日志。
        </p>
      </div>

      {/* Metrics Bento */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <span className="text-xs text-slate-500">今日总计划</span>
          <strong className="block text-2xl font-bold text-slate-800 mt-1">{todos.length}</strong>
        </div>
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <span className="text-xs text-emerald-600 font-medium">已完成</span>
          <strong className="block text-2xl font-bold text-emerald-600 mt-1">{completedCount}</strong>
        </div>
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <span className="text-xs text-amber-600 font-medium">已延期</span>
          <strong className="block text-2xl font-bold text-amber-600 mt-1">{postponedCount}</strong>
        </div>
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm">
          <span className="text-xs text-red-500 font-medium">已取消 / 待办中</span>
          <strong className="block text-2xl font-bold text-slate-700 mt-1">{cancelledCount} / {openCount}</strong>
        </div>
      </div>

      {/* Audit Log Timeline */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <h3 className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <History size={16} className="text-indigo-600" />
            <span>行动变更留痕 (Audit Log)</span>
          </h3>
          <span className="text-xs text-slate-400">SQLite audit_log 结构化事实</span>
        </div>

        {loading ? (
          <div className="py-6 text-center text-slate-400 text-xs">正在读取本地审计事实...</div>
        ) : auditLogs.length === 0 ? (
          <div className="py-6 text-center text-slate-400 text-xs">暂无审计留痕记录。</div>
        ) : (
          <div className="space-y-3">
            {auditLogs.map((log) => (
              <div key={log.id} className="flex items-start justify-between text-xs p-2.5 rounded-xl bg-slate-50 border border-slate-100">
                <div>
                  <strong className="text-slate-800 font-semibold">{log.action}</strong>
                  <span className="text-slate-500 ml-2">
                    {log.before_value ? `(${log.before_value} → ${log.after_value})` : log.after_value}
                  </span>
                </div>
                <span className="text-slate-400 text-[11px]">{log.created_at}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

createRoot(document.getElementById("root")).render(<App />);
