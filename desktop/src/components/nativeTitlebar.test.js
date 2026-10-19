import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("native title bar", () => {
  it("keeps window dragging enabled in both UI and Tauri capabilities", () => {
    const menuSource = readFileSync(new URL("./DesktopMenuBar.jsx", import.meta.url), "utf8");
    const capabilities = JSON.parse(
      readFileSync(new URL("../../src-tauri/capabilities/default.json", import.meta.url), "utf8"),
    );

    expect(menuSource).toContain("data-tauri-drag-region");
    expect(menuSource).toContain("getCurrentWindow().startDragging()");
    expect(capabilities.permissions).toContain("core:window:allow-start-dragging");
  });
});
