import React, { useEffect, useState, useMemo } from "react";
import {
  Play,
  RefreshCw,
  Clock,
  Calendar,
  Zap,
  Activity,
  CheckSquare,
  BookOpen,
  MessageSquare,
  Globe,
  TrendingUp,
  Moon,
  Terminal,
  Check,
  X,
  Copy,
  ChevronRight,
  AlertCircle,
  Eye,
  SlidersHorizontal,
  Layers
} from "lucide-react";
import { apiUrl, fetchJson } from "../localApi";

const WORKFLOW_ICONS = {
  "todo-morning": CheckSquare,
  "brief": BookOpen,
  "chat": MessageSquare,
  "news": Globe,
  "fund": TrendingUp,
  "todo-evening": Moon,
  "fitness": Activity,
};

const CATEGORY_NAMES = {
  planning: "规划与日程",
  knowledge: "知识与简报",
  communication: "交流与复盘",
  information: "全球资讯",
  finance: "量化投顾",
  lifestyle: "健康生活",
};

export default function WorkflowPage() {
  const [payload, setPayload] = useState({ workflows: [], runs: [] });
  const [busy, setBusy] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState(null);

  // Time picker modal state for a workflow
  const [timeModalWorkflow, setTimeModalWorkflow] = useState(null);
  const [timeInput, setTimeInput] = useState("07:00");
  const [timeSaving, setTimeSaving] = useState(false);

  // Log Inspector Drawer state
  const [logDrawerRun, setLogDrawerRun] = useState(null);
  const [logContent, setLogContent] = useState("");
  const [logLoading, setLogLoading] = useState(false);
  const [copiedLog, setCopiedLog] = useState(false);

  // Active filter category
  const [activeCategory, setActiveCategory] = useState("all");

  const load = async () => {
    try {
      const data = await fetchJson("/api/v1/workflows");
      setPayload(data);
    } catch {
      // Keep existing payload if failed
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  // Run a workflow immediately
  const handleRun = async (key) => {
    setBusy(key);
    try {
      await fetchJson(`/api/v1/workflows/${key}/run`, { method: "POST" });
      await load();
    } finally {
      setBusy("");
    }
  };

  // Toggle workflow schedule enabled state
  const handleToggleSchedule = async (workflow, e) => {
    e.stopPropagation();
    const newEnabled = !workflow.enabled;
    try {
      await fetchJson(`/api/v1/workflows/${workflow.key}/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newEnabled, time: workflow.schedule_time }),
      });
      await load();
    } catch {
      alert("更新调度状态失败，请检查本地服务");
    }
  };

  // Open time picker modal
  const handleOpenTimeModal = (workflow) => {
    setTimeModalWorkflow(workflow);
    setTimeInput(workflow.schedule_time || "07:00");
  };

  // Save new scheduled time
  const handleSaveTime = async () => {
    if (!timeModalWorkflow) return;
    setTimeSaving(true);
    try {
      await fetchJson(`/api/v1/workflows/${timeModalWorkflow.key}/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ time: timeInput, enabled: true }),
      });
      setTimeModalWorkflow(null);
      await load();
    } catch {
      alert("保存定时时间失败");
    } finally {
      setTimeSaving(false);
    }
  };

  // Sync tasks to Windows Task Scheduler
  const handleSyncTasks = async () => {
    setSyncing(true);
    try {
      const res = await fetchJson("/api/v1/workflows/sync-tasks", { method: "POST" });
      setSyncNotice(res.message || "Windows 计划任务已同步");
      setTimeout(() => setSyncNotice(null), 4000);
      await load();
    } catch {
      setSyncNotice("同步任务计划失败，请以管理员身份检查系统权限");
      setTimeout(() => setSyncNotice(null), 4000);
    } finally {
      setSyncing(false);
    }
  };

  // Open Log Drawer for a specific run
  const handleOpenLog = async (runId, workflowKey) => {
    setLogDrawerRun({ id: runId, workflow_key: workflowKey });
    setLogLoading(true);
    setLogContent("");
    setCopiedLog(false);
    try {
      const res = await fetchJson(`/api/v1/workflows/runs/${runId}/log`);
      setLogContent(res.content || "日志为空");
    } catch {
      setLogContent("读取日志失败：服务未连接或日志文件不存在");
    } finally {
      setLogLoading(false);
    }
  };

  // Copy full log
  const handleCopyLog = () => {
    if (!logContent) return;
    navigator.clipboard.writeText(logContent);
    setCopiedLog(true);
    setTimeout(() => setCopiedLog(false), 2000);
  };

  // Calculate statistics for Bento cards
  const workflowsList = payload.workflows || [];
  const runsList = payload.runs || [];

  const enabledCount = workflowsList.filter((w) => w.enabled).length;
  const totalCount = workflowsList.length;

  // Find next upcoming agent
  const nextAgent = useMemo(() => {
    const active = workflowsList.filter((w) => w.enabled && w.next_run_hint && !w.next_run_hint.includes("未启用"));
    if (active.length === 0) return null;
    // Prefer today's upcoming, else the first enabled
    const todayUpcoming = active.find((w) => w.next_run_hint.includes("今日"));
    return todayUpcoming || active[0];
  }, [workflowsList]);

  // Calculate success rate over recent runs
  const successRate = useMemo(() => {
    if (runsList.length === 0) return 100;
    const finished = runsList.filter((r) => r.status === "success" || r.status === "failed");
    if (finished.length === 0) return 100;
    const success = finished.filter((r) => r.status === "success").length;
    return Math.round((success / finished.length) * 100);
  }, [runsList]);

  // Filtered workflows by category
  const filteredWorkflows = useMemo(() => {
    if (activeCategory === "all") return workflowsList;
    return workflowsList.filter((w) => w.category === activeCategory);
  }, [workflowsList, activeCategory]);

  return (
    <section className="workspace-page workflow-scheduler-page">
      {/* Page Heading */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">AUTOMATION & AGENT SCHEDULER</span>
          <h2>工作流与定时智能体</h2>
          <p>专属自动化智能体调度总控中心 · 自由配置触发时刻 · 双向同步系统计划任务 · 毫秒级执行透视</p>
        </div>
        <div className="heading-actions flex items-center gap-3">
          <button
            className="secondary flex items-center gap-2"
            onClick={handleSyncTasks}
            disabled={syncing}
            title="将当前定时时刻一键注册并同步至 Windows 系统计划任务"
          >
            <Zap size={14} className={syncing ? "animate-spin text-amber-500" : "text-amber-500"} />
            {syncing ? "正在同步宿主..." : "同步系统计划任务"}
          </button>
          <button className="secondary flex items-center gap-2" onClick={load}>
            <RefreshCw size={14} />
            刷新状态
          </button>
        </div>
      </div>

      {/* Sync Notification Banner */}
      {syncNotice && (
        <div className="wf-notice-banner animate-fade-in">
          <Check size={14} className="text-emerald-500" />
          <span>{syncNotice}</span>
        </div>
      )}

      {/* Bento 3-Grid Overview Stat Cards */}
      <div className="db-bento-grid">
        {/* Card 1: Active Scheduled Agents */}
        <div className="db-bento-card">
          <div className="db-bento-icon-box accent">
            <Clock size={20} />
          </div>
          <div className="db-bento-info">
            <span className="db-bento-label">定时调度托管总览</span>
            <strong className="db-bento-value">
              {enabledCount} <span className="unit">/ {totalCount} 个智能体已激活</span>
            </strong>
            <small className="db-bento-desc">已挂载 Windows Task Scheduler 自动唤醒</small>
          </div>
        </div>

        {/* Card 2: Next Upcoming Agent */}
        <div className="db-bento-card">
          <div className="db-bento-icon-box green">
            <Zap size={20} />
          </div>
          <div className="db-bento-info">
            <span className="db-bento-label">下一个即将触发</span>
            <strong className="db-bento-value">
              {nextAgent ? nextAgent.title : "暂无待触发"}
            </strong>
            <small className="db-bento-desc text-emerald-600 font-medium">
              {nextAgent ? nextAgent.next_run_hint : "所有调度任务已处于休眠或手动状态"}
            </small>
          </div>
        </div>

        {/* Card 3: 24h Success Rate */}
        <div className="db-bento-card">
          <div className="db-bento-icon-box">
            <Activity size={20} />
          </div>
          <div className="db-bento-info">
            <span className="db-bento-label">自动化执行健康度</span>
            <strong className="db-bento-value flex items-center gap-2">
              <span className="pulse" />
              {successRate}%
              <span className="unit">成功率 (共 {runsList.length} 次运行)</span>
            </strong>
            <small className="db-bento-desc">异常自动隔离并录入 SQLite 审计记录</small>
          </div>
        </div>
      </div>

      {/* Category Filter Tabs */}
      <div className="wf-category-bar">
        <div className="wf-tabs-wrap">
          <button
            className={`wf-tab-btn ${activeCategory === "all" ? "active" : ""}`}
            onClick={() => setActiveCategory("all")}
          >
            全部智能体 ({workflowsList.length})
          </button>
          {["planning", "knowledge", "communication", "information", "finance", "lifestyle"].map((cat) => {
            const count = workflowsList.filter((w) => w.category === cat).length;
            if (count === 0) return null;
            return (
              <button
                key={cat}
                className={`wf-tab-btn ${activeCategory === cat ? "active" : ""}`}
                onClick={() => setActiveCategory(cat)}
              >
                {CATEGORY_NAMES[cat]} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {/* Workflow Agent Cards Grid */}
      <div className="wf-agent-grid">
        {filteredWorkflows.map((item) => {
          const IconComp = WORKFLOW_ICONS[item.key] || Zap;
          const isBusy = busy === item.key;
          const lastRun = item.last_run;

          return (
            <article className={`wf-agent-card ${item.enabled ? "is-enabled" : "is-disabled"}`} key={item.key}>
              {/* Card Header: Icon + Title + Schedule Toggle */}
              <div className="wf-card-header">
                <div className="wf-card-icon-title">
                  <div className={`wf-agent-icon-wrap ${item.enabled ? "active-icon" : ""}`}>
                    <IconComp size={18} />
                  </div>
                  <div className="wf-card-meta">
                    <span className="wf-cat-tag">{CATEGORY_NAMES[item.category] || "通用智能体"}</span>
                    <h3>{item.title}</h3>
                  </div>
                </div>

                {/* Schedule Pill & Toggle Switch */}
                <div className="wf-schedule-switch-wrap">
                  <button
                    className={`wf-schedule-pill-btn ${item.enabled ? "pill-active" : "pill-muted"}`}
                    onClick={() => handleOpenTimeModal(item)}
                    title="点击修改每天定时时刻"
                  >
                    <Clock size={12} />
                    <span>{item.enabled ? `每天 ${item.schedule_time}` : "仅手动触发"}</span>
                  </button>

                  {/* Sleek Toggle Switch */}
                  <label className="wf-switch-label" title={item.enabled ? "点击暂停定时调度" : "点击开启定时调度"}>
                    <input
                      type="checkbox"
                      checked={Boolean(item.enabled)}
                      onChange={(e) => handleToggleSchedule(item, e)}
                    />
                    <span className="wf-switch-slider" />
                  </label>
                </div>
              </div>

              {/* Description */}
              <p className="wf-agent-desc">{item.description}</p>

              {/* Input / Output Tags */}
              <div className="wf-pipeline-tags">
                <div className="wf-tag-group">
                  <span className="wf-tag-label">输入源</span>
                  <span className="wf-tag-val">{item.inputs}</span>
                </div>
                <div className="wf-tag-group">
                  <span className="wf-tag-label">产出物</span>
                  <span className="wf-tag-val">{item.outputs}</span>
                </div>
              </div>

              {/* Next Trigger & Last Run Info */}
              <div className="wf-status-row">
                <div className="wf-status-col">
                  <span className="wf-col-label">下次触发</span>
                  <strong className={`wf-col-val ${item.enabled ? "text-emerald-700" : "text-slate-400"}`}>
                    {item.next_run_hint}
                  </strong>
                </div>

                <div className="wf-status-col text-right">
                  <span className="wf-col-label">上次执行</span>
                  <div className="wf-last-run-status">
                    {lastRun ? (
                      <span className={`wf-run-badge ${lastRun.status}`}>
                        {lastRun.status === "success" ? "✓ 成功" : lastRun.status === "running" ? "● 运行中" : "✕ 异常"}
                        {lastRun.duration_seconds !== null && ` (${lastRun.duration_seconds}s)`}
                      </span>
                    ) : (
                      <span className="text-slate-400 text-xs">未曾执行</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Card Footer Actions */}
              <div className="wf-card-actions">
                <button
                  className="wf-action-btn secondary"
                  onClick={() => handleOpenTimeModal(item)}
                  title="调整定时时刻与调度频次"
                >
                  <SlidersHorizontal size={13} />
                  配置时刻
                </button>

                {lastRun && (
                  <button
                    className="wf-action-btn secondary"
                    onClick={() => handleOpenLog(lastRun.id, item.key)}
                    title="透视上次执行日志"
                  >
                    <Terminal size={13} />
                    查看日志
                  </button>
                )}

                <button
                  className="primary compact wf-run-btn"
                  disabled={isBusy}
                  onClick={() => handleRun(item.key)}
                >
                  {isBusy ? (
                    <>
                      <RefreshCw size={13} className="animate-spin" />
                      运行中...
                    </>
                  ) : (
                    <>
                      <Play size={13} />
                      立即运行
                    </>
                  )}
                </button>
              </div>
            </article>
          );
        })}
      </div>

      {/* Recent Runs Audit Table */}
      <div className="db-main-workbench wf-runs-workbench mt-6">
        <div className="db-workbench-toolbar">
          <div className="db-table-badge-indicator">
            <Terminal size={16} />
            <h3>最近运行审计记录 (Recent Runs)</h3>
            <span className="db-column-count-tag">近 {runsList.length} 次执行</span>
          </div>

          <div className="db-toolbar-right">
            <button className="secondary compact" onClick={load}>
              <RefreshCw size={12} />
              刷新历史
            </button>
          </div>
        </div>

        <div className="db-table-scroll-container">
          <table className="db-data-table">
            <thead>
              <tr>
                <th>智能体工作流</th>
                <th>执行状态</th>
                <th>启动时间</th>
                <th>执行耗时</th>
                <th>退出码 / 错误摘要</th>
                <th className="th-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {runsList.map((run) => {
                const IconComp = WORKFLOW_ICONS[run.workflow_key] || Zap;
                const isSuccess = run.status === "success";
                const isRunning = run.status === "running";
                const isFailed = run.status === "failed";

                return (
                  <tr key={run.id} className="db-data-row">
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="wf-table-agent-icon">
                          <IconComp size={14} />
                        </span>
                        <strong className="text-slate-800 text-xs">{run.workflow_key}</strong>
                      </div>
                    </td>
                    <td>
                      <span
                        className={`db-status-badge ${
                          isSuccess ? "badge-emerald" : isRunning ? "badge-amber" : "badge-rose"
                        }`}
                      >
                        <span className="status-dot" />
                        {isSuccess ? "执行成功" : isRunning ? "正在执行中..." : "执行异常"}
                      </span>
                    </td>
                    <td className="text-xs text-slate-600">
                      {run.started_at ? run.started_at.replace("T", " ").slice(0, 19) : "—"}
                    </td>
                    <td className="text-xs font-mono text-slate-700">
                      {run.duration_seconds !== null && run.duration_seconds !== undefined
                        ? `${run.duration_seconds} 秒`
                        : isRunning
                        ? "计算中..."
                        : "—"}
                    </td>
                    <td className="text-xs text-slate-500 max-w-xs truncate" title={run.error_message || ""}>
                      {run.error_message ? (
                        <span className="text-rose-600 flex items-center gap-1 font-mono">
                          <AlertCircle size={12} />
                          {run.error_message}
                        </span>
                      ) : (
                        <span className="text-slate-400">code 0 (正常)</span>
                      )}
                    </td>
                    <td className="td-actions">
                      <button
                        className="wf-table-log-btn"
                        onClick={() => handleOpenLog(run.id, run.workflow_key)}
                        title="打开纯黑终端透视日志"
                      >
                        <Eye size={12} />
                        日志透视
                      </button>
                    </td>
                  </tr>
                );
              })}

              {runsList.length === 0 && (
                <tr>
                  <td colSpan="6" className="db-empty-cell">
                    <div className="db-empty-state">
                      <div className="db-empty-icon">
                        <Terminal size={28} />
                      </div>
                      <h4>暂无最近执行记录</h4>
                      <p>当工作流由定时任务自动触发或手动点击运行时，全生命周期日志将在此留痕。</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Schedule Time Configurator */}
      {timeModalWorkflow && (
        <div className="db-modal-overlay" onClick={() => !timeSaving && setTimeModalWorkflow(null)}>
          <div className="db-modal-dialog max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="db-modal-header">
              <div className="db-modal-title-wrap">
                <span className="eyebrow">SCHEDULE CONFIG</span>
                <h3>调整定时时刻: {timeModalWorkflow.title}</h3>
              </div>
              <button
                type="button"
                className="db-modal-close-btn"
                onClick={() => setTimeModalWorkflow(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="db-modal-body">
              <div className="space-y-4">
                <div>
                  <label className="db-form-label mb-2 block">
                    <span>每日触发时间 (HH:mm)</span>
                    <span className="text-xs text-slate-400">24小时制</span>
                  </label>
                  <input
                    type="time"
                    value={timeInput}
                    onChange={(e) => setTimeInput(e.target.value)}
                    className="db-form-input text-lg font-mono text-center py-3"
                  />
                </div>

                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs text-slate-600 leading-relaxed">
                  <div className="font-semibold text-slate-800 mb-1 flex items-center gap-1">
                    <Clock size={13} className="text-indigo-600" />
                    系统任务计划自动联动
                  </div>
                  保存后，此设置将持久化保存在本地 SQLite 中；点击顶部「同步系统计划任务」即可无缝刷新 Windows Task Scheduler。
                </div>
              </div>
            </div>

            <div className="db-modal-footer">
              <button
                type="button"
                className="secondary"
                onClick={() => setTimeModalWorkflow(null)}
                disabled={timeSaving}
              >
                取消
              </button>
              <button
                type="button"
                className="primary"
                onClick={handleSaveTime}
                disabled={timeSaving}
              >
                {timeSaving ? "保存中..." : "确认并保存时刻"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Drawer / Modal: Terminal Live Log Inspector */}
      {logDrawerRun && (
        <div className="db-modal-overlay" onClick={() => setLogDrawerRun(null)}>
          <div
            className="wf-terminal-modal"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Terminal Header */}
            <div className="wf-terminal-header">
              <div className="wf-terminal-traffic-lights">
                <span className="wf-tl-dot red" onClick={() => setLogDrawerRun(null)} />
                <span className="wf-tl-dot yellow" />
                <span className="wf-tl-dot green" />
              </div>

              <div className="wf-terminal-title">
                <Terminal size={14} className="text-emerald-400" />
                <span>workflow-agent:{logDrawerRun.workflow_key}</span>
                <span className="wf-terminal-runid">[{logDrawerRun.id.slice(0, 8)}]</span>
              </div>

              <div className="wf-terminal-actions">
                <button
                  className="wf-terminal-btn"
                  onClick={handleCopyLog}
                  title="复制全量执行日志"
                >
                  {copiedLog ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                  <span>{copiedLog ? "已复制" : "复制日志"}</span>
                </button>
                <button
                  className="wf-terminal-btn"
                  onClick={() => setLogDrawerRun(null)}
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Terminal Body */}
            <div className="wf-terminal-body">
              {logLoading ? (
                <div className="wf-terminal-loading">
                  <RefreshCw size={20} className="animate-spin text-emerald-400 mb-2" />
                  <span>正在从本地读取进程执行日志流...</span>
                </div>
              ) : (
                <pre className="wf-terminal-pre">{logContent}</pre>
              )}
            </div>

            {/* Terminal Footer */}
            <div className="wf-terminal-footer">
              <span className="text-xs text-slate-400">
                UTF-8 字符流 · 零脱敏本地留痕 · 按 ESC 或点击右上角关闭
              </span>
              <button
                className="secondary compact text-xs"
                onClick={() => handleOpenLog(logDrawerRun.id, logDrawerRun.workflow_key)}
              >
                重新抓取
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
