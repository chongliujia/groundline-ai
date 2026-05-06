下面是重新命名和重新定位后的技术方案，项目名统一为：

# Groundline

> **Groundline is an open-source retrieval engine for grounded, citation-ready LLM context.**

中文定位：

> **Groundline 是一个开源检索引擎，用于把复杂文档转化为可溯源、可引用、可权限控制的 LLM 上下文。**

---

# 1. 项目愿景

Groundline 的核心目标不是再做一个普通 RAG 框架，也不是重新造一个 OpenSearch / Milvus / Qdrant。

它要解决的是：

```text
从原始文档到可信 LLM 上下文之间的检索基础设施问题。
```

Groundline 关注的不是“让 LLM 能回答”，而是让 LLM 拿到的上下文满足：

```text
grounded      有依据
citation-ready 可引用
traceable     可追溯
permission-aware 可权限控制
version-aware 可识别版本
retrieval-optimized 可高质量召回
eval-ready    可评测
```

一句话：

```text
Groundline builds the evidence line between source documents and LLM answers.
```

---

# 2. 为什么需要 Groundline

大部分企业 RAG 系统失败，不是因为 LLM 不够强，而是因为上下文供应链不可靠。

常见问题包括：

```text
1. 文档解析质量差
2. PDF、Word、PPT、图片、表格被粗暴转成纯文本
3. Markdown 被当成唯一事实源，丢失页码、bbox、表格结构、图片 OCR
4. chunk 按固定字符数切，破坏语义结构
5. 只用向量检索，精确词、编号、日期、人名、条款召回差
6. metadata 缺失，无法按部门、版本、权限、时间过滤
7. rerank 和 context packing 没有标准化链路
8. 最终给 LLM 的上下文无法引用、无法审计
9. 没有 eval，检索质量无法量化
10. 从 demo 扩展到百万级 chunk 后需要推倒重来
```

Groundline 的目标是把这条链路标准化：

```text
Document
  → Block AST
  → Markdown View
  → Semantic Chunk
  → Hybrid Index
  → Fusion
  → Rerank
  → Context Pack
  → Citation-ready Context
```

---

# 3. 项目定位

Groundline 是一个 **RAG-native retrieval engine**。

它位于三类系统中间：

```text
上层：
  LLM 应用
  Chatbot
  Agent
  Copilot
  Knowledge Assistant

中层：
  Groundline
  文档解析
  chunk
  hybrid retrieval
  rerank
  context packing
  citation

底层：
  Vector DB
  Search Engine
  Metadata DB
  Object Storage
  Embedding Model
  Reranker
```

也就是说，Groundline 不是替代底层数据库，而是统一管理 RAG 检索链路。

---

# 4. 设计原则

Groundline 的核心设计原则如下：

```text
1. Markdown is a view, not the canonical source.
2. Block AST is the canonical document representation.
3. Chunk is the retrieval unit.
4. Parent chunk is the context unit.
5. Metadata is part of retrieval quality.
6. Hybrid retrieval is the default.
7. Vector-only search is an optimization, not the baseline.
8. Rerank is a service boundary.
9. Context must be citation-ready.
10. Every retrieval step should be traceable.
11. Every index update should be incremental.
12. Every quality claim should be measurable.
```

中文解释：

```text
Markdown 是给 LLM 和开发者看的文本视图；
Block AST 才是文档解析后的标准结构；
chunk 是检索单元；
parent chunk 是回答上下文单元；
metadata 不只是附加字段，而是检索质量的一部分；
默认应该是 hybrid retrieval，而不是单纯向量搜索；
最终输出必须能引用来源。
```

---

# 5. Groundline 总体架构

```text
                         ┌──────────────────────────────┐
                         │          LLM Apps             │
                         │ Chatbot / Agent / Copilot     │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │        Groundline API         │
                         │ REST / SDK / CLI              │
                         └──────────────┬───────────────┘
                                        │
┌───────────────────────────────────────▼──────────────────────────────────────┐
│                              Groundline Core                                  │
│                                                                                │
│  ┌────────────────────┐   ┌────────────────────┐   ┌──────────────────────┐  │
│  │ Ingestion Engine   │   │ Retrieval Engine   │   │ Evaluation Engine    │  │
│  └─────────┬──────────┘   └─────────┬──────────┘   └──────────┬───────────┘  │
│            │                        │                         │              │
│  ┌─────────▼──────────┐   ┌─────────▼──────────┐   ┌──────────▼───────────┐  │
│  │ Parser Layer       │   │ Query Router       │   │ Golden Dataset       │  │
│  │ Block AST          │   │ Hybrid Retrieval   │   │ Recall@K / MRR       │  │
│  │ Markdown Renderer  │   │ RRF Fusion         │   │ Citation Accuracy    │  │
│  │ Chunker            │   │ Reranker           │   │ Regression Reports   │  │
│  │ Embedder           │   │ Context Builder    │   └──────────────────────┘  │
│  │ Indexer            │   └────────────────────┘                              │
│  └────────────────────┘                                                        │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
┌─────────▼──────────┐       ┌──────────▼─────────┐       ┌──────────▼─────────┐
│ Vector Backend     │       │ Search Backend     │       │ Metadata Backend   │
│ Qdrant             │       │ BM25               │       │ SQLite             │
│ Milvus             │       │ OpenSearch         │       │ Postgres           │
│ Vespa              │       │ Elasticsearch      │       │                    │
└─────────┬──────────┘       └──────────┬─────────┘       └──────────┬─────────┘
          │                             │                             │
┌─────────▼──────────┐       ┌──────────▼─────────┐       ┌──────────▼─────────┐
│ Object Store       │       │ Rerank Backend     │       │ Observability      │
│ Local FS           │       │ CrossEncoder       │       │ Logs / Metrics     │
│ S3 / MinIO         │       │ API Reranker       │       │ Traces / Eval      │
└────────────────────┘       └────────────────────┘       └────────────────────┘
```

