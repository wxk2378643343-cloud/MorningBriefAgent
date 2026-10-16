import React, { useEffect, useState } from "react";
import { Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { apiUrl, fetchJson } from "../localApi";

export default function DatabasePage() {
  const [tables, setTables] = useState([]); const [table, setTable] = useState(""); const [data, setData] = useState({ columns: [], rows: [] });
  const [editing, setEditing] = useState(null); const [json, setJson] = useState("{}"); const [error, setError] = useState("");
  const loadTables = () => fetchJson("/api/v1/database/tables").then((p) => { setTables(p.tables || []); if (!table && p.tables?.[0]) setTable(p.tables[0].name); }).catch(() => setError("数据库服务未连接"));
  const loadRows = () => table && fetchJson(`/api/v1/database/table?table=${encodeURIComponent(table)}`).then((payload) => { setData(payload); setError(""); }).catch(() => { setData({ columns: [], rows: [] }); setError("读取表失败"); });
  useEffect(() => { loadTables(); }, []); useEffect(() => { loadRows(); }, [table]);
  const save = async () => { try { const record = JSON.parse(json); const endpoint = apiUrl("/api/v1/database/records"); const response = await fetch(endpoint, { method: editing ? "PATCH" : "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(editing ? { table, id: editing, record } : { table, record }) }); if (!response.ok) throw new Error(); setEditing(null); setJson("{}"); loadTables(); loadRows(); } catch { setError("保存失败：请输入合法 JSON，并填写必填字段"); } };
  const remove = async (id) => { if (!window.confirm("确定删除这条记录吗？")) return; try { await fetchJson("/api/v1/database/records", { method: "DELETE", headers: {"Content-Type":"application/json"}, body: JSON.stringify({table, id}) }); loadTables(); loadRows(); } catch { setError("删除失败：记录可能已不存在或本地服务不可用"); } };
  return <section className="workspace-page"><div className="page-heading"><div><span className="eyebrow">SQLITE</span><h2>数据库</h2><p>只操作业务记录，不开放任意 SQL；所有改动都经过本地 API。</p></div><button className="secondary" onClick={() => {loadTables();loadRows();}}><RefreshCw size={15}/>刷新</button></div>
    <div className="database-layout"><aside className="table-list">{tables.map((item) => <button className={table === item.name ? "active" : ""} key={item.name} onClick={() => setTable(item.name)}>{item.name}<small>{item.count} 条</small></button>)}</aside>
    <div className="runtime-panel database-panel"><div className="db-title"><div><span className="eyebrow">TABLE</span><h3>{table || "暂无表"}</h3></div><button className="primary compact" onClick={() => {setEditing(null);setJson("{}");}}><Plus size={14}/>新增</button></div>
      {error && <div className="error-banner">{error}</div>}<table><thead><tr>{data.columns.map((column) => <th key={column.name}>{column.name}</th>)}<th>操作</th></tr></thead><tbody>{data.rows.map((row) => <tr key={String(row[data.primary_key])}>{data.columns.map((column) => <td key={column.name}>{String(row[column.name] ?? "—").slice(0, 80)}</td>)}<td><button className="icon-button" onClick={() => {setEditing(row[data.primary_key]);setJson(JSON.stringify(row, null, 2));}}><Save size={14}/></button><button className="icon-button danger" onClick={() => remove(row[data.primary_key])}><Trash2 size={14}/></button></td></tr>)}{!data.rows.length && <tr><td colSpan={data.columns.length + 1}>暂无数据</td></tr>}</tbody></table>
      <div className="record-editor"><div><strong>{editing ? "编辑记录" : "新增记录"}</strong><span>使用 JSON 填写字段，未填写的字段使用数据库默认值。</span></div><textarea value={json} onChange={(e) => setJson(e.target.value)} /><button className="primary" onClick={save}>保存记录</button></div>
    </div></div></section>;
}
