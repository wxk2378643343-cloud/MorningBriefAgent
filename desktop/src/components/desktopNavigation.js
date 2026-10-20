export const DESKTOP_SECTIONS = [
  { key: "工作台", label: "工作台首页", shortcut: "Ctrl+1", icon: "dashboard" },
  { key: "文件与数据", label: "知识库与文件工作台", shortcut: "Ctrl+2", icon: "files" },
  { key: "工作流", label: "工作流调度中心", shortcut: "Ctrl+3", icon: "workflow" },
  { key: "数据库", label: "SQLite 数据库中心", shortcut: "Ctrl+4", icon: "database" },
  { key: "Agent 运行", label: "Agent 运行时监控", shortcut: "Ctrl+5", icon: "agent" },
];

export const SETTINGS_SECTION = {
  key: "设置",
  label: "系统设置与配置中心",
  shortcut: "Ctrl+,",
  icon: "settings",
};

export const WORKFLOW_ACTIONS = [
  { key: "morning_brief", name: "晨间简报与指数资讯", label: "立即执行：晨间新闻行情简报", tone: "amber" },
  { key: "evening_review", name: "夜间智能复盘与健康报告", label: "立即执行：夜间智能复盘", tone: "indigo" },
  { key: "todo_sync", name: "待办归档与飞书多维表格同步", label: "立即执行：待办事项双向同步", tone: "emerald" },
];
