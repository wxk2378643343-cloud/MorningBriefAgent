import React, { useEffect } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import {
  FileText,
  PencilLine,
  Save,
  Trash2,
  X,
} from "lucide-react";

function FileTabs({ tabs, selected, files, onSelect, onClose }) {
  return (
    <div className="editor-tabs" role="tablist" aria-label="已打开文件">
      {tabs.map((path) => {
        const file = files.find((item) => item.relativePath === path);
        if (!file) return null;
        return (
          <button
            className={`editor-tab ${path === selected ? "active" : ""}`}
            key={path}
            onClick={() => onSelect(path)}
            role="tab"
            type="button"
          >
            <FileText size={14} />
            <span>{file.name}</span>
            <X
              aria-label={`关闭 ${file.name}`}
              className="editor-tab-close"
              onClick={(event) => {
                event.stopPropagation();
                onClose(path);
              }}
              size={13}
            />
          </button>
        );
      })}
    </div>
  );
}

export default function FileEditorPane({
  file,
  files,
  tabs,
  selected,
  content,
  binaryUrl,
  editing,
  saving,
  message,
  onSelect,
  onClose,
  onToggleEdit,
  onChange,
  onSave,
  onDelete,
}) {
  useEffect(() => {
    const saveWithShortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (editing && !saving) onSave();
      }
    };
    window.addEventListener("keydown", saveWithShortcut);
    return () => window.removeEventListener("keydown", saveWithShortcut);
  }, [editing, onSave, saving]);

  if (!file) {
    return (
      <section className="editor-empty">
        <FileText size={30} />
        <h2>打开一个文件开始</h2>
        <p>从左侧文件树选择你的本地 Markdown、日志或数据文件。</p>
      </section>
    );
  }

  const editable = file.type === "markdown";
  return (
    <section className="file-editor">
      <FileTabs
        files={files}
        onClose={onClose}
        onSelect={onSelect}
        selected={selected}
        tabs={tabs}
      />
      <header className="editor-header">
        <div>
          <div className="editor-breadcrumb">{file.relativePath}</div>
          <h2>{file.name}</h2>
        </div>
        {editable && (
          <div className="editor-actions">
            <button
              className={`editor-action ${editing ? "active" : ""}`}
              onClick={onToggleEdit}
              type="button"
            >
              <PencilLine size={15} />
              {editing ? "编辑中" : "编辑"}
            </button>
            <button
              className="editor-action primary"
              disabled={!editing || saving}
              onClick={onSave}
              type="button"
            >
              <Save size={15} />
              {saving ? "保存中" : "保存"}
            </button>
            <button className="editor-action danger" onClick={onDelete} type="button">
              <Trash2 size={15} />
              删除
            </button>
          </div>
        )}
      </header>
      {message && <div className="editor-message">{message}</div>}
      <div className="editor-content">
        {editing && editable ? (
          <CodeMirror
            className="markdown-code-editor"
            extensions={[markdown()]}
            height="100%"
            onChange={onChange}
            value={content ?? ""}
          />
        ) : content !== null ? (
          <pre className="markdown-preview">{content}</pre>
        ) : binaryUrl && file.type === "image" ? (
          <img className="binary-preview" src={binaryUrl} alt={file.name} />
        ) : binaryUrl && file.type === "pdf" ? (
          <iframe className="binary-preview pdf-preview" src={binaryUrl} title={file.name} />
        ) : (
          <div className="unsupported-file">此文件类型暂不支持内嵌预览。</div>
        )}
      </div>
      <footer className="editor-status">
        <span>{editing ? "编辑模式" : "只读预览"}</span>
        <span>{editing ? "Ctrl + S 保存" : file.type}</span>
      </footer>
    </section>
  );
}
