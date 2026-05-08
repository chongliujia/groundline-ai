from groundline.core.schemas import Document, PipelineEvent, QueryRequest


def test_public_schemas_have_defaults() -> None:
    document = Document(doc_id="doc_1", tenant_id="default", source_uri="demo.md", source_type="md")
    request = QueryRequest(query="what is covered?")
    event = PipelineEvent(event_id="event_1", stage="parse", status="completed")

    assert document.acl_groups == []
    assert request.top_k == 8
    assert event.metadata == {}
