export const DESKTOP_SECTIONS = [
  { key: "今天", label: "今日日程与待办", shortcut: "Ctrl+1", icon: "today" },
  { key: "待办", label: "待办事项管理", shortcut: "Ctrl+2", icon: "todos" },
  { key: "日程", label: "日历日程概览", shortcut: "Ctrl+3", icon: "schedule" },
  { key: "复盘", label: "每日/每周行动复盘", shortcut: "Ctrl+4", icon: "review" },
];

export const SETTINGS_SECTION = {
  key: "设置",
  label: "系统设置与配置中心",
  shortcut: "Ctrl+,",
  icon: "settings",
};

export const WORKFLOW_ACTIONS = [
  { key: "todo-morning", name: "早间行动与日程", label: "立即执行：早间计划与日程派发", tone: "amber" },
  { key: "todo-evening", name: "晚间复盘总结", label: "立即执行：晚间行动复盘与归档", tone: "indigo" },
];
