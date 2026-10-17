import { expect, test } from "vitest";
import { folderSyncPreviewMessage, folderSyncRequest } from "./folderSync";

test("builds a preview-first folder sync request", () => {
  const request = folderSyncRequest("source-1", " D:\\KnowledgeBackup ");
  expect(request.path).toBe("/api/v1/folder-sync");
  expect(JSON.parse(request.options.body)).toEqual({
    source_id: "source-1",
    target_root: "D:\\KnowledgeBackup",
    apply: false,
  });
});

test("explains additions and non-overwriting conflicts", () => {
  expect(
    folderSyncPreviewMessage({
      added: ["new.md"],
      conflicts: ["existing.md"],
    }),
  ).toMatch(/1 个冲突会保留目标版本/);
  expect(folderSyncPreviewMessage({ added: [], conflicts: [] })).toMatch(
    /最新状态/,
  );
});
