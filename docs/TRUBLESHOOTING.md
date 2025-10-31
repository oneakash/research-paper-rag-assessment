# 🔧 Troubleshooting Guide

## Common Issues and Solutions

### 🚀 Installation & Setup Issues

#### Problem: Docker Container Won't Start

**Symptoms:**

- `docker-compose up` fails
- Services exit immediately
- Port already in use errors

**Solutions:**

```bash
# Check if ports are already in use
netstat -tlnp | grep :8000
netstat -tlnp | grep :6333
netstat -tlnp | grep :5432

# Kill processes using ports
sudo lsof -ti:8000 | xargs kill -9
sudo lsof -ti:6333 | xargs kill -9

# Remove existing containers
docker-compose down -v
docker container prune -f

# Check Docker resources
docker system df
docker system prune -f

# Restart Docker service
sudo systemctl restart docker

# Try starting again
docker-compose up -d
```

#### Problem: Environment Variables Not Loading

**Symptoms:**

- API key errors
- Database connection failures
- "Configuration not found" errors

**Solutions:**

```bash
# Check environment file exists
ls -la .env*

# Validate environment file format
cat .env.docker | grep -v '^#' | grep '='

# Test environment loading
docker-compose --env-file .env.docker config

# Verify variables in container
docker-compose exec rag-app printenv | grep GEMINI
```

### 🗄️ Database Issues

#### Problem: PostgreSQL Connection Failed

**Symptoms:**

- "Connection refused" errors
- "Database does not exist" errors
- Authentication failures

**Solutions:**

```bash
# Check PostgreSQL status
docker-compose exec postgres pg_isready -U rag_user

# Check database exists
docker-compose exec postgres psql -U rag_user -l

# Create database if missing
docker-compose exec postgres createdb -U rag_user research_papers

# Reset database
docker-compose exec postgres dropdb -U rag_user research_papers
docker-compose exec postgres createdb -U rag_user research_papers

# Check connection string
docker-compose exec rag-app python -c "
import os
print('DATABASE_URL:', os.getenv('DATABASE_URL'))
"

# Test manual connection
docker-compose exec postgres psql postgresql://rag_user:rag_password@localhost:5432/research_papers
```

#### Problem: Database Migration Errors

**Symptoms:**

- Table doesn't exist errors
- Schema version conflicts
- Permission denied errors

**Solutions:**

```bash
# Check current schema
docker-compose exec postgres psql -U rag_user research_papers -c "\dt"

# Run migrations manually
docker-compose exec rag-app python -c "
from src.database import create_tables
create_tables()
print('Tables created successfully')
"

# Reset schema completely
docker-compose exec postgres psql -U rag_user research_papers -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO rag_user;
"
```

### 🔍 Qdrant Vector Database Issues

#### Problem: Qdrant Connection Timeout

**Symptoms:**

- "Search failed: timed out" errors
- Vector search not working
- Empty search results

**Solutions:**

```bash
# Check Qdrant health
curl http://localhost:6333/health

# Check collections
curl http://localhost:6333/collections

# Check specific collection
curl http://localhost:6333/collections/research_papers

# Test direct connection
docker-compose exec rag-app python -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='qdrant', port=6333, timeout=10)
print('Collections:', client.get_collections())
"

# Restart Qdrant
docker-compose restart qdrant

# Check Qdrant logs
docker-compose logs qdrant
```

#### Problem: Empty Vector Collection

**Symptoms:**

- "Collection is empty" messages
- No search results
- Zero points in collection

**Solutions:**

```bash
# Check collection status
curl http://localhost:6333/collections/research_papers

# Check if papers are uploaded
curl http://localhost:8000/api/papers

# Re-upload and reprocess papers
curl -X POST "http://localhost:8000/api/papers/upload" \
  -F "file=@your_paper.pdf"

# Manually check vector count
docker-compose exec rag-app python -c "
from src.services.qdrant_service import QdrantManager
qm = QdrantManager()
qm._initialize_connection()
info = qm.client.get_collection('research_papers')
print(f'Points: {info.points_count}')
"
```

### 🤖 LLM Integration Issues

#### Problem: Gemini API Errors

**Symptoms:**

- "finish_reason: 2" (MAX_TOKENS)
- "API key not valid" errors
- "No content found" responses

