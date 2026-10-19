import React from "react";
import {
  Bot,
  Database,
  FolderOpen,
  LayoutDashboard,
  Settings2,
  Workflow,
} from "lucide-react";
import DesktopMenuBar from "./DesktopMenuBar";
import { DESKTOP_SECTIONS } from "./desktopNavigation";

const NAVIGATION_ICONS = {
  dashboard: LayoutDashboard,
  files: FolderOpen,
  workflow: Workflow,
  database: Database,
  agent: Bot,
};

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
  onQuickRun,
  children,
}) {
  return (
    <div className="app-shell-frame">
      <header className="shell-top-chrome" data-tauri-drag-region>
        <DesktopMenuBar
          onNavigate={onNavigate}
          activeSection={activeSection}
          workspace={workspace}
          onQuickRun={onQuickRun}
        />
      </header>

      <div className="shell-workspace-body">
        <aside className="sidebar">
          <div className="workspace-label">本地工作台</div>
          <nav>
            {DESKTOP_SECTIONS.map(({ key, icon }) => (
              <NavItem
                key={key}
                icon={NAVIGATION_ICONS[icon]}
                label={key}
                active={activeSection === key}
                onClick={() => onNavigate(key)}
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
