# 📡 API Documentation

## Base URL

```
http://localhost:8000
```

## Authentication

Currently no authentication required. In production, implement API keys or OAuth.

## Response Format

All responses follow this structure:

```json
{
  "status": "success|error",
  "data": {...},
  "message": "Optional message",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## Endpoints

### 🏥 System Health

#### GET `/api/system/health`

Check system status and service availability.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "services": {
    "database": "connected",
    "qdrant": "connected",
    "gemini": "initialized",
    "embedding_model": "loaded"
  },
  "rag_pipeline": {
    "qdrant_connected": true,
    "gemini_service": "initialized",
    "token_manager": "ready",
    "status": "healthy"
  }
}
```

### 📄 Paper Management

#### POST `/api/papers/upload`

Upload a PDF research paper.

**Request:**

```bash
curl -X POST "http://localhost:8000/api/papers/upload" \
  -F "file=@paper.pdf"
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "paper_id": 1,
    "title": "Attention Is All You Need",
    "authors": "Vaswani et al.",
    "year": 2017,
    "total_chunks": 45,
    "total_tokens": 12500,
    "processing_time": 23.4
  }
}
```

**Error Responses:**

- `400`: Invalid file format
- `413`: File too large (>100MB)
- `500`: Processing error

#### GET `/api/papers`

List all uploaded papers.

**Parameters:**

- `limit` (optional): Number of papers to return (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response:**

```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "title": "Attention Is All You Need",
      "authors": "Vaswani et al.",
      "year": 2017,
      "upload_date": "2024-01-01T10:00:00Z",
      "total_chunks": 45,
      "file_size": 2048576
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### GET `/api/papers/{paper_id}`

Get details for a specific paper.

**Response:**

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "title": "Attention Is All You Need",
    "authors": "Vaswani et al.",
    "year": 2017,
    "upload_date": "2024-01-01T10:00:00Z",
    "total_chunks": 45,
    "total_tokens": 12500,
    "sections": ["Abstract", "Introduction", "Methods", "Results"],
    "pages": 15
  }
}
```

#### DELETE `/api/papers/{paper_id}`

Delete a paper and its associated data.

**Response:**

```json
{
  "status": "success",
  "message": "Paper deleted successfully"
}
```

### 🔍 Query System

#### POST `/api/query`

Query the knowledge base.

**Request Body:**

```json
{
  "question": "What is the main contribution of the transformer paper?",
  "top_k": 3,
  "paper_ids": [1, 2], // Optional: limit to specific papers
  "include_metadata": true // Optional: include detailed metadata
}
```

**Response:**

```json
{
  "answer": "The main contribution is the introduction of the Transformer architecture...",
  "citations": [
    {
      "paper_title": "Attention Is All You Need",
      "section": "Abstract",
      "page": 1,
      "relevance_score": 0.89
    }
  ],
  "sources_used": ["paper_1.pdf"],
  "confidence": 0.85,
  "processing_time": 2.3,
  "query_id": "uuid-string"
}
```

**Error Responses:**

- `400`: Invalid question format
- `404`: No papers found
- `500`: Processing error

### 📊 Analytics

#### GET `/api/queries/history`

Get query history.

**Parameters:**

- `limit` (optional): Number of queries (default: 50)
- `user_id` (optional): Filter by user
- `days` (optional): Last N days

**Response:**

```json
{
  "status": "success",
  "data": [
    {
      "query_text": "What is machine learning?",
      "timestamp": "2024-01-01T10:00:00Z",
      "response_time": 2.1,
      "confidence": 0.82,
      "papers_referenced": ["paper_1.pdf"]
    }
  ],
  "total": 150
}
```

#### GET `/api/analytics/popular`

Get popular queries and topics.

**Parameters:**

- `days` (optional): Time period (default: 7)
- `limit` (optional): Number of results (default: 20)

**Response:**

```json
{
  "status": "success",
  "data": {
    "popular_queries": [
      { "query": "machine learning", "count": 45 },
      { "query": "neural networks", "count": 32 }
    ],
    "popular_papers": [
      { "title": "Attention Is All You Need", "query_count": 78 }
    ],
    "avg_response_time": 2.4,
    "total_queries": 1250
  }
}
```

## Error Handling

### Standard Error Response

```json
{
  "status": "error",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Detailed error description",
    "details": {
      "field": "specific field that caused error",
      "value": "invalid value"
    }
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Error Codes

| Code                 | Description               |
| -------------------- | ------------------------- |
| `INVALID_REQUEST`    | Malformed request         |
| `FILE_TOO_LARGE`     | Upload exceeds size limit |
| `UNSUPPORTED_FORMAT` | Invalid file type         |
| `PROCESSING_ERROR`   | Server processing error   |
| `NOT_FOUND`          | Resource not found        |
| `RATE_LIMITED`       | Too many requests         |

## Rate Limiting

- **Upload**: 10 files per hour
- **Query**: 100 requests per minute
- **Analytics**: 60 requests per minute

Rate limit headers included in responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## SDKs and Examples

### Python SDK

```python
import requests

class RAGClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def upload_paper(self, file_path):
        with open(file_path, 'rb') as f:
            response = requests.post(
                f"{self.base_url}/api/papers/upload",
                files={"file": f}
            )
        return response.json()

    def query(self, question, top_k=3):
        response = requests.post(
            f"{self.base_url}/api/query",
            json={"question": question, "top_k": top_k}
        )
        return response.json()

# Usage
client = RAGClient()
result = client.query("What is machine learning?")
print(result["answer"])
```

### JavaScript SDK

```javascript
class RAGClient {
  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async uploadPaper(file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${this.baseUrl}/api/papers/upload`, {
      method: "POST",
      body: formData,
    });

    return await response.json();
  }

  async query(question, topK = 3) {
    const response = await fetch(`${this.baseUrl}/api/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: question,
        top_k: topK,
      }),
    });

    return await response.json();
  }
}

// Usage
const client = new RAGClient();
const result = await client.query("What is machine learning?");
console.log(result.answer);
```

## Testing the API

### Using curl

```bash
# Health check
curl http://localhost:8000/api/system/health

# Upload paper
curl -X POST "http://localhost:8000/api/papers/upload" \
  -F "file=@paper.pdf"

# Query
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main contribution?", "top_k": 3}'

# Get papers
curl http://localhost:8000/api/papers

# Query history
curl "http://localhost:8000/api/queries/history?limit=10"
```

### Using Postman

1. Import the [Postman Collection](postman/RAG_API.postman_collection.json)
2. Set environment variable `baseUrl` to `http://localhost:8000`
3. Run the collection tests

### Using Python requests

```python
import requests
import json

base_url = "http://localhost:8000"

# Test health
health = requests.get(f"{base_url}/api/system/health")
print("Health:", health.json())

# Test query
query_data = {
    "question": "What is machine learning?",
    "top_k": 3
}
response = requests.post(
    f"{base_url}/api/query",
    json=query_data
)
print("Answer:", response.json()["answer"])
```

## WebSocket Support (Future)

Planning to add real-time features:

- Live query processing updates
- Real-time analytics dashboard
- Progress updates for large uploads

```javascript
// Future WebSocket API
const ws = new WebSocket("ws://localhost:8000/ws/queries");
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log("Processing update:", update);
};
```
