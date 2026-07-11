import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "./apiClient";
import type {
  ApiDecisionRecord, ApiFeedbackEvent, ApiOperationalActionProposal, ApiOperationalActionRun,
  ApiOperationalAttentionResponse, ApiOperationalOutcome, ApiOwner, ApiRoutingPolicy, ApiSignal
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
