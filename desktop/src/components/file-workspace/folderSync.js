export function folderSyncRequest(sourceId, targetRoot, apply = false) {
  return {
    path: "/api/v1/folder-sync",
    options: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: sourceId,
        target_root: String(targetRoot ?? "").trim(),
        apply,
      }),
    },
  };
}

export function folderSyncPreviewMessage(sync) {
  const added = sync?.added?.length ?? 0;
  const conflicts = sync?.conflicts?.length ?? 0;
  if (added) {
    return `将复制 ${added} 个新文件。${conflicts ? `另有 ${conflicts} 个冲突会保留目标版本。` : ""}`;
  }
  return conflicts
    ? `没有可复制的新文件；检测到 ${conflicts} 个冲突，均未覆盖。`
    : "目标文件夹已是最新状态。";
}
