import React, { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { apiUrl, fetchJson } from "../localApi";

export default function WorkflowPage() {
  const [payload, setPayload] = useState({ workflows: [], runs: [] });
  const [busy, setBusy] = useState("");
  const load = () => fetchJson("/api/v1/workflows").then(setPayload).catch(() => {});
  useEffect(() => { load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, []);
  const run = async (key) => {
    setBusy(key);
    try { await fetchJson(`/api/v1/workflows/${key}/run`, { method: "POST" }); await load(); }
    finally { setBusy(""); }
  };
  return <section className="workspace-page">
    <div className="page-heading"><div><span className="eyebrow">WORKFLOWS</span><h2>工作流</h2><p>每个工作流都有明确的输入、输出和触发方式，按需运行即可。</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/>刷新</button></div>
    <div className="workflow-grid">{payload.workflows.map((item) => <article className="workflow-card" key={item.key}>
      <div className="workflow-card-head"><div><span className="status-pill">{item.schedule}</span><h3>{item.title}</h3></div><button className="primary compact" disabled={busy === item.key} onClick={() => run(item.key)}><Play size={14}/>{busy === item.key ? "运行中" : "运行"}</button></div>
      <p>{item.description}</p><dl><div><dt>输入</dt><dd>{item.inputs}</dd></div><div><dt>输出</dt><dd>{item.outputs}</dd></div><div><dt>命令</dt><dd><code>python main.py {item.command}</code></dd></div></dl>
    </article>)}</div>
    <div className="runtime-panel workflow-runs"><div className="db-title"><h3>最近运行</h3><span className="eyebrow">LOCAL RUNS</span></div><table><thead><tr><th>工作流</th><th>状态</th><th>开始时间</th><th>错误</th></tr></thead><tbody>{payload.runs.map((run) => <tr key={run.id}><td>{run.workflow_key}</td><td>{run.status}</td><td>{run.started_at}</td><td>{run.error_message || "—"}</td></tr>)}{!payload.runs.length && <tr><td colSpan="4">暂无运行记录</td></tr>}</tbody></table></div>
  </section>;
}
