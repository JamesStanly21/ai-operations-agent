import { useState } from "react";
import {
  AlertCircle,
  Check,
  Circle,
  Clock3,
  Loader2,
  Pencil,
  Save,
  ShieldCheck,
  X,
} from "lucide-react";
import "./ApprovalPlan.css";

const stateLabels = {
  pending_approval: "Pending review",
  approved: "Approved",
  executing: "Executing",
  completed: "Completed",
  partially_completed: "Partially completed",
  failed: "Failed",
  rejected: "Rejected",
  stale: "Needs refresh",
};

function actionTitle(action) {
  const args = action.arguments || {};
  if (args.title) return args.title;
  if (args.task_id) return `Task #${args.task_id}`;
  return action.action.replaceAll("_", " ");
}

function actionLabel(action) {
  return ({
    create_task: "Create task",
    complete_task: "Complete task",
    update_task: "Update task",
    create_reminder: "Create reminder",
  })[action] || action.replaceAll("_", " ");
}

function actionMessage(action) {
  const result = action.result || {};
  const inner = result.result || {};
  return action.error || result.error || inner.message || inner.error || "Action is awaiting approval.";
}

function ActionMarker({ status }) {
  if (status === "completed") return <span className="approval-action-marker complete"><Check size={13} /></span>;
  if (status === "failed" || status === "stale") return <span className="approval-action-marker failed"><X size={13} /></span>;
  if (status === "skipped") return <span className="approval-action-marker skipped"><Circle size={11} /></span>;
  if (status === "executing") return <span className="approval-action-marker running"><Loader2 size={13} className="spin" /></span>;
  return <span className="approval-action-marker pending"><Circle size={11} /></span>;
}

function copyActions(actions) {
  return (actions || []).map((action) => ({
    action: action.action,
    arguments: { ...(action.arguments || {}) },
  }));
}