---

# 6. 核心概念

## 6.1 Document

原始文档，例如：

```text
PDF
DOCX
PPTX
HTML
Markdown
TXT
图片
扫描件
表格文件
```

Groundline 不直接把 document 当作检索单元。

---

## 6.2 Block AST

Block AST 是 Groundline 的 canonical representation。

它描述文档中的结构化元素：

```text
heading
paragraph
list
table
image
code
quote
header
footer
footnote
page_break
```

每个 block 保留：

```text
block_id
block_type
text
markdown
page
bbox
heading_path
confidence
source metadata
```

---

## 6.3 Markdown View

Markdown 是 block AST 的一种渲染视图。

它用于：

```text
1. 给 LLM 读
2. 给开发者调试
3. 给 context packing 使用
4. 给 citation context 输出
```

但 Markdown 不是唯一事实源。

正确关系是：

```text
Block AST = canonical source
Markdown = LLM-friendly view
Chunk = retrieval unit
Embedding = retrieval feature
```

---

## 6.4 Chunk

Chunk 是检索单元。

一个 chunk 应该是：

```text
可独立理解
可检索
可引用
可过滤
可重排
可映射回原文
```

Chunk 不只是文本，它包含：

```text
content_markdown
content_text
text_for_embedding
heading_path
doc_id
version_id
page_start
page_end
block_ids
image_ids
table_ids
metadata
acl_groups
```

---

## 6.5 Parent Chunk

Parent chunk 是上下文单元。

典型关系：

```text
child chunk:
  用于精准召回，300～1000 tokens

parent chunk:
  用于回答上下文，1500～4000 tokens
```

查询时：

```text
检索 child chunk
  → rerank child chunk
  → 扩展 parent chunk
  → 组装 citation-ready context
```

---

## 6.6 Grounded Context

Grounded context 是 Groundline 的最终输出。

它不是简单 top-k 文本，而是：

```json
{
  "doc_id": "doc_123",
  "version_id": "v4",
  "chunk_id": "c_001",
  "title": "2025年财务报销制度",
  "section": "差旅报销 > 住宿标准",
  "page_start": 12,
  "page_end": 13,
  "content_markdown": "### 住宿标准\n\n员工出差住宿标准如下……",
  "source_uri": "s3://docs/finance-policy.pdf",
  "citation": {
    "doc_id": "doc_123",
    "version_id": "v4",
    "chunk_id": "c_001",
    "page_start": 12,
    "page_end": 13
  }
}
```

这就是 Groundline 的核心产物：

```text
grounded, citation-ready LLM context
```

---

# 7. 核心数据模型

## 7.1 Document

```python
class Document(BaseModel):
    doc_id: str
    tenant_id: str

    source_uri: str
    source_type: str

    title: str | None = None
    doc_type: str | None = None
    domain: str | None = None
    language: str | None = None

    current_version_id: str | None = None

    acl_groups: list[str] = []
    metadata: dict[str, Any] = {}

    created_at: datetime
    updated_at: datetime
```

---

## 7.2 DocumentVersion

```python
class DocumentVersion(BaseModel):
    doc_id: str
    version_id: str

    content_hash: str

    parser_version: str
    chunker_version: str
    embedding_model: str | None = None

    is_latest: bool = True
    is_active: bool = True

    valid_from: datetime | None = None
    valid_to: datetime | None = None

    supersedes: str | None = None
    superseded_by: str | None = None

    created_at: datetime
    updated_at: datetime
```

---

## 7.3 Block

```python
class Block(BaseModel):
    block_id: str
    doc_id: str
    version_id: str

    block_type: Literal[
        "heading",
        "paragraph",
        "list",
        "table",
        "image",
        "code",
        "quote",
        "header",
        "footer",
        "footnote",
        "page_break",
    ]

    text: str | None = None
    markdown: str | None = None

    page: int | None = None
    bbox: list[float] | None = None

    heading_level: int | None = None
    heading_path: list[str] = []

    table_id: str | None = None
    image_id: str | None = None

    confidence: float | None = None

    metadata: dict[str, Any] = {}
```

---

## 7.4 ImageAsset

```python
class ImageAsset(BaseModel):
    image_id: str
    doc_id: str
    version_id: str

    image_uri: str

    page: int | None = None
    bbox: list[float] | None = None

    caption: str | None = None
    ocr_text: str | None = None
    visual_summary: str | None = None

    metadata: dict[str, Any] = {}
```

