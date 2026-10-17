import { expect, test } from "vitest";
import {
  canRelocateFile,
  lifecycleErrorMessage,
  lifecycleRequest,
  renameDestination,
} from "./fileLifecycle.js";

test("offers lifecycle actions only for Markdown files", () => {
  expect(canRelocateFile({ type: "markdown" })).toBe(true);
  expect(canRelocateFile({ type: "image" })).toBe(false);
  expect(canRelocateFile(null)).toBe(false);
});

test("builds a same-folder destination for rename", () => {
  expect(renameDestination("notes/today.md", "tomorrow.md")).toBe(
    "notes/tomorrow.md",
  );
  expect(renameDestination("today.md", "tomorrow.md")).toBe("tomorrow.md");
  expect(renameDestination("notes/today.md", "../escape.md")).toBeNull();
});

test("explains that destination conflicts never overwrite files", () => {
  expect(lifecycleErrorMessage("destination_exists")).toMatch(/未执行覆盖/);
  expect(lifecycleErrorMessage("invalid_relative_path")).toMatch(/相对路径/);
});

test("submits a same-source PATCH command to the local API", () => {
  const request = lifecycleRequest(
    "source-1",
    "notes/today.md",
    "archive/today.md",
  );
  expect(request.path).toBe("/api/v1/files");
  expect(request.options.method).toBe("PATCH");
  expect(JSON.parse(request.options.body)).toEqual({
    source_id: "source-1",
    path: "notes/today.md",
    destination_path: "archive/today.md",
  });
});
