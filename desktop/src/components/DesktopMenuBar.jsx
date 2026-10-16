import React, { useState, useEffect, useRef } from "react";
import {
  FileText,
  FolderOpen,
  RefreshCw,
  LayoutDashboard,
  Workflow,
  Database,
  Bot,
  Settings,
  Zap,
  Maximize2,
  Minimize2,
  Info,
  ShieldCheck,
  CheckCircle2,
  ChevronRight,
  Sparkles,
} from "lucide-react";

export default function DesktopMenuBar({
  onNavigate,
  activeSection,
  workspace,
  onQuickRun,
  serviceState,
  serviceLabel,
}) {
  const [activeMenu, setActiveMenu] = useState(null); // 'file' | 'view' | 'workflow' | 'window' | null
  const [showAbout, setShowAbout] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const menuBarRef = useRef(null);

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuBarRef.current && !menuBarRef.current.contains(e.target)) {
        setActiveMenu(null);
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        setActiveMenu(null);
        setShowAbout(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleShortcuts = (e) => {
      // Ignore if typing in input or textarea
      if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;

      if ((e.ctrlKey || e.metaKey) && !e.shiftKey) {
        if (e.key === "1") {
          e.preventDefault();
          onNavigate && onNavigate("工作台");
        } else if (e.key === "2") {
          e.preventDefault();
          onNavigate && onNavigate("文件与数据");
        } else if (e.key === "3") {
          e.preventDefault();
          onNavigate && onNavigate("工作流");
        } else if (e.key === "4") {
          e.preventDefault();
          onNavigate && onNavigate("数据库");
        } else if (e.key === "5") {
          e.preventDefault();
          onNavigate && onNavigate("Agent 运行");
        } else if (e.key === ",") {
          e.preventDefault();
          onNavigate && onNavigate("设置");
        } else if (e.key === "r" && !e.altKey) {
          // let normal refresh happen or handle gracefully
        }
      }

      if (e.key === "F11") {
        e.preventDefault();
        toggleFullscreen();
      }
    };

    window.addEventListener("keydown", handleShortcuts);
    return () => window.removeEventListener("keydown", handleShortcuts);
  }, [onNavigate]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  const handleMenuClick = (menuName) => {
    setActiveMenu(activeMenu === menuName ? null : menuName);
  };

  const handleMenuMouseEnter = (menuName) => {
    if (activeMenu !== null && activeMenu !== menuName) {
      setActiveMenu(menuName);
    }
  };

  const triggerAction = (actionFn) => {
    setActiveMenu(null);
    if (actionFn) actionFn();
  };

  const triggerWorkflow = async (key, name) => {
    setActiveMenu(null);
    if (onQuickRun) {
      onQuickRun(key, name);
    } else {
      try {
        await fetch(`http://127.0.0.1:8765/api/v1/workflows/${key}/run`, { method: "POST" });
        alert(`已成功在后台触发 [${name}] 工作流`);
      } catch {
        alert(`触发 [${name}] 失败，请检查本地后端是否运行在 8765 端口`);
      }
    }
  };

  return (
    <>
      <nav className="desktop-native-menubar" ref={menuBarRef} aria-label="应用主菜单">
        {/* Brand App Badge */}
        <div className="menubar-brand">
          <Sparkles size={13} className="text-amber-500" />
          <span className="font-semibold tracking-tight text-slate-800 text-[12px]">MorningBrief</span>
        </div>

        {/* 1. 文件 (File) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "file" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("file")}
            onMouseEnter={() => handleMenuMouseEnter("file")}
          >
            文件 <span>(F)</span>
          </button>
          {activeMenu === "file" && (
            <div className="menubar-dropdown animate-in">
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => onNavigate && onNavigate("工作流"))}
              >
                <div className="item-label">
                  <FileText size={14} className="text-slate-500" />
                  <span>新建工作流任务 / 简报</span>
                </div>
                <span className="shortcut-tag">Ctrl+N</span>
              </button>
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => onNavigate && onNavigate("文件与数据"))}
              >
                <div className="item-label">
                  <FolderOpen size={14} className="text-indigo-500" />
                  <span>浏览本地知识库目录</span>
                </div>
                <span className="shortcut-tag">Ctrl+O</span>
              </button>
              <div className="dropdown-divider" />
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => window.location.reload())}
              >
                <div className="item-label">
                  <RefreshCw size={14} className="text-slate-500" />
                  <span>重新加载视图与状态</span>
                </div>
                <span className="shortcut-tag">Ctrl+R</span>
              </button>
            </div>
          )}
        </div>

        {/* 2. 视图 (View) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "view" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("view")}
            onMouseEnter={() => handleMenuMouseEnter("view")}
          >
            视图 <span>(V)</span>
          </button>
          {activeMenu === "view" && (
            <div className="menubar-dropdown animate-in">
              <button
                type="button"
                className={`dropdown-item ${activeSection === "工作台" ? "active-page" : ""}`}
                onClick={() => triggerAction(() => onNavigate && onNavigate("工作台"))}
              >
                <div className="item-label">
                  <LayoutDashboard size={14} className="text-sky-500" />
                  <span>工作台首页</span>
                </div>
                <span className="shortcut-tag">Ctrl+1</span>
              </button>
              <button
                type="button"
                className={`dropdown-item ${activeSection === "文件与数据" ? "active-page" : ""}`}
                onClick={() => triggerAction(() => onNavigate && onNavigate("文件与数据"))}
              >
                <div className="item-label">
                  <FolderOpen size={14} className="text-indigo-500" />
                  <span>知识库与文件工作台</span>
                </div>
                <span className="shortcut-tag">Ctrl+2</span>
              </button>
              <button
                type="button"
                className={`dropdown-item ${activeSection === "工作流" ? "active-page" : ""}`}
                onClick={() => triggerAction(() => onNavigate && onNavigate("工作流"))}
              >
                <div className="item-label">
                  <Workflow size={14} className="text-amber-500" />
                  <span>工作流调度中心</span>
                </div>
                <span className="shortcut-tag">Ctrl+3</span>
              </button>
              <button
                type="button"
                className={`dropdown-item ${activeSection === "数据库" ? "active-page" : ""}`}
                onClick={() => triggerAction(() => onNavigate && onNavigate("数据库"))}
              >
                <div className="item-label">
                  <Database size={14} className="text-emerald-500" />
                  <span>SQLite 数据库中心</span>
                </div>
                <span className="shortcut-tag">Ctrl+4</span>
              </button>
              <button
                type="button"
                className={`dropdown-item ${activeSection === "Agent 运行" ? "active-page" : ""}`}
                onClick={() => triggerAction(() => onNavigate && onNavigate("Agent 运行"))}
              >
                <div className="item-label">
                  <Bot size={14} className="text-purple-500" />
                  <span>Agent 运行时监控</span>
                </div>
                <span className="shortcut-tag">Ctrl+5</span>
              </button>
              <div className="dropdown-divider" />
              <button
                type="button"
                className={`dropdown-item ${activeSection === "设置" ? "active-page" : ""}`}
                onClick={() => triggerAction(() => onNavigate && onNavigate("设置"))}
              >
                <div className="item-label">
                  <Settings size={14} className="text-slate-600" />
                  <span>系统设置与配置中心</span>
                </div>
                <span className="shortcut-tag">Ctrl+,</span>
              </button>
            </div>
          )}
        </div>

        {/* 3. 工作流 (Workflow / Run) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "workflow" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("workflow")}
            onMouseEnter={() => handleMenuMouseEnter("workflow")}
          >
            工作流 <span>(W)</span>
          </button>
          {activeMenu === "workflow" && (
            <div className="menubar-dropdown animate-in">
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerWorkflow("morning_brief", "晨间简报与指数资讯")}
              >
                <div className="item-label">
                  <Zap size={14} className="text-amber-500" />
                  <span>立即执行：晨间新闻行情简报</span>
                </div>
                <span className="shortcut-tag">07:45</span>
              </button>
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerWorkflow("evening_review", "夜间智能复盘与健康报告")}
              >
                <div className="item-label">
                  <Zap size={14} className="text-indigo-500" />
                  <span>立即执行：夜间智能复盘</span>
                </div>
                <span className="shortcut-tag">02:00</span>
              </button>
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerWorkflow("todo_sync", "待办归档与飞书多维表格同步")}
              >
                <div className="item-label">
                  <CheckCircle2 size={14} className="text-emerald-500" />
                  <span>立即执行：待办事项双向同步</span>
                </div>
                <span className="shortcut-tag">Sync</span>
              </button>
              <div className="dropdown-divider" />
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => onNavigate && onNavigate("工作流"))}
              >
                <div className="item-label">
                  <Workflow size={14} className="text-slate-500" />
                  <span>管理全部定时任务调度器...</span>
                </div>
                <ChevronRight size={12} className="text-slate-400" />
              </button>
            </div>
          )}
        </div>

        {/* 4. 窗口与帮助 (Window) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "window" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("window")}
            onMouseEnter={() => handleMenuMouseEnter("window")}
          >
            窗口 <span>(W)</span>
          </button>
          {activeMenu === "window" && (
            <div className="menubar-dropdown animate-in">
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(toggleFullscreen)}
              >
                <div className="item-label">
                  {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                  <span>{isFullscreen ? "退出全屏" : "切换全屏模式"}</span>
                </div>
                <span className="shortcut-tag">F11</span>
              </button>
              <div className="dropdown-divider" />
              <div className="dropdown-info-row">
                <ShieldCheck size={14} className="text-emerald-600" />
                <span>后端核心: {serviceState === "ready" ? "8765 活跃" : "未连接"}</span>
              </div>
              <div className="dropdown-info-row">
                <Bot size={14} className="text-indigo-600" />
                <span>飞书守护: pythonw 进程监听中</span>
              </div>
              <div className="dropdown-divider" />
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => setShowAbout(true))}
              >
                <div className="item-label">
                  <Info size={14} className="text-slate-500" />
                  <span>关于 MorningBrief Agent</span>
                </div>
                <span className="shortcut-tag">v0.1.0</span>
              </button>
            </div>
          )}
        </div>

        {/* Window Drag Zone & Right Meta */}
        <div className="menubar-drag-zone" data-tauri-drag-region />

        <div className="menubar-right-meta">
          <span className="menubar-live-dot" />
          <span className="text-[11px] text-slate-500 font-medium">{serviceState === "ready" ? "8765 核心已连接" : "本地核心就绪"}</span>
        </div>
      </nav>

      {/* About Modal */}
      {showAbout && (
        <div className="menubar-modal-backdrop" onClick={() => setShowAbout(false)}>
          <div className="menubar-about-modal animate-in" onClick={(e) => e.stopPropagation()}>
            <div className="about-modal-header">
              <div className="about-icon-capsule">
                <Sparkles size={24} className="text-white" />
              </div>
              <h3>MorningBrief Agent 桌面端</h3>
              <p className="version-pill">Version 0.1.0 (Bento Executive Edition)</p>
            </div>
            <div className="about-modal-body">
              <div className="about-meta-row">
                <span>本地运行时架构</span>
                <strong>Tauri 2.0 + React 19 + Python 3.11</strong>
              </div>
              <div className="about-meta-row">
                <span>数据本地私有化</span>
                <strong>SQLite3 + Obsidian Markdown</strong>
              </div>
              <div className="about-meta-row">
                <span>挂载知识库</span>
                <strong className="truncate max-w-[200px]">{workspace?.name || "wxk2378643343-cloud"}</strong>
              </div>
              <div className="about-meta-row">
                <span>安全与网络</span>
                <span className="status-badge-inline">100% 局域网离线私有</span>
              </div>
            </div>
            <div className="about-modal-footer">
              <button
                type="button"
                className="primary !rounded-full !bg-black !px-6 !py-2 !text-white hover:!bg-slate-800"
                onClick={() => setShowAbout(false)}
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
