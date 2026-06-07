from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerStage:
    name: str
    input_contract: str
    output_contract: str
    idempotency_key: str


def build_stage_plan() -> list[WorkerStage]:
    return [
        WorkerStage("connector.fetch", "ConnectorTarget", "RawConnectorArtifact[]", "target.id + remote id + remote modified timestamp"),
        WorkerStage("source.extract", "RawConnectorArtifact", "NormalizedSourceDocument", "remote id + artifact checksum"),
        WorkerStage("chunk.normalize", "NormalizedSourceDocument", "SourceChunk[]", "source.id + chunk checksum"),
        WorkerStage("hierarchy.build", "SourceChunk[]", "Topic[] + hierarchy proposals", "target.id + source checksum + heading path"),
        WorkerStage("entity.resolve", "SourceChunk[] + reviewed graph", "ResolvedEntity[]", "project.id + normalized label + remote id"),
        WorkerStage("relation.propose", "ResolvedEntity[] + explicit links", "CandidateGraph", "source.id + candidate hash"),
        WorkerStage("content.embed", "NormalizedSourceDocument", "ContentEmbedding", "source.id + embedding model + checksum"),
        WorkerStage("proposal.generate", "CandidateGraph + ContentEmbedding", "ExtractionProposal[]", "candidate hash + project.id"),
        WorkerStage("autocommit.evaluate", "ExtractionProposal[]", "ReviewDecision[]", "proposal.id + threshold + graph settings version"),
        WorkerStage("review.commit", "ReviewDecision", "GraphUpdate", "reviewDecision.id"),
        WorkerStage("agent.plan", "PlanningSession + PlanningMessage", "GraphBuildSpec + AgentRun", "session.id + message.id + provider + model"),
        WorkerStage("agent.retrieve", "AgentRun + GraphQuery", "GraphContext + AgentCitation[]", "project.id + query hash + lens + graph version"),
        WorkerStage("agent.reason", "GraphContext + ProviderConfig", "AgentAnswer + AgentStep", "agentRun.id + provider + model + prompt hash"),
        WorkerStage("agent.research.fetch", "ResearchTask", "NormalizedSourceDocument[]", "project.id + task.id + query + provider + model"),
        WorkerStage("agent.propose", "NormalizedSourceDocument[] + AgentAnswer", "Source[] + ExtractionProposal[]", "task.id + source checksum + model"),
        WorkerStage("agent.action.await_review", "AgentRun", "AgentActionProposal[]", "agentRun.id + action payload hash"),
        WorkerStage("agent.action.apply", "AgentActionProposal + ReviewDecision", "GraphUpdate | ReviewDecision", "actionProposal.id + reviewer.id"),
    ]


class WorkerSettings:
    redis_url = "redis://127.0.0.1:6379/0"


class WorkerSettingsForArq:
    functions = []
    redis_settings = None
