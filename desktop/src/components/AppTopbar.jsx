import React, { useState } from "react";
import {
  Search,
  FolderOpen,
  Zap,
  Command,
  ChevronRight,
} from "lucide-react";

export default function AppTopbar({
  eyebrow,
  title,
  activeSection,
  onNavigate,
  workspace,
  onQuickRun,
}) {
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const workspaceName = workspace?.name || "本地知识库 (wxk2378643343-cloud)";
  const handleSearchSubmit = (e) => {
    if (e.key === "Enter" && searchQuery.trim()) {
      if (onNavigate) {
        onNavigate("文件与数据");
      }
    }
  };

  return (
    <header className="desktop-app-topbar">
      {/* Left: Module Breadcrumb & Active Workspace Tag */}
      <div className="topbar-left-zone">
        <div className="topbar-breadcrumb">
          <span className="topbar-eyebrow">{eyebrow || "LOCAL WORKBENCH"}</span>
          <div className="topbar-title-wrap">
            <h1 className="topbar-main-title">{title}</h1>
            {workspace && (
              <button
                type="button"
                className="topbar-workspace-chip"
                onClick={() => onNavigate && onNavigate("文件与数据")}
                title={`当前挂载知识库: ${workspace.root_path || workspaceName}`}
              >
                <FolderOpen size={12} className="text-indigo-500" />
                <span className="truncate max-w-[180px]">{workspace.name || "知识库已挂载"}</span>
                <ChevronRight size={10} className="text-slate-400" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Center: Universal Command Search Capsule (Raycast / Linear style) */}
      <div className="topbar-center-zone">
        <div className={`topbar-search-capsule ${searchFocused ? "is-focused" : ""}`}>
          <Search size={14} className="search-icon" />
          <input
            type="text"
            placeholder="搜索知识库、工作流或业务记录... (Enter)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            onKeyDown={handleSearchSubmit}
            className="search-input"
          />
          <div className="shortcut-badge">
            <Command size={10} />
            <span>K</span>
          </div>
        </div>
      </div>

      {/* Right: Desktop Controls & Live Service Indicators (No settings button) */}
      <div className="topbar-right-zone">
        {/* Quick Run Workflow Button */}
        <button
          type="button"
          className="topbar-action-icon-btn"
          onClick={() => {
            if (onQuickRun) onQuickRun();
            else if (onNavigate) onNavigate("工作流");
          }}
          title="一键唤醒工作流调度中心"
        >
          <Zap size={15} className="text-amber-500" />
        </button>
      </div>
    </header>
  );
}
