import type {
  AgentToolKind,
  ApiAgentCitation,
  ApiAgentRun,
  ApiAgentToolCall,
  ApiPlanningMessage,
  ApiPlanningSession,
  ApiProviderDescriptor
} from "./workspaceTypes";

function BlueprintMap({
  topics,
  openQuestions,
  researchTasks
}: {
  topics: Array<{ name?: string; priority?: string }>;
  openQuestions: string[];
  researchTasks: Array<{ query?: string; source_policy?: string; priority?: string }>;
}) {
  const visibleTopics = topics.length > 0 ? topics.slice(0, 4) : [{ name: "Goal", priority: "seed" }];
  const visibleQuestions = openQuestions.slice(0, 3);
  const visibleTasks = researchTasks.length > 0 ? researchTasks.slice(0, 3) : [{ query: "Seed research", source_policy: "mixed" }];

  return (
    <div className="blueprint-map" aria-label="Graph build map">
      <div className="blueprint-cluster blueprint-cluster-topics">
        <p className="eyebrow">Topics</p>
        {visibleTopics.map((topic, index) => (
          <span key={`${topic.name}-${index}`}>{topic.name ?? "Topic"}</span>
        ))}
      </div>
      <div className="blueprint-core">
        <strong>Graph spec</strong>
        <span>citation-gated</span>
      </div>
      <div className="blueprint-cluster blueprint-cluster-questions">
        <p className="eyebrow">Questions</p>
        {visibleQuestions.length > 0
          ? visibleQuestions.map((question) => <span key={question}>{question}</span>)
          : <span>Clarify unknowns</span>}
      </div>
      <div className="blueprint-cluster blueprint-cluster-tasks">
        <p className="eyebrow">Research</p>
        {visibleTasks.map((task, index) => (
          <span key={`${task.query}-${index}`}>{task.query ?? "Research task"}</span>
        ))}
      </div>
    </div>
  );
}


