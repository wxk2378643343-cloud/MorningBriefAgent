import { describe, expect, it } from "vitest";
import {
  formatFileUpdatedAt,
  normalizeWorkspaceFile,
  syncStatusLabel,
} from "./fileMetadata";

describe("file metadata presentation", () => {
  it("keeps source, update time and sync status from the API contract", () => {
    const file = normalizeWorkspaceFile({
      file_name: "today.md",
      file_type: "markdown",
      relative_path: "notes/today.md",
      updated_at: "2027-01-15T08:00:00.000Z",
      source: { name: "知识库", type: "obsidian" },
      sync_status: "synced",
    });

    expect(file).toMatchObject({
      name: "today.md",
      relativePath: "notes/today.md",
      sourceName: "知识库",
      sourceType: "obsidian",
      syncStatus: "synced",
    });
    expect(formatFileUpdatedAt(file.updatedAt)).not.toBe("更新时间未知");
    expect(syncStatusLabel(file.syncStatus)).toBe("已同步");
  });

  it("shows explicit fallbacks for incomplete metadata", () => {
    const file = normalizeWorkspaceFile({
      relative_path: "legacy.md",
      sync_status: "unexpected",
    });

    expect(file.sourceName).toBe("未知来源");
    expect(file.syncStatus).toBe("unknown");
    expect(formatFileUpdatedAt(file.updatedAt)).toBe("更新时间未知");
    expect(formatFileUpdatedAt("not-a-date")).toBe("更新时间未知");
    expect(syncStatusLabel(file.syncStatus)).toBe("状态未知");
  });
});
