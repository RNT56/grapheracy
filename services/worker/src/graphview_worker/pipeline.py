from dataclasses import dataclass

from arq.connections import RedisSettings
from arq.cron import cron

from graphview_api.settings import Settings
from graphview_worker.jobs import dispatch_outbox, enqueue_scheduled_connector_syncs, execute_durable_job, run_context_retention, shutdown, startup, worker_health


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
        WorkerStage("agent_context.normalize", "AgentContextEvent[]", "AgentContextArtifact[] + AgentContextBlob[]", "session.id + event sequence"),
        WorkerStage("agent_context.enrich", "AgentContextArtifact[] + repository index", "AgentContextGraph inferred edges", "session.id + artifact checksum + repo commit"),
        WorkerStage("agent_context.retention", "AgentContextBlob[] + retention policy", "PurgedBlob[] + retention activity", "project.id + retention window + blob expires_at"),
    ]


class WorkerSettingsForArq:
    functions = [execute_durable_job, dispatch_outbox, enqueue_scheduled_connector_syncs, run_context_retention, worker_health]
    cron_jobs = [
        cron(dispatch_outbox, second={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, unique=True),
        cron(enqueue_scheduled_connector_syncs, minute=set(range(60)), second=15, unique=True),
        cron(run_context_retention, hour=3, minute=15, unique=True),
    ]
    redis_settings = RedisSettings.from_dsn(Settings().arq_redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 12
    max_tries = 5
    job_timeout = 900
    health_check_interval = 30
    retry_jobs = True