export default function ApprovalPlan({
  approval,
  busy,
  error,
  onApprove,
  onReject,
  onEdit,
  onRefresh,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState([]);

  if (!approval) return null;

  const pending = approval.status === "pending_approval";
  const beginEdit = () => {
    setDraft(copyActions(approval.actions));
    setEditing(true);
  };

  const changeArgument = (index, key, value) => {
    setDraft((current) => current.map((item, itemIndex) => itemIndex === index
      ? { ...item, arguments: { ...item.arguments, [key]: value } }
      : item));
  };

  const saveChanges = async () => {
    const actions = draft.map(({ action, arguments: args }) => {
      const cleaned = { ...args };
      if (action === "complete_task" || action === "update_task") {
        cleaned.task_id = Number(cleaned.task_id);
      }
      if (action === "update_task") {
        if (!cleaned.title?.trim()) delete cleaned.title;
        if (cleaned.description === "") delete cleaned.description;
      }
      return { action, arguments: cleaned };
    });
    try {
      await onEdit(actions);
      setEditing(false);
    } catch {
      // The parent renders the API error while preserving the draft for correction.
    }
  };

  return (
    <section className="approval-panel" aria-labelledby="approval-panel-title">
      <div className="approval-panel-heading">
        <div>
          <div className="approval-eyebrow"><ShieldCheck size={13} /> HUMAN REVIEW</div>
          <h3 id="approval-panel-title">Review plan</h3>
        </div>
        <span className={`approval-status approval-status-${approval.status}`}>
          {approval.status === "executing" && <Loader2 size={12} className="spin" />}
          {stateLabels[approval.status] || approval.status?.replaceAll("_", " ")}
        </span>
      </div>

      <div className="approval-summary">
        <strong>{approval.objective}</strong>
        <span>{approval.actions?.length || 0} proposed {approval.actions?.length === 1 ? "action" : "actions"} · Revision {approval.revision}</span>
      </div>

      {pending && approval.revision > 1 && (
        <div className="approval-notice" role="status">
          <ShieldCheck size={15} />
          <span>Plan updated. Approval is required again before any action can execute.</span>
        </div>
      )}
      {approval.status === "stale" && (
        <div className="approval-notice stale" role="status">
          <AlertCircle size={15} />
          <span>Workspace state changed after this plan was prepared. Refresh the proposal and review it again; no stale action was executed.</span>
        </div>
      )}
      {approval.status === "partially_completed" && (
        <div className="approval-notice warning" role="status">
          <AlertCircle size={15} />
          <span>Execution stopped before every action completed. Review the successful and failed steps below.</span>
        </div>
      )}
      {error && <div className="approval-notice error" role="alert"><AlertCircle size={15} /><span>{error}</span></div>}

      {approval.actions?.length ? (
        <ol className="approval-action-list">
          {(editing ? draft : approval.actions).map((action, index) => {
            const args = action.arguments || {};
            const status = editing ? "pending" : action.status;
            return (
              <li className="approval-action" key={approval.actions[index]?.id || `${action.action}-${index}`}>
                <span className="approval-order">{String(index + 1).padStart(2, "0")}</span>
                <ActionMarker status={status} />
                <div className="approval-action-content">
                  <div className="approval-action-heading">
                    <span>{actionLabel(action.action)}</span>
                    {!editing && <small className={`approval-step-status ${status || "pending"}`}>{(status || "pending").replaceAll("_", " ")}</small>}
                  </div>
                  {editing ? (
                    <div className="approval-edit-fields">
                      {(action.action === "create_task" || action.action === "create_reminder") && <label>Title<input value={args.title || ""} onChange={(event) => changeArgument(index, "title", event.target.value)} /></label>}
                      {(action.action === "complete_task" || action.action === "update_task") && <label>Task ID<input type="number" min="1" value={args.task_id ?? ""} onChange={(event) => changeArgument(index, "task_id", event.target.value)} /></label>}
                      {action.action === "update_task" && <label>New title<input value={args.title || ""} onChange={(event) => changeArgument(index, "title", event.target.value)} placeholder="Leave blank to keep current title" /></label>}
                      {(action.action === "create_task" || action.action === "update_task") && <label>Description<textarea rows="2" value={args.description || ""} onChange={(event) => changeArgument(index, "description", event.target.value)} placeholder="Optional description" /></label>}
                      {action.action === "create_reminder" && <label>Reminder time<input type="datetime-local" value={(args.reminder_time || "").replace(" ", "T").slice(0, 16)} onChange={(event) => changeArgument(index, "reminder_time", event.target.value.replace("T", " "))} /></label>}
                    </div>
                  ) : (
                    <>
                      <strong className="approval-action-title">{actionTitle(action)}</strong>
                      {args.description && <p className="approval-action-description">{args.description}</p>}
                      {args.reminder_time && <p className="approval-action-meta"><Clock3 size={12} />{args.reminder_time}</p>}
                      {args.task_id && <p className="approval-action-meta">Task #{args.task_id}</p>}
                      {!pending && ["completed", "failed", "skipped", "stale"].includes(status) && <p className={`approval-action-result ${status}`}>{actionMessage(action)}</p>}
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="approval-empty"><Check size={15} />No additional actions are necessary.</div>
      )}

      {approval.message && <div className="approval-rationale"><strong>{pending ? "Planner rationale" : "Update"}</strong><p>{approval.message}</p></div>}

      {pending && (
        <div className="approval-actions-footer">
          {editing ? (
            <>
              <button className="button secondary" onClick={() => setEditing(false)} disabled={Boolean(busy)}><X size={13} />Cancel</button>
              <button className="button primary" onClick={saveChanges} disabled={Boolean(busy) || !draft.length}>{busy === "edit" ? <Loader2 size={13} className="spin" /> : <Save size={13} />}{busy === "edit" ? "Saving…" : "Save changes"}</button>
            </>
          ) : (
            <>
              <button className="button secondary reject-button" onClick={onReject} disabled={Boolean(busy)}>{busy === "reject" ? <Loader2 size={13} className="spin" /> : <X size={13} />}Reject</button>
              <button className="button secondary" onClick={beginEdit} disabled={Boolean(busy)}><Pencil size={13} />Edit</button>
              <button className="button primary" onClick={onApprove} disabled={Boolean(busy) || !approval.actions?.length}>{busy === "approve" ? <Loader2 size={13} className="spin" /> : <Check size={13} />}{busy === "approve" ? "Executing…" : "Approve plan"}</button>
            </>
          )}
        </div>
      )}
      {!pending && approval.status === "rejected" && approval.rejection_reason && <p className="approval-rejection-reason">Reason: {approval.rejection_reason}</p>}
      {approval.status === "stale" && (
        <div className="approval-actions-footer">
          <button className="button primary" onClick={onRefresh} disabled={Boolean(busy)}>
            {busy === "review" ? <Loader2 size={13} className="spin" /> : <ShieldCheck size={13} />}
            {busy === "review" ? "Refreshing…" : "Prepare refreshed plan"}
          </button>
        </div>
      )}
    </section>
  );
}
