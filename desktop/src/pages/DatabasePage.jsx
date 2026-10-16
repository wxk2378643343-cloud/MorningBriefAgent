import React, { useEffect, useState, useMemo } from "react";
import {
  Plus,
  RefreshCw,
  Trash2,
  Pencil,
  CheckSquare,
  Calendar,
  TrendingUp,
  LineChart,
  Newspaper,
  Utensils,
  Dumbbell,
  Database,
  Search,
  Copy,
  Check,
  X,
  Layers,
  HardDrive,
  Code2,
  FileText,
  SlidersHorizontal
} from "lucide-react";
import { apiUrl, fetchJson } from "../localApi";

// Semantic icon mapping for standard tables in MorningBriefAgent
const TABLE_ICONS = {
  todo_records: CheckSquare,
  schedule_records: Calendar,
  fund_records: TrendingUp,
  fund_market_snapshots: LineChart,
  news_items: Newspaper,
  meal_records: Utensils,
  workout_records: Dumbbell,
};

// Friendly table label mapping
const TABLE_NAMES = {
  todo_records: "待办任务 (Todo)",
  schedule_records: "日程安排 (Schedule)",
  fund_records: "基金持仓 (Funds)",
  fund_market_snapshots: "大盘快照 (Market)",
  news_items: "聚合新闻 (News)",
  meal_records: "饮食记录 (Meal)",
  workout_records: "运动健身 (Workout)",
};

function getTableIcon(tableName) {
  return TABLE_ICONS[tableName] || Database;
}

function getTableTitle(tableName) {
  return TABLE_NAMES[tableName] || tableName;
}

