from pathlib import Path

from sqlalchemy import Column, DateTime, Float, ForeignKey, MetaData, String, Table, Text, create_engine
from sqlalchemy.pool import StaticPool

metadata = MetaData()

graph_projects = Table(
    "graph_projects",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(240), nullable=False),
    Column("description", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

sources = Table(
    "sources",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("title", String(240), nullable=False),
    Column("uri", Text, nullable=True),
    Column("object_key", Text, nullable=True),
    Column("checksum", String(128), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

content_nodes = Table(
    "content_nodes",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("label", String(240), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("summary", Text, nullable=True),
    Column("topic_ids_json", Text, nullable=False),
    Column("provenance_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

semantic_edges = Table(
    "semantic_edges",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("source_node_id", String(64), ForeignKey("content_nodes.id"), nullable=False),
    Column("target_node_id", String(64), ForeignKey("content_nodes.id"), nullable=False),
    Column("relation", String(40), nullable=False),
    Column("weight", Float, nullable=True),
    Column("provenance_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("source_id", String(64), ForeignKey("sources.id"), nullable=False),
    Column("status", String(40), nullable=False),
    Column("stage", String(40), nullable=False),
    Column("trace_id", String(128), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error_code", String(80), nullable=True),
)

extraction_proposals = Table(
    "extraction_proposals",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("ingestion_run_id", String(64), ForeignKey("ingestion_runs.id"), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("proposed_value_json", Text, nullable=False),
    Column("confidence", Float, nullable=True),
    Column("provenance_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

review_decisions = Table(
    "review_decisions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("graph_projects.id"), nullable=False, index=True),
    Column("proposal_id", String(64), ForeignKey("extraction_proposals.id"), nullable=False),
    Column("reviewer_id", String(128), nullable=False),
    Column("decision", String(40), nullable=False),
    Column("edited_value_json", Text, nullable=True),
    Column("rationale", Text, nullable=True),
    Column("decided_at", DateTime(timezone=True), nullable=False),
)


def create_app_engine(database_url: str):
    if database_url.startswith("sqlite:///"):
        sqlite_path = database_url.removeprefix("sqlite:///")
        if sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            return create_engine(database_url, connect_args={"check_same_thread": False})
        return create_engine(database_url, connect_args={"check_same_thread": False})
    if database_url == "sqlite://":
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url)
