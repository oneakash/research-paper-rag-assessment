from src.services.qdrant_service import QdrantManager
from src.services.gemini_service import GeminiService
from typing import List, Optional, Dict, Any
import tiktoken
import time

class TokenManager:
    def __init__(self, model_name="gpt-3.5-turbo"):
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except:
            self.encoding = tiktoken.get_encoding("cl100k_base")  # fallback
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))
    
    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit"""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        
        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)

class RAGPipeline:
    def __init__(self):
        self.qdrant_mgr = QdrantManager()
        self.token_manager = TokenManager()
        
        # Model token limits (conservative estimates)
        self.model_limits = {
            "gemini-2.5-flash": 1000000,  # 1M tokens
            "gemini-2.5-pro": 2000000,    # 2M tokens
            "gemini-2.0-flash": 1000000   # 1M tokens
        }
        
        # Reserve tokens for response
        self.max_context_tokens = 2800  # Leave room for response
        
        # Initialize Gemini service (required)
        try:
            self.llm_service = GeminiService()
            print("✅ Successfully initialized Gemini service")
        except Exception as e:
            print(f"❌ Failed to initialize Gemini service: {str(e)}")
            raise RuntimeError(f"Gemini service initialization failed: {str(e)}. Please check your API key and configuration.")

    def _optimize_context_for_tokens(self, search_results: List, question: str, max_tokens: int = 2800):
        """Intelligently build context within token limits"""
        
        # Reserve tokens for question and prompt structure
        question_tokens = self.token_manager.count_tokens(question)
        prompt_overhead = 200  # For prompt structure
        available_tokens = max_tokens - question_tokens - prompt_overhead
        
        print(f"📊 Token budget: {available_tokens} tokens available for context")
        
        # Strategy 1: Prioritized chunking
        prioritized_chunks = []
        
        for hit in search_results:
            chunk_text = hit.payload.get('text', '')
            chunk_tokens = self.token_manager.count_tokens(chunk_text)
            
            prioritized_chunks.append({
                'hit': hit,
                'text': chunk_text,
                'tokens': chunk_tokens,
                'score': hit.score,
                'priority': self._calculate_chunk_priority(hit, question)
            })
        
        # Sort by priority (score + relevance)
        prioritized_chunks.sort(key=lambda x: x['priority'], reverse=True)
        
        # Strategy 2: Adaptive chunking
        selected_chunks = []
        used_tokens = 0
        
        for chunk in prioritized_chunks:
            if used_tokens + chunk['tokens'] <= available_tokens:
                selected_chunks.append(chunk)
                used_tokens += chunk['tokens']
                print(f"   ✅ Added chunk: {chunk['tokens']} tokens (total: {used_tokens})")
            else:
                # Try to fit a truncated version
                remaining_tokens = available_tokens - used_tokens
                if remaining_tokens > 100:  # Only if meaningful space left
                    truncated_text = self.token_manager.truncate_to_tokens(
                        chunk['text'], remaining_tokens - 50
                    )
                    chunk['text'] = truncated_text + "..."
                    chunk['tokens'] = remaining_tokens - 50
                    selected_chunks.append(chunk)
                    used_tokens += chunk['tokens']
                    print(f"   ✂️ Added truncated chunk: {chunk['tokens']} tokens")
                break
        
        print(f"📝 Final context uses {used_tokens}/{available_tokens} tokens")
        return selected_chunks

    def _calculate_chunk_priority(self, hit, question: str) -> float:
        """Calculate chunk priority based on multiple factors"""
        base_score = hit.score
        
        # Boost for exact keyword matches
        text_lower = hit.payload.get('text', '').lower()
        question_lower = question.lower()
        
        keyword_boost = 0
        question_words = question_lower.split()
        for word in question_words:
            if len(word) > 3 and word in text_lower:
                keyword_boost += 0.1
        
        # Boost for important sections
        section = hit.payload.get('section', 'Unknown').lower()
        section_boost = 0
        if section in ['abstract', 'conclusion', 'results', 'findings']:
            section_boost = 0.2
        elif section in ['introduction', 'methodology']:
            section_boost = 0.1
        
        # Penalty for very short or very long chunks
        text_length = len(hit.payload.get('text', ''))
        length_factor = 1.0
        if text_length < 100:
            length_factor = 0.8  # Too short
        elif text_length > 2000:
            length_factor = 0.9  # Too long
        
        priority = (base_score + keyword_boost + section_boost) * length_factor
        return priority

    def query(self, question: str, top_k: int = 5, paper_ids: Optional[List[int]] = None):
        """Query processing using only real Gemini service"""
        start_time = time.time()
        
        try:
            print(f"🔍 Processing query: '{question}' with top_k={top_k}")
            
            # Use chunk-based search with proper tracking
            initial_limit = min(top_k * 2, 15)  # Get 2x more for better selection
            
            # Use the new chunk-based search method
            chunks = self.qdrant_mgr.search_similar_chunks(
                query_text=question,
                limit=initial_limit,
                paper_ids=paper_ids,
                track_query=True
            )
            
            if not chunks:
                print("❌ No chunks found")
                return {
                    "answer": "No relevant information found for your question.",
                    "sources": [],
                    "context_used": 0,
                    "papers_searched": [],
                    "processing_time": time.time() - start_time
                }
            
            print(f"📊 Found {len(chunks)} chunks from search")
            
            # Convert chunks to the format expected by optimize_context_for_tokens
            mock_hits = []
            for chunk in chunks:
                class MockHit:
                    def __init__(self, chunk):
                        self.score = chunk.score
                        self.payload = {
                            'text': chunk.text,
                            'paper_title': chunk.metadata.get('paper_title'),
                            'section': chunk.metadata.get('section'),
                            'page': chunk.metadata.get('page'),
                            'paper_id': chunk.metadata.get('paper_id')
                        }
                mock_hits.append(MockHit(chunk))
            
            # Remove duplicates
            unique_results = self._deduplicate_results(mock_hits)
            print(f"📋 After deduplication: {len(unique_results)} unique results")
            
            # Optimize context for token limits
            selected_chunks = self._optimize_context_for_tokens(
                unique_results, question, self.max_context_tokens
            )
            
            # Build optimized context
            context_parts = []
            citations = []
            
            for chunk_data in selected_chunks:
                hit = chunk_data['hit']
                text_content = chunk_data['text']
                
                context_parts.append(
                    f"Paper: {hit.payload['paper_title']}\n"
                    f"Section: {hit.payload.get('section', 'Unknown')}, Page: {hit.payload['page']}\n"
                    f"Content: {text_content}\n"
                )
                
                citations.append({
                    "paper_title": hit.payload['paper_title'],
                    "section": hit.payload.get('section', 'Unknown'),
                    "page": hit.payload['page'],
                    "score": hit.score
                })
            
            context = "\n---\n".join(context_parts)
            context_tokens = self.token_manager.count_tokens(context)
            print(f"📝 Final context: {len(context)} chars, {context_tokens} tokens")
            
            # Generate answer using only Gemini service
            print("🤖 Generating answer using Gemini service")
            answer = self.llm_service.generate_answer(context, question)
            print(f"💬 Generated answer length: {len(answer)} characters")
            
            processing_time = time.time() - start_time
            print(f"⏱️ Total processing time: {processing_time:.3f}s")
            
            return {
                "answer": answer,
                "sources": citations,
                "context_used": len(context_parts),
                "papers_searched": list(set([c["paper_title"] for c in citations])),
                "processing_time": processing_time,
                "cached": False,
                "token_estimate": context_tokens + len(answer) // 4
            }
            
        except Exception as e:
            print(f"❌ Query failed: {str(e)}")
            # If Gemini fails, don't fallback to mock - let the error propagate
            raise RuntimeError(f"Query failed: {str(e)}")

    def _deduplicate_results(self, search_results):
        """Enhanced deduplication with similarity checking"""
        unique_results = []
        seen_fingerprints = set()
        
        for hit in search_results:
            text = hit.payload.get('text', '')
            
            # Create content fingerprint (first 100 + last 100 chars)
            if len(text) > 200:
                fingerprint = text[:100] + text[-100:]
            else:
                fingerprint = text
            
            # Add page and paper info to fingerprint
            fingerprint += f"_{hit.payload.get('paper_title', '')}_{hit.payload.get('page', 0)}"
            
            if fingerprint not in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                unique_results.append(hit)
                print(f"   📄 Unique: {hit.payload.get('paper_title', 'Unknown')} "
                      f"page {hit.payload.get('page', 0)} (score: {hit.score:.3f})")
            else:
                print(f"   🔄 Duplicate: {hit.payload.get('paper_title', 'Unknown')} "
                      f"page {hit.payload.get('page', 0)}")
        
        return unique_results

    def health_check(self) -> Dict[str, Any]:
        """Check the health of the RAG pipeline components"""
        return {
            "qdrant_connected": self.qdrant_mgr.is_connected(),
            "gemini_service": "initialized" if self.llm_service else "not_initialized",
            "token_manager": "ready",
            "status": "healthy" if self.qdrant_mgr.is_connected() and self.llm_service else "degraded"
        }