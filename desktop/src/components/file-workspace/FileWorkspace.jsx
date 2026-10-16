import React, { useEffect, useMemo, useState } from "react";
import { FilePlus2, FolderOpen, RefreshCw } from "lucide-react";
import { apiUrl, fetchJson } from "../../localApi";
import FileTree from "../FileTree";
import FileEditorPane from "./FileEditorPane";
import "./fileWorkspace.css";

const TEXT_TYPES = new Set(["markdown", "json", "log", "file"]);

function asFile(item) {
  return {
    name: item.file_name,
    type: String(item.file_type || "").toLowerCase(),
    relativePath: item.relative_path,
    modifiedAt: item.modified_at,
  };
}

export default function FileWorkspace({ serviceState }) {
  const [source, setSource] = useState(null);
  const [files, setFiles] = useState([]);
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
        `/api/v1/files?source_id=${encodeURIComponent(nextSource.id)}`,
      );
      const nextFiles = (payload.files ?? []).map(asFile);
      setSource(nextSource);
      setFiles(nextFiles);
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
    if (!window.confirm(`确定删除“${selectedFile.name}”吗？此操作无法撤销。`)) return;
    try {
      await fetchJson("/api/v1/files", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: source.id, path: selectedFile.relativePath }),
      });
      setTabs((current) => current.filter((path) => path !== selectedFile.relativePath));
      setSelected("");
      setContent(null);
      setMessage("文件已删除。");
      await loadFiles(false);
    } catch {
      setMessage("删除失败，文件仍保留在本地。");
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

  const binaryUrl = binaryPreview
    ? `data:${binaryPreview.content_type};base64,${binaryPreview.content_base64}`
    : null;

  return (
    <section className="desktop-file-workspace">
      <header className="workspace-toolbar">
        <div className="workspace-location">
          <FolderOpen size={16} />
          <span>{source?.name ?? "本地工作区"}</span>
          <small>{source?.root_path ?? "正在载入…"}</small>
        </div>
        <div className="workspace-toolbar-actions">
          <button onClick={createFile} type="button"><FilePlus2 size={15} />新建</button>
          <button onClick={() => loadFiles()} type="button"><RefreshCw size={15} />刷新</button>
        </div>
      </header>
      <div className="desktop-file-layout">
        <aside className="explorer-panel">
          <div className="explorer-title">
            <span>EXPLORER</span>
            <small>{files.length} 个文件</small>
          </div>
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
