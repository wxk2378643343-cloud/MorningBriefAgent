import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import SettingsPage from "./SettingsPage";

describe("SettingsPage", () => {
  it("renders safely before onboarding status has loaded", () => {
    const markup = renderToStaticMarkup(
      <SettingsPage status={null} onOpenSetup={vi.fn()} onReconfigure={vi.fn()} />,
    );

    expect(markup).toContain("设置");
    expect(markup).toContain("0/4");
    expect(markup).toContain("这项配置还没有完成");
  });

  it("renders completed and skipped status summaries", () => {
    const markup = renderToStaticMarkup(
      <SettingsPage
        status={{
          completed_count: 2,
          skipped_count: 1,
          steps: [
            { step_key: "workspace", status: "completed" },
            { step_key: "provider", status: "skipped" },
          ],
        }}
        onOpenSetup={vi.fn()}
        onReconfigure={vi.fn()}
      />,
    );

    expect(markup).toContain("2/4");
    expect(markup).toContain("1 项稍后配置");
    expect(markup).toContain("配置已生效");
  });
});