---

## 7.5 TableAsset

```python
class TableAsset(BaseModel):
    table_id: str
    doc_id: str
    version_id: str

    markdown: str
    html: str | None = None
    cells: list[dict[str, Any]] = []

    page: int | None = None
    bbox: list[float] | None = None

    summary: str | None = None

    metadata: dict[str, Any] = {}
```

---

## 7.6 Chunk

```python
class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    version_id: str
    tenant_id: str

    parent_chunk_id: str | None = None
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None

    title: str | None = None
    heading_path: list[str] = []

    content_markdown: str
    content_text: str
    text_for_embedding: str

    block_ids: list[str] = []
    image_ids: list[str] = []
    table_ids: list[str] = []

    page_start: int | None = None
    page_end: int | None = None

    doc_type: str | None = None
    domain: str | None = None
    language: str | None = None

    acl_groups: list[str] = []

    content_hash: str
    embedding_hash: str | None = None

    is_latest: bool = True
    is_active: bool = True

    index_generation: int | None = None

    metadata: dict[str, Any] = {}

    created_at: datetime
    updated_at: datetime
```

---

# 8. Ingestion Engine

Groundline 的 ingestion engine 负责把原始文档变成可检索索引。

## 8.1 Ingestion 流程

```text
Raw Document
  ↓
File Loader
  ↓
Content Hash
  ↓
Parser Selection
  ↓
Layout Parsing
  ↓
OCR / Image Extraction
  ↓
Table Extraction
  ↓
Block AST Normalization
  ↓
Markdown Rendering
  ↓
Semantic Chunking
  ↓
Parent-child Chunking
  ↓
Embedding
  ↓
Vector Index
  ↓
BM25 Index
  ↓
Metadata Index
  ↓
Validation
  ↓
Publish
```

---

## 8.2 Parser Layer

Parser 不直接输出 chunk，而是输出 block AST。

第一版支持：

```text
txt
md
html
```

v0.1 暂时不支持 PDF 解析，但会预留：

```text
source_type = pdf
parser registry
page / bbox 字段
ImageAsset / TableAsset 数据模型
PDF parser adapter 位置
```

后续支持：

```text
pdf text extraction
docx
pptx
xlsx
scanned pdf
image OCR
layout-aware pdf
```

Parser 输出示例：

```json
{
  "doc_id": "doc_123",
  "version_id": "v1",
  "blocks": [
    {
      "block_id": "b_001",
      "block_type": "heading",
      "text": "差旅报销",
      "markdown": "## 差旅报销",
      "page": 3,
      "heading_level": 2,
      "heading_path": ["财务制度", "差旅报销"]
    },
    {
      "block_id": "b_002",
      "block_type": "paragraph",
      "text": "员工出差住宿标准如下……",
      "markdown": "员工出差住宿标准如下……",
      "page": 3,
      "heading_path": ["财务制度", "差旅报销"]
    }
  ]
}
```

---

## 8.3 Markdown Renderer

Renderer 把 block AST 转成 Markdown View。

例如：

```markdown
# 2025年财务报销制度

## 差旅报销

### 住宿标准

员工出差住宿标准如下……

| 城市级别 | 标准 |
|---|---|
| 一线城市 | 800元/晚 |
| 二线城市 | 600元/晚 |

![付款审批流程图](s3://bucket/images/payment_flow.png)

图中文字 OCR：提交申请 → 财务审核 → 部门负责人审批 → 付款
```

---

## 8.4 Chunker

Chunker 的设计目标：

```text
1. 不按固定字数粗暴切
2. 按 block 组合
3. 保留 heading_path
4. 不切坏表格
5. 图片 OCR 和说明要进入 chunk
6. 支持 child chunk
7. 支持 parent chunk
8. 支持 prev / next chunk
```

Chunker 输入：

```text
Block AST
```

Chunker 输出：

```text
Chunk[]
ParentChunk[]
```

---

## 8.5 Embedding

Embedding 输入不直接用 `content_markdown`，而是使用 `text_for_embedding`。

原因：

```text
content_markdown:
  保留结构，适合 LLM 和前端展示

content_text:
  适合 BM25 / 全文检索

text_for_embedding:
  适合语义向量检索
```

例如：

```json
{
  "content_markdown": "![付款流程图](s3://...)\n\nOCR: 提交 → 审核 → 付款",
  "content_text": "付款流程图 OCR 提交 审核 付款",
  "text_for_embedding": "供应商付款审批流程，包括提交申请、财务审核、负责人审批和付款。"
}
```

---

## 8.6 Incremental Indexing

Groundline 必须支持增量索引。

判断规则：

```text
文件内容 hash 变化:
  重新 parse、chunk、embedding、index

parser_version 变化:
  重新 parse、chunk、embedding、index

chunker_version 变化:
  重新 chunk、embedding、index

embedding_model 变化:
  重新 embedding、vector index

metadata 变化:
  只更新 metadata index

ACL 变化:
  只更新权限字段

文档删除:
  tombstone，异步 hard delete
```

---

# 9. Retrieval Engine

Groundline 的 retrieval engine 不是简单向量检索，而是 hybrid retrieval pipeline。

## 9.1 查询流程

