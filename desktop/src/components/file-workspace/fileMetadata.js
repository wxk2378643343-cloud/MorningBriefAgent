const SYNC_STATUS_LABELS = {
  synced: "已同步",
  stale: "待重新扫描",
  missing: "文件缺失",
  unknown: "状态未知",
};

export function normalizeWorkspaceFile(item) {
  const source = item?.source ?? {};
  const syncStatus = Object.hasOwn(SYNC_STATUS_LABELS, item?.sync_status)
    ? item.sync_status
    : "unknown";
  return {
    name: item?.file_name || item?.relative_path || "未命名文件",
    type: String(item?.file_type || "file").toLowerCase(),
    relativePath: item?.relative_path || "",
    updatedAt: item?.updated_at || null,
    sourceName: source.name || "未知来源",
    sourceType: source.type || "unknown",
    syncStatus,
  };
}

export function formatFileUpdatedAt(value) {
  if (!value) return "更新时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "更新时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function syncStatusLabel(status) {
  return SYNC_STATUS_LABELS[status] ?? SYNC_STATUS_LABELS.unknown;
}
