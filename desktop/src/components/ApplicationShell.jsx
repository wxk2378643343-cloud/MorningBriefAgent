import React from "react";
import {
  Bot,
  Database,
  FolderOpen,
  LayoutDashboard,
  Settings2,
  Sparkles,
  Workflow,
} from "lucide-react";
import DesktopMenuBar from "./DesktopMenuBar";

const NAVIGATION = [
  ["工作台", LayoutDashboard],
  ["文件与数据", FolderOpen],
  ["工作流", Workflow],
  ["数据库", Database],
  ["Agent 运行", Bot],
];

function NavItem({ icon: Icon, label, active, onClick }) {
  return (
    <button
      type="button"
      className={`nav-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span><Icon size={17} /></span>
      {label}
    </button>
  );
}

export default function ApplicationShell({
  activeSection,
  onNavigate,
  workspace,
  serviceState,
  serviceLabel,
  onQuickRun,
  children,
}) {
  return (
    <div className="app-shell-frame">
      {/* 1. 应用最外层骨架顶梁：横贯 100vw 的原生桌面菜单栏 (架子上) */}
      <header className="shell-top-chrome">
        <DesktopMenuBar
          onNavigate={onNavigate}
          activeSection={activeSection}
          workspace={workspace}
          onQuickRun={onQuickRun}
          serviceState={serviceState}
          serviceLabel={serviceLabel}
        />
      </header>

      {/* 2. 应用骨架下部主体：左侧边栏 + 右侧主工作台 */}
      <div className="shell-workspace-body">
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-mark"><Sparkles size={17} /></span>
            <span>MorningBrief</span>
          </div>
          <div className="workspace-label">本地工作台</div>
          <nav>
            {NAVIGATION.map(([label, Icon]) => (
              <NavItem
                key={label}
                icon={Icon}
                label={label}
                active={activeSection === label}
                onClick={() => onNavigate(label)}
              />
            ))}
          </nav>
          <div className="sidebar-bottom">
            <NavItem
              icon={Settings2}
              label="设置"
              active={activeSection === "设置"}
              onClick={() => onNavigate("设置")}
            />
            <div className="local-only"><span /> 仅在本机运行</div>
          </div>
        </aside>

        {children}
      </div>
    </div>
  );
}
