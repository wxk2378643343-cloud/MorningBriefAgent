import React, { useEffect, useMemo, useState } from "react";
import {
  Clock3,
  FolderSync,
  FilePlus2,
  FolderOpen,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { fetchJson } from "../../localApi";
import FileTree from "../FileTree";
import FileEditorPane from "./FileEditorPane";
import {
  lifecycleErrorMessage,
  lifecycleRequest,
  renameDestination,
} from "./fileLifecycle";
import {
  formatFileUpdatedAt,
  normalizeWorkspaceFile,
} from "./fileMetadata";
import { folderSyncPreviewMessage, folderSyncRequest } from "./folderSync";
import "./fileWorkspace.css";

const TEXT_TYPES = new Set(["markdown", "json", "log", "file"]);

export default function FileWorkspace({ serviceState }) {
  const [source, setSource] = useState(null);
  const [files, setFiles] = useState([]);
  const [recoveries, setRecoveries] = useState([]);
  const [selected, setSelected] = useState("");
  const [tabs, setTabs] = useState([]);
  const [content, setContent] = useState(null);
  const [binaryPreview, setBinaryPreview] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [live, setLive] = useState(false);

  const selectedFile = useMemo(
    () => files.find((file) => file.relativePath === selected),
    [files, selected],
  );

  const loadFiles = async (keepSelected = true) => {
    try {
      const sources = await fetchJson("/api/v1/data-sources");
      const nextSource = sources.sources?.find(
        (item) => item.id === sources.active_source_id,
      ) ?? sources.sources?.[0];
      if (!nextSource) throw new Error("no_source");
      const payload = await fetchJson(
        `/api/v1/files?source_id=${encodeURIComponent(nextSource.id)}&sort=recent`,
      );
      const recoveryPayload = await fetchJson(
        `/api/v1/file-recoveries?source_id=${encodeURIComponent(nextSource.id)}`,
      ).catch(() => ({ recoveries: [] }));
      const nextFiles = (payload.files ?? []).map(normalizeWorkspaceFile);
      setSource(nextSource);
      setFiles(nextFiles);
      setRecoveries(recoveryPayload.recoveries ?? []);
      setLive(true);
      setSelected((current) => {
        if (keepSelected && nextFiles.some((file) => file.relativePath === current)) return current;
        return nextFiles[0]?.relativePath ?? "";
      });
    } catch {
      setLive(false);
      setMessage("无法读取本地工作区，请确认本地服务和工作区均已启动。");
    }
  };

  useEffect(() => {
    loadFiles(false);
  }, []);

  useEffect(() => {
    if (!source || !selectedFile) {
      setContent(null);
      return;
    }
    setEditing(false);
    setMessage("");
    const path = encodeURIComponent(selectedFile.relativePath);
    if (!TEXT_TYPES.has(selectedFile.type)) {
      setContent(null);
      if (["image", "pdf"].includes(selectedFile.type)) {
        fetchJson(`/api/v1/file-binary?source_id=${encodeURIComponent(source.id)}&path=${path}`)
          .then((payload) => setBinaryPreview(payload.file ?? null))
          .catch(() => setBinaryPreview(null));
      } else {
        setBinaryPreview(null);
      }
      return;
    }
    setBinaryPreview(null);
    fetchJson(`/api/v1/files?source_id=${encodeURIComponent(source.id)}&path=${path}`)
      .then((payload) => {
        const value = payload.file?.content ?? "";
        setContent(value);
        setDraft(value);
      })
      .catch(() => {
        setContent(null);
        setMessage("文件内容读取失败。");
      });
  }, [source, selectedFile]);

  const openFile = (path) => {
    setTabs((current) => (current.includes(path) ? current : [...current, path]));
    setSelected(path);
  };

  const closeFile = (path) => {
    setTabs((current) => {
      const next = current.filter((item) => item !== path);
      if (path === selected) setSelected(next.at(-1) ?? "");
      return next;
    });
  };

  const saveFile = async () => {
    if (!source || !selectedFile) return;
    setSaving(true);
    setMessage("");
    try {
      await fetchJson("/api/v1/files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: source.id,
          path: selectedFile.relativePath,
          content: draft,
        }),
      });
      setContent(draft);
      setEditing(false);
      setMessage("已保存到本地工作区。");
      await loadFiles();
    } catch {
      setMessage("保存失败，原文件没有被修改。");
    } finally {
      setSaving(false);
    }
  };

  const deleteSelectedFile = async () => {
    if (!source || !selectedFile) return;
    if (!window.confirm(`确定删除“${selectedFile.name}”吗？删除后可从本地回收记录恢复。`)) return;
    try {
      const payload = await fetchJson("/api/v1/files", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: source.id,
          path: selectedFile.relativePath,
          request_id: globalThis.crypto?.randomUUID?.() ?? `delete-${Date.now()}`,
        }),
      });
      setTabs((current) => current.filter((path) => path !== selectedFile.relativePath));
      setSelected("");
      setContent(null);
      setRecoveries((current) => [payload.recovery, ...current]);
      setMessage("文件已移入本地回收区，可使用“恢复最近删除”撤销。");
      await loadFiles(false);
    } catch {
      setMessage("删除失败，文件仍保留在本地。");
    }
  };

  const restoreLatestFile = async () => {
    if (!source || !recoveries[0]) return;
    const recovery = recoveries[0];
    try {
      await fetchJson("/api/v1/files/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: source.id,
          operation_id: recovery.id,
        }),
      });
      await loadFiles(false);
      openFile(recovery.relative_path);
      setMessage(`已恢复 ${recovery.file_name ?? recovery.relative_path}。`);
    } catch (error) {
      setMessage(
        error.message === "restore_target_exists"
          ? "恢复失败：原路径已有文件，未覆盖现有内容。"
          : "恢复失败，回收记录仍保留。",
      );
    }
  };

  const createFile = async () => {
    if (!source) return;
    const path = window.prompt("Markdown 相对路径，例如：05-知识库/新笔记.md");
    if (!path) return;
    try {
      await fetchJson("/api/v1/files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: source.id, path, content: "# 新笔记\n\n" }),
      });
      await loadFiles(false);
      openFile(path);
      setEditing(true);
      setMessage("已创建新文件。");
    } catch {
      setMessage("创建失败：仅允许在工作区内创建 Markdown 或文本文件。");
    }
  };

  const syncToFolder = async () => {
    if (!source) return;
    const targetRoot = window.prompt("同步到本地文件夹（请输入完整路径）");
    if (!targetRoot?.trim()) return;
    setMessage("正在检查目标文件夹…");
    try {
      const previewRequest = folderSyncRequest(source.id, targetRoot, false);
      const preview = await fetchJson(
        previewRequest.path,
        previewRequest.options,
      );
      const added = preview.sync?.added?.length ?? 0;
      if (!added) {
        setMessage(folderSyncPreviewMessage(preview.sync));
        return;
      }
      const confirmed = window.confirm(
        `${folderSyncPreviewMessage(preview.sync)}继续吗？`,
      );
      if (!confirmed) {
        setMessage("已取消同步，目标文件夹没有改变。");
        return;
      }
      const applyRequest = folderSyncRequest(source.id, targetRoot, true);
      const applied = await fetchJson(applyRequest.path, applyRequest.options);
      setMessage(
        `已同步 ${applied.sync?.copied?.length ?? 0} 个文件；冲突文件未覆盖。`,
      );
    } catch (error) {
      setMessage(`文件夹同步失败：${error.message}`);
    }
  };

  const relocateSelectedFile = async (destinationPath, successMessage) => {
    if (!source || !selectedFile || !destinationPath) return;
    const previousPath = selectedFile.relativePath;
    setMessage("");
    try {
      const request = lifecycleRequest(source.id, previousPath, destinationPath);
      const payload = await fetchJson(request.path, request.options);
      const nextPath = payload.destination_path;
      setTabs((current) => current.map((path) => (
        path === previousPath ? nextPath : path
      )));
      setSelected(nextPath);
      setEditing(false);
      setMessage(successMessage);
      await loadFiles();
    } catch (error) {
      setMessage(lifecycleErrorMessage(error.message));
    }
  };

  const renameSelectedFile = async () => {
    if (!selectedFile) return;
    const nextName = window.prompt("新的 Markdown 文件名", selectedFile.name);
    if (nextName === null) return;
    const destinationPath = renameDestination(selectedFile.relativePath, nextName);
    if (!destinationPath) {
      setMessage("请输入不包含路径分隔符的文件名。");
      return;
    }
    await relocateSelectedFile(destinationPath, "文件已重命名。");
  };

  const moveSelectedFile = async () => {
    if (!selectedFile) return;
    const destinationPath = window.prompt(
      "移动到知识库内的相对路径",
      selectedFile.relativePath,
    );
    if (destinationPath === null) return;
    await relocateSelectedFile(destinationPath.trim(), "文件已移动。");
  };

  const binaryUrl = binaryPreview
    ? `data:${binaryPreview.content_type};base64,${binaryPreview.content_base64}`
    : null;

  return (
    <section className="desktop-file-workspace">
      <header className="workspace-toolbar">
        <div className="workspace-location">
          <FolderOpen size={16} />
          <span>知识库</span>
          <small>{source?.root_path ?? "正在载入…"}</small>
        </div>
        <div className="workspace-toolbar-actions">
          <button onClick={createFile} type="button"><FilePlus2 size={15} />新建</button>
          <button onClick={syncToFolder} type="button">
            <FolderSync size={15} />同步到文件夹
          </button>
          <button disabled={!recoveries.length} onClick={restoreLatestFile} type="button">
            <RotateCcw size={15} />恢复最近删除
          </button>
          <button onClick={() => loadFiles()} type="button"><RefreshCw size={15} />刷新</button>
        </div>
      </header>
      <div className="desktop-file-layout">
        <aside className="explorer-panel">
          <div className="explorer-title">
            <span>EXPLORER</span>
            <small>{files.length} 个文件</small>
          </div>
          <div className="recent-files" aria-label="最近修改">
            <div className="recent-files-title">
              <span>最近修改</span>
              <Clock3 size={12} />
            </div>
            {files.slice(0, 5).map((file) => (
              <button
                className={selected === file.relativePath ? "active" : ""}
                key={file.relativePath}
                onClick={() => openFile(file.relativePath)}
                type="button"
              >
                <span>{file.name}</span>
                <small>{formatFileUpdatedAt(file.updatedAt)}</small>
              </button>
            ))}
            {!files.length && <p>暂无已索引文件</p>}
          </div>
          <div className="all-files-label">全部文件</div>
          <FileTree files={files.map((file) => [file.name, file.type, "", "", file.relativePath])} selected={selected} onSelect={openFile} />
          <div className="explorer-status">
            <span className={`local-indicator ${live && serviceState === "ready" ? "online" : ""}`} />
            {live && serviceState === "ready" ? "本地工作区已连接" : "本地服务未连接"}
          </div>
        </aside>
        <FileEditorPane
          binaryUrl={binaryUrl}
          content={editing ? draft : content}
          editing={editing}
          file={selectedFile}
          files={files}
          message={message}
          onChange={setDraft}
          onClose={closeFile}
          onDelete={deleteSelectedFile}
          onMove={moveSelectedFile}
          onRename={renameSelectedFile}
          onSave={saveFile}
          onSelect={openFile}
          onToggleEdit={() => setEditing((value) => !value)}
          saving={saving}
          selected={selected}
          tabs={tabs}
        />
      </div>
    </section>
  );
}
