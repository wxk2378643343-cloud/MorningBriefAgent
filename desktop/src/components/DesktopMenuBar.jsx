import React, { useState, useEffect, useRef } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  FileText,
  FolderOpen,
  RefreshCw,
  LayoutDashboard,
  CheckSquare,
  Calendar,
  History,
  Workflow,
  Database,
  Bot,
  Settings,
  Zap,
  Maximize2,
  Minimize2,
  Info,
  CheckCircle2,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import WindowControls from "./WindowControls";
import { DESKTOP_SECTIONS, SETTINGS_SECTION, WORKFLOW_ACTIONS } from "./desktopNavigation";

const MENU_ICONS = {
  today: [LayoutDashboard, "text-sky-500"],
  todos: [CheckSquare, "text-emerald-500"],
  schedule: [Calendar, "text-indigo-500"],
  review: [History, "text-amber-500"],
  settings: [Settings, "text-slate-600"],
};

const WORKFLOW_TONE_CLASSES = {
  amber: "text-amber-500",
  indigo: "text-indigo-500",
  emerald: "text-emerald-500",
};

export default function DesktopMenuBar({
  onNavigate,
  activeSection,
  workspace,
  onQuickRun,
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
        const destination = DESKTOP_SECTIONS[Number(e.key) - 1]?.key;
        if (destination) {
          e.preventDefault();
          onNavigate?.(destination);
        } else if (e.key === ",") {
          e.preventDefault();
          onNavigate?.(SETTINGS_SECTION.key);
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
      document.documentElement.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const handleMenuClick = (menuName) => {
    setActiveMenu(activeMenu === menuName ? null : menuName);
  };

  const handleMenuMouseEnter = (menuName) => {
    if (activeMenu !== null) {
      setActiveMenu(menuName);
    }
  };

  const triggerAction = (actionFn) => {
    setActiveMenu(null);
    actionFn?.();
  };

  const runWorkflow = async (key, name) => {
    setActiveMenu(null);
    try {
      await fetch(`http://127.0.0.1:8765/api/v1/workflows/${key}/run`, { method: "POST" });
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="desktop-menubar-root" ref={menuBarRef} data-tauri-drag-region>
      {/* Left Application Logo & Identification */}
      <div className="menubar-brand" data-tauri-drag-region>
        <span className="brand-dot" />
        <span className="brand-title">MorningBrief</span>
        <span className="brand-badge">Core</span>
      </div>

      {/* Menus Container */}
      <div className="menubar-items-container">
        {/* 1. 文件 (File) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "file" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("file")}
            onMouseEnter={() => handleMenuMouseEnter("file")}
          >
            文件
          </button>
          {activeMenu === "file" && (
            <div className="menubar-dropdown animate-in">
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => onNavigate?.("设置"))}
              >
                <div className="item-label">
                  <Settings size={14} className="text-slate-500" />
                  <span>首选项与本地设置...</span>
                </div>
                <span className="shortcut-tag">Ctrl+,</span>
              </button>
              <div className="dropdown-divider" />
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => window.location.reload())}
              >
                <div className="item-label">
                  <RefreshCw size={14} className="text-slate-500" />
                  <span>重新加载工作区</span>
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
            视图
          </button>
          {activeMenu === "view" && (
            <div className="menubar-dropdown animate-in">
              {DESKTOP_SECTIONS.map(({ key, label, shortcut, icon }) => {
                const [Icon, iconClass] = MENU_ICONS[icon] || [LayoutDashboard, "text-sky-500"];
                return (
                  <button
                    key={key}
                    type="button"
                    className={`dropdown-item ${activeSection === key ? "active-page" : ""}`}
                    onClick={() => triggerAction(() => onNavigate?.(key))}
                  >
                    <div className="item-label">
                      <Icon size={14} className={iconClass} />
                      <span>{label}</span>
                    </div>
                    <span className="shortcut-tag">{shortcut}</span>
                  </button>
                );
              })}
              <div className="dropdown-divider" />
              {(() => {
                const [Icon, iconClass] = MENU_ICONS[SETTINGS_SECTION.icon] || [Settings, "text-slate-600"];
                return (
                  <button
                    type="button"
                    className={`dropdown-item ${activeSection === SETTINGS_SECTION.key ? "active-page" : ""}`}
                    onClick={() => triggerAction(() => onNavigate?.(SETTINGS_SECTION.key))}
                  >
                    <div className="item-label">
                      <Icon size={14} className={iconClass} />
                      <span>{SETTINGS_SECTION.label}</span>
                    </div>
                    <span className="shortcut-tag">{SETTINGS_SECTION.shortcut}</span>
                  </button>
                );
              })()}
            </div>
          )}
        </div>

        {/* 3. 规划 (Planning Actions) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "workflow" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("workflow")}
            onMouseEnter={() => handleMenuMouseEnter("workflow")}
          >
            规划
          </button>
          {activeMenu === "workflow" && (
            <div className="menubar-dropdown animate-in">
              <div className="dropdown-header">核心工作流</div>
              {WORKFLOW_ACTIONS.map(({ key, name, label, tone }) => (
                <button
                  key={key}
                  type="button"
                  className="dropdown-item"
                  onClick={() => triggerAction(() => runWorkflow(key, name))}
                >
                  <div className="item-label">
                    <Zap size={14} className={WORKFLOW_TONE_CLASSES[tone] || "text-amber-500"} />
                    <span>{label}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 4. 窗口 (Window) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "window" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("window")}
            onMouseEnter={() => handleMenuMouseEnter("window")}
          >
            窗口
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
                  <span>{isFullscreen ? "退出全屏模式" : "进入全屏模式"}</span>
                </div>
                <span className="shortcut-tag">F11</span>
              </button>
            </div>
          )}
        </div>

        {/* 5. 帮助 (Help) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "help" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("help")}
            onMouseEnter={() => handleMenuMouseEnter("help")}
          >
            帮助
          </button>
          {activeMenu === "help" && (
            <div className="menubar-dropdown animate-in">
              <button
                type="button"
                className="dropdown-item"
                onClick={() => triggerAction(() => setShowAbout(true))}
              >
                <div className="item-label">
                  <Info size={14} className="text-sky-500" />
                  <span>关于 MorningBrief 个人助手...</span>
                </div>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Spacer for Drag Region */}
      <div className="menubar-drag-spacer" data-tauri-drag-region />

      {/* Current Workspace Quick Indicator */}
      <div className="menubar-status-indicator" data-tauri-drag-region>
        <span className="status-ping" />
        <span className="status-text truncate">
          {workspace?.name ? `${workspace.name}` : "本地离线工作区"}
        </span>
      </div>

      {/* Native Window Controls on the far right */}
      <WindowControls />

      {/* About Modal */}
      {showAbout && (
        <div className="about-modal-backdrop animate-fade-in" onClick={() => setShowAbout(false)}>
          <div className="about-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="about-modal-header">
              <div className="about-logo-box">
                <LayoutDashboard size={28} className="text-white" />
              </div>
              <h3>MorningBrief 个人助手</h3>
              <span className="about-version-badge">Core v0.2.0 • 离线优先</span>
            </div>

            <div className="about-modal-content">
              <p className="about-tagline">
                聚焦个人日程安排、待办追踪与行动留痕闭环。
              </p>
              <div className="about-feature-list">
                <div className="about-feat-item">
                  <CheckCircle2 size={15} className="text-emerald-500" />
                  <span>待办与日程：自然语言提取候选，确认后落盘</span>
                </div>
                <div className="about-feat-item">
                  <CheckCircle2 size={15} className="text-emerald-500" />
                  <span>单一事实源：SQLite 结构化事实与审计记录</span>
                </div>
                <div className="about-feat-item">
                  <CheckCircle2 size={15} className="text-emerald-500" />
                  <span>可选外部同步：按需连接飞书任务与日历</span>
                </div>
              </div>
            </div>

            <div className="about-modal-footer">
              <button
                type="button"
                className="primary compact"
                onClick={() => setShowAbout(false)}
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