export function PlanningWorkspace({
  goal,
  message,
  providerList,
  selectedSession,
  sessions,
  createPending,
  sendPending,
  onGoalChange,
  onMessageChange,
  onCreateSession,
  onSendMessage,
  onSelectSession,
  onOpenSettings,
  onRunResearch
}: {
  goal: string;
  message: string;
  providerList: ApiProviderDescriptor[];
  selectedSession?: ApiPlanningSession;
  sessions: ApiPlanningSession[];
  createPending: boolean;
  sendPending: boolean;
  onGoalChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onCreateSession: () => void;
  onSendMessage: () => void;
  onSelectSession: (id: string) => void;
  onOpenSettings: () => void;
  onRunResearch: (query: string) => void;
}) {
  const buildSpec = selectedSession?.build_spec;
  const openQuestions = buildSpec?.spec.open_questions ?? [];
  const researchTasks = buildSpec?.spec.research_tasks ?? [];
  const topics = buildSpec?.spec.topics ?? [];

  return (
    <section className="planning-workspace" aria-label="Planning Mode">
      <aside className="panel planning-rail" aria-label="Planning sessions">
        <div className="panel-head planning-rail-head">
          <span>
            Planning
            <small>{sessions.length} session{sessions.length === 1 ? "" : "s"}</small>
          </span>
          <button type="button" disabled={createPending || !goal.trim()} onClick={onCreateSession}>New</button>
        </div>
        <div className="planning-view-tabs" role="tablist" aria-label="Planning view">
          <button type="button" role="tab" aria-selected="true">
            Sessions
          </button>
          <button type="button" role="tab" aria-selected="false" onClick={onOpenSettings}>
            Settings
          </button>
        </div>
        <div className="planning-session-list">
          {sessions.map((session) => (
            <button
              className="planning-session-row"
              key={session.id}
              type="button"
              aria-pressed={session.id === selectedSession?.id}
              onClick={() => onSelectSession(session.id)}
            >
              <strong>{session.title}</strong>
              <span>{session.messages.length} turns / {session.lens}</span>
            </button>
          ))}
          {sessions.length === 0 && <span className="source-content-empty">No planning sessions yet.</span>}
        </div>
      </aside>

      <section className="panel planning-chat" aria-label="Planning Mode conversation">
	        <div className="planning-chat-head">
	          <div>
	            <p className="eyebrow">Planning Mode</p>
	            <h2>{selectedSession?.title ?? "New graph plan"}</h2>
	          </div>
	        </div>
        <label className="planning-goal">
          Goal
          <textarea value={goal} onChange={(event) => onGoalChange(event.target.value)} />
        </label>
        <div className="planning-thread" aria-label="Planning conversation messages">
          {(selectedSession?.messages ?? []).map((item) => (
            <article className={`planning-message planning-message-${item.role}`} key={item.id}>
              <span>{item.role}</span>
              <p>{item.content}</p>
              {planningMessageToolCalls(item).length > 0 && (
                <div className="planning-tool-stack" aria-label="Agent activity">
                  {planningMessageToolCalls(item).map((toolCall) => (
                    <AgentToolCallCard toolCall={toolCall} key={toolCall.id} />
                  ))}
                </div>
              )}
            </article>
          ))}
          {!selectedSession?.messages.length && (
            <article className="planning-message planning-message-system">
              <span>system</span>
              <p>No planning turns yet.</p>
            </article>
          )}
        </div>
        <form
          className="planning-composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (message.trim()) onSendMessage();
          }}
        >
          <input value={message} onChange={(event) => onMessageChange(event.target.value)} placeholder="Ask the agent to read, research, or plan" />
          <button type="submit" disabled={sendPending || !message.trim()}>Send</button>
          <button type="button" disabled={!goal.trim()} onClick={() => onRunResearch(goal)}>Research</button>
        </form>
      </section>

      <aside className="panel planning-preview" aria-label="Artifact Preview">
        <div className="panel-head">
          <span>Artifact Preview</span>
          <strong>{buildSpec?.status ?? "draft"}</strong>
	        </div>
	        <div className="planning-preview-body">
	          <section className="blueprint-panel" aria-label="AI-native graph blueprint">
	            <div className="blueprint-head">
	              <div>
	                <p className="eyebrow">AI-native blueprint</p>
	                <strong>{buildSpec?.title ?? selectedSession?.title ?? "Draft graph"}</strong>
	              </div>
	              <span>{topics.length} topics / {openQuestions.length} questions / {researchTasks.length} tasks</span>
	            </div>
	            <BlueprintMap topics={topics} openQuestions={openQuestions} researchTasks={researchTasks} />
	            <div className="blueprint-lifecycle" aria-label="Graph build lifecycle">
	              <span>Plan</span>
	              <span>Research</span>
	              <span>Propose</span>
	              <span>Review</span>
	            </div>
	          </section>
	          <section>
	            <p className="eyebrow">Providers</p>
            <div className="provider-strip">
              {providerList.map((provider) => (
                <span className={provider.enabled ? "is-enabled" : ""} key={provider.id}>
                  {provider.label}
                </span>
              ))}
            </div>
          </section>
          <section>
            <p className="eyebrow">Topics</p>
            {topics.slice(0, 5).map((topic, index) => (
              <div className="preview-line" key={`${topic.name}-${index}`}>
                <strong>{topic.name ?? "Topic"}</strong>
                <span>{topic.priority ?? "review"}</span>
              </div>
            ))}
            {topics.length === 0 && <span className="source-content-empty">Build spec topics will appear here.</span>}
          </section>
          <section>
            <p className="eyebrow">Open questions</p>
            {openQuestions.slice(0, 4).map((question) => (
              <div className="preview-line" key={question}>
                <span>{question}</span>
              </div>
            ))}
          </section>
          <section>
            <p className="eyebrow">Research tasks</p>
            {researchTasks.slice(0, 4).map((task, index) => (
              <button className="preview-line preview-action" type="button" key={`${task.query}-${index}`} onClick={() => task.query && onRunResearch(task.query)}>
                <strong>{task.query ?? "Research task"}</strong>
                <span>{task.source_policy ?? "mixed"}</span>
              </button>
            ))}
            {researchTasks.length === 0 && (
              <button className="preview-line preview-action" type="button" onClick={() => onRunResearch(goal)}>
                <strong>Run seed research</strong>
                <span>mixed</span>
              </button>
            )}
          </section>
        </div>
      </aside>
    </section>
  );
}

