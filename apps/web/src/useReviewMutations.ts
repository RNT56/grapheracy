import { useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchJson } from "./apiClient";
import type { ApiProposal } from "./workspaceTypes";

export type ProposalDraft = string | { sourceId: string; label?: string; summary?: string; locator?: string };

export function useReviewMutations() {
  const queryClient = useQueryClient();
  const invalidateReview = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["proposals"] }),
    queryClient.invalidateQueries({ queryKey: ["review-queue"] }),
    queryClient.invalidateQueries({ queryKey: ["review-dashboard"] }),
    queryClient.invalidateQueries({ queryKey: ["review-activity"] }),
    queryClient.invalidateQueries({ queryKey: ["graph-activity"] }),
    queryClient.invalidateQueries({ queryKey: ["review-sources"] }),
    queryClient.invalidateQueries({ queryKey: ["review-decisions"] }),
    queryClient.invalidateQueries({ queryKey: ["insights"] }),
    queryClient.invalidateQueries({ queryKey: ["neighborhood"] }),
    queryClient.invalidateQueries({ queryKey: ["path"] })
  ]);
  const createProposal = useMutation({
    mutationFn: (payload: ProposalDraft) => {
      const sourceId = typeof payload === "string" ? payload : payload.sourceId;
      const label = typeof payload === "string" ? "Reviewed concept" : payload.label ?? "Reviewed concept";
      const summary = typeof payload === "string"
        ? "Candidate concept created from the Graphview evidence workspace."
        : payload.summary ?? "Candidate concept created from the selected evidence passage.";
      const locator = typeof payload === "string" ? "web shell" : payload.locator ?? "evidence reader";
      return fetchJson<ApiProposal>("/proposals", {
        method: "POST",
        body: JSON.stringify({
          source_id: sourceId,
          kind: "content_node",
          confidence: 0.82,
          locator,
          proposed_value: { label, kind: "concept", summary }
        })
      });
    },
    onSuccess: invalidateReview
  });
  const reviewProposal = useMutation({
    mutationFn: (payload: { proposalId: string; decision: "accept" | "reject" | "edit" | "defer"; rationale?: string }) =>
      fetchJson("/review-decisions", {
        method: "POST",
        body: JSON.stringify({
          proposal_id: payload.proposalId,
          decision: payload.decision,
          rationale: payload.rationale ?? `${payload.decision} from Graphview review queue`
        })
      }),
    onSuccess: async () => {
      await invalidateReview();
      await queryClient.invalidateQueries({ queryKey: ["graph"] });
    }
  });
  return { createProposal, reviewProposal };
}
