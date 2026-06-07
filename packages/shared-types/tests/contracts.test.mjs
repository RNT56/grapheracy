import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("shared contracts expose required public interfaces", async () => {
  const source = await readFile(new URL("../src/index.ts", import.meta.url), "utf8");
  for (const name of [
    "GraphProject",
    "Topic",
    "Source",
    "ContentNode",
    "SemanticEdge",
    "IngestionRun",
    "ExtractionProposal",
    "ReviewDecision",
    "ContentEmbedding",
    "ExtractionLensDescriptor",
    "GraphLensDescriptor",
    "GraphInsights",
    "GraphNeighborhood",
    "GraphPath",
    "ReviewQueueItem",
    "ReviewQueue",
    "ReviewDashboard",
    "ReviewActivityItem",
    "ReviewActivity",
    "SourceReviewSummary",
    "SourceReviewCoverage",
    "GraphSettings",
    "ConnectorAccount",
    "ConnectorTarget",
    "ConnectorSyncRun",
    "SourceChunk",
    "Provenance",
    "PlanningSession",
    "PlanningMessage",
    "GraphBuildSpec",
    "AgentRun",
    "AgentStep",
    "ResearchTask",
    "GraphQueryRequest",
    "GraphQueryAnswer",
    "AgentCitation",
    "AgentActionProposal",
    "FocusTarget",
    "AgentToolCall",
    "AgentGeneratedArtifact",
    "GraphObjectRef",
    "GraphVisualState",
    "GraphTooltipModel",
    "GraphActivityEvent",
    "Signal",
    "Observation",
    "Alert",
    "AttentionItem",
    "Owner",
    "RoutingPolicy",
    "DecisionRecord",
    "ActionSafetyMetadata",
    "ActionProposal",
    "ActionRun",
    "Outcome",
    "FeedbackEvent",
    "ProviderDescriptor",
    "ProviderModelDescriptor"
  ]) {
    assert.match(source, new RegExp(`interface ${name}`));
  }
  assert.match(source, /NODE_KIND_DEFINITIONS/);
  assert.match(source, /ContentNodeKind/);
  assert.match(source, /normalizeContentNodeKind/);
  assert.match(source, /NODE_KIND_ALIASES/);
  for (const nodeKind of ["topic", "source", "dataset", "api", "repository", "module", "package", "file", "symbol", "policy", "vendor", "incident", "project", "owner", "review_cycle", "workflow", "process", "requirement", "risk", "metric", "event", "task", "team", "product", "feature", "asset", "location"]) {
    assert.match(source, new RegExp(`id: "${nodeKind}"`));
  }
  assert.match(source, /ExtractionLensId/);
  assert.match(source, /GraphLensId/);
  assert.match(source, /ProviderId/);
  assert.match(source, /AgentRunStatus/);
  assert.match(source, /AgentRunMode/);
  assert.match(source, /FocusTargetKind/);
  assert.match(source, /AgentToolKind/);
  assert.match(source, /AgentToolStatus/);
  assert.match(source, /ReviewWorkItemKind/);
  assert.match(source, /GraphVisualStatus/);
  assert.match(source, /GraphActivityEventKind/);
  assert.match(source, /GraphActivityEventStatus/);
  assert.match(source, /GraphActivityEventId/);
  for (const status of ["hover", "focus", "related", "dimmed", "scanning", "cited", "incoming", "candidate", "ready", "blocked", "accepted", "rejected", "edited", "deferred", "stale", "sensed", "routed", "assigned", "sla_at_risk", "action_proposed", "action_running", "outcome_waiting", "outcome_succeeded", "outcome_failed", "feedback_applied", "reopened"]) {
    assert.match(source, new RegExp(`"${status}"`));
  }
  for (const eventKind of ["agent_scan", "source_incoming", "proposal_candidate", "review_ready", "review_blocked", "review_accepted", "evidence_cited", "signal_sensed", "alert_routed", "attention_assigned", "decision_recorded", "action_proposed", "action_running", "outcome_succeeded", "outcome_failed", "feedback_applied", "attention_reopened"]) {
    assert.match(source, new RegExp(`"${eventKind}"`));
  }
  for (const name of ["SignalKind", "NervousSystemSeverity", "AttentionStatus", "OwnerType", "RoutingPolicyId", "ActionSafetyLevel", "OutcomeStatus", "FeedbackKind"]) {
    assert.match(source, new RegExp(name));
  }
  for (const signalKind of ["source_changed", "source_stale", "conflict_detected", "connector_issue", "agent_action_pending", "outcome_due", "policy_violation"]) {
    assert.match(source, new RegExp(`"${signalKind}"`));
  }
  assert.match(source, /ResearchTaskStatus/);
  assert.match(source, /AgentActionProposalStatus/);
  assert.match(source, /source_open/);
  assert.match(source, /proposal_create/);
  assert.match(source, /connector_sync/);
  assert.match(source, /graphview-local/);
  assert.match(source, /openai/);
  assert.match(source, /anthropic/);
  assert.match(source, /gemini/);
  assert.match(source, /ConnectorKind/);
  assert.match(source, /google-workspace/);
  assert.match(source, /notion/);
  assert.match(source, /contains/);
  assert.match(source, /references/);
  assert.match(source, /owned_by/);
  assert.match(source, /has_review_cycle/);
  assert.match(source, /governs/);
  assert.doesNotMatch(source, /GraphMode/);
  assert.doesNotMatch(source, /engineering-repository/);
  assert.doesNotMatch(source, /ops-document-map/);
});
