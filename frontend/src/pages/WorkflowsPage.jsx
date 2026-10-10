import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  Circle,
  Clock3,
  Loader2,
  Play,
  RefreshCw,
  Workflow,
  X,
} from "lucide-react";
import "./WorkflowsPage.css";

const statusIcons = {
  completed: Check,
  running: Circle,
  pending: Circle,
  failed: X,
};

function latestRun(detail) {
  if (!detail) return null;
  if (detail.run) return { run: detail.run, steps: detail.steps || [] };
  return detail.runs?.[detail.runs.length - 1] || null;
}

function dateLabel(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function stepResult(step) {
  const result = step.result;
  if (!result) return "No result returned.";
  const inner = result.result;
  if (inner && typeof inner === "object" && inner.message) return inner.message;
  if (result.message) return result.message;
  if (result.error) return result.error;
  return JSON.stringify(result, null, 2);
}

function relatedResources(step) {
  if (!step.resource_refs?.length) return [];
  const tool = step.action || "";
  const kind = tool.includes("task") ? "Task" : tool.includes("reminder") ? "Reminder" : "Resource";
  return step.resource_refs.map((ref) => `${kind} #${ref}`);
}

export default function WorkflowsPage({ apiUrl }) {
  const [workflows, setWorkflows] = useState([]);
  const [details, setDetails] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const selectedIdRef = useRef(null);
  const [objective, setObjective] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadingDetailId, setLoadingDetailId] = useState(null);
  const [error, setError] = useState("");

  const loadWorkflows = useCallback(async (preferredId = null) => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/workflows`);
      if (!response.ok) throw new Error("Could not load workflows from the backend.");
      const items = await response.json();
      setWorkflows(items);

      const entries = await Promise.all(items.map(async (workflow) => {
        try {
          const detailResponse = await fetch(`${apiUrl}/workflows/${workflow.id}`);
          if (!detailResponse.ok) return [workflow.id, null];
          return [workflow.id, await detailResponse.json()];
        } catch {
          return [workflow.id, null];
        }
      }));
      const nextDetails = Object.fromEntries(entries.filter(([, detail]) => detail));
      setDetails(nextDetails);
      const nextSelectedId = preferredId && items.some((item) => item.id === preferredId)
        ? preferredId
        : selectedIdRef.current && items.some((item) => item.id === selectedIdRef.current)
          ? selectedIdRef.current
          : items[0]?.id || null;
      selectedIdRef.current = nextSelectedId;
      setSelectedId(nextSelectedId);
    } catch (loadError) {
      setError(loadError.message || "Could not connect to the workflow API.");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    loadWorkflows();
  }, [loadWorkflows]);

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedId) || null,
    [workflows, selectedId],
  );
  const selectedDetail = details[selectedId] || null;
  const selectedRun = latestRun(selectedDetail);
  const selectedSteps = selectedRun?.steps || [];

  const startWorkflow = async (event) => {
    event.preventDefault();
    const trimmedObjective = objective.trim();
    if (!trimmedObjective || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: trimmedObjective }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not start this workflow.");
      setObjective("");
      await loadWorkflows(data.workflow?.id || null);
    } catch (submitError) {
      setError(submitError.message || "Could not start this workflow.");
    } finally {
      setSubmitting(false);
    }
  };

  const selectWorkflow = async (workflow) => {
    selectedIdRef.current = workflow.id;
    setSelectedId(workflow.id);
    if (details[workflow.id]) return;
    setLoadingDetailId(workflow.id);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/workflows/${workflow.id}`);
      if (!response.ok) throw new Error("Could not load this workflow’s details.");
      const detail = await response.json();
      setDetails((current) => ({ ...current, [workflow.id]: detail }));
    } catch (detailError) {
      setError(detailError.message || "Could not load workflow details.");
    } finally {
      setLoadingDetailId(null);
    }
  };

  return (
    <>
      <header className="topbar dashboard-header workflows-header">
        <div>
          <div className="eyebrow">WORKSPACE</div>
          <h1>Workflows</h1>
          <p>Turn an objective into an agent-run sequence of tracked actions.</p>
        </div>
        <button className="refresh-button" onClick={() => loadWorkflows()} disabled={loading || submitting}>
          <RefreshCw size={15} className={loading ? "spin" : ""} />
          Refresh
        </button>
      </header>

      <form className="workflow-start-card" onSubmit={startWorkflow}>
        <div className="workflow-start-copy">
          <div className="workflow-start-icon"><Workflow size={20} /></div>
          <div><h2>Start a workflow</h2><p>Describe the outcome you want the agent to handle.</p></div>
        </div>
        <div className="workflow-form-row">
          <input
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            placeholder="e.g. Prepare my hackathon presentation for tomorrow"
            aria-label="Workflow objective"
            disabled={submitting}
          />
          <button className="workflow-submit-button" type="submit" disabled={!objective.trim() || submitting}>
            {submitting ? <Loader2 size={16} className="spin" /> : <Play size={15} fill="currentColor" />}
            {submitting ? "Running…" : "Start Workflow"}
          </button>
        </div>
      </form>

      {error && <div className="workflow-error" role="alert"><AlertCircle size={16} />{error}</div>}

      <div className="workflow-layout">
        <section className="dashboard-panel workflow-list-panel">
          <div className="panel-heading">
            <div><h2>Workflow history</h2><p>Objectives handled by the operations agent</p></div>
            <span className="item-count">{workflows.length} {workflows.length === 1 ? "workflow" : "workflows"}</span>
          </div>
          {loading ? (
            <div className="workflow-inline-loading"><Loader2 size={17} className="spin" /> Loading workflows…</div>
          ) : workflows.length === 0 ? (
            <div className="dashboard-empty workflow-list-empty"><div className="empty-icon"><Workflow size={23} /></div><h3>No workflows yet</h3><p>Start a workflow above to see its progress here.</p></div>
          ) : (
            <div className="workflow-list">
              {workflows.map((workflow) => {
                const runData = latestRun(details[workflow.id]);
                const steps = runData?.steps || [];
                const completed = steps.filter((step) => step.status === "completed").length;
                return (
                  <button
                    type="button"
                    className={`workflow-list-item ${workflow.id === selectedId ? "selected" : ""}`}
                    key={workflow.id}
                    onClick={() => selectWorkflow(workflow)}
                  >
                    <div className="workflow-list-topline">
                      <span className="workflow-list-title">{workflow.title}</span>
                      <StatusBadge status={workflow.status} />
                    </div>
                    <p>{workflow.objective}</p>
                    <div className="workflow-list-meta">
                      <span>{completed} / {steps.length} steps</span>
                      <span>Updated {dateLabel(workflow.updated_at)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <section className="dashboard-panel workflow-detail-panel">
          {!selectedWorkflow ? (
            <div className="dashboard-empty"><div className="empty-icon"><Workflow size={23} /></div><h3>Select a workflow</h3><p>Choose a workflow from the list to inspect its execution steps.</p></div>
          ) : !selectedDetail && (loading || loadingDetailId === selectedWorkflow.id) ? (
            <div className="workflow-inline-loading"><Loader2 size={17} className="spin" /> Loading workflow details…</div>
          ) : !selectedDetail ? (
            <div className="dashboard-empty"><div className="empty-icon"><AlertCircle size={23} /></div><h3>Details unavailable</h3><p>Could not load this workflow’s steps. Refresh to try again.</p></div>
          ) : (
            <>
              <div className="workflow-detail-heading">
                <div className="workflow-detail-title-row">
                  <div className="workflow-detail-icon"><Workflow size={18} /></div>
                  <div><div className="eyebrow">WORKFLOW DETAIL</div><h2>{selectedWorkflow.title}</h2></div>
                </div>
                <StatusBadge status={selectedWorkflow.status} />
              </div>
              <div className="workflow-detail-meta">
                <span>Created {dateLabel(selectedWorkflow.created_at)}</span>
                <span>Updated {dateLabel(selectedWorkflow.updated_at)}</span>
              </div>
              <div className="workflow-objective"><span>Objective</span><p>{selectedWorkflow.objective}</p></div>
              {selectedRun?.run?.final_message && <div className="workflow-final-message">{selectedRun.run.final_message}</div>}
              <div className="workflow-steps-heading"><h3>Execution steps</h3><span>{selectedSteps.filter((step) => step.status === "completed").length} / {selectedSteps.length} completed</span></div>
              {selectedSteps.length === 0 ? (
                <div className="workflow-no-steps">No tool actions were recorded for this workflow.</div>
              ) : (
                <ol className="workflow-timeline">
                  {selectedSteps.map((step, index) => <WorkflowStep key={step.id} step={step} index={index} />)}
                </ol>
              )}
            </>
          )}
        </section>
      </div>
    </>
  );
}

function StatusBadge({ status = "pending" }) {
  return <span className={`workflow-status-badge workflow-status-${status.replaceAll("_", "-")}`}>{status.replaceAll("_", " ")}</span>;
}

function WorkflowStep({ step, index }) {
  const Icon = statusIcons[step.status] || Circle;
  const refs = relatedResources(step);
  return (
    <li className={`workflow-step workflow-step-${step.status}`}>
      <div className="workflow-step-marker" aria-label={step.status}>
        <Icon size={15} strokeWidth={step.status === "completed" ? 3 : 2.25} />
      </div>
      <article className="workflow-step-card">
        <div className="workflow-step-topline">
          <div><span className="workflow-step-number">Step {index + 1}</span><h4>{step.title}</h4></div>
          <StatusBadge status={step.status} />
        </div>
        <div className="workflow-step-action">{step.action?.replaceAll("_", " ")}</div>
        {step.error ? <div className="workflow-step-error"><AlertCircle size={14} />{step.error}</div> : <pre className="workflow-step-result">{stepResult(step)}</pre>}
        {refs.length > 0 && <div className="workflow-resource-refs">{refs.map((ref) => <span key={ref}>{ref}</span>)}</div>}
        {step.started_at && <div className="workflow-step-time"><Clock3 size={12} />{dateLabel(step.finished_at || step.started_at)}</div>}
      </article>
    </li>
  );
}