function planningMessageToolCalls(message: ApiPlanningMessage): ApiAgentToolCall[] {
  if (message.role !== "assistant") return [];
  const metadata = isRecord(message.metadata) ? message.metadata : {};
  const buildSpec = isRecord(metadata.buildSpec) ? metadata.buildSpec : undefined;
  if (!buildSpec) return [];
  const openQuestions = Array.isArray(buildSpec.open_questions) ? buildSpec.open_questions : [];
  const researchTasks = Array.isArray(buildSpec.research_tasks) ? buildSpec.research_tasks : [];
  const topics = Array.isArray(buildSpec.topics) ? buildSpec.topics : [];
  const calls: ApiAgentToolCall[] = [
    {
      id: `${message.id}-graph-query`,
      kind: "graph_query",
      input: { message_id: message.id },
      status: "succeeded",
      citations: [],
      affected_graph_ids: [],
      summary: `Mapped ${topics.length} topics and ${openQuestions.length} open questions.`
    }
  ];
  if (researchTasks.length > 0) {
    calls.push({
      id: `${message.id}-research`,
      kind: "research_run",
      input: { tasks: researchTasks.slice(0, 3) },
      status: "pending_review",
      citations: [],
      affected_graph_ids: [],
      summary: `${researchTasks.length} research task${researchTasks.length === 1 ? "" : "s"} ready for review.`
    });
  }
  calls.push({
    id: `${message.id}-proposal`,
    kind: "proposal_create",
    input: { artifact: "graph_build_spec" },
    status: "pending_review",
    citations: [],
    affected_graph_ids: [],
    summary: "Graph build spec is available as a reviewable artifact."
  });
  return calls;
}

export function AgentToolCallCard({ toolCall }: { toolCall: ApiAgentToolCall }) {
  return (
    <article className={`agent-tool-card agent-tool-${toolCall.status}`}>
      <div>
        <span>{toolKindLabel(toolCall.kind)}</span>
        <strong>{toolStatusLabel(toolCall.status)}</strong>
      </div>
      <p>{toolCall.summary ?? "Agent activity recorded."}</p>
      <footer>
        <span>{toolCall.citations.length} citations</span>
        <span>{toolCall.affected_graph_ids.length} affected</span>
      </footer>
    </article>
  );
}

export function agentRunToolCalls(run: ApiAgentRun): ApiAgentToolCall[] {
  if (run.tool_calls?.length) return run.tool_calls;
  const status = run.status === "waiting_for_review" ? "pending_review" : run.status === "failed" ? "failed" : "succeeded";
  const kind: AgentToolKind =
    run.kind === "research"
      ? "research_run"
      : run.kind === "action_apply"
        ? "review_action"
        : "graph_query";
  const proposalIds = Array.isArray(run.output.proposal_ids) ? run.output.proposal_ids.filter((item): item is string => typeof item === "string") : [];
  const affectedGraphIds = [
    typeof run.output.source_id === "string" ? run.output.source_id : undefined,
    ...proposalIds
  ].filter((item): item is string => Boolean(item));
  return [
    {
      id: `${run.id}-tool`,
      kind,
      input: {},
      status,
      citations: Array.isArray(run.output.citations) ? run.output.citations as ApiAgentCitation[] : [],
      affected_graph_ids: affectedGraphIds,
      resulting_proposal_id: proposalIds[0],
      summary:
        typeof run.output.answer === "string"
          ? run.output.answer
          : typeof run.output.message === "string"
            ? run.output.message
            : `${toolKindLabel(kind)} completed.`
    }
  ];
}

function toolKindLabel(kind: AgentToolKind) {
  if (kind === "graph_query") return "Graph query";
  if (kind === "source_search") return "Source search";
  if (kind === "source_open") return "Source read";
  if (kind === "research_run") return "Research";
  if (kind === "proposal_create") return "Graph proposal";
  if (kind === "review_action") return "Review action";
  if (kind === "connector_sync") return "Connector sync";
  return "Graph layout";
}

function toolStatusLabel(status: ApiAgentToolCall["status"]) {
  if (status === "pending_review") return "Review";
  if (status === "running") return "Running";
  if (status === "succeeded") return "Done";
  if (status === "failed") return "Failed";
  return "Blocked";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
