from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
import os
import tempfile
from src.services.pdf_processor import extract_text_with_pages, extract_text_with_sections
from src.services.qdrant_service import QdrantManager
from src.services.db_service import get_db
from src.models.paper import Paper
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()
qdrant_mgr = QdrantManager()

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    paper_ids: Optional[List[int]] = None

class CitationResponse(BaseModel):
    paper_title: str
    section: str
    page: int
    relevance_score: float

class QueryResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    sources_used: List[str]
    confidence: float

@router.post("/api/papers/upload")
async def upload_paper(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Save temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name

    try:
        # Extract with section awareness
        extraction_result = extract_text_with_sections(temp_path)
        
        # Save to database with metadata
        paper = Paper(
            title=extraction_result["metadata"]["title"] or file.filename.replace(".pdf", ""),
            filename=file.filename,
            authors=",".join(extraction_result["metadata"]["authors"]),
            year=extraction_result["metadata"]["year"],
            doi=extraction_result["metadata"]["doi"],
            total_pages=extraction_result["total_pages"]
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)
        
        # Add to vector database with enhanced metadata
        chunks_indexed = qdrant_mgr.add_chunks(
            extraction_result["chunks"], 
            paper.id, 
            paper.title,
            paper_metadata=extraction_result["metadata"]
        )
        
        return {
            "paper_id": paper.id,
            "title": paper.title,
            "authors": extraction_result["metadata"]["authors"],
            "year": extraction_result["metadata"]["year"],
            "total_pages": extraction_result["total_pages"],
            "sections_found": list(extraction_result["sections"].keys()),
            "chunks_indexed": chunks_indexed,
            "status": "processed"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

from src.services.rag_pipeline import RAGPipeline

rag = RAGPipeline()

@router.post("/api/query", response_model=QueryResponse)
async def query_papers(
    request: QueryRequest,
    db: Session = Depends(get_db)
):
    try:
        print(f"🎯 API: Processing query '{request.question}' with top_k={request.top_k}")
        
        # Check RAG pipeline health first
        health = rag.health_check()
        if health["status"] == "degraded":
            raise HTTPException(
                status_code=503, 
                detail=f"RAG pipeline not ready: Qdrant connected: {health['qdrant_connected']}, Gemini: {health['gemini_service']}"
            )
        
        # Use the RAG pipeline
        result = rag.query(
            question=request.question,
            top_k=request.top_k,
            paper_ids=request.paper_ids
        )
        
        print(f"📊 API: RAG pipeline returned {len(result.get('sources', []))} sources")
        
        # Transform to expected format
        citations = []
        sources_used = set()
        
        for source in result["sources"]:
            citations.append(CitationResponse(
                paper_title=source["paper_title"],
                section=source.get("section", "Unknown"),
                page=source["page"],
                relevance_score=round(source["score"], 3)
            ))
            sources_used.add(f"{source['paper_title']}.pdf")
        
        # Calculate confidence based on top relevance scores
        confidence = calculate_confidence(result["sources"])
        
        print(f"✅ API: Returning response with {len(citations)} citations, confidence: {confidence:.3f}")
        
        return QueryResponse(
            answer=result["answer"],
            citations=citations,
            sources_used=list(sources_used),
            confidence=confidence
        )
        
    except RuntimeError as e:
        print(f"❌ API: RAG pipeline error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG pipeline error: {str(e)}")
    except Exception as e:
        print(f"❌ API: Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

def calculate_confidence(sources: List[dict]) -> float:
    """Calculate confidence based on relevance scores"""
    if not sources:
        return 0.0
    
    # Get top 3 scores for confidence calculation
    top_scores = sorted([s["score"] for s in sources[:3]], reverse=True)
    
    if len(top_scores) == 1:
        return min(top_scores[0], 0.95)
    elif len(top_scores) == 2:
        return min((top_scores[0] + top_scores[1]) / 2, 0.95)
    else:
        # Weight recent scores more heavily
        weighted_avg = (top_scores[0] * 0.5 + top_scores[1] * 0.3 + top_scores[2] * 0.2)
        return min(weighted_avg, 0.95)

# Paper Management
@router.get("/api/papers")
async def list_papers(db: Session = Depends(get_db)):
    """List all papers with enhanced metadata"""
    papers = db.query(Paper).all()
    
    paper_list = []
    for paper in papers:
        # Get vector stats if available
        stats = qdrant_mgr.get_paper_stats(paper.id) if qdrant_mgr.is_connected() else {}
        
        paper_info = {
            "id": paper.id,
            "title": paper.title,
            "filename": paper.filename,
            "authors": paper.authors.split(",") if paper.authors else [],
            "year": paper.year,
            "total_pages": paper.total_pages,
            "created_at": paper.created_at,
            "chunks_indexed": stats.get("total_chunks", 0),
            "total_tokens": stats.get("total_tokens", 0)
        }
        paper_list.append(paper_info)
    
    return {
        "papers": paper_list,
        "total_count": len(paper_list),
        "qdrant_connected": qdrant_mgr.is_connected()
    }

@router.get("/api/papers/{paper_id}")
async def get_paper(paper_id: int, db: Session = Depends(get_db)):
    """Get detailed paper information"""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Get vector stats
    vector_stats = qdrant_mgr.get_paper_stats(paper_id) if qdrant_mgr.is_connected() else {}
    
    return {
        "id": paper.id,
        "title": paper.title,
        "filename": paper.filename,
        "authors": paper.authors.split(",") if paper.authors else [],
        "year": paper.year,
        "doi": paper.doi,
        "total_pages": paper.total_pages,
        "created_at": paper.created_at,
        "vector_stats": vector_stats
    }

@router.delete("/api/papers/{paper_id}")
async def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    """Delete paper and associated vectors"""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    try:
        # Delete from vector store first
        vector_result = qdrant_mgr.delete_paper_vectors(paper_id) if qdrant_mgr.is_connected() else {"deleted_count": 0}
        
        # Delete from database
        db.delete(paper)
        db.commit()
        
        return {
            "message": f"Paper '{paper.title}' deleted successfully",
            "paper_id": paper_id,
            "vectors_deleted": vector_result.get("deleted_count", 0)
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

@router.get("/api/papers/{paper_id}/stats")
async def get_paper_stats(paper_id: int, db: Session = Depends(get_db)):
    """Get detailed statistics for a specific paper"""
    if not qdrant_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Vector search service unavailable")
    
    # Verify paper exists in database
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    try:
        stats = qdrant_mgr.get_paper_stats(paper_id)
        if "error" in stats:
            raise HTTPException(status_code=500, detail=stats["error"])
        return {"status": "success", "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/papers/{paper_id}/vectors")
async def delete_paper_vectors(paper_id: int, db: Session = Depends(get_db)):
    """Delete only vectors associated with a paper (keep database record)"""
    if not qdrant_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Vector search service unavailable")
    
    try:
        # Delete from vector store only
        vector_result = qdrant_mgr.delete_paper_vectors(paper_id)
        
        return {
            "status": "success",
            "message": f"Vectors for paper {paper_id} deleted",
            "vector_deletion": vector_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/queries/history")
async def get_query_history(limit: int = 50):
    """Get recent query history"""
    try:
        print(f"📊 API: Fetching query history with limit={limit}")
        history = qdrant_mgr.get_query_history(limit)
        print(f"📊 API: Retrieved {len(history)} history entries")
        
        # Add more detailed response
        response = {
            "status": "success", 
            "data": history, 
            "count": len(history),
            "total_tracked": len(qdrant_mgr.query_history),
            "qdrant_connected": qdrant_mgr.is_connected()
        }
        
        return response
    except Exception as e:
        print(f"❌ API: Failed to get query history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/analytics/popular")
async def get_popular_analytics(days: int = 7):
    """Get analytics for popular queries and topics"""
    try:
        print(f"📊 API: Fetching analytics for {days} days")
        analytics = qdrant_mgr.get_analytics_summary(days)
        print(f"📊 API: Analytics summary: {analytics}")
        
        return {"status": "success", "data": analytics}
    except Exception as e:
        print(f"❌ API: Failed to get analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/analytics/collections")
async def get_collection_analytics():
    """Get vector collection information"""
    if not qdrant_mgr.is_connected():
        return {
            "status": "error", 
            "message": "Qdrant not connected",
            "data": {"qdrant_connected": False}
        }
    
    try:
        info = qdrant_mgr.get_collection_info()
        return {"status": "success", "data": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/search/hybrid")
async def hybrid_search(request: QueryRequest):
    """Advanced hybrid search with multiple strategies"""
    if not qdrant_mgr.is_connected():
        raise HTTPException(status_code=503, detail="Vector search service unavailable")
    
    try:
        print(f"🔍 API: Hybrid search for '{request.question}'")
        
        # Use chunk-based search
        chunks = qdrant_mgr.search_similar_chunks(
            query_text=request.question,
            limit=request.top_k,
            paper_ids=request.paper_ids
        )
        
        # Convert chunks to response format
        citations = []
        for chunk in chunks:
            citations.append({
                "paper_title": chunk.metadata['paper_title'],
                "section": chunk.metadata.get('section', 'Unknown'),
                "page": chunk.metadata['page'],
                "score": round(chunk.score, 3),
                "priority_score": round(chunk.priority_score, 3),
                "token_count": chunk.token_estimate,
                "text_preview": chunk.text[:200] + "..." if len(chunk.text) > 200 else chunk.text
            })
        
        print(f"✅ API: Hybrid search returned {len(citations)} results")
        
        return {
            "results": citations,
            "total_found": len(citations),
            "search_type": "chunk_based_hybrid"
        }
        
    except Exception as e:
        print(f"❌ API: Hybrid search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/system/health")
async def system_health():
    """Check system health including all services"""
    try:
        rag_health = rag.health_check()
        
        health_status = {
            "status": rag_health["status"],
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": "connected",
                "qdrant": "connected" if rag_health["qdrant_connected"] else "disconnected",
                "gemini": rag_health["gemini_service"],
                "embedding_model": "loaded" if qdrant_mgr.encoder else "not_loaded"
            },
            "rag_pipeline": rag_health
        }
        
        return health_status
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "services": {"database": "unknown", "qdrant": "unknown", "gemini": "unknown"}
        }

@router.get("/api/debug/query-tracking")
async def debug_query_tracking():
    """Debug endpoint to check query tracking"""
    return {
        "query_history_length": len(qdrant_mgr.query_history),
        "last_5_queries": qdrant_mgr.query_history[-5:] if qdrant_mgr.query_history else [],
        "qdrant_connected": qdrant_mgr.is_connected(),
        "encoder_loaded": qdrant_mgr.encoder is not None
    }