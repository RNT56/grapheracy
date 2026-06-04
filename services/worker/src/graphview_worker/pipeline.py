from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerStage:
    name: str
    input_contract: str
    output_contract: str
    idempotency_key: str


def build_stage_plan() -> list[WorkerStage]:
    return [
        WorkerStage("source.fetch", "Source", "RawArtifact", "source.id + checksum"),
        WorkerStage("source.extract", "RawArtifact", "NormalizedText", "source.id + artifact checksum"),
        WorkerStage("content.analyze", "NormalizedText", "CandidateGraph", "ingestionRun.id + extract checksum"),
        WorkerStage("proposal.generate", "CandidateGraph", "ExtractionProposal[]", "candidate hash + project.id"),
        WorkerStage("review.commit", "ReviewDecision", "GraphUpdate", "reviewDecision.id"),
    ]


class WorkerSettings:
    redis_url = "redis://127.0.0.1:6379/0"


class WorkerSettingsForArq:
    functions = []
    redis_settings = None
