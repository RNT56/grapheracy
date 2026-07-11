import type {
  ApiAgentContextBlobContent,
  ApiAgentContextGraph,
  ApiAgentContextSession
} from "./workspaceTypes";

function formatShortDate(value?: string | null) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return value;
  }
}

export function AgentContextWorkspace({
  sessions,
  selectedSessionId,
  selectedArtifactId,
  graph,
  artifactContent,
  artifactContentLoading,
  artifactContentError,
  loading,
  onSelectSession,
  onSelectArtifact,
  onRefresh
}: {
  sessions: ApiAgentContextSession[];
  selectedSessionId?: string;
  selectedArtifactId?: string;
  graph?: ApiAgentContextGraph;
  artifactContent?: ApiAgentContextBlobContent;
  artifactContentLoading: boolean;
  artifactContentError: boolean;
  loading: boolean;
  onSelectSession: (sessionId: string) => void;
  onSelectArtifact: (artifactId: string | undefined) => void;
  onRefresh: () => void;
}) {
  const selectedSession = sessions.find((session) => session.id === selectedSessionId) ?? sessions[0];
  const events = graph?.events ?? [];
  const artifacts = graph?.artifacts ?? [];
  const selectedArtifact = artifacts.find((artifact) => artifact.id === selectedArtifactId);
  const gatewayCount = events.filter((event) => event.authority === "gateway").length;
  const adapterCount = events.filter((event) => event.authority === "adapter_reported").length;
  const passiveCount = events.filter((event) => event.authority === "passive_reconciled").length;
  const promptEvents = events.filter((event) => ["prompt_built", "model_request", "model_response"].includes(event.event_kind));
  const editEvents = events.filter((event) => ["edit_applied", "diff_observed", "commit_observed"].includes(event.event_kind));

  return (
    <section className="agent-context-workspace" aria-label="Active agent context">
      <header className="workspace-head compact">
        <div>
          <p>Active context</p>
          <h2>{selectedSession?.title ?? "No captured sessions"}</h2>
          <span>
            {selectedSession
              ? `${selectedSession.runtime_kind} / ${selectedSession.status} / ${selectedSession.authority.replaceAll("_", " ")}`
              : "Waiting for adapter sessions"}
          </span>
        </div>
        <button type="button" className="provider-save-settings" onClick={onRefresh}>
          Refresh
        </button>
      </header>

      <div className="agent-context-grid">
        <aside className="agent-context-sessions" aria-label="Captured sessions">
          <div className="context-section-head">
            <div>
              <span>Sessions</span>
              <strong>{sessions.length}</strong>
            </div>
          </div>
          <div className="agent-context-session-list">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                aria-pressed={session.id === selectedSession?.id}
                onClick={() => onSelectSession(session.id)}
              >
                <strong>{session.title}</strong>
                <span>{session.runtime_kind} / {session.status}</span>
                <small>{formatShortDate(session.updated_at)}</small>
              </button>
            ))}
            {sessions.length === 0 && <div className="outline-empty">No agent context sessions captured.</div>}
          </div>
        </aside>

        <section className="agent-context-main" aria-label="Context graph and timeline">
          <div className="agent-context-metrics" aria-label="Active context metrics">
            <span><strong>{events.length}</strong> events</span>
            <span><strong>{artifacts.length}</strong> artifacts</span>
            <span><strong>{gatewayCount}</strong> gateway</span>
            <span><strong>{adapterCount + passiveCount}</strong> reconciled</span>
          </div>

          <div className="agent-context-panels">
            <article className="agent-context-card" aria-label="Context graph projection">
              <div className="context-section-head">
                <div>
                  <span>Context graph</span>
                  <strong>{graph?.nodes.length ?? 0}.{graph?.edges.length ?? 0}</strong>
                </div>
              </div>
              <div className="context-projection-list">
                {(graph?.edges ?? []).slice(0, 12).map((edge) => {
                  const source = graph?.nodes.find((node) => node.id === edge.source_id);
                  const target = graph?.nodes.find((node) => node.id === edge.target_id);
                  return (
                    <div key={edge.id} className={edge.observed ? "is-observed" : "is-inferred"}>
                      <span>{source?.label ?? edge.source_id}</span>
                      <strong>{edge.relation.replaceAll("_", " ")}</strong>
                      <span>{target?.label ?? edge.target_id}</span>
                    </div>
                  );
                })}
                {loading && <div className="outline-empty">Loading active context.</div>}
                {!loading && (graph?.edges.length ?? 0) === 0 && <div className="outline-empty">No context graph edges yet.</div>}
              </div>
            </article>

            <article className="agent-context-card" aria-label="Prompt and edit activity">
              <div className="context-section-head">
                <div>
                  <span>Prompt and edits</span>
                  <strong>{promptEvents.length}.{editEvents.length}</strong>
                </div>
              </div>
              <div className="agent-context-badge-row">
                {promptEvents.slice(0, 6).map((event) => (
                  <span key={event.id} className={`authority-${event.authority}`}>
                    {event.event_kind.replaceAll("_", " ")}
                  </span>
                ))}
                {editEvents.slice(0, 6).map((event) => (
                  <span key={event.id} className={`authority-${event.authority}`}>
                    {event.event_kind.replaceAll("_", " ")}
                  </span>
                ))}
                {promptEvents.length + editEvents.length === 0 && <span>No prompt or edit events.</span>}
              </div>
            </article>

            <article className="agent-context-card agent-context-inspector" aria-label="Content inspector">
              <div className="context-section-head">
                <div>
                  <span>Content inspector</span>
                  <strong>{selectedArtifact?.title ?? "None"}</strong>
                </div>
              </div>
              {selectedArtifact ? (
                <div className="agent-context-inspector-body">
                  <div className="agent-context-badge-row">
                    <span>{selectedArtifact.kind}</span>
                    <span>{selectedArtifact.content_type}</span>
                    {artifactContent?.blob && <span>{artifactContent.blob.redaction_status.replaceAll("_", " ")}</span>}
                    {artifactContent?.blob && <span>{artifactContent.blob.encryption_status.replaceAll("_", " ")}</span>}
                  </div>
                  <small>{selectedArtifact.path ?? selectedArtifact.uri ?? selectedArtifact.id}</small>
                  {artifactContentLoading && <div className="outline-empty">Loading artifact content.</div>}
                  {artifactContentError && (
                    <div className="outline-empty">Content requires maintainer access or is no longer retained.</div>
                  )}
                  {!artifactContentLoading && !artifactContentError && artifactContent?.text && (
                    <pre>{artifactContent.text}</pre>
                  )}
                  {!artifactContentLoading && !artifactContentError && artifactContent && !artifactContent.text && (
                    <div className="outline-empty">Metadata-only artifact. Text content was binary, oversized, or purged.</div>
                  )}
                </div>
              ) : (
                <div className="outline-empty">Select an event artifact to inspect retained content.</div>
              )}
            </article>
          </div>

          <div className="agent-context-timeline" aria-label="Active context timeline">
            {events.slice().reverse().slice(0, 20).map((event) => {
              const artifact = artifacts.find((item) => item.id === event.artifact_id);
              return (
                <article key={event.id} className={`agent-context-event authority-${event.authority}`}>
                  <span>{event.event_kind.replaceAll("_", " ")}</span>
                  <strong>{event.summary}</strong>
                  <small>
                    {event.authority.replaceAll("_", " ")}
                    {artifact ? ` / ${artifact.path ?? artifact.title}` : ""}
                  </small>
                  {artifact && (
                    <button
                      type="button"
                      className="agent-context-artifact-button"
                      aria-pressed={artifact.id === selectedArtifactId}
                      onClick={() => onSelectArtifact(artifact.id === selectedArtifactId ? undefined : artifact.id)}
                    >
                      Inspect artifact
                    </button>
                  )}
                </article>
              );
            })}
            {!loading && events.length === 0 && <div className="outline-empty">No active context events yet.</div>}
          </div>
        </section>
      </div>
    </section>
  );
}