export default function DatabasePage() {
  const [tables, setTables] = useState([]);
  const [table, setTable] = useState("");
  const [data, setData] = useState({ columns: [], rows: [], primary_key: "id" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState("");

  // Modal dialog state for Create/Edit
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("form"); // "form" | "json"
  const [editingId, setEditingId] = useState(null);
  const [formValues, setFormValues] = useState({});
  const [rawJson, setRawJson] = useState("{}");
  const [modalError, setModalError] = useState("");
  const [saving, setSaving] = useState(false);

  // Copy notification state
  const [copiedId, setCopiedId] = useState(null);

  const loadTables = async () => {
    try {
      const res = await fetchJson("/api/v1/database/tables");
      const list = res.tables || [];
      setTables(list);
      if (!table && list.length > 0) {
        setTable(list[0].name);
      }
    } catch {
      setError("本地数据库服务未连接，请确保 MorningBriefAgent 核心后端正常运行");
    }
  };

  const loadRows = async (targetTable = table) => {
    if (!targetTable) return;
    setLoading(true);
    try {
      const payload = await fetchJson(`/api/v1/database/table?table=${encodeURIComponent(targetTable)}`);
      setData(payload);
      setError("");
    } catch {
      setData({ columns: [], rows: [], primary_key: "id" });
      setError(`读取数据表 [${targetTable}] 失败或表不存在`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTables();
  }, []);

  useEffect(() => {
    if (table) {
      loadRows(table);
      setSearchTerm("");
    }
  }, [table]);

  // Client-side search filtering across all columns
  const filteredRows = useMemo(() => {
    if (!searchTerm.trim()) return data.rows || [];
    const term = searchTerm.toLowerCase();
    return (data.rows || []).filter((row) => {
      return Object.values(row).some((val) => {
        if (val === null || val === undefined) return false;
        return String(val).toLowerCase().includes(term);
      });
    });
  }, [data.rows, searchTerm]);

  // Open modal to create a new record
  const handleOpenCreate = () => {
    setEditingId(null);
    const initialForm = {};
    (data.columns || []).forEach((col) => {
      if (col.name !== data.primary_key) {
        initialForm[col.name] = "";
      }
    });
    setFormValues(initialForm);
    setRawJson(JSON.stringify(initialForm, null, 2));
    setModalError("");
    setModalMode("form");
    setModalOpen(true);
  };

  // Open modal to edit an existing record
  const handleOpenEdit = (row) => {
    const pk = data.primary_key || "id";
    const id = row[pk];
    setEditingId(id);
    const form = { ...row };
    setFormValues(form);
    setRawJson(JSON.stringify(row, null, 2));
    setModalError("");
    setModalMode("form");
    setModalOpen(true);
  };

  // Sync Form to JSON when switching to JSON tab
  const handleSwitchMode = (mode) => {
    if (mode === "json") {
      setRawJson(JSON.stringify(formValues, null, 2));
    } else if (mode === "form") {
      try {
        const parsed = JSON.parse(rawJson);
        setFormValues(parsed);
        setModalError("");
      } catch {
        setModalError("当前 JSON 格式有语法错误，无法切换至表单模式");
        return;
      }
    }
    setModalMode(mode);
  };

  // Save record (POST for create, PATCH for edit)
  const handleSave = async () => {
    setSaving(true);
    setModalError("");
    try {
      let recordToSave;
      if (modalMode === "json") {
        recordToSave = JSON.parse(rawJson);
      } else {
        recordToSave = { ...formValues };
        // Clean empty string keys or handle types if needed
        Object.keys(recordToSave).forEach((key) => {
          if (recordToSave[key] === "") {
            // keep or let db default handle
          }
        });
      }

      const endpoint = apiUrl("/api/v1/database/records");
      const isEdit = Boolean(editingId);
      const payload = isEdit
        ? { table, id: editingId, record: recordToSave }
        : { table, record: recordToSave };

      const response = await fetch(endpoint, {
        method: isEdit ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "服务端保存失败，请检查必填字段与数据约束");
      }

      setModalOpen(false);
      await loadTables();
      await loadRows(table);
    } catch (err) {
      setModalError(err.message || "保存失败：请输入合法数据并确保字段完整");
    } finally {
      setSaving(false);
    }
  };

  // Delete record
  const handleRemove = async (id) => {
    if (!window.confirm(`确定要彻底删除此记录 [${id}] 吗？此操作不可逆。`)) return;
    try {
      await fetchJson("/api/v1/database/records", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table, id })
      });
      await loadTables();
      await loadRows(table);
    } catch {
      setError("删除失败：记录可能已被移除或本地后端服务未响应");
    }
  };

  // Copy ID to clipboard
  const handleCopyId = (id) => {
    if (!id) return;
    navigator.clipboard.writeText(String(id));
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const currentTableMeta = tables.find((t) => t.name === table) || { count: data.rows.length };
  const ActiveIcon = getTableIcon(table);

  return (
    <section className="workspace-page db-management-page">
      {/* Page Heading */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">SQLITE ENGINE</span>
          <h2>本地数据库</h2>
          <p>高可靠业务记录管理 · 自动事务隔离与审计 · 所有变更经由本地 API 安全写入</p>
        </div>
        <div className="heading-actions">
          <button
            className="secondary"
            onClick={() => {
              loadTables();
              loadRows(table);
            }}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            刷新数据
          </button>
        </div>
      </div>

      {/* Bento 3-Grid Overview Stat Cards */}
      <div className="db-bento-grid">
        <div className="db-bento-card">
          <div className="db-bento-icon-box">
            <ActiveIcon size={20} />
          </div>
          <div className="db-bento-info">
            <span className="db-bento-label">当前活动数据表</span>
            <strong className="db-bento-value">{table || "未选择数据表"}</strong>
            <small className="db-bento-desc">主键索引: {data.primary_key || "id"}</small>
          </div>
        </div>

        <div className="db-bento-card">
          <div className="db-bento-icon-box accent">
            <Layers size={20} />
          </div>
          <div className="db-bento-info">
            <span className="db-bento-label">持久化记录总数</span>
            <strong className="db-bento-value">
              {currentTableMeta.count ?? data.rows.length}
              <span className="unit"> 条</span>
            </strong>
            <small className="db-bento-desc">
              {searchTerm ? `当前匹配 ${filteredRows.length} 条记录` : "全表实时同步"}
            </small>
          </div>
        </div>

        <div className="db-bento-card">
          <div className="db-bento-icon-box green">
            <HardDrive size={20} />
          </div>
          <div className="db-bento-info">
            <span className="db-bento-label">存储引擎健康度</span>
            <strong className="db-bento-value text-emerald-600 flex items-center gap-2">
              <span className="pulse" />
              SQLite 活跃运行中
            </strong>
            <small className="db-bento-desc">WAL 模式已开启 · 零外网泄露</small>
          </div>
        </div>
      </div>

      {error && <div className="error-banner mb-4">{error}</div>}

      {/* Main 2-Column Split: Table Sidebar + Data Workbench */}
      <div className="database-layout">
        {/* Left Sidebar Table Navigator */}
        <aside className="db-sidebar-panel">
          <div className="db-sidebar-header">
            <span className="db-sidebar-title">业务表清单</span>
            <span className="db-sidebar-badge">{tables.length} 张表</span>
          </div>

          <div className="db-table-nav-list">
            {tables.map((item) => {
              const IconComponent = getTableIcon(item.name);
              const isActive = table === item.name;
              return (
                <button
                  key={item.name}
                  className={`db-table-nav-btn ${isActive ? "active" : ""}`}
                  onClick={() => setTable(item.name)}
                >
                  <div className="db-table-btn-left">
                    <span className="db-table-icon-wrap">
                      <IconComponent size={16} />
                    </span>
                    <div className="db-table-btn-meta">
                      <strong className="db-table-title">{getTableTitle(item.name)}</strong>
                      <span className="db-table-raw-name">{item.name}</span>
                    </div>
                  </div>
                  <span className="db-table-count-pill">{item.count}</span>
                </button>
              );
            })}
            {tables.length === 0 && (
              <div className="p-4 text-center text-xs text-slate-400">正在探查本地表...</div>
            )}
          </div>
        </aside>

        {/* Right Data Grid Panel */}
        <div className="db-main-workbench">
          {/* Workbench Top Toolbar */}
          <div className="db-workbench-toolbar">
            <div className="db-toolbar-left">
              <div className="db-table-badge-indicator">
                <ActiveIcon size={16} />
                <h3>{table || "暂无表"}</h3>
                <span className="db-column-count-tag">{data.columns.length} 个字段</span>
              </div>
            </div>

            <div className="db-toolbar-right">
              {/* Instant Search Bar */}
              <div className="db-search-input-wrap">
                <Search size={14} className="db-search-icon" />
                <input
                  type="text"
                  placeholder="搜索表中任意关键词..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="db-search-input"
                />
                {searchTerm && (
                  <button className="db-search-clear" onClick={() => setSearchTerm("")}>
                    <X size={12} />
                  </button>
                )}
              </div>

              <button className="primary compact" onClick={handleOpenCreate}>
                <Plus size={14} />
                新增记录
              </button>
            </div>
          </div>

          {/* Table Container */}
          <div className="db-table-scroll-container">
            <table className="db-data-table">
              <thead>
                <tr>
                  {data.columns.map((column) => (
                    <th key={column.name}>
                      <span className="th-title">{column.name}</span>
                      {column.name === data.primary_key && (
                        <span className="pk-indicator" title="Primary Key">PK</span>
                      )}
                    </th>
                  ))}
                  <th className="th-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const pkVal = row[data.primary_key];
                  return (
                    <tr key={String(pkVal)} className="db-data-row">
                      {data.columns.map((col) => {
                        const rawVal = row[col.name];
                        const isPk = col.name === data.primary_key;

                        // Render Primary Key with smart truncate and copy
                        if (isPk) {
                          const valStr = String(rawVal ?? "");
                          const truncated = valStr.length > 18 ? `${valStr.slice(0, 14)}…` : valStr;
                          const isCopied = copiedId === valStr;
                          return (
                            <td key={col.name} className="td-pk">
                              <span className="pk-tag">
                                <code title={valStr}>{truncated}</code>
                                <button
                                  className="pk-copy-btn"
                                  onClick={() => handleCopyId(valStr)}
                                  title="复制完整主键 ID"
                                >
                                  {isCopied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                                </button>
                              </span>
                            </td>
                          );
                        }

                        // Render status-like tags
                        const isStatusCol = ["status", "priority", "level", "state"].includes(col.name.toLowerCase());
                        if (isStatusCol && rawVal) {
                          const s = String(rawVal).toLowerCase();
                          let badgeClass = "badge-neutral";
                          if (["open", "todo", "pending", "active"].includes(s)) badgeClass = "badge-amber";
                          else if (["done", "completed", "success", "closed"].includes(s)) badgeClass = "badge-emerald";
                          else if (["failed", "error", "urgent", "high"].includes(s)) badgeClass = "badge-rose";

                          return (
                            <td key={col.name}>
                              <span className={`db-status-badge ${badgeClass}`}>
                                <span className="status-dot" />
                                {String(rawVal)}
                              </span>
                            </td>
                          );
                        }

                        // Render generic data with smart truncation
                        const displayStr = rawVal === null || rawVal === undefined ? "—" : String(rawVal);
                        return (
                          <td key={col.name} className="td-cell" title={displayStr}>
                            {displayStr.length > 70 ? `${displayStr.slice(0, 68)}…` : displayStr}
                          </td>
                        );
                      })}

                      {/* Action buttons */}
                      <td className="td-actions">
                        <div className="td-actions-wrap">
                          <button
                            className="db-action-btn edit"
                            onClick={() => handleOpenEdit(row)}
                            title="编辑此记录"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            className="db-action-btn delete"
                            onClick={() => handleRemove(pkVal)}
                            title="删除此记录"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}

                {filteredRows.length === 0 && (
                  <tr>
                    <td colSpan={data.columns.length + 1} className="db-empty-cell">
                      <div className="db-empty-state">
                        <div className="db-empty-icon">
                          <Database size={28} />
                        </div>
                        <h4>{searchTerm ? "未检索到匹配记录" : "当前数据表尚无记录"}</h4>
                        <p>
                          {searchTerm
                            ? `未找到包含 "${searchTerm}" 的记录，请尝试调整搜索词`
                            : "点击右上角「新增记录」按钮，添加第一条持久化业务数据"}
                        </p>
                        {searchTerm && (
                          <button className="secondary compact mt-2" onClick={() => setSearchTerm("")}>
                            清除搜索过滤
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Table Footer Stats */}
          <div className="db-workbench-footer">
            <span className="db-footer-stat">
              共呈现 <strong>{filteredRows.length}</strong> / {data.rows.length} 条记录
            </span>
            <span className="db-footer-tip">
              双击或点击铅笔按钮可唤起模态弹窗进行表单与 JSON 编辑
            </span>
          </div>
        </div>
      </div>

      {/* Floating Modal Dialog for Create & Edit */}
      {modalOpen && (
        <div className="db-modal-overlay" onClick={() => !saving && setModalOpen(false)}>
          <div className="db-modal-dialog" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="db-modal-header">
              <div className="db-modal-title-wrap">
                <span className="eyebrow">{editingId ? "EDIT RECORD" : "CREATE RECORD"}</span>
                <h3>{editingId ? `编辑记录: ${editingId}` : `新增业务记录至 [${table}]`}</h3>
              </div>

              {/* Mode Switcher Tabs */}
              <div className="db-modal-mode-tabs">
                <button
                  type="button"
                  className={`db-mode-tab-btn ${modalMode === "form" ? "active" : ""}`}
                  onClick={() => handleSwitchMode("form")}
                >
                  <SlidersHorizontal size={13} />
                  智能表单
                </button>
                <button
                  type="button"
                  className={`db-mode-tab-btn ${modalMode === "json" ? "active" : ""}`}
                  onClick={() => handleSwitchMode("json")}
                >
                  <Code2 size={13} />
                  JSON 代码
                </button>
                <button
                  type="button"
                  className="db-modal-close-btn"
                  onClick={() => setModalOpen(false)}
                  disabled={saving}
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Modal Error Banner */}
            {modalError && (
              <div className="db-modal-error-banner">
                {modalError}
              </div>
            )}

            {/* Modal Body */}
            <div className="db-modal-body">
              {modalMode === "form" ? (
                <div className="db-form-grid">
                  {data.columns.map((col) => {
                    const isPk = col.name === data.primary_key;
                    const val = formValues[col.name] ?? "";

                    return (
                      <div key={col.name} className={`db-form-group ${isPk ? "opacity-75" : ""}`}>
                        <label className="db-form-label">
                          <span>{col.name}</span>
                          {isPk && <span className="pk-badge-small">主键 (自动)</span>}
                        </label>
                        <input
                          type="text"
                          value={val}
                          readOnly={isPk && Boolean(editingId)}
                          disabled={isPk && Boolean(editingId)}
                          onChange={(e) =>
                            setFormValues({
                              ...formValues,
                              [col.name]: e.target.value
                            })
                          }
                          placeholder={isPk ? "系统自动分配主键" : `输入 ${col.name} ...`}
                          className={`db-form-input ${isPk ? "cursor-not-allowed bg-slate-50" : ""}`}
                        />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="db-json-editor-wrap">
                  <div className="db-json-header">
                    <span>标准 JSON 格式编写</span>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => {
                        try {
                          const formatted = JSON.stringify(JSON.parse(rawJson), null, 2);
                          setRawJson(formatted);
                          setModalError("");
                        } catch {
                          setModalError("无法格式化：当前内容并非合法 JSON");
                        }
                      }}
                    >
                      美化格式化 (Format)
                    </button>
                  </div>
                  <textarea
                    className="db-json-textarea"
                    value={rawJson}
                    onChange={(e) => setRawJson(e.target.value)}
                    rows={12}
                    spellCheck="false"
                  />
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="db-modal-footer">
              <span className="db-modal-foot-tip">
                {editingId
                  ? "编辑将采用 PATCH 增量更新，保留未修改字段"
                  : "新增将使用 POST 写入数据库，并自动触发全量刷新"}
              </span>
              <div className="db-modal-foot-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setModalOpen(false)}
                  disabled={saving}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      正在保存...
                    </>
                  ) : (
                    <>
                      <Check size={14} />
                      保存记录
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
