import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const UI_FILES = [
  new URL("../main.jsx", import.meta.url),
  new URL("./AppTopbar.jsx", import.meta.url),
  new URL("./DesktopMenuBar.jsx", import.meta.url),
  new URL("../pages/DatabasePage.jsx", import.meta.url),
];

describe("truthful desktop status copy", () => {
  it("does not present unverified runtime claims", () => {
    const source = UI_FILES.map((file) => readFileSync(file, "utf8")).join("\n");
    const unsupportedClaims = [
      "飞书守护就绪",
      "飞书长连接守护进程活跃",
      "7 个专属智能体就绪",
      "100% 局域网离线私有",
      "零外网泄露",
      "SQLite 活跃运行中",
    ];

    for (const claim of unsupportedClaims) {
      expect(source).not.toContain(claim);
    }
  });
});
