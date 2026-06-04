from sqlalchemy import Column, DateTime, ForeignKey, MetaData, String, Table, Text

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
