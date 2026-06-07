from io import BytesIO

from pypdf import PdfWriter

from graphview_worker.ingestion import RawSource, extract_pdf_text, ingest_source


def test_ingest_markdown_generates_embedding_and_proposals() -> None:
    result = ingest_source(
        RawSource(
            kind="markdown",
            title="Graphview Review Flow",
            content="# Graphview Review Flow\n\nGraphview Review Flow preserves source provenance.",
            uri="file://notes.md",
        )
    )

    assert result.source_checksum
    assert result.embedding_model == "graphview-local-hash-v1"
    assert len(result.embedding_vector) == 16
    assert result.proposals[0].locator == "file://notes.md"
    assert result.proposals[0].proposed_value["label"] == "Graphview Review Flow"


def test_extract_pdf_text_handles_valid_pdf_bytes() -> None:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)

    assert extract_pdf_text(output.getvalue()) == ""


def test_ingest_repository_generates_symbol_and_dependency_proposals() -> None:
    result = ingest_source(
        RawSource(
            kind="repository",
            title="Graphview repository",
            content='packages/graph-core/src/index.ts\nexport function planGraphRender() {}\nimport "react";',
            uri="git://graphview",
        ),
        proposal_limit=5,
    )

    labels = {proposal.proposed_value["label"] for proposal in result.proposals if proposal.kind == "content_node"}
    assert "Symbol planGraphRender" in labels
    assert "Dependency react" in labels
    assert "Path packages/graph-core/src/index.ts" in labels
    symbol = next(proposal for proposal in result.proposals if proposal.proposed_value["label"] == "Symbol planGraphRender")
    assert symbol.proposed_value["kind"] == "symbol"
    assert symbol.proposed_value["metadata"]["extractionLenses"] == ["engineering"]
    dependency = next(proposal for proposal in result.proposals if proposal.proposed_value["label"] == "Dependency react")
    assert dependency.proposed_value["kind"] == "package"
    edge = next(
        proposal
        for proposal in result.proposals
        if proposal.kind == "semantic_edge" and "engineering" in proposal.proposed_value.get("metadata", {}).get("extractionLenses", [])
    )
    assert edge.proposed_value["sourceLabel"] == "Repository Graphview repository"
    assert edge.proposed_value["relation"] in {"contains", "defines", "imports", "mentions"}


def test_ingest_ops_document_preserves_owner_metadata() -> None:
    result = ingest_source(
        RawSource(
            kind="ops-document",
            title="Vendor Review Process",
            content="# Vendor Review Process\nOwner: Security Ops\nReview: monthly\nProject Exception Workflow",
            uri="ops://vendor-review",
        ),
        proposal_limit=8,
    )

    ops_value = next(
        proposal.proposed_value
        for proposal in result.proposals
        if "ops" in proposal.proposed_value.get("metadata", {}).get("extractionLenses", [])
    )
    assert ops_value["metadata"]["extractionLenses"] == ["ops"]
    assert ops_value["metadata"]["owner"] == "Security Ops"
    assert ops_value["metadata"]["reviewCycle"] == "monthly"
    assert "Owner: Security Ops" in ops_value["summary"]
    edge = next(
        proposal
        for proposal in result.proposals
        if proposal.kind == "semantic_edge" and "ops" in proposal.proposed_value.get("metadata", {}).get("extractionLenses", [])
    )
    assert edge.proposed_value["metadata"]["extractionLenses"] == ["ops"]
    assert edge.proposed_value["relation"] in {"mentions", "depends_on", "supports", "owned_by", "has_review_cycle", "governs"}
