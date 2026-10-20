import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("file workspace startup", () => {
  it("does not discard files when optional recovery history is unavailable", () => {
    const source = readFileSync(new URL("./FileWorkspace.jsx", import.meta.url), "utf8");

    expect(source).toContain("fetchJson(`/api/v1/files?");
    expect(source).toContain(".catch(() => ({ recoveries: [] }))");
    expect(source).not.toContain("Promise.all([");
  });
});
