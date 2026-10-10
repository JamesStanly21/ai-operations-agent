import {
  Activity,
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  CheckCircle2,
  CheckSquare2,
  ClipboardCheck,
  CircleAlert,
  Clock3,
  ListChecks,
  Loader2,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import ApprovalPlan from "../components/ApprovalPlan.jsx";

const agentExamples = [
  "Check my tasks and complete the task called Prepare hackathon demo",
  "Create a task called Submit the project report",
  "Remind me to review the demo tomorrow at 9 AM",
];

function PageHeading({ eyebrow = "OPERATIONS WORKSPACE", title, description, actions }) {
  return (
    <div className="page-heading">
      <div><div className="eyebrow">{eyebrow}<span className="live-indicator" />LIVE WORKSPACE</div><h1>{title}</h1><p>{description}</p></div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}

function MetricCard({ label, value, note, icon: Icon, tone = "blue", movement }) {
  return <article className="metric-card">
    <div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={17} /></span></div>
    <div className="metric-value-row"><strong>{value}</strong>{movement && <span className="metric-live">{movement}</span>}</div>
    <small>{note}</small>
  </article>;
}

function EmptyState({ icon: Icon = ListChecks, title, detail, action }) {
  return <div className="workspace-empty"><span className="empty-symbol"><Icon size={22} /></span><strong>{title}</strong><p>{detail}</p>{action}</div>;
}

function StatusPill({ status }) {
  const normalized = (status || "unknown").toLowerCase().replaceAll("_", "-");
  return <span className={`status-pill status-${normalized}`}>{(status || "unknown").replaceAll("_", " ")}</span>;
}

export function DashboardPage({ tasks, reminders, workflows, workflowsAvailable, agentResult, loading, error, onRefresh, onNavigate, onAgentRun }) {
  const pending = tasks.filter((task) => task.status === "pending");
  const completed = tasks.filter((task) => task.status === "completed");
  const scheduled = reminders.filter((reminder) => reminder.status === "scheduled");
  const attentionWorkflows = workflows.filter((workflow) => ["failed", "partially_completed"].includes(workflow.status));
  const total = tasks.length || 0;
  const completeRatio = total ? Math.round((completed.length / total) * 100) : 0;

  return <>
    <PageHeading title="Operations overview" description="A live view of tasks, reminders, and workflows in your workspace." actions={<><button className="button secondary" onClick={onRefresh} disabled={loading}><RefreshCw size={14} className={loading ? "spin" : ""} />Refresh</button><button className="button primary" onClick={onAgentRun}><Sparkles size={15} />Ask OpsAgent</button></>} />
    <section className="metrics-grid" aria-label="Workspace metrics">
      <MetricCard label="Total tasks" value={tasks.length} note="Current task records" icon={ListChecks} tone="blue" movement="Live" />
      <MetricCard label="Pending" value={pending.length} note="Awaiting completion" icon={Clock3} tone="amber" />
      <MetricCard label="Completed" value={completed.length} note="Marked complete" icon={CheckCircle2} tone="green" />
      <MetricCard label="Scheduled reminders" value={scheduled.length} note="From the reminder service" icon={Activity} tone="purple" />
    </section>

    {error && <div className="inline-notice"><AlertCircle size={15} />Some live data could not be loaded. Retry to refresh the workspace.</div>}

    <section className="dashboard-grid">
      <article className="panel focus-panel">
        <div className="panel-heading"><div><h2>Today’s focus</h2><p>Open tasks currently in the shared task state</p></div><button className="text-action" onClick={() => onNavigate("tasks")}>View tasks <ArrowRight size={14} /></button></div>
        {loading && tasks.length === 0 ? <div className="panel-loading"><Loader2 size={16} className="spin" />Loading task state…</div> : pending.length === 0 ? <EmptyState title="No open tasks" detail="New tasks created by the Agent will appear here." action={<button className="text-action" onClick={onAgentRun}>Create one with OpsAgent <ArrowRight size={14} /></button>} /> : (
          <div className="focus-list">{pending.slice(0, 5).map((task) => <button className="focus-row" key={task.id} onClick={() => onNavigate("tasks")}><span className="focus-check"><Check size={13} /></span><span className="focus-copy"><strong>{task.title}</strong><small>{task.description || "Pending task"}</small></span><span className="focus-status">Pending</span><ArrowUpRight size={14} className="focus-open" /></button>)}</div>
        )}
      </article>

      <article className="panel workload-panel">
        <div className="panel-heading"><div><h2>Current workload</h2><p>Task mix from live records</p></div><span className="panel-icon"><Activity size={16} /></span></div>
        <div className="workload-total"><strong>{total}</strong><span>tasks tracked</span></div>
        <div className="workload-progress" aria-label={`${completeRatio}% of tasks completed`}><i style={{ width: `${completeRatio}%` }} /></div>
        <div className="workload-legend"><span><i className="legend-dot pending-dot" />Pending <b>{pending.length}</b></span><span><i className="legend-dot completed-dot" />Completed <b>{completed.length}</b></span></div>
        <div className="workload-footnote">No weekly task history is available from the current API.</div>
      </article>

      <article className="panel attention-panel">
        <div className="panel-heading"><div><h2>Needs your attention</h2><p>Workflow runs that did not complete cleanly</p></div><button className="text-action" onClick={() => onNavigate("risk")}>Risk Center <ArrowRight size={14} /></button></div>
        {workflowsAvailable === false ? <EmptyState icon={AlertCircle} title="Workflow status unavailable" detail="Could not read workflow status from the backend." /> : attentionWorkflows.length === 0 ? <EmptyState icon={CheckCircle2} title="No workflow issues" detail="No failed or partially completed runs are reported." /> : <div className="attention-list">{attentionWorkflows.slice(0, 4).map((workflow) => <button className="attention-row" key={workflow.id} onClick={() => onNavigate("workflows")}><span className={`attention-icon ${workflow.status === "failed" ? "danger" : "warning"}`}><CircleAlert size={16} /></span><span><strong>{workflow.title}</strong><small>{workflow.status.replaceAll("_", " ")}</small></span><ArrowUpRight size={14} /></button>)}</div>}
      </article>

      <article className="panel recent-panel">
        <div className="panel-heading"><div><h2>Recent activity</h2><p>Latest activity available in this session</p></div><button className="text-action" onClick={() => onNavigate("activity")}>View history <ArrowRight size={14} /></button></div>
        {agentResult?.steps?.length ? <div className="recent-list">{agentResult.steps.slice(-4).reverse().map((step, index) => <div className="recent-row" key={`${step.step || index}-${step.action?.action}`}><span className="recent-check"><Check size={13} /></span><span><strong>{step.action?.action?.replaceAll("_", " ") || "Agent action"}</strong><small>{step.observation?.result?.message || step.observation?.message || "Observed by the Agent"}</small></span></div>)}</div> : workflows.length ? <div className="recent-list">{workflows.slice(0, 3).map((workflow) => <div className="recent-row" key={workflow.id}><span className="recent-check workflow-check"><Workflow size={13} /></span><span><strong>{workflow.title}</strong><small>Workflow · {workflow.status.replaceAll("_", " ")}</small></span></div>)}</div> : <EmptyState icon={Activity} title="No recent activity" detail="Run an Agent instruction or start a workflow to see recent activity here." />}
      </article>
    </section>
  </>;
}

export function AgentWorkspacePage({ instruction, setInstruction, loading, result, onRun, health, approval, approvalBusy, approvalError, onReview, onApprovePlan, onRejectPlan, onEditPlan }) {
  return <>
    <PageHeading title="AI Operations Agent" description="Give OpsAgent an objective. It will plan, execute, observe, and react." actions={<span className={`connection-pill ${health === "healthy" ? "connected" : ""}`}><i />{health === "healthy" ? "Backend connected" : "Backend unavailable"}</span>} />
    <div className="agent-layout">
      <section className="panel agent-main-panel">
        <div className="agent-intro"><span className="agent-spark"><Sparkles size={18} /></span><div><h2>What needs to get done?</h2><p>Describe an operations task in plain language.</p></div></div>
        <label className="agent-prompt-label" htmlFor="agent-prompt">Your instruction</label>
        <div className="agent-prompt-box"><textarea id="agent-prompt" value={instruction} onChange={(event) => setInstruction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) onRun(); }} placeholder="e.g. Check my tasks and complete the task called Prepare hackathon demo" rows={5} /><div className="agent-prompt-footer"><span>Ctrl / ⌘ + Enter runs directly</span><div className="agent-prompt-actions"><button className="button secondary" disabled={!instruction.trim() || loading || Boolean(approvalBusy)} onClick={onReview}>{approvalBusy === "review" ? <><Loader2 size={14} className="spin" />Preparing…</> : <><ClipboardCheck size={14} />Review Plan</>}</button><button className="button primary" disabled={!instruction.trim() || loading || Boolean(approvalBusy)} onClick={onRun}>{loading ? <><Loader2 size={15} className="spin" />Running…</> : <><Play size={14} fill="currentColor" />Run Agent</>}</button></div></div></div>
        {approvalBusy === "review" && <div className="approval-loading"><Loader2 size={14} className="spin" />Preparing a proposal from the current workspace state…</div>}
        {approvalError && !approval && <div className="approval-inline-error" role="alert"><AlertCircle size={14} />{approvalError}</div>}
        <ApprovalPlan approval={approval} busy={approvalBusy} error={approvalError} onApprove={onApprovePlan} onReject={onRejectPlan} onEdit={onEditPlan} onRefresh={onReview} />
        <div className="suggestion-list"><span>Try an instruction</span>{agentExamples.map((example) => <button key={example} onClick={() => setInstruction(example)}>{example}<ArrowUpRight size={12} /></button>)}</div>
        <div className="agent-result-area">
          <div className="section-title-row"><div><h3>Execution trace</h3><p>Actions and observations from the latest run</p></div>{result && <StatusPill status={result.success ? "completed" : "failed"} />}</div>
          {!result ? <EmptyState icon={Activity} title="Ready when you are" detail="The Agent’s PLAN → ACT → OBSERVE → REACT trace will appear here." /> : <>
            {result.steps?.length ? <ol className="agent-trace">{result.steps.map((step, index) => <li key={`${step.step || index}-${step.action?.action}`}><span className={`trace-marker ${step.observation?.success === false ? "trace-failed" : ""}`}>{step.observation?.success === false ? <AlertCircle size={14} /> : <Check size={14} />}</span><div><strong>{step.action?.action?.replaceAll("_", " ") || "Agent action"}</strong><small>{step.observation?.result?.message || step.observation?.message || step.observation?.error || "Action observed"}</small></div></li>)}</ol> : <div className="trace-empty">No tool actions were recorded.</div>}
            <div className={`agent-final-message ${result.success ? "success" : "failure"}`}><strong>{result.success ? "Run finished" : "Run incomplete"}</strong><span>{result.final_message || "The Agent finished processing the instruction."}</span></div>
          </>}
        </div>
      </section>
      <aside className="agent-side-column">
        <section className="panel how-panel"><div className="panel-heading"><div><h2>How the Agent works</h2><p>One action at a time, using the shared workspace state</p></div></div>{[["01", "Plan", "Choose the next action for your objective."], ["02", "Act", "Route the decision to the existing task or reminder tool."], ["03", "Observe", "Read the tool result and update the execution trace."], ["04", "React", "Continue or finish based on the observation."]].map(([number, title, detail]) => <div className="how-step" key={number}><span>{number}</span><div><strong>{title}</strong><small>{detail}</small></div></div>)}</section>
        <div className="agent-note"><Sparkles size={15} /><p>The Agent and dashboards use the same FastAPI task and reminder state.</p></div>
      </aside>
    </div>
  </>;
}

