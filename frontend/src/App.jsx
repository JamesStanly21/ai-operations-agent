import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Bell,
  Bot,
  CheckSquare2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Globe2,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  Users,
  Workflow,
  X,
} from "lucide-react";
import WorkflowsPage from "./pages/WorkflowsPage.jsx";
import {
  ActivityHistoryPage,
  AgentWorkspacePage,
  DashboardPage,
  PlaceholderPage,
  RemindersPage,
  TasksPage,
} from "./pages/OperationsPages.jsx";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const navigation = [
  {
    label: "WORKSPACE",
    items: [
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
      { id: "agent", label: "AI Operations Agent", icon: Bot, badge: "AI" },
    ],
  },
  {
    label: "MANAGE",
    items: [
      { id: "tasks", label: "Tasks", icon: CheckSquare2 },
      { id: "reminders", label: "Reminders", icon: Clock3 },
      { id: "workflows", label: "Workflows", icon: Workflow },
      { id: "risk", label: "Risk Center", icon: ShieldAlert },
      { id: "team", label: "Team", icon: Users },
      { id: "activity", label: "Activity History", icon: Activity },
      { id: "settings", label: "Settings", icon: Settings },
    ],
  },
];

const pageLabels = Object.fromEntries(
  navigation.flatMap((group) => group.items.map(({ id, label }) => [id, label])),
);