```text
User Query
  ↓
Query Understanding
  ↓
Route Selection
  ↓
ACL / Metadata Filter
  ↓
BM25 Retrieval
  ↓
Dense Vector Retrieval
  ↓
Title / Heading Retrieval
  ↓
Optional Entity Recall
  ↓
RRF Fusion
  ↓
Deduplication
  ↓
Rerank
  ↓
Parent / Adjacent Expansion
  ↓
Context Packing
  ↓
Grounded Context Output
```

---

## 9.2 Query Router

Router 根据 query 和 user context 选择过滤条件。

输入：

```json
{
  "query": "2025年差旅住宿标准是什么？",
  "tenant_id": "tenant_default",
  "user_groups": ["finance"],
  "filters": {
    "doc_type": "policy",
    "domain": "finance",
    "is_latest": true
  }
}
```

Router 输出：

```json
{
  "tenant_id": "tenant_default",
  "domains": ["finance"],
  "filters": {
    "doc_type": "policy",
    "domain": "finance",
    "is_latest": true,
    "is_active": true
  },
  "retrieval_plan": {
    "bm25_top_k": 100,
    "vector_top_k": 100,
    "title_top_k": 30,
    "fusion_top_k": 100,
    "rerank_top_k": 50,
    "context_top_k": 12
  }
}
```

---

## 9.3 Hybrid Retrieval

Groundline 默认使用多路召回：

```text
1. BM25 recall
2. Dense vector recall
3. Title / heading recall
4. Metadata recall
5. Optional entity recall
```

不同 query 类型使用不同权重。

```text
精确编号 / 条款 / 人名:
  BM25 权重大

语义问题:
  vector 权重大

最新政策:
  metadata + recency 权重大

历史版本:
  version / valid_time 权重大

表格问题:
  table chunk 权重大

图片 / 流程图问题:
  image OCR chunk 权重大
```

---

## 9.4 RRF Fusion

RRF 是 Groundline 的默认 fusion baseline。

```python
def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalHit]],
    k: int = 60,
    top_n: int = 100,
) -> list[RetrievalHit]:
    scores: dict[str, float] = {}
    best_hit: dict[str, RetrievalHit] = {}

    for results in ranked_lists:
        for rank, hit in enumerate(results, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            best_hit.setdefault(hit.chunk_id, hit)

    fused = []
    for chunk_id, score in scores.items():
        hit = best_hit[chunk_id]
        hit.score = score
        hit.source = "rrf"
        fused.append(hit)

    return sorted(fused, key=lambda h: h.score, reverse=True)[:top_n]
```

---

## 9.5 Deduplication

Groundline 需要去重：

```text
同一 chunk 去重
同一 parent chunk 下多个 child 合并
同一文档不同版本去重
near-duplicate chunk 去重
模板文档去重
```

默认规则：

```text
优先保留：
  is_latest = true
  rerank_score 高
  page 命中精准
  heading_path 更相关
  权限有效
```

---

## 9.6 Rerank

Rerank 是 Groundline 的独立服务边界。

Rerank 输入不是裸文本，而是结构化 candidate：

```json
{
  "query": "2025年差旅住宿标准是什么？",
  "candidates": [
    {
      "chunk_id": "c_001",
      "doc_title": "2025年财务报销制度",
      "heading_path": ["差旅报销", "住宿标准"],
      "content_text": "员工出差住宿标准如下……",
      "doc_type": "policy",
      "updated_at": "2025-03-01",
      "is_latest": true,
      "page_start": 12
    }
  ]
}
```

Rerank 输出：

```json
{
  "results": [
    {
      "chunk_id": "c_001",
      "rerank_score": 0.932,
      "rank": 1
    }
  ]
}
```

MVP 支持：

```text
no rerank fallback
sentence-transformers cross-encoder rerank
```

后续支持：

```text
external rerank API
light rerank
heavy rerank
rerank cache
Rust rerank proxy
```

---

## 9.7 Context Builder

Context Builder 负责把 reranked chunks 变成 LLM 可用的 grounded context。

它要做：

```text
1. ACL 再过滤
2. 去重
3. parent expansion
4. adjacent chunk expansion
5. 表格补全
6. 图片 OCR 补全
7. 控制同一文档占比
8. 控制 token budget
9. 保留 citation
10. 输出 trace
```

输出示例：

```json
{
  "contexts": [
    {
      "chunk_id": "doc_123_v1_c0042",
      "doc_id": "doc_123",
      "version_id": "v1",
      "title": "2025年财务报销制度",
      "section": "差旅报销 > 住宿标准",
      "page_start": 12,
      "page_end": 13,
      "content_markdown": "### 住宿标准\n\n员工出差住宿标准如下……",
      "source_uri": "s3://docs/finance_policy.pdf",
      "citation": {
        "doc_id": "doc_123",
        "version_id": "v1",
        "chunk_id": "doc_123_v1_c0042",
        "page_start": 12,
        "page_end": 13
      },
      "scores": {
        "fusion_score": 0.041,
        "rerank_score": 0.932
      }
    }
  ]
}
```

---

# 10. API 设计

## 10.1 Collection API

