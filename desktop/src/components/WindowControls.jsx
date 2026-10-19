import React, { useEffect, useState } from "react";
import { Minus, Square, X } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";

export default function WindowControls() {
  const [maximized, setMaximized] = useState(false);
  const isDesktop = Boolean(window.__TAURI_INTERNALS__);

  useEffect(() => {
    if (!isDesktop) return undefined;
    const appWindow = getCurrentWindow();
    const refresh = () => appWindow.isMaximized().then(setMaximized).catch(() => {});
    refresh();
    let unlisten;
    appWindow.onResized(refresh).then((cleanup) => {
      unlisten = cleanup;
    });
    return () => unlisten?.();
  }, [isDesktop]);

  if (!isDesktop) return null;

  const appWindow = getCurrentWindow();
  const toggleMaximize = async () => {
    await appWindow.toggleMaximize();
    setMaximized(await appWindow.isMaximized());
  };

  return (
    <div className="window-controls" aria-label="窗口控制">
      <button type="button" onClick={() => appWindow.minimize()} aria-label="最小化">
        <Minus size={15} />
      </button>
      <button type="button" onClick={toggleMaximize} aria-label={maximized ? "还原" : "最大化"}>
        <Square size={maximized ? 13 : 12} className={maximized ? "is-restored-icon" : ""} />
      </button>
      <button type="button" className="window-close" onClick={() => appWindow.close()} aria-label="关闭">
        <X size={16} />
      </button>
    </div>
  );
}
