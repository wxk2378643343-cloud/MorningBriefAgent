export function canRelocateFile(file) {
  return file?.type === "markdown";
}

export function lifecycleRequest(sourceId, path, destinationPath) {
  return {
    path: "/api/v1/files",
    options: {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: sourceId,
        path,
        destination_path: destinationPath,
      }),
    },
  };
}

export function renameDestination(relativePath, nextName) {
  const normalizedPath = String(relativePath ?? "").replaceAll("\\", "/");
  const normalizedName = String(nextName ?? "").trim();
  if (!normalizedName || normalizedName.includes("/") || normalizedName.includes("\\")) {
    return null;
  }
  const separator = normalizedPath.lastIndexOf("/");
  return separator < 0
    ? normalizedName
    : `${normalizedPath.slice(0, separator)}/${normalizedName}`;
}

export function lifecycleErrorMessage(code) {
  return {
    cross_source_move_not_allowed: "不能把文件移动到其他数据源。",
    destination_exists: "目标位置已有同名文件，未执行覆盖。",
    destination_same_as_source: "目标路径与当前路径相同。",
    file_not_found: "原文件不存在，请刷新后重试。",
    invalid_relative_path: "目标必须是知识库内的相对路径。",
    only_markdown_files_can_be_moved: "仅支持重命名或移动 Markdown 文件。",
  }[code] ?? "操作失败，原文件和索引已保持不变。";
}