```http
POST   /collections
GET    /collections
GET    /collections/{collection_name}
DELETE /collections/{collection_name}
```

Create collection:

```json
{
  "name": "enterprise_docs",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "chunker": "heading-aware",
  "vector_backend": "faiss",
  "search_backend": "bm25",
  "metadata_backend": "sqlite"
}
```

---

## 10.2 Document API

```http
POST   /collections/{collection_name}/documents
POST   /collections/{collection_name}/ingest
GET    /collections/{collection_name}/documents/{doc_id}
GET    /collections/{collection_name}/documents/{doc_id}/versions
DELETE /collections/{collection_name}/documents/{doc_id}
```

Ingest request:

```json
{
  "source_uri": "./docs/finance_policy.pdf",
  "tenant_id": "tenant_default",
  "title": "2025年财务报销制度",
  "doc_type": "policy",
  "domain": "finance",
  "acl_groups": ["finance", "hr"],
  "metadata": {
    "owner": "finance_team"
  }
}
```

---

## 10.3 Query API

```http
POST /collections/{collection_name}/query
```

Request:

```json
{
  "query": "2025年差旅住宿标准是什么？",
  "tenant_id": "tenant_default",
  "user_groups": ["finance"],
  "top_k": 12,
  "filters": {
    "doc_type": "policy",
    "domain": "finance",
    "is_latest": true
  },
  "include_trace": true
}
```

Response:

```json
{
  "query": "2025年差旅住宿标准是什么？",
  "contexts": [
    {
      "chunk_id": "doc_123_v1_c0042",
      "doc_id": "doc_123",
      "version_id": "v1",
      "title": "2025年财务报销制度",
      "section": "差旅报销 > 住宿标准",
      "page_start": 12,
      "page_end": 13,
      "content_markdown": "### 住宿标准\n\n员工出差住宿标准如下……",
      "source_uri": "./docs/finance_policy.pdf",
      "citation": {
        "doc_id": "doc_123",
        "version_id": "v1",
        "chunk_id": "doc_123_v1_c0042",
        "page_start": 12,
        "page_end": 13
      },
      "scores": {
        "fusion_score": 0.041,
        "rerank_score": 0.932
      }
    }
  ],
  "trace": {
    "bm25_hits": 100,
    "vector_hits": 100,
    "title_hits": 30,
    "fused_hits": 128,
    "reranked_hits": 50,
    "final_contexts": 12
  }
}
```

---

## 10.4 Eval API

```http
POST /collections/{collection_name}/eval
GET  /collections/{collection_name}/eval/{run_id}
```

Eval dataset JSONL:

```json
{"query":"2025年差旅住宿标准是什么？","gold_chunk_ids":["doc_123_v1_c0042"],"query_type":"policy_latest"}
{"query":"供应商付款审批流程是什么？","gold_doc_ids":["doc_456"],"query_type":"process_question"}
```

---

# 11. CLI 设计

CLI 名称：

```bash
groundline
```

命令：

```bash
groundline init

groundline ingest ./docs \
  --collection enterprise_docs \
  --tenant tenant_default \
  --domain finance

groundline query "2025年差旅住宿标准是什么？" \
  --collection enterprise_docs \
  --user-groups finance \
  --trace

groundline eval ./evalset.jsonl \
  --collection enterprise_docs

groundline inspect doc doc_123

groundline inspect chunk doc_123_v1_c0042

groundline serve --host 0.0.0.0 --port 8080

groundline rebuild --collection enterprise_docs --generation next

groundline publish --collection enterprise_docs --generation 18
```

---

# 12. Python SDK 设计

```python
from groundline import Groundline

engine = Groundline.from_local("./groundline_data")

engine.ingest(
    path="./docs",
    collection="demo",
    tenant_id="default",
    domain="finance",
    acl_groups=["finance"],
)

result = engine.query(
    collection="demo",
    query="供应商付款需要哪些审批？",
    tenant_id="default",
    user_groups=["finance"],
    top_k=8,
)

for ctx in result.contexts:
    print(ctx.title)
    print(ctx.section)
    print(ctx.page_start)
    print(ctx.content_markdown)
    print(ctx.citation)
```

---

# 13. Storage Backend 设计

## 13.1 MVP Backend

第一版目标是面向开发者和开源 demo，本地可跑，验证完整链路。

```text
Object Store:
  local filesystem

Metadata Store:
  SQLite

Vector Store:
  Qdrant

Keyword Store:
  rank_bm25

Embedding:
  sentence-transformers

Rerank:
  optional cross-encoder

API:
  FastAPI

CLI:
  Typer
```

---

## 13.2 Production Backend

后续支持生产部署：

```text
Object Store:
  S3 / MinIO

Metadata Store:
  Postgres

Vector Store:
  Qdrant Cloud / Milvus

Search Store:
  OpenSearch / Elasticsearch

Queue:
  Redis Streams / RabbitMQ / Kafka

Workers:
  Celery / Dramatiq / custom worker

Observability:
  Prometheus
  OpenTelemetry
  structured logs
```

---

## 13.3 Large-scale Backend

大型场景支持：