**Solutions:**

```bash
# Verify API key
curl -H "x-goog-api-key: YOUR_API_KEY" \
  https://generativelanguage.googleapis.com/v1/models

# Test minimal request
docker-compose exec rag-app python -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_API_KEY')
model = genai.GenerativeModel('gemini-1.5-flash')
response = model.generate_content('Hello')
print(response.text)
"

# Check token usage
docker-compose logs rag-app | grep "token usage"

# Reduce context size
# Edit src/services/gemini_service.py
# Reduce max_context_length to 200
```

#### Problem: Fallback Responses Only

**Symptoms:**

- All responses start with "Based on the research..."
- No real LLM-generated content
- Generic answers

**Solutions:**

```bash
# Check LLM service status
curl http://localhost:8000/api/system/health

# Test with minimal question
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello", "top_k": 1}'

# Enable debug logging
# Set DEBUG=true in .env.docker
docker-compose restart rag-app

# Check detailed logs
docker-compose logs rag-app | grep "DEBUG:"
```

### 📄 PDF Processing Issues

#### Problem: PDF Upload Fails

**Symptoms:**

- "Failed to extract text" errors
- Empty document after upload
- Processing timeouts

**Solutions:**

```bash
# Check file format
file your_paper.pdf

# Test with different PDF
curl -X POST "http://localhost:8000/api/papers/upload" \
  -F "file=@simple_test.pdf"

# Check file size
ls -lh your_paper.pdf

# Test PDF processing manually
docker-compose exec rag-app python -c "
import PyPDF2
with open('your_paper.pdf', 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    print(f'Pages: {len(reader.pages)}')
    print(f'First page text: {reader.pages[0].extract_text()[:100]}')
"

# Check upload directory permissions
docker-compose exec rag-app ls -la uploads/
```

#### Problem: No Text Extracted from PDF

**Symptoms:**

- Upload succeeds but zero chunks created
- "No content found" in processing
- Empty search results

**Solutions:**

```bash
# Try different PDF extraction method
docker-compose exec rag-app python -c "
import pdfplumber
with pdfplumber.open('your_paper.pdf') as pdf:
    text = pdf.pages[0].extract_text()
    print(f'Extracted: {text[:200]}')
"

# Check if PDF is scanned/image-based
# Install OCR capability
pip install pytesseract
sudo apt-get install tesseract-ocr

# Use OCR for scanned PDFs
docker-compose exec rag-app python -c "
from pdf2image import convert_from_path
import pytesseract
pages = convert_from_path('your_paper.pdf')
text = pytesseract.image_to_string(pages[0])
print(f'OCR text: {text[:200]}')
"
```

### 🔧 Performance Issues

#### Problem: Slow Query Responses

**Symptoms:**

- Queries taking >30 seconds
- Timeout errors
- High CPU usage

**Solutions:**

```bash
# Check system resources
docker stats

# Monitor query performance
curl http://localhost:8000/api/analytics/popular

# Optimize Qdrant search
# Reduce top_k parameter
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "top_k": 2}'

# Check for memory issues
free -h
docker-compose exec rag-app python -c "
import psutil
print(f'Memory: {psutil.virtual_memory().percent}%')
print(f'CPU: {psutil.cpu_percent()}%')
"

# Scale services
docker-compose up -d --scale rag-app=2
```

#### Problem: Memory Exhaustion

**Symptoms:**

- Out of memory errors
- Container restarts
- Slow performance

**Solutions:**

```bash
# Check memory usage
docker stats --no-stream

# Increase container memory limits
# In docker-compose.yml:
deploy:
  resources:
    limits:
      memory: 4G

# Clear caches
docker-compose exec redis redis-cli FLUSHALL

# Optimize embedding model
# Use smaller model in .env.docker:
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2  # Smaller model
```

### 🌐 Network and API Issues

#### Problem: API Endpoints Not Accessible

**Symptoms:**

- Connection refused errors
- 404 errors for valid endpoints
- Network timeouts

**Solutions:**

```bash
# Check service status
docker-compose ps

# Test internal connectivity
docker-compose exec rag-app curl http://localhost:8000/api/system/health

# Check port mapping
docker port $(docker-compose ps -q rag-app)

# Test from host
curl -v http://localhost:8000/api/system/health

# Check firewall settings
sudo ufw status
sudo iptables -L

# Restart networking
docker-compose down
docker network prune -f
docker-compose up -d
```

