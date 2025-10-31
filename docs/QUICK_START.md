# 📖 RAG System Documentation

## 📋 Table of Contents

- [Quick Start Guide](docs/QUICK_START.md)
- [API Documentation](docs/API.md)
- [Docker Deployment](docs/DOCKER.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Configuration Guide](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Performance Tuning](docs/PERFORMANCE.md)
- [Security Guide](docs/SECURITY.md)
- [FAQ](docs/FAQ.md)

## 🎯 Overview

The Research Paper RAG (Retrieval-Augmented Generation) System is a production-ready solution for querying academic papers using advanced AI techniques. It combines vector search, natural language processing, and large language models to provide accurate, cited responses to research questions.

### Key Features

- 📄 **PDF Processing**: Automatic text extraction and chunking
- 🔍 **Vector Search**: Semantic similarity search using embeddings
- 🤖 **AI Answers**: LLM-generated responses with citations
- 📊 **Analytics**: Query tracking and performance metrics
- 🐳 **Containerized**: Docker-ready deployment
- 🔒 **Secure**: Environment-based configuration
- ⚡ **Fast**: Optimized for production workloads

### System Requirements

- **Python**: 3.10 or higher
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Storage**: 10GB available space
- **Docker**: 20.10 or higher (for containerized deployment)
- **API Keys**: Google Gemini API access

## 🚀 Quick Start

1. **Clone the repository**

   ```bash
   git clone https://github.com/oneakash/research-paper-rag-assessment.git
   cd research-paper-rag-assessment
   ```

2. **Start with Docker (Recommended)**

   ```bash
   # Copy environment template
   cp .env.example .env.docker

   # Edit with your API keys
   nano .env.docker

   # Start all services
   docker-compose --env-file .env.docker up -d
   ```

3. **Verify installation**

   ```bash
   curl http://localhost:8000/api/system/health
   ```

4. **Upload your first paper**

   ```bash
   curl -X POST "http://localhost:8000/api/papers/upload" \
     -F "file=@your_paper.pdf"
   ```

5. **Ask your first question**
   ```bash
   curl -X POST "http://localhost:8000/api/query" \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the main contribution?", "top_k": 3}'
   ```

## 📖 Detailed Documentation

![System architecture](assets/architecture.svg)

For comprehensive guides, see the [docs/](docs/) directory:

- **New Users**: Start with [Quick Start Guide](docs/QUICK_START.md)
- **DevOps**: Check [Docker Deployment](docs/DOCKER.md)
- **Issues**: Consult [Troubleshooting](docs/TROUBLESHOOTING.md)