```text
Query Gateway:
  Rust service

Fusion Engine:
  Rust / PyO3

Filter Engine:
  Rust bitmap filter

Shard Catalog:
  Postgres / etcd

Search Backend:
  OpenSearch / Vespa / Tantivy

Vector Backend:
  Qdrant / Milvus / Vespa
```

---

# 14. Index Generation

Groundline 支持 index generation，用于无停机更新和回滚。

## 14.1 Generation 目标

```text
1. 后台构建新索引
2. 验证新索引质量
3. 原子发布
4. 快速回滚
5. 避免半更新状态污染线上查询
```

---

## 14.2 Generation 表

```sql
CREATE TABLE index_generations (
    generation_id INTEGER PRIMARY KEY,
    collection_name TEXT NOT NULL,
    status TEXT NOT NULL,

    vector_backend_generation TEXT,
    search_backend_generation TEXT,
    metadata_generation TEXT,

    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP
);
```

---

## 14.3 发布流程

```text
1. 创建 generation_18
2. 后台写入 vector index
3. 后台写入 BM25 index
4. 后台写入 metadata index
5. 跑 smoke test
6. 跑 eval subset
7. 检查 doc count / chunk count / failure count
8. publish generation_18
9. 保留 generation_17 用于回滚
10. 延迟清理旧 generation
```

---

# 15. 大规模设计：300 万～3000 万 chunk

Groundline 的长期目标是支持大型文档检索场景。

## 15.1 分片策略

推荐两级分片：

```text
一级：
  tenant_id / domain

二级：
  time_bucket / hash(doc_id)
```

示例：

```text
tenant_a/finance/2026_q2/shard_00
tenant_a/finance/2026_q2/shard_01
tenant_a/legal/2026_q2/shard_00
tenant_a/hr/archive_2024/shard_00
```

---

## 15.2 冷热分层

```text
hot:
  最新文档
  高频文档
  核心制度
  当前产品文档

warm:
  低频但仍需在线检索的文档

cold:
  历史版本
  低频归档
  老项目文档

archive:
  默认不进入实时向量索引
  按需恢复或异步查询
```

---

## 15.3 查询路由

```text
latest query:
  hot only

normal query:
  hot + warm

historical query:
  warm + cold

archive query:
  cold + archive manifest

version comparison:
  hot + warm + cold
```

---

## 15.4 大型查询链路

```text
Query
  ↓
Intent Classification
  ↓
Shard Routing
  ↓
Bounded Fan-out Retrieval
  ↓
BM25 + Vector + Title Recall
  ↓
RRF Fusion
  ↓
Dedupe
  ↓
Light Rerank
  ↓
Heavy Rerank optional
  ↓
Parent Expansion
  ↓
Context Packing
```

典型参数：

```text
bm25_top_k_per_shard = 50
vector_top_k_per_shard = 50
max_shards_per_query = 8 ~ 24
fusion_top_k = 300
light_rerank_top_k = 100
heavy_rerank_top_k = 50
context_top_k = 8 ~ 20
```

---

# 16. Evaluation Engine

Groundline 必须内置 eval，而不是依赖人工感觉调检索。

## 16.1 Eval Dataset

```json
{
  "query": "2025年差旅住宿标准是什么？",
  "gold_doc_ids": ["doc_123"],
  "gold_chunk_ids": ["doc_123_v1_c0042"],
  "query_type": "policy_latest"
}
```

---

## 16.2 Retrieval Metrics

```text
Recall@5
Recall@10
MRR
NDCG@10
Hit Rate
```

---

## 16.3 Context Metrics

```text
citation_accuracy
stale_doc_rate
acl_violation_rate
context_duplication_rate
parent_expansion_success_rate
table_hit_rate
image_ocr_hit_rate
```

---

## 16.4 Eval Report

```json
{
  "run_id": "eval_2026_05_06_001",
  "collection": "enterprise_docs",
  "metrics": {
    "recall_at_5": 0.72,
    "recall_at_10": 0.84,
    "mrr": 0.61,
    "ndcg_at_10": 0.79,
    "citation_accuracy": 0.88
  },
  "by_query_type": {
    "policy_latest": {
      "recall_at_10": 0.91,
      "stale_doc_rate": 0.02
    },
    "exact_match": {
      "recall_at_10": 0.86
    },
    "semantic": {
      "recall_at_10": 0.81
    }
  }
}
```

---

# 17. Observability

Groundline 每次 query 都应支持 trace。

## 17.1 Query Trace

```json
{
  "query_id": "q_001",
  "routing": {
    "tenant_id": "tenant_default",
    "domains": ["finance"],
    "filters": {
      "is_latest": true,
      "is_active": true
    }
  },
  "retrieval": {
    "bm25_hits": 100,
    "vector_hits": 100,
    "title_hits": 30
  },
  "fusion": {
    "method": "rrf",
    "fused_hits": 128
  },
  "rerank": {
    "enabled": true,
    "input_candidates": 50,
    "output_candidates": 12,
    "latency_ms": 218
  },
  "context": {
    "final_items": 8,
    "parent_expansions": 3,
    "deduped_items": 11
  }
}
```

---

## 17.2 Metrics

