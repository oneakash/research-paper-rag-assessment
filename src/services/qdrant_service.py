from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue, MatchAny
from sentence_transformers import SentenceTransformer
import uuid
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from src.config import EMBEDDING_MODEL_NAME, QDRANT_HOST, QDRANT_PORT

class TokenAwareChunk:
    """Container for managing chunks with token awareness"""
    def __init__(self, text: str, metadata: Dict[str, Any], score: float = 0.0):
        self.text = text
        self.metadata = metadata
        self.score = score
        self.token_estimate = self._estimate_tokens(text)
        self.priority_score = score
    
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate tokens using 4 chars per token rule"""
        return len(text) // 4
    
    def truncate_to_tokens(self, max_tokens: int) -> 'TokenAwareChunk':
        """Create a truncated version of this chunk"""
        if self.token_estimate <= max_tokens:
            return self
        
        max_chars = max_tokens * 4
        truncated_text = self.text[:max_chars]
        
        # Try to truncate at sentence boundary
        last_period = truncated_text.rfind('.')
        last_newline = truncated_text.rfind('\n')
        
        boundary = max(last_period, last_newline)
        if boundary > max_chars * 0.8:  # If boundary is reasonably close
            truncated_text = self.text[:boundary + 1]
        else:
            truncated_text = truncated_text + "..."
        
        new_chunk = TokenAwareChunk(truncated_text, self.metadata.copy(), self.score)
        new_chunk.metadata['truncated'] = True
        new_chunk.metadata['original_tokens'] = self.token_estimate
        return new_chunk

class QdrantManager:
    def __init__(self):
        self.collection_name = "research_papers"
        self.analytics_collection = "query_analytics"
        self.max_history_size = 1000
        self.query_history = []
        
        # Token management settings
        self.max_context_tokens = 3000
        self.max_chunk_tokens = 400
        self.target_chunks = 5
        
        # Initialize with connection retry
        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize Qdrant connection with retry logic"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                print(f"🔄 Attempting to connect to Qdrant (attempt {attempt + 1}/{max_retries})...")
                
                # Initialize client with more aggressive timeout settings
                self.client = QdrantClient(
                    host=QDRANT_HOST, 
                    port=QDRANT_PORT,
                    timeout=30,  # Increased timeout
                    prefer_grpc=False,  # Use HTTP instead of gRPC
                    api_key=None,
                    prefix=None,
                    https=False
                )
                
                # Test connection with a simple operation
                collections = self.client.get_collections()
                print(f"✅ Successfully connected to Qdrant. Found {len(collections.collections)} collections")
                
                # Initialize encoder
                print("🔄 Loading embedding model...")
                self.encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
                print("✅ Embedding model loaded")
                
                # Ensure collections exist
                self._ensure_collections()
                return
                
            except Exception as e:
                print(f"❌ Failed to connect to Qdrant (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    print(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print("❌ All connection attempts failed. Starting in offline mode.")
                    self._initialize_offline_mode()

    def _initialize_offline_mode(self):
        """Initialize in offline mode when Qdrant is not available"""
        print("🚫 Initializing in offline mode")
        self.client = None
        self.encoder = None
        self._offline_mode = True

    def _ensure_collections(self):
        """Ensure both main and analytics collections exist"""
        if not self.client:
            print("⚠️ Cannot create collections: Qdrant not connected")
            return
            
        try:
            # Main collection for research papers
            if not self.client.collection_exists(self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
                print(f"✅ Created collection: {self.collection_name}")
            
            # Analytics collection for query tracking
            if not self.client.collection_exists(self.analytics_collection):
                self.client.create_collection(
                    collection_name=self.analytics_collection,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
                print(f"✅ Created analytics collection: {self.analytics_collection}")
                
        except Exception as e:
            print(f"⚠️ Failed to create collections: {str(e)}")

    def is_connected(self) -> bool:
        """Check if Qdrant is connected"""
        return self.client is not None

    def add_chunks(self, chunks, paper_id, paper_title, paper_metadata=None):
        """Add document chunks to vector store with token-aware processing"""
        if not self.is_connected():
            print("⚠️ Cannot add chunks: Qdrant not connected")
            return 0
            
        if not chunks:
            print("⚠️ No chunks to add")
            return 0

        points = []
        successful_chunks = 0
        
        for i, chunk in enumerate(chunks):
            try:
                # Create token-aware chunk for processing
                chunk_text = chunk["text"]
                token_count = len(chunk_text) // 4  # Estimate tokens
                
                # If chunk is too large, split it
                if token_count > self.max_chunk_tokens:
                    sub_chunks = self._split_large_chunk(chunk_text, self.max_chunk_tokens)
                    print(f"📄 Split large chunk into {len(sub_chunks)} sub-chunks")
                else:
                    sub_chunks = [chunk_text]
                
                # Process each sub-chunk
                for j, sub_chunk_text in enumerate(sub_chunks):
                    # Generate embedding
                    vector = self.encoder.encode(sub_chunk_text).tolist()
                    point_id = str(uuid.uuid4())
                    
                    payload = {
                        "text": sub_chunk_text,
                        "page": chunk["page"],
                        "section": chunk.get("section", "Unknown"),
                        "word_count": len(sub_chunk_text.split()),
                        "token_count": len(sub_chunk_text) // 4,
                        "paper_id": paper_id,
                        "paper_title": paper_title,
                        "chunk_index": i,
                        "sub_chunk_index": j if len(sub_chunks) > 1 else None,
                        "created_at": datetime.now().isoformat(),
                    }
                    
                    # Add paper metadata
                    if paper_metadata:
                        payload.update({
                            "authors": paper_metadata.get("authors", []),
                            "year": paper_metadata.get("year", None),
                            "doi": paper_metadata.get("doi", None),
                            "abstract": paper_metadata.get("abstract", ""),
                        })
                    
                    point = PointStruct(id=point_id, vector=vector, payload=payload)
                    points.append(point)
                    successful_chunks += 1
                
            except Exception as e:
                print(f"❌ Failed to process chunk {i}: {str(e)}")
                continue
        
        if points:
            try:
                self.client.upsert(collection_name=self.collection_name, points=points)
                print(f"✅ Added {successful_chunks} chunks for paper: {paper_title}")
            except Exception as e:
                print(f"❌ Failed to upsert points: {str(e)}")
                return 0
        
        return successful_chunks

    def _split_large_chunk(self, text: str, max_tokens: int) -> List[str]:
        """Split large chunks into smaller token-aware pieces"""
        max_chars = max_tokens * 4
        
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        current_pos = 0
        
        while current_pos < len(text):
            end_pos = min(current_pos + max_chars, len(text))
            
            # Try to find a good breaking point
            chunk_text = text[current_pos:end_pos]
            
            if end_pos < len(text):  # Not the last chunk
                # Look for paragraph or sentence breaks
                last_para = chunk_text.rfind('\n\n')
                last_sentence = chunk_text.rfind('. ')
                last_newline = chunk_text.rfind('\n')
                
                # Use the best available break point
                break_point = max(last_para, last_sentence, last_newline)
                if break_point > max_chars * 0.7:  # If break point is reasonable
                    chunk_text = text[current_pos:current_pos + break_point + 1]
                    current_pos += break_point + 1
                else:
                    current_pos = end_pos
            else:
                current_pos = end_pos
            
            if chunk_text.strip():
                chunks.append(chunk_text.strip())
        
        return chunks

    def search_similar_chunks(self, query_text: str, limit: int = 15, paper_ids: Optional[List[int]] = None, 
                             track_query: bool = True) -> List[TokenAwareChunk]:
        """Search for similar chunks with token awareness"""
        if not self.is_connected():
            print("⚠️ Cannot search: Qdrant not connected")
            return []
            
        start_time = time.time()
        
        try:
            # First, check collection status
            print(f"🔍 Checking collection status...")
            try:
                collection_info = self.client.get_collection(self.collection_name)
                print(f"📊 Collection '{self.collection_name}' has {collection_info.points_count} points")
                
                if collection_info.points_count == 0:
                    print("⚠️ Collection is empty - no vectors to search")
                    return []
                    
            except Exception as e:
                print(f"❌ Failed to check collection: {str(e)}")
                return []
            
            # Generate query vector
            print(f"🔄 Encoding query: '{query_text[:50]}...'")
            encoding_start = time.time()
            query_vector = self.encoder.encode(query_text).tolist()
            encoding_time = time.time() - encoding_start
            print(f"✅ Query encoded in {encoding_time:.3f}s, vector size: {len(query_vector)}")
            
            # Build filter for specific papers if requested
            search_filter = None
            if paper_ids:
                print(f"📋 Building filter for papers: {paper_ids}")
                if len(paper_ids) == 1:
                    search_filter = Filter(
                        must=[
                            FieldCondition(
                                key="paper_id",
                                match=MatchValue(value=paper_ids[0])
                            )
                        ]
                    )
                else:
                    search_filter = Filter(
                        must=[
                            FieldCondition(
                                key="paper_id",
                                match=MatchAny(any=paper_ids)
                            )
                        ]
                    )
                print(f"✅ Filter created: {search_filter}")
            else:
                print("📋 No filter - searching all papers")
            
            # Get more results initially for better selection
            search_limit = min(limit * 2, 50)
            print(f"🔍 Starting vector search with limit: {search_limit}")
            
            # Perform search with timeout monitoring
            search_start = time.time()
            try:
                search_result = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=search_filter,
                    limit=search_limit,
                    with_payload=True,
                    with_vectors=False
                )
                search_time = time.time() - search_start
                print(f"✅ Vector search completed in {search_time:.3f}s")
                
            except Exception as search_error:
                search_time = time.time() - search_start
                print(f"❌ Vector search failed after {search_time:.3f}s: {str(search_error)}")
                print(f"❌ Search error type: {type(search_error).__name__}")
                
                # Try a simpler search without filter if the original failed
                if search_filter:
                    print("🔄 Retrying search without filter...")
                    try:
                        search_result = self.client.search(
                            collection_name=self.collection_name,
                            query_vector=query_vector,
                            query_filter=None,
                            limit=10,  # Smaller limit
                            with_payload=True,
                            with_vectors=False
                        )
                        print("✅ Retry without filter succeeded")
                    except Exception as retry_error:
                        print(f"❌ Retry also failed: {str(retry_error)}")
                        return []
                else:
                    return []
            
            total_time = time.time() - start_time
            print(f"📊 Found {len(search_result)} raw results in {total_time:.3f}s")
            
            if not search_result:
                print("⚠️ No search results found")
                return []
            
            # Log first few results for debugging
            print(f"📋 Sample results:")
            for i, hit in enumerate(search_result[:3]):
                paper_title = hit.payload.get('paper_title', 'Unknown')[:50]
                section = hit.payload.get('section', 'Unknown')
                page = hit.payload.get('page', 0)
                score = hit.score
                print(f"  {i+1}. {paper_title} | {section} p{page} | score: {score:.3f}")
            
            # Convert to TokenAwareChunks
            print(f"🔄 Converting to TokenAwareChunks...")
            token_chunks = []
            for hit in search_result:
                chunk = TokenAwareChunk(
                    text=hit.payload.get('text', ''),
                    metadata={
                        'paper_title': hit.payload.get('paper_title', 'Unknown'),
                        'section': hit.payload.get('section', 'Unknown'),
                        'page': hit.payload.get('page', 0),
                        'paper_id': hit.payload.get('paper_id'),
                        'token_count': hit.payload.get('token_count', len(hit.payload.get('text', '')) // 4)
                    },
                    score=hit.score
                )
                token_chunks.append(chunk)
            
            print(f"✅ Converted {len(token_chunks)} chunks")
            
            # Smart deduplication and selection
            print(f"🔄 Optimizing chunks for tokens...")
            optimized_chunks = self._optimize_chunks_for_tokens(token_chunks, query_text, limit)
            
            # Track query for analytics with correct parameters
            if track_query and optimized_chunks:
                result_scores = [chunk.score for chunk in optimized_chunks]
                print(f"📊 Tracking query: '{query_text[:30]}...' with {len(optimized_chunks)} results")
                self._track_query(
                    query_text=query_text,
                    paper_ids=paper_ids or [],
                    results_count=len(optimized_chunks),
                    search_time=total_time,
                    result_scores=result_scores
                )
                print(f"📊 Query tracked. History size: {len(self.query_history)}")
            
            print(f"✅ Returning {len(optimized_chunks)} optimized chunks")
            return optimized_chunks
            
        except Exception as e:
            total_time = time.time() - start_time
            print(f"❌ Search failed after {total_time:.3f}s: {str(e)}")
            print(f"❌ Error type: {type(e).__name__}")
            import traceback
            print(f"❌ Full traceback: {traceback.format_exc()}")
            return []

    def _optimize_chunks_for_tokens(self, chunks: List[TokenAwareChunk], query: str, target_count: int) -> List[TokenAwareChunk]:
        """Optimize chunk selection based on tokens and relevance"""
        if not chunks:
            return []
        
        # Remove duplicates based on content similarity
        unique_chunks = self._deduplicate_chunks(chunks)
        print(f"📋 After deduplication: {len(unique_chunks)} unique chunks")
        
        # Calculate priority scores (combine relevance + keyword matching)
        for chunk in unique_chunks:
            chunk.priority_score = self._calculate_chunk_priority(chunk, query)
        
        # Sort by priority
        unique_chunks.sort(key=lambda x: x.priority_score, reverse=True)
        
        # Select chunks that fit within token budget
        selected_chunks = []
        total_tokens = 0
        query_tokens = len(query) // 4
        available_tokens = self.max_context_tokens - query_tokens - 100  # Reserve for prompt
        
        print(f"📊 Token budget: {available_tokens} tokens available")
        
        for chunk in unique_chunks:
            if len(selected_chunks) >= target_count:
                break
                
            chunk_tokens = chunk.token_estimate
            
            if total_tokens + chunk_tokens <= available_tokens:
                selected_chunks.append(chunk)
                total_tokens += chunk_tokens
                print(f"   ✅ Added chunk: {chunk_tokens} tokens (total: {total_tokens})")
            elif available_tokens - total_tokens > 50:  # If there's still meaningful space
                # Try to fit a truncated version
                remaining_tokens = available_tokens - total_tokens - 10
                truncated_chunk = chunk.truncate_to_tokens(remaining_tokens)
                selected_chunks.append(truncated_chunk)
                total_tokens += truncated_chunk.token_estimate
                print(f"   ✂️ Added truncated chunk: {truncated_chunk.token_estimate} tokens")
                break
            else:
                print(f"   ❌ No space for chunk: {chunk_tokens} tokens")
                break
        
        print(f"📝 Final selection: {len(selected_chunks)} chunks, {total_tokens} tokens")
        return selected_chunks

    def _deduplicate_chunks(self, chunks: List[TokenAwareChunk]) -> List[TokenAwareChunk]:
        """Remove duplicate chunks based on content similarity"""
        unique_chunks = []
        seen_content_hashes = set()
        seen_paper_pages = set()
        
        for chunk in chunks:
            # Create content hash (first 100 + last 50 chars)
            text = chunk.text
            if len(text) > 150:
                content_key = text[:100] + text[-50:]
            else:
                content_key = text
            
            content_hash = hash(content_key)
            
            # Also check paper + page combination to avoid duplicates
            paper_page_key = f"{chunk.metadata.get('paper_id')}_{chunk.metadata.get('page')}"
            
            if content_hash not in seen_content_hashes:
                # If same page, keep the one with higher score
                if paper_page_key in seen_paper_pages:
                    # Find existing chunk from same page and compare scores
                    existing_idx = None
                    for i, existing_chunk in enumerate(unique_chunks):
                        if f"{existing_chunk.metadata.get('paper_id')}_{existing_chunk.metadata.get('page')}" == paper_page_key:
                            existing_idx = i
                            break
                    
                    if existing_idx is not None and chunk.score > unique_chunks[existing_idx].score:
                        unique_chunks[existing_idx] = chunk  # Replace with higher score
                else:
                    unique_chunks.append(chunk)
                    seen_content_hashes.add(content_hash)
                    seen_paper_pages.add(paper_page_key)
        
        return unique_chunks

    def _calculate_chunk_priority(self, chunk: TokenAwareChunk, query: str) -> float:
        """Calculate priority score for chunk selection"""
        base_score = chunk.score
        
        text_lower = chunk.text.lower()
        query_lower = query.lower()
        
        # Keyword matching bonus
        query_words = [w for w in query_lower.split() if len(w) > 2]
        keyword_matches = sum(1 for word in query_words if word in text_lower)
        keyword_bonus = (keyword_matches / len(query_words)) * 0.2 if query_words else 0
        
        # Exact phrase bonus
        phrase_bonus = 0.15 if query_lower in text_lower else 0
        
        # Section importance
        section = chunk.metadata.get('section', '').lower()
        section_weights = {
            'abstract': 0.2, 'conclusion': 0.2, 'results': 0.15,
            'findings': 0.15, 'introduction': 0.1, 'methodology': 0.1
        }
        section_bonus = section_weights.get(section, 0)
        
        # Length preference (moderate length preferred)
        token_count = chunk.token_estimate
        if 50 <= token_count <= 300:
            length_bonus = 0.05
        elif token_count < 30:
            length_bonus = -0.1  # Too short
        else:
            length_bonus = 0  # Acceptable
        
        priority = base_score + keyword_bonus + phrase_bonus + section_bonus + length_bonus
        return priority

    # Keep the original search_similar for backward compatibility
    def search_similar(self, query_text: str, limit: int = 5, paper_ids: Optional[List[int]] = None, 
                      track_query: bool = True):
        """Original search method - returns Qdrant results for compatibility"""
        chunks = self.search_similar_chunks(query_text, limit, paper_ids, track_query)
        
        # Convert back to Qdrant-style results for compatibility
        class MockHit:
            def __init__(self, chunk: TokenAwareChunk):
                self.score = chunk.score
                self.payload = {
                    'text': chunk.text,
                    'paper_title': chunk.metadata.get('paper_title'),
                    'section': chunk.metadata.get('section'),
                    'page': chunk.metadata.get('page'),
                    'paper_id': chunk.metadata.get('paper_id'),
                    'token_count': chunk.metadata.get('token_count')
                }
        
        return [MockHit(chunk) for chunk in chunks]

    # Update other methods to maintain compatibility...
    def get_paper_stats(self, paper_id: int) -> Dict[str, Any]:
        """Get statistics for a specific paper"""
        if not self.is_connected():
            return {"error": "Qdrant not connected"}
            
        try:
            search_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
                ),
                limit=10000,
                with_payload=True,
                with_vectors=False
            )
            
            chunks = search_result[0]
            
            if not chunks:
                return {"error": "No chunks found for this paper"}
            
            # Calculate token-aware statistics
            total_chunks = len(chunks)
            total_words = sum(chunk.payload.get('word_count', 0) for chunk in chunks)
            total_tokens = sum(chunk.payload.get('token_count', len(chunk.payload.get('text', '')) // 4) for chunk in chunks)
            sections = Counter(chunk.payload.get('section', 'Unknown') for chunk in chunks)
            pages = Counter(chunk.payload.get('page', 0) for chunk in chunks)
            
            first_chunk = chunks[0]
            paper_title = first_chunk.payload.get('paper_title', 'Unknown')
            
            return {
                "paper_id": paper_id,
                "paper_title": paper_title,
                "total_chunks": total_chunks,
                "total_words": total_words,
                "total_tokens": total_tokens,
                "avg_tokens_per_chunk": total_tokens / total_chunks if total_chunks > 0 else 0,
                "sections": dict(sections),
                "pages": dict(pages),
                "created_at": first_chunk.payload.get('created_at')
            }
            
        except Exception as e:
            return {"error": f"Failed to get paper stats: {str(e)}"}

    def delete_paper_vectors(self, paper_id: int) -> Dict[str, Any]:
        """Delete all vectors associated with a paper"""
        if not self.is_connected():
            return {"error": "Qdrant not connected"}
            
        try:
            search_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
                ),
                limit=10000,
                with_payload=False,
                with_vectors=False
            )
            
            point_ids = [point.id for point in search_result[0]]
            
            if not point_ids:
                return {"message": "No vectors found for this paper", "deleted_count": 0}
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=point_ids
            )
            
            return {
                "message": f"Successfully deleted vectors for paper {paper_id}",
                "deleted_count": len(point_ids)
            }
            
        except Exception as e:
            return {"error": f"Failed to delete paper vectors: {str(e)}"}

    def get_query_history(self, limit: int = 50) -> List[Dict]:
        """Get recent query history"""
        return self.query_history[-limit:]

    def get_analytics_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get analytics summary for the last N days"""
        if not self.query_history:
            return {"message": "No query history available", "days": days}
            
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_queries = [
            q for q in self.query_history 
            if datetime.fromisoformat(q['timestamp']) >= cutoff_date
        ]
        
        if not recent_queries:
            return {"message": "No recent queries found", "days": days}
        
        total_queries = len(recent_queries)
        avg_search_time = sum(q.get('search_time', 0) for q in recent_queries) / total_queries
        avg_results = sum(q.get('results_count', 0) for q in recent_queries) / total_queries
        
        all_words = []
        for q in recent_queries:
            all_words.extend(q['query_text'].lower().split())
        
        word_counts = Counter(w for w in all_words if len(w) > 3)
        popular_terms = dict(word_counts.most_common(10))
        
        return {
            "period_days": days,
            "total_queries": total_queries,
            "avg_search_time": round(avg_search_time, 3),
            "avg_results_per_query": round(avg_results, 1),
            "popular_terms": popular_terms,
            "queries_per_day": round(total_queries / days, 1),
            "qdrant_connected": self.is_connected()
        }

    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the vector collections"""
        if not self.is_connected():
            return {"error": "Qdrant not connected"}
            
        try:
            main_info = self.client.get_collection(self.collection_name)
            
            result = {
                "main_collection": {
                    "name": self.collection_name,
                    "points_count": main_info.points_count,
                    "vectors_count": main_info.vectors_count,
                    "indexed_vectors_count": main_info.indexed_vectors_count,
                    "segments_count": main_info.segments_count
                }
            }
            
            try:
                analytics_info = self.client.get_collection(self.analytics_collection)
                result["analytics_collection"] = {
                    "name": self.analytics_collection,
                    "points_count": analytics_info.points_count,
                    "vectors_count": analytics_info.vectors_count
                }
            except:
                result["analytics_collection"] = {"error": "Analytics collection not found"}
                
            return result
            
        except Exception as e:
            return {"error": f"Failed to get collection info: {str(e)}"}

    def _track_query(self, query_text: str, paper_ids: List[int], results_count: int, 
                search_time: float, result_scores: List[float], search_type: str = "standard"):
        """Track query for analytics"""
        try:
            # Calculate scores
            avg_score = sum(result_scores) / len(result_scores) if result_scores else 0.0
            max_score = max(result_scores) if result_scores else 0.0
            
            query_record = {
                "query_text": query_text,
                "timestamp": datetime.now().isoformat(),
                "paper_ids": paper_ids,
                "results_count": results_count,
                "search_time": round(search_time, 3),
                "avg_score": round(avg_score, 3),
                "max_score": round(max_score, 3),
                "search_type": search_type,
                "query_length": len(query_text),
                "query_words": len(query_text.split())
            }
            
            self.query_history.append(query_record)
            print(f"📊 Added query record: {query_record['query_text'][:50]}...")
            
            # Keep history size manageable
            if len(self.query_history) > self.max_history_size:
                self.query_history = self.query_history[-self.max_history_size:]
                
        except Exception as e:
            print(f"❌ Failed to track query: {str(e)}")

    def search_hybrid(self, query_text: str, limit: int = 10, paper_ids: Optional[List[int]] = None):
        """Hybrid search using chunk-based approach"""
        return self.search_similar_chunks(query_text, limit=limit, paper_ids=paper_ids, track_query=True)