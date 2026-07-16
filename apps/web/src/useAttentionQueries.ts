import { useMutation, useQuery } from "@tanstack/react-query";
import { fetchJson, waitForJob } from "./apiClient";
import type {
  ApiActionCredentialKind, ApiDecisionRecord, ApiFeedbackEvent, ApiOperationalActionProposal,
  ApiOperationalActionRun, ApiOperationalAttentionItem, ApiOperationalAttentionResponse,
  ApiOperationalOutcome, ApiOwner, ApiRoutingPolicy, ApiSignal
} from "./workspaceTypes";

export function useAttentionQueries(selectedGraphId: string) {
  const signals = useQuery({
    queryKey: ["signals", selectedGraphId],
    queryFn: () => fetchJson<{ signals: ApiSignal[] }>("/signals?limit=8"),
    retry: false
  });
  const observations = useQuery({
    queryKey: ["observations", selectedGraphId],
    queryFn: () => fetchJson<{ observations: unknown[] }>("/observations?limit=8"),
    retry: false
  });
  const alerts = useQuery({
    queryKey: ["alerts", selectedGraphId],
    queryFn: () => fetchJson<{ alerts: unknown[] }>("/alerts?limit=8"),
    retry: false
  });
  const operationalAttention = useQuery({
    queryKey: ["attention", selectedGraphId],
    queryFn: () => fetchJson<ApiOperationalAttentionResponse>("/attention?limit=8"),
    retry: false
  });
  const owners = useQuery({
    queryKey: ["owners"],
    queryFn: () => fetchJson<{ owners: ApiOwner[] }>("/owners?limit=20"),
    retry: false
  });
  const routingPolicies = useQuery({
    queryKey: ["routing-policies"],
    queryFn: () => fetchJson<{ routing_policies: ApiRoutingPolicy[] }>("/routing-policies?limit=20"),
    retry: false
  });
  const decisionRecords = useQuery({
    queryKey: ["decision-records", selectedGraphId],
    queryFn: () => fetchJson<{ decision_records: ApiDecisionRecord[] }>("/decision-records?limit=8"),
    retry: false
  });
  const operationalActionProposals = useQuery({
    queryKey: ["action-proposals", selectedGraphId],
    queryFn: () => fetchJson<{ action_proposals: ApiOperationalActionProposal[] }>("/action-proposals?limit=8"),
    retry: false
  });
  const operationalActionRuns = useQuery({
    queryKey: ["action-runs", selectedGraphId],
    queryFn: () => fetchJson<{ action_runs: ApiOperationalActionRun[] }>("/action-runs?limit=8"),
    retry: false
  });
  const outcomes = useQuery({
    queryKey: ["outcomes", selectedGraphId],
    queryFn: () => fetchJson<{ outcomes: ApiOperationalOutcome[] }>("/outcomes?limit=8"),
    retry: false
  });
  const feedbackEvents = useQuery({
    queryKey: ["feedback-events", selectedGraphId],
    queryFn: () => fetchJson<{ feedback_events: ApiFeedbackEvent[] }>("/feedback-events?limit=8"),
    retry: false
  });

  return {
    signals,
    observations,
    alerts,
    operationalAttention,
    owners,
    routingPolicies,
    decisionRecords,
    operationalActionProposals,
    operationalActionRuns,
    outcomes,
    feedbackEvents
  };
}