```text
Ingestion:
  documents_total
  parse_success_rate
  parse_failure_rate
  chunks_total
  avg_chunks_per_doc
  embedding_latency_ms
  indexing_latency_ms

Query:
  query_total
  query_latency_p50
  query_latency_p95
  query_latency_p99
  bm25_latency_ms
  vector_latency_ms
  fusion_latency_ms
  rerank_latency_ms
  context_build_latency_ms

Quality:
  recall_at_10
  mrr
  citation_accuracy
  stale_doc_rate
  acl_violation_rate
```

---

# 18. Repo 结构

```text
groundline/
  README.md
  LICENSE
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  SECURITY.md
  CHANGELOG.md
  ROADMAP.md
  pyproject.toml
  docker-compose.yml

  docs/
    technical-design.md
    architecture.md
    document-model.md
    chunking.md
    retrieval.md
    indexing.md
    evaluation.md
    roadmap.md

  groundline/
    __init__.py

    app/
      main.py
      dependencies.py
      routes/
        collections.py
        documents.py
        query.py
        eval.py
        admin.py

    core/
      schemas.py
      config.py
      errors.py
      hashing.py
      ids.py

    ingestion/
      loader.py
      parser.py
      markdown_renderer.py
      chunker.py
      embedder.py
      indexer.py
      jobs.py

    retrieval/
      router.py
      filters.py
      bm25.py
      vector.py
      fusion.py
      reranker.py
      dedupe.py
      context_builder.py
      trace.py

    storage/
      metadata_store.py
      object_store.py
      vector_store.py
      search_store.py

    adapters/
      vector/
        qdrant_store.py
        milvus_store.py

      search/
        bm25_store.py
        opensearch_store.py

      metadata/
        sqlite_store.py
        postgres_store.py

      object/
        local_store.py
        s3_store.py

      embedding/
        sentence_transformers.py
        openai.py

      rerank/
        cross_encoder.py
        api.py

    evals/
      dataset.py
      metrics.py
      runner.py
      report.py

    cli/
      main.py
      commands/
        init.py
        ingest.py
        query.py
        eval.py
        inspect.py
        serve.py

  tests/
    unit/
    integration/
    fixtures/

  examples/
    quickstart/
      docs/
      evalset.jsonl
      README.md

  scripts/
    ingest_demo.py
    query_demo.py
```

---

# 19. README 首屏草案

````markdown
# Groundline

Groundline is an open-source retrieval engine for grounded, citation-ready LLM context.

It turns messy enterprise documents into structured, searchable, traceable, and permission-aware context for LLM applications.

## Why Groundline?

Most RAG systems fail before the LLM sees the context:

- documents are poorly parsed
- chunks are badly split
- metadata is missing
- vector-only retrieval misses exact matches
- citations are unreliable
- retrieval quality is hard to evaluate
- scaling from demo to production requires rework

Groundline provides a production-shaped retrieval layer:

- Block-level document model
- Markdown view for LLM context
- Heading-aware chunking
- Parent-child chunk expansion
- Dense + BM25 hybrid retrieval
- Reciprocal Rank Fusion
- Reranker integration
- Metadata and ACL filtering
- Citation-ready context output
- Retrieval evaluation toolkit

## Quickstart

```bash
pip install groundline

groundline init

groundline ingest ./docs --collection demo

groundline query "What does the policy say about travel reimbursement?" --collection demo --trace
````

## Philosophy

Markdown is a view.
Block AST is the source.
Chunk is the retrieval unit.
Context must be grounded.

````

---

# 20. MVP 范围

v0.1 的首批用户是开发者和开源 demo 用户。核心目标是让用户能在本地快速完成：

```text
local docs
  → ingest
  → chunk
  → Qdrant + BM25 index
  → query
  → citation-ready context
```

v0.1 不追求企业生产部署能力，也不把 PDF 解析作为第一阶段目标；PDF 相关字段、接口和 adapter 位置会提前预留。

## v0.1 必须完成

```text
1. Python package
2. CLI
3. FastAPI server
4. 本地文件 ingest
5. txt / md / html parser
6. Block AST schema
7. Markdown renderer
8. heading-aware chunker
9. parent-child chunk
10. sentence-transformers embedding
11. Qdrant vector index
12. rank_bm25 keyword index
13. SQLite metadata store
14. RRF fusion
15. optional cross-encoder rerank
16. context packing
17. citation-ready query response
18. eval runner
19. quickstart example
20. Dockerfile / docker-compose
````

---

## v0.1 不做

```text
1. 分布式索引
2. 复杂 ACL
3. 热温冷分层
4. 多租户生产隔离
5. Dashboard
6. 内置 OCR 引擎
7. Rust data plane
8. 自研向量数据库
9. 自研倒排索引
10. PDF parsing
11. scanned PDF / layout-aware PDF
```

---

# 21. 技术栈

## v0.1

```text
Language:
  Python 3.11+

API:
  FastAPI

CLI:
  Typer

Schema:
  Pydantic

Metadata:
  SQLite

Vector:
  Qdrant

BM25:
  rank_bm25

Embedding:
  sentence-transformers

Rerank:
  sentence-transformers CrossEncoder optional

Testing:
  pytest

Formatting:
  ruff
  black

Packaging:
  pyproject.toml

Container:
  Docker
  Docker Compose
```

