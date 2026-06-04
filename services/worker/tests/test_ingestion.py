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