#### Problem: CORS Errors

**Symptoms:**

- Browser console CORS errors
- Cross-origin request blocked
- Preflight request failures

**Solutions:**

```bash
# Add CORS headers in nginx.conf
add_header 'Access-Control-Allow-Origin' '*';
add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization';

# Or configure in FastAPI
# In src/main.py:
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🛠️ Debugging Tools

### Log Analysis

```bash
# Real-time logs
docker-compose logs -f --tail=50

# Search for errors
docker-compose logs | grep -i error

# Filter by service
docker-compose logs rag-app | grep "ERROR"

# Save logs to file
docker-compose logs > debug.log 2>&1
```

### Container Inspection

```bash
# Enter container shell
docker-compose exec rag-app bash

# Check running processes
docker-compose exec rag-app ps aux

# Check disk usage
docker-compose exec rag-app df -h

# Check environment variables
docker-compose exec rag-app printenv
```

### Database Debugging

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U rag_user research_papers

# Check table contents
\dt
SELECT COUNT(*) FROM papers;
SELECT * FROM papers LIMIT 5;

# Check indexes
\di

# Analyze query performance
EXPLAIN ANALYZE SELECT * FROM papers WHERE title ILIKE '%keyword%';
```

### Vector Database Debugging

```bash
# Qdrant collection info
curl http://localhost:6333/collections/research_papers

# Sample points
curl -X POST http://localhost:6333/collections/research_papers/points/scroll \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}'

# Search test
curl -X POST http://localhost:6333/collections/research_papers/points/search \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, 0.3, ...],
    "limit": 3
  }'
```

## 🚨 Emergency Recovery

### Complete System Reset

```bash
# Stop all services
docker-compose down -v

# Remove all data (WARNING: This deletes everything!)
docker volume rm $(docker volume ls -q)

# Clean Docker system
docker system prune -af

# Restart from scratch
cp .env.example .env.docker
# Edit .env.docker with your settings
docker-compose up -d

# Re-upload papers
curl -X POST "http://localhost:8000/api/papers/upload" \
  -F "file=@paper1.pdf"
```

### Backup and Restore

```bash
# Create backup
mkdir -p backups/$(date +%Y%m%d)
docker-compose exec postgres pg_dump -U rag_user research_papers > backups/$(date +%Y%m%d)/database.sql
docker cp $(docker-compose ps -q qdrant):/qdrant/storage backups/$(date +%Y%m%d)/qdrant/

# Restore from backup
docker-compose exec -T postgres psql -U rag_user research_papers < backups/20240101/database.sql
docker cp backups/20240101/qdrant/ $(docker-compose ps -q qdrant):/qdrant/storage
```

### Health Check Script

```bash
#!/bin/bash
# health_check.sh

echo "🏥 RAG System Health Check"
echo "========================="

# Check Docker
if ! docker --version > /dev/null 2>&1; then
    echo "❌ Docker not installed or not running"
    exit 1
fi

# Check services
services=("postgres" "qdrant" "redis" "rag-app")
for service in "${services[@]}"; do
    if docker-compose ps $service | grep -q "Up"; then
        echo "✅ $service is running"
    else
        echo "❌ $service is not running"
    fi
done

# Check API endpoints
echo "🔗 Testing API endpoints..."
if curl -f http://localhost:8000/api/system/health > /dev/null 2>&1; then
    echo "✅ API health endpoint working"
else
    echo "❌ API health endpoint failed"
fi

# Check database connection
if docker-compose exec -T postgres pg_isready -U rag_user > /dev/null 2>&1; then
    echo "✅ Database connection working"
else
    echo "❌ Database connection failed"
fi

# Check Qdrant
if curl -f http://localhost:6333/health > /dev/null 2>&1; then
    echo "✅ Qdrant connection working"
else
    echo "❌ Qdrant connection failed"
fi

echo "✅ Health check complete"
```

Make it executable and run:

```bash
chmod +x health_check.sh
./health_check.sh
```

This troubleshooting guide should help you resolve most common issues with the RAG system!