export function useAttentionMutations({
  selectedGraphId,
  selectedGraphLensId,
  selectedSourceId,
  fallbackSourceId,
  actionCredentialStatus,
  owners,
  proposals,
  onSignalCreated,
  onChanged
}: {
  selectedGraphId: string;
  selectedGraphLensId: string;
  selectedSourceId?: string;
  fallbackSourceId?: string;
  actionCredentialStatus: Record<ApiActionCredentialKind, boolean>;
  owners: ApiOwner[];
  proposals: ApiOperationalActionProposal[];
  onSignalCreated: () => void;
  onChanged: () => Promise<void>;
}) {
  const createOperationalSignal = useMutation({
    mutationFn: () => {
      const candidateSource = selectedSourceId ?? fallbackSourceId;
      return fetchJson<ApiSignal>("/signals", {
        method: "POST",
        body: JSON.stringify({
          kind: "source_changed",
          severity: "medium",
          source_kind: "manual",
          source_id: candidateSource,
          title: candidateSource ? "Source needs attention" : "Graph workspace signal",
          summary: candidateSource
            ? "A graph source was flagged from the Attention workspace for owner routing."
            : "The graph workspace was manually flagged for attention routing.",
          payload: { graph_id: selectedGraphId, lens: selectedGraphLensId, selected_source_id: candidateSource }
        })
      });
    },
    onSuccess: async () => {
      onSignalCreated();
      await onChanged();
    }
  });
  const createOperationalDecision = useMutation({
    mutationFn: (item: ApiOperationalAttentionItem) =>
      fetchJson<ApiDecisionRecord>("/decision-records", {
        method: "POST",
        body: JSON.stringify({
          attention_item_id: item.id,
          alert_id: item.alert_id,
          decision: "approve",
          rationale: "Approved from the graph-centered Attention loop."
        })
      }),
    onSuccess: onChanged
  });
  const createOperationalAction = useMutation({
    mutationFn: (item: ApiOperationalAttentionItem) => {
      const owner = owners.find((candidate) => candidate.id === item.owner_id);
      const actionType = item.source_id
        ? "mark_source_stale"
        : actionCredentialStatus.smtp && owner?.contact
          ? "create_notification"
          : "request_owner_confirmation";
      return fetchJson<ApiOperationalActionProposal>("/action-proposals", {
        method: "POST",
        body: JSON.stringify({
          decision_record_id: item.decision_record_id,
          alert_id: item.alert_id,
          attention_item_id: item.id,
          action_type: actionType,
          title: actionType === "mark_source_stale" ? "Mark source stale" : actionType === "create_notification" ? "Notify owner" : "Request owner confirmation",
          summary: actionType === "mark_source_stale"
            ? "Flag the linked source as stale until it is refreshed."
            : actionType === "create_notification"
              ? "Notify the responsible owner that the graph needs attention."
              : "Keep the action inside Graphview until an owner contact and SMTP credential are configured.",
          payload: actionType === "mark_source_stale"
            ? { source_id: item.source_id }
            : actionType === "create_notification"
              ? { credential_id: "smtp", to: owner?.contact, attention_item_id: item.id }
              : { owner_id: item.owner_id, attention_item_id: item.id }
        })
      });
    },
    onSuccess: onChanged
  });
  const approveOperationalAction = useMutation({
    mutationFn: (action: ApiOperationalActionProposal) =>
      fetchJson<ApiOperationalActionProposal>(`/action-proposals/${encodeURIComponent(action.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({ rationale: "Approved from the graph-centered Attention loop." })
      }),
    onSuccess: onChanged
  });
  const runOperationalAction = useMutation({
    mutationFn: async (action: ApiOperationalActionProposal) => {
      if (["create_external_ticket", "create_notification", "trigger_workflow"].includes(action.action_type)) {
        const job = await fetchJson<{ id: string }>(`/action-proposals/${encodeURIComponent(action.id)}/run`, {
          method: "POST",
          body: "{}"
        });
        return waitForJob<ApiOperationalActionRun>(job.id);
      }
      return fetchJson<ApiOperationalActionRun>("/action-runs", {
        method: "POST",
        body: JSON.stringify({ action_proposal_id: action.id })
      });
    },
    onSuccess: onChanged
  });
  const recordOperationalOutcome = useMutation({
    mutationFn: (run: ApiOperationalActionRun) => {
      const action = proposals.find((proposal) => proposal.id === run.action_proposal_id);
      return fetchJson<ApiOperationalOutcome>(`/action-runs/${encodeURIComponent(run.id)}/outcome`, {
        method: "POST",
        body: JSON.stringify({
          attention_item_id: action?.attention_item_id,
          status: run.status === "succeeded" ? "resolved" : "failed",
          title: run.status === "succeeded" ? "Action outcome resolved" : "Action outcome failed",
          summary: run.status === "succeeded"
            ? "The approved operational action completed and the attention item can be resolved."
            : "The approved operational action failed and needs follow-up.",
          result: { action_run_id: run.id, action_type: run.action_type, target: run.target }
        })
      });
    },
    onSuccess: onChanged
  });
  return {
    createOperationalSignal,
    createOperationalDecision,
    createOperationalAction,
    approveOperationalAction,
    runOperationalAction,
    recordOperationalOutcome
  };
}