---

## v0.2

```text
Metadata:
  Postgres

Vector:
  Milvus adapter

Search:
  OpenSearch adapter

Object:
  S3 / MinIO adapter

Queue:
  Redis Streams or Celery

Observability:
  OpenTelemetry
  Prometheus metrics
```

---

## v0.3+

```text
Index:
  index generation
  incremental indexing
  tombstone delete

Retrieval:
  query routing
  metadata-aware retrieval
  rerank cache

Scale:
  shard catalog
  hot/warm/cold tier

Rust:
  query gateway
  RRF fusion
  dedupe
  ACL filter
```

---

# 22. Roadmap

## v0.1 — Local Groundline

目标：面向开发者和开源 demo，本地跑通完整 retrieval pipeline。

```text
documents
  → block AST
  → chunks
  → embeddings
  → BM25
  → vector search
  → RRF
  → rerank
  → citation-ready contexts
```

---

## v0.2 — Production Adapters

目标：接入生产型 backend。

```text
Postgres
Qdrant
Milvus
OpenSearch
S3 / MinIO
PDF text parser
```

---

## v0.3 — Incremental Groundline

目标：支持增量索引和 generation。

```text
content hash
chunk hash
embedding hash
tombstone
index generation
rollback
```

---

## v0.4 — Groundline Eval

目标：检索质量可评测。

```text
eval dataset
Recall@K
MRR
NDCG@K
citation accuracy
query type breakdown
regression report
```

---

## v0.5 — Groundline Server

目标：更完整的服务化运行时。

```text
job queue
worker
rerank service
query trace
metrics
Docker Compose production template
```

---

## v0.6 — Large-scale Groundline

目标：支持百万级到千万级 chunk 的工程能力。

```text
tenant/domain routing
shard catalog
hot/warm/cold tier
bounded fan-out
rerank cache
parent chunk cache
```

---

## v1.0 — Stable Groundline

目标：稳定 API 和生产部署指南。

```text
stable SDK
stable REST API
stable schema
production docs
adapter compatibility
migration guide
```

---

# 23. 开源治理

建议 license：

```text
Apache-2.0
```

原因：

```text
1. 企业友好
2. 有专利授权条款
3. 适合基础设施项目
4. 方便未来商业化托管服务
```

仓库必备文件：

```text
README.md
LICENSE
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
CHANGELOG.md
ROADMAP.md
```

Issue labels：

```text
good first issue
help wanted
bug
enhancement
docs
adapter
chunking
retrieval
rerank
evaluation
large-scale
rust
```

---

# 24. 项目模块命名

Python package：

```text
groundline
```

CLI：

```text
groundline
```

服务：

```text
groundline-server
```

核心模块：

```text
groundline-core
```

后续 Rust 服务：

```text
groundline-gateway
groundline-fusion
groundline-filter
```

Docker image：

```text
groundline/groundline
groundline/server
groundline/worker
```

---

# 25. 第一阶段开发任务

## Week 1：项目骨架

```text
1. 创建 repo
2. 添加 Apache-2.0 LICENSE
3. 写 README 首屏
4. 建 pyproject.toml
5. 建 groundline package
6. 定义 Pydantic schemas
7. 实现 CLI init
8. 实现 SQLite metadata store
```

---

## Week 2：Ingestion MVP

```text
1. local file loader
2. txt parser
3. markdown parser
4. html parser
5. parser registry with reserved pdf adapter slot
6. block AST
7. markdown renderer
8. heading-aware chunker
9. chunk persistence
```

---

## Week 3：Index MVP

```text
1. embedding adapter
2. Qdrant vector store
3. rank_bm25 search store
4. indexer
5. content hash
6. incremental skip
```

---

## Week 4：Query MVP

```text
1. BM25 retriever
2. vector retriever
3. RRF fusion
4. dedupe
5. context builder
6. citation output
7. CLI query
```

---

## Week 5：Server + Eval

```text
1. FastAPI server
2. collection API
3. ingest API
4. query API
5. eval runner
6. Recall@K
7. MRR
8. quickstart example
```

---

## Week 6：开源可用性

```text
1. Dockerfile
2. docker-compose
3. pytest
4. GitHub Actions
5. docs
6. examples
7. CONTRIBUTING
8. ROADMAP
```

---

# 26. 最终版本定位

Groundline 的最终定位可以写成：

```text
Groundline is the retrieval layer between your documents and your LLM.
```

更完整：

```text
Groundline is an open-source retrieval engine for grounded, citation-ready LLM context. It turns complex documents into structured chunks, hybrid indexes, reranked evidence, and traceable context for reliable RAG applications.
```

中文：

```text
Groundline 是文档和 LLM 之间的检索层。
它把复杂文档转化为结构化 chunk、混合索引、重排序证据和可追溯上下文，
用于构建可靠的 RAG 应用。
```

我建议仓库创建时直接使用：

```text
repo:
  groundline

description:
  Open-source retrieval engine for grounded, citation-ready LLM context.

license:
  Apache-2.0

initial branch:
  main
```

第一版的核心目标不要做大而全，而是把这条链路做漂亮：

```text
source documents
  → grounded context
```

这就是 Groundline 的价值。
