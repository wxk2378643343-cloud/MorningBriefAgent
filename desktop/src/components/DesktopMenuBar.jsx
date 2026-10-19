import React, { useState, useEffect, useRef } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
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
  CheckCircle2,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import WindowControls from "./WindowControls";
import { DESKTOP_SECTIONS, SETTINGS_SECTION, WORKFLOW_ACTIONS } from "./desktopNavigation";

const MENU_ICONS = {
  dashboard: [LayoutDashboard, "text-sky-500"],
  files: [FolderOpen, "text-indigo-500"],
  workflow: [Workflow, "text-amber-500"],
  database: [Database, "text-emerald-500"],
  agent: [Bot, "text-purple-500"],
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

  const startNativeDrag = (event) => {
    if (
      event.button !== 0
      || event.target.closest("button, input, textarea, select, a, [role='menuitem']")
      || !window.__TAURI_INTERNALS__
    ) {
      return;
    }
    getCurrentWindow().startDragging().catch(() => {});
  };

  return (
    <>
      <nav
        className="desktop-native-menubar"
        ref={menuBarRef}
        aria-label="应用主菜单"
        data-tauri-drag-region
        onMouseDown={startNativeDrag}
      >
        {/* Brand App Badge */}
        <div className="menubar-brand" data-tauri-drag-region>
          <Sparkles size={13} className="text-amber-500" />
          <span className="font-semibold tracking-tight text-slate-800 text-[12px]" data-tauri-drag-region>
            MorningBrief
          </span>
        </div>

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
            视图
          </button>
          {activeMenu === "view" && (
            <div className="menubar-dropdown animate-in">
              {DESKTOP_SECTIONS.map(({ key, label, shortcut, icon }) => {
                const [Icon, iconClass] = MENU_ICONS[icon];
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
                const [Icon, iconClass] = MENU_ICONS[SETTINGS_SECTION.icon];
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

        {/* 3. 工作流 (Workflow / Run) */}
        <div className="menubar-item-wrap">
          <button
            type="button"
            className={`menubar-btn ${activeMenu === "workflow" ? "is-active" : ""}`}
            onClick={() => handleMenuClick("workflow")}
            onMouseEnter={() => handleMenuMouseEnter("workflow")}
          >
            工作流
          </button>
          {activeMenu === "workflow" && (
            <div className="menubar-dropdown animate-in">
              {WORKFLOW_ACTIONS.map(({ key, name, label, tone }) => (
                <button
                  key={key}
                  type="button"
                  className="dropdown-item"
                  onClick={() => triggerWorkflow(key, name)}
                >
                  <div className="item-label">
                    {key === "todo_sync"
                      ? <CheckCircle2 size={14} className={WORKFLOW_TONE_CLASSES[tone]} />
                      : <Zap size={14} className={WORKFLOW_TONE_CLASSES[tone]} />}
                    <span>{label}</span>
                  </div>
                </button>
              ))}
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
                  <span>{isFullscreen ? "退出全屏" : "切换全屏模式"}</span>
                </div>
                <span className="shortcut-tag">F11</span>
              </button>
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

        <WindowControls />
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
