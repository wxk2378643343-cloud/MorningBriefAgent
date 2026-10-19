import { describe, expect, it } from "vitest";
import { DESKTOP_SECTIONS, SETTINGS_SECTION, WORKFLOW_ACTIONS } from "./desktopNavigation";

describe("desktop navigation model", () => {
  it("keeps navigation destinations and shortcuts unique", () => {
    const sections = [...DESKTOP_SECTIONS, SETTINGS_SECTION];
    expect(new Set(sections.map(({ key }) => key)).size).toBe(sections.length);
    expect(new Set(sections.map(({ shortcut }) => shortcut)).size).toBe(sections.length);
  });

  it("keeps workflow actions addressable by a stable key", () => {
    expect(new Set(WORKFLOW_ACTIONS.map(({ key }) => key)).size).toBe(WORKFLOW_ACTIONS.length);
    expect(WORKFLOW_ACTIONS.every(({ key, name, label }) => key && name && label)).toBe(true);
  });
});
