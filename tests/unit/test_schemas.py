from groundline.core.schemas import Document, QueryRequest


def test_public_schemas_have_defaults() -> None:
    document = Document(doc_id="doc_1", tenant_id="default", source_uri="demo.md", source_type="md")
    request = QueryRequest(query="what is covered?")

    assert document.acl_groups == []
    assert request.top_k == 8