export function TasksPage({ tasks, loading, query, taskError, actionId, onComplete, onRefresh, onAgent }) {
  const pending = tasks.filter((task) => task.status === "pending");
  const completed = tasks.filter((task) => task.status === "completed");
  const filtered = tasks.filter((task) => `${task.title} ${task.description || ""} ${task.status}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <>
    <PageHeading title="Tasks" description="Track and complete work managed by OpsAgent." actions={<><button className="button secondary" onClick={onRefresh} disabled={loading}><RefreshCw size={14} className={loading ? "spin" : ""} />Refresh</button><button className="button primary" onClick={onAgent}><Sparkles size={15} />Ask OpsAgent</button></>} />
    <section className="metrics-grid compact-metrics"><MetricCard label="Total tasks" value={tasks.length} note="Shared task state" icon={ListChecks} /><MetricCard label="Pending" value={pending.length} note="Open work" icon={Clock3} tone="amber" /><MetricCard label="Completed" value={completed.length} note="Finished work" icon={CheckCircle2} tone="green" /></section>
    <section className="panel page-table-panel"><div className="panel-heading"><div><h2>All tasks</h2><p>Tasks created and managed through the operations agent</p></div><span className="record-count">{filtered.length} records</span></div>
      {taskError && <div className="inline-notice error"><AlertCircle size={15} />{taskError}</div>}
      <div className="table-toolbar"><span className="table-total">{query ? `Filtered by “${query}”` : "Current workspace tasks"}</span><button className="table-refresh" onClick={onRefresh} disabled={loading}><RefreshCw size={13} />Refresh list</button></div>
      {loading && tasks.length === 0 ? <div className="panel-loading"><Loader2 size={16} className="spin" />Loading tasks…</div> : filtered.length === 0 ? <EmptyState icon={Search} title={query ? "No matching tasks" : "No tasks yet"} detail={query ? "Try a different search term." : "Ask OpsAgent to create a task and it will appear here."} action={!query && <button className="button secondary" onClick={onAgent}><Sparkles size={14} />Open Agent</button>} /> : <div className="table-scroll"><table className="workspace-table"><thead><tr><th>TASK</th><th>DESCRIPTION</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{filtered.map((task) => <tr key={task.id}><td><div className="table-task-title"><span className={`task-row-icon ${task.status === "completed" ? "done" : ""}`}><CheckSquare2 size={15} /></span><strong>{task.title}</strong></div><small className="table-subline">Task #{task.id}</small></td><td className="task-description-cell">{task.description || "—"}</td><td><StatusPill status={task.status} /></td><td>{task.status === "pending" ? <button className="complete-task-button" onClick={() => onComplete(task.id)} disabled={actionId === task.id}>{actionId === task.id ? <Loader2 size={14} className="spin" /> : <Check size={14} />}Complete</button> : <span className="muted-action">Completed</span>}</td></tr>)}</tbody></table></div>}
    </section>
  </>;
}

export function RemindersPage({ reminders, loading, onRefresh }) {
  const scheduled = reminders.filter((reminder) => reminder.status === "scheduled");
  return <>
    <PageHeading title="Reminders" description="Review reminders scheduled by your operations agent." actions={<button className="button secondary" onClick={onRefresh} disabled={loading}><RefreshCw size={14} className={loading ? "spin" : ""} />Refresh</button>} />
    <section className="metrics-grid reminders-metrics"><MetricCard label="Total reminders" value={reminders.length} note="Shared reminder state" icon={Activity} tone="blue" /><MetricCard label="Scheduled" value={scheduled.length} note="Awaiting their reminder time" icon={Clock3} tone="green" /></section>
    <section className="panel page-table-panel"><div className="panel-heading"><div><h2>Scheduled reminders</h2><p>Reminders currently held in the agent workspace</p></div><span className="record-count">{reminders.length} records</span></div>
      {loading && reminders.length === 0 ? <div className="panel-loading"><Loader2 size={16} className="spin" />Loading reminders…</div> : reminders.length === 0 ? <EmptyState icon={Clock3} title="No reminders yet" detail="Reminders created by OpsAgent will appear here." /> : <div className="table-scroll"><table className="workspace-table"><thead><tr><th>REMINDER</th><th>REMINDER TIME</th><th>STATUS</th></tr></thead><tbody>{reminders.map((reminder) => <tr key={reminder.id}><td><div className="table-task-title"><span className="task-row-icon reminder-icon"><Clock3 size={15} /></span><strong>{reminder.title}</strong></div><small className="table-subline">Reminder #{reminder.id}</small></td><td>{reminder.reminder_time}</td><td><StatusPill status={reminder.status} /></td></tr>)}</tbody></table></div>}
    </section>
  </>;
}

export function ActivityHistoryPage({ agentResult, workflows, workflowsAvailable }) {
  const hasAgentActivity = Boolean(agentResult?.steps?.length || agentResult?.final_message);
  return <>
    <PageHeading title="Activity History" description="A session-level view of agent execution and saved workflow runs." />
    <section className="panel page-table-panel"><div className="panel-heading"><div><h2>Recent workspace activity</h2><p>Agent run details are kept in this browser session; workflows are read from the backend.</p></div><span className="record-count">{(agentResult?.steps?.length || 0) + workflows.length} entries</span></div>
      {hasAgentActivity && <div className="activity-session"><div className="activity-session-header"><span className="activity-session-icon"><Bot size={15} /></span><div><strong>Latest AI Operations Agent run</strong><small>{agentResult.success ? "Completed" : "Incomplete"}</small></div><StatusPill status={agentResult.success ? "completed" : "failed"} /></div><p>{agentResult.final_message || "Agent run finished."}</p>{agentResult.steps?.map((step, index) => <div className="activity-event" key={`${index}-${step.action?.action}`}><span className="activity-event-dot" /><div><strong>{step.action?.action?.replaceAll("_", " ")}</strong><small>{step.observation?.result?.message || step.observation?.message || "Action observed"}</small></div></div>)}</div>}
      {workflows.length > 0 ? <div className="activity-workflows">{workflows.map((workflow) => <article className="activity-workflow-row" key={workflow.id}><span className="activity-session-icon"><Workflow size={15} /></span><div><strong>{workflow.title}</strong><small>Updated {new Date(workflow.updated_at).toLocaleString()}</small></div><StatusPill status={workflow.status} /></article>)}</div> : !hasAgentActivity && workflowsAvailable !== false ? <EmptyState icon={Activity} title="No activity yet" detail="Run an Agent instruction or workflow to populate activity available in this session." /> : null}
      {workflowsAvailable === false && <div className="history-limitation"><AlertCircle size={14} /><span>Workflow history could not be loaded from the backend.</span></div>}
      <div className="history-limitation"><AlertCircle size={14} /><span>Agent history is not persisted by the current API. This view shows the latest run in this browser plus workflow records that are currently available.</span></div>
    </section>
  </>;
}

export function PlaceholderPage({ page, tasks = [], workflows = [], workflowsAvailable, health = "unknown" }) {
  if (page === "risk") {
    const flaggedWorkflows = workflows.filter((item) => ["failed", "partially_completed"].includes(item.status));
    return <><PageHeading title="Risk Center" description="Review issues exposed by the current workflow state." /><section className="panel placeholder-panel"><div className="panel-heading"><div><h2>Workflow execution issues</h2><p>Only status data returned by the Workflow API is shown here.</p></div><span className="record-count">{workflowsAvailable === false ? "Unavailable" : `${flaggedWorkflows.length} flagged`}</span></div>{workflowsAvailable === false ? <EmptyState icon={AlertCircle} title="Workflow status unavailable" detail="Could not read workflow records from the backend." /> : flaggedWorkflows.length ? <div className="attention-list">{flaggedWorkflows.map((workflow) => <div className="attention-row" key={workflow.id}><span className="attention-icon danger"><ShieldAlert size={16} /></span><span><strong>{workflow.title}</strong><small>{workflow.status.replaceAll("_", " ")}</small></span></div>)}</div> : <EmptyState icon={ShieldAlert} title="No workflow risks reported" detail="Current task records do not include due dates, priorities, or dependency risk. No additional risk metrics are available." />}</section><p className="page-data-note">Task records currently available: {tasks.length}. No risk attributes are inferred from task titles or descriptions.</p></>;
  }
  if (page === "team") return <><PageHeading title="Team" description="Team workload and membership for this operations workspace." /><section className="panel placeholder-panel"><EmptyState icon={Users} title="Team data is not connected" detail="The current backend does not expose team members or assignments. This page will show workspace records when a team API is available." /></section></>;
  return <><PageHeading title="Settings" description="Workspace preferences and connection information." /><div className="settings-layout"><section className="panel settings-panel"><div className="panel-heading"><div><h2>Workspace preferences</h2><p>Preferences available in this frontend</p></div></div><div className="setting-row"><div><strong>Language</strong><small>The current interface is available in English.</small></div><select defaultValue="en" aria-label="Language"><option value="en">English (EN)</option></select></div><div className="setting-row"><div><strong>Workspace</strong><small>Local development environment</small></div><span className="setting-value">OpsAgent AI</span></div><div className="setting-row"><div><strong>Backend connection</strong><small>FastAPI health endpoint</small></div><StatusPill status={health === "healthy" ? "completed" : "failed"} /></div><div className="setting-row"><div><strong>Time zone</strong><small>Browser time zone</small></div><span className="setting-value">{Intl.DateTimeFormat().resolvedOptions().timeZone}</span></div></section><aside className="panel settings-aside"><span className="settings-emblem"><Sparkles size={20} /></span><h3>Built around your operations</h3><p>Tasks, reminders, and workflows come from the same backend state used by OpsAgent.</p><small>Connected through the existing FastAPI APIs</small></aside></div></>;
}