async function getJson(path, options) {
  const response = await fetch(`${API_URL}${path}`, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`);
  return data;
}

function App() {
  const [page, setPage] = useState("dashboard");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [tasks, setTasks] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [workflowDataAvailable, setWorkflowDataAvailable] = useState(null);
  const [health, setHealth] = useState("checking");
  const [dataLoading, setDataLoading] = useState(true);
  const [dataError, setDataError] = useState("");
  const [agentInstruction, setAgentInstruction] = useState("");
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  const [approval, setApproval] = useState(null);
  const [approvalBusy, setApprovalBusy] = useState("");
  const [approvalError, setApprovalError] = useState("");
  const [taskActionId, setTaskActionId] = useState(null);
  const [taskError, setTaskError] = useState("");

  const refreshData = useCallback(async () => {
    setDataLoading(true);
    setDataError("");
    const requests = await Promise.allSettled([
      getJson("/tasks"),
      getJson("/reminders"),
      getJson("/workflows"),
      getJson("/health"),
    ]);
    const errors = [];
    if (requests[0].status === "fulfilled") setTasks(requests[0].value.tasks || []);
    else errors.push("Tasks could not be loaded.");
    if (requests[1].status === "fulfilled") setReminders(requests[1].value.reminders || []);
    else errors.push("Reminders could not be loaded.");
    if (requests[2].status === "fulfilled") {
      setWorkflows(requests[2].value || []);
      setWorkflowDataAvailable(true);
    } else {
      setWorkflowDataAvailable(false);
      errors.push("Workflows could not be loaded.");
    }
    if (requests[3].status === "fulfilled") setHealth(requests[3].value.status || "healthy");
    else setHealth("offline");
    setDataError(errors.join(" "));
    setDataLoading(false);
  }, []);

  useEffect(() => {
    refreshData();
  }, [refreshData]);

  const navigate = (id) => {
    setPage(id);
    setMobileNavOpen(false);
    setNotificationsOpen(false);
  };

  const runAgent = async () => {
    if (!agentInstruction.trim() || agentLoading) return;
    setAgentLoading(true);
    setAgentResult(null);
    try {
      const data = await getJson("/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: agentInstruction.trim() }),
      });
      setAgentResult(data);
      await refreshData();
    } catch (error) {
      setAgentResult({ success: false, final_message: error.message || "Could not connect to the AI agent." });
    } finally {
      setAgentLoading(false);
    }
  };

  const reviewPlan = async () => {
    if (!agentInstruction.trim() || approvalBusy || agentLoading) return;
    setApprovalBusy("review");
    setApprovalError("");
    setApproval(null);
    try {
      const data = await getJson("/approvals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: agentInstruction.trim() }),
      });
      setApproval(data);
    } catch (error) {
      setApprovalError(error.message || "Could not prepare a plan for review.");
    } finally {
      setApprovalBusy("");
    }
  };

  const editApproval = async (actions) => {
    if (!approval || approvalBusy) return;
    setApprovalBusy("edit");
    setApprovalError("");
    try {
      const data = await getJson(`/approvals/${approval.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actions }),
      });
      setApproval(data);
      return data;
    } catch (error) {
      setApprovalError(error.message || "Could not update this proposal.");
      throw error;
    } finally {
      setApprovalBusy("");
    }
  };

  const approvePlan = async () => {
    if (!approval || approvalBusy) return;
    setApprovalBusy("approve");
    setApprovalError("");
    try {
      const data = await getJson(`/approvals/${approval.id}/approve`, { method: "POST" });
      setApproval(data);
      await refreshData();
    } catch (error) {
      setApprovalError(error.message || "Could not execute this approved plan.");
    } finally {
      setApprovalBusy("");
    }
  };

  const rejectPlan = async () => {
    if (!approval || approvalBusy) return;
    setApprovalBusy("reject");
    setApprovalError("");
    try {
      const data = await getJson(`/approvals/${approval.id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setApproval(data);
    } catch (error) {
      setApprovalError(error.message || "Could not reject this proposal.");
    } finally {
      setApprovalBusy("");
    }
  };

  const completeTask = async (taskId) => {
    setTaskActionId(taskId);
    setTaskError("");
    try {
      await getJson(`/tasks/${taskId}/complete`, { method: "POST" });
      await refreshData();
    } catch (error) {
      setTaskError(error.message || "Could not complete this task.");
    } finally {
      setTaskActionId(null);
    }
  };

  const searchTasks = (event) => {
    if (event.key === "Enter" && query.trim()) navigate("tasks");
  };

  const activePageLabel = pageLabels[page] || "Dashboard";

  return (
    <div className="app-shell">
      {mobileNavOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Sparkles size={19} /></div>
          <div className="brand-copy"><strong>OpsAgent <span>AI</span></strong><small>OPERATIONS WORKSPACE</small></div>
          <button className="mobile-close icon-button" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)}><X size={17} /></button>
        </div>

        <div className="workspace-switch">
          <div className="workspace-avatar">O</div>
          <div><strong>Operations workspace</strong><span>Local workspace</span></div>
          <ChevronDown size={15} />
        </div>

        {navigation.map((group) => (
          <div className="nav-group" key={group.label}>
            <div className="nav-label">{group.label}</div>
            <nav aria-label={group.label}>
              {group.items.map(({ id, label, icon: Icon, badge }) => (
                <button className={`nav-item ${page === id ? "active" : ""}`} key={id} onClick={() => navigate(id)}>
                  <Icon size={17} strokeWidth={1.8} />
                  <span>{label}</span>
                  {badge && <small className="nav-badge">{badge}</small>}
                </button>
              ))}
            </nav>
          </div>
        ))}

        <div className="sidebar-bottom">
          <div className="sidebar-help"><CircleHelp size={16} /><div><strong>Need a hand?</strong><span>Explore your operations workspace.</span></div></div>
          <div className="sidebar-profile">
            <div className="profile-avatar">OA</div>
            <div><strong>OpsAgent User</strong><span>Workspace member</span></div>
            <button className="icon-button profile-menu-button" aria-label="Workspace profile menu"><span>•••</span></button>
          </div>
        </div>
      </aside>

      <div className="main-wrap">
        <header className="workspace-topbar">
          <div className="topbar-left">
            <button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileNavOpen(true)}><Menu size={19} /></button>
            <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{activePageLabel}</strong></div>
          </div>
          <div className="topbar-actions">
            <label className="global-search">
              <Search size={15} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={searchTasks} placeholder="Search tasks…" aria-label="Search tasks" />
              <kbd>↵</kbd>
            </label>
            <div className="notification-wrap">
              <button className={`icon-button notification-button ${notificationsOpen ? "selected" : ""}`} onClick={() => setNotificationsOpen((open) => !open)} aria-label="Notifications"><Bell size={17} /></button>
              {notificationsOpen && <div className="notification-popover"><strong>Notifications</strong><p>No notification feed is configured for this workspace.</p></div>}
            </div>
            <div className="topbar-profile"><div className="profile-avatar small-avatar">OA</div><div><strong>OpsAgent User</strong><span>Local workspace</span></div><ChevronDown size={14} /></div>
            <label className="language-control"><Globe2 size={14} /><select aria-label="Workspace language" defaultValue="en"><option value="en">EN</option></select></label>
          </div>
        </header>

        <main className="content">
          {dataError && <div className="data-error" role="alert"><span>{dataError}</span><button className="button secondary" onClick={refreshData} disabled={dataLoading}>Retry</button></div>}
          {page === "dashboard" && <DashboardPage tasks={tasks} reminders={reminders} workflows={workflows} workflowsAvailable={workflowDataAvailable} agentResult={agentResult} loading={dataLoading} error={dataError} onRefresh={refreshData} onNavigate={navigate} onAgentRun={() => navigate("agent")} />}
          {page === "agent" && <AgentWorkspacePage instruction={agentInstruction} setInstruction={setAgentInstruction} loading={agentLoading} result={agentResult} onRun={runAgent} health={health} approval={approval} approvalBusy={approvalBusy} approvalError={approvalError} onReview={reviewPlan} onApprovePlan={approvePlan} onRejectPlan={rejectPlan} onEditPlan={editApproval} />}
          {page === "tasks" && <TasksPage tasks={tasks} loading={dataLoading} query={query} taskError={taskError} actionId={taskActionId} onComplete={completeTask} onRefresh={refreshData} onAgent={() => navigate("agent")} />}
          {page === "reminders" && <RemindersPage reminders={reminders} loading={dataLoading} onRefresh={refreshData} />}
          {page === "workflows" && <WorkflowsPage apiUrl={API_URL} />}
          {page === "risk" && <PlaceholderPage page="risk" tasks={tasks} workflows={workflows} workflowsAvailable={workflowDataAvailable} />}
          {page === "team" && <PlaceholderPage page="team" />}
          {page === "activity" && <ActivityHistoryPage agentResult={agentResult} workflows={workflows} workflowsAvailable={workflowDataAvailable} />}
          {page === "settings" && <PlaceholderPage page="settings" health={health} />}
          <footer className="workspace-footer"><span>OpsAgent AI</span><span>•</span><span>Operations workspace</span><span className={`footer-health ${health === "healthy" ? "online" : ""}`}><i />{health === "healthy" ? "Backend connected" : health === "checking" ? "Checking backend" : "Backend unavailable"}</span></footer>
        </main>
      </div>
    </div>
  );
}

export default App;
