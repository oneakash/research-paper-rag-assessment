# Architecture

High-level overview of the research-paper RAG assessment system that ingests papers, builds indexes, answers queries, and evaluates retrieval/answers with automated metrics.

## Diagram (SVG)
Add your diagram file at: docs/assets/architecture.svg

Embed it in this page with either:
- Markdown (GitHub-friendly):
    ![System architecture](./assets/architecture.svg)
- HTML (control size):
    <img src="./assets/architecture.svg" alt="System architecture" width="900" />

Notes:
- Use a relative path from ARCHITECTURE.md.
- Consider Git LFS for large SVGs.
- Prefer explicit fills/strokes in the SVG for dark/light themes.

## Components
- Ingestion
    - Sources: PDFs, ArXiv/DOI, metadata API.
    - Normalization: metadata, deduping, versioning.
- Preprocessing
    - Text extraction (PDF), cleaning, sectioning.
    - Chunking (by headings/tokens), citation/figure capture.
- Embeddings and Index
    - Embedding model: <fill: e.g., OpenAI/Azure/local>.
    - Vector store: <fill: e.g., FAISS/Chroma/pgvector>.
    - Text index: BM25 for hybrid retrieval.
    - Artifact store for raw/processed docs.
- Retrieval and Reranking
    - Hybrid dense+BM25, filters (venue/year/topic).
    - Cross-encoder reranker (optional).
- Answering
    - Prompt assembly with citations.
    - Generator LLM with grounded context.
- Evaluation (Assessment)
    - Query set generation (manual/synthetic).
    - Metrics: Recall@k, Precision@k, nDCG, MRR, Context Recall, Faithfulness, Answer Relevance.
    - LLM-as-judge with bias controls and calibration.
    - Report and regression tracking.
- Orchestration and APIs
    - Service exposing /ingest, /index, /query, /evaluate.
    - Batch jobs for indexing and eval runs.
- Observability
    - Structured logs, traces, metrics, eval artifacts.
- Security
    - Secrets management, PII redaction, rate limits.

## Data Flow
1) Ingest sources → raw store
2) Parse/extract → cleaned text + metadata
3) Chunk/annotate → chunks + citations
4) Embed chunks → vectors
5) Upsert → vector store + BM25 index
6) Query → retrieve (hybrid) → rerank
7) Generate answer + cite sources
8) Evaluate with metrics → store reports and traces

## Deployment
- Local: Docker Compose for API, vector DB, evaluator.
- Cloud: Kubernetes (Helm) with object storage and managed DB.
- Config via env/secret store; infra as code.

## Paths to Update
- SVG: docs/assets/architecture.svg
- This page: docs/ARCHITECTURE.md
