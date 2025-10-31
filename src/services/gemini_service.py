
import google.generativeai as genai
from src.config import GEMINI_API_KEY
from typing import Dict, List, Any
import re
from collections import Counter

# Configure API key
genai.configure(api_key=GEMINI_API_KEY)

class GeminiService:
    def __init__(self, model_name="gemini-2.5-flash"):  # Use stable model
        try:
            print(f"DEBUG: Attempting to use model: {model_name}")
            self.model = genai.GenerativeModel(model_name)
            print(f"DEBUG: Successfully initialized {model_name}")
        except Exception as e:
            print(f"DEBUG: Failed to initialize {model_name}: {str(e)}")
            fallback_models = [
                "gemini-2.5-pro"
            ]
            for fallback in fallback_models:
                try:
                    print(f"DEBUG: Trying fallback model: {fallback}")
                    self.model = genai.GenerativeModel(fallback)
                    print(f"DEBUG: Successfully initialized {fallback}")
                    break
                except Exception as e2:
                    print(f"DEBUG: Failed to initialize {fallback}: {str(e2)}")
                    continue
            else:
                raise Exception("No working Gemini model found")

    def generate_answer(self, context: str, question: str) -> str:
        # DRASTICALLY reduce context to avoid MAX_TOKENS
        max_context_length = 400  # Very small to ensure we don't hit limits
        if len(context) > max_context_length:
            # Take first part of context (usually most relevant)
            context = context[:max_context_length]
            # Try to end at a sentence
            last_period = context.rfind('.')
            if last_period > max_context_length * 0.8:
                context = context[:last_period + 1]
            else:
                context = context + "..."
            print(f"DEBUG: Context truncated to {len(context)} characters")
        
        # Very minimal prompt to save tokens
        prompt = f"{context}\n\nQ: {question}\nA:"
        
        try:
            print(f"DEBUG: Sending request to Gemini...")
            print(f"DEBUG: Context length: {len(context)} characters")
            print(f"DEBUG: Prompt length: {len(prompt)} characters")
            print(f"DEBUG: Estimated total tokens: ~{len(prompt)//3}")  # More conservative estimate
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=150,  # Very small output limit
                    temperature=0.1,
                    top_p=0.9,
                    top_k=20,
                    candidate_count=1  # Only one candidate
                ),
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
            )
            
            print(f"DEBUG: Response received")
            print(f"DEBUG: Response type: {type(response)}")
            
            # Check usage metadata first
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, 'prompt_token_count', 0)
                candidates_tokens = getattr(usage, 'candidates_token_count', 0) 
                total_tokens = getattr(usage, 'total_token_count', 0)
                print(f"DEBUG: Token usage - prompt: {prompt_tokens}, candidates: {candidates_tokens}, total: {total_tokens}")
                
                # If we're using too many prompt tokens, this explains the issue
                if prompt_tokens > 500:
                    print(f"WARNING: Prompt tokens ({prompt_tokens}) are too high!")
            
            # Enhanced extraction with better error handling
            extracted_text = self._extract_response_text(response)
            
            if extracted_text and len(extracted_text.strip()) > 5:
                print(f"DEBUG: Successfully extracted: '{extracted_text[:100]}...'")
                return extracted_text
            else:
                print(f"DEBUG: No meaningful text extracted, using enhanced fallback")
                return self._generate_enhanced_fallback(context, question)
                
        except Exception as e:
            print(f"DEBUG: Exception occurred: {type(e).__name__}: {str(e)}")
            return self._generate_enhanced_fallback(context, question)

    def _extract_response_text(self, response) -> str:
        """Extract text from response with comprehensive debugging"""
        
        # Method 1: Try response.text (most direct)
        try:
            if hasattr(response, 'text') and response.text:
                text = response.text.strip()
                print(f"DEBUG: Method 1 - response.text: '{text[:50]}...'")
                return text
        except Exception as e:
            print(f"DEBUG: Method 1 failed: {str(e)}")
        
        # Method 2: Check candidates with detailed inspection
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            finish_reason = candidate.finish_reason
            print(f"DEBUG: Candidate finish_reason: {finish_reason}")
            
            # Detailed finish_reason analysis
            if finish_reason == 1:
                print("DEBUG: Finish reason: STOP (normal completion)")
            elif finish_reason == 2:
                print("DEBUG: Finish reason: MAX_TOKENS (hit token limit)")
            elif finish_reason == 3:
                print("DEBUG: Finish reason: SAFETY (blocked by safety)")
            elif finish_reason == 4:
                print("DEBUG: Finish reason: RECITATION (blocked for recitation)")
            else:
                print(f"DEBUG: Finish reason: OTHER ({finish_reason})")
            
            # Check content structure
            if hasattr(candidate, 'content') and candidate.content:
                print(f"DEBUG: Content role: {getattr(candidate.content, 'role', 'unknown')}")
                
                if hasattr(candidate.content, 'parts'):
                    parts_count = len(candidate.content.parts) if candidate.content.parts else 0
                    print(f"DEBUG: Content parts count: {parts_count}")
                    
                    # Even if parts count is 0, check if there's partial content
                    if parts_count > 0:
                        for i, part in enumerate(candidate.content.parts):
                            if hasattr(part, 'text') and part.text:
                                text = part.text.strip()
                                print(f"DEBUG: Method 2 - part {i} text: '{text[:50]}...'")
                                return text
                    else:
                        print(f"DEBUG: No parts in content - likely MAX_TOKENS with no output")
                        
                        # For MAX_TOKENS with no content, try to get partial content
                        if finish_reason == 2:
                            # Check if there's any text in the candidate structure
                            candidate_str = str(candidate)
                            if 'text:' in candidate_str:
                                # Try to extract any partial text
                                import re
                                text_match = re.search(r'text:\s*"([^"]*)"', candidate_str)
                                if text_match:
                                    partial_text = text_match.group(1).strip()
                                    if partial_text:
                                        print(f"DEBUG: Found partial text: '{partial_text}'")
                                        return partial_text
        
        # Method 3: Try response dictionary
        try:
            response_dict = response.to_dict() if hasattr(response, 'to_dict') else {}
            if 'candidates' in response_dict:
                for cand in response_dict['candidates']:
                    if 'content' in cand and 'parts' in cand['content']:
                        for part in cand['content']['parts']:
                            if isinstance(part, dict) and 'text' in part:
                                text = part['text'].strip()
                                if text:
                                    print(f"DEBUG: Method 3 - dict text: '{text[:50]}...'")
                                    return text
        except Exception as e:
            print(f"DEBUG: Method 3 failed: {str(e)}")
        
        print(f"DEBUG: All extraction methods failed - no content found")
        return None

    def _generate_enhanced_fallback(self, context: str, question: str) -> str:
        """Generate enhanced fallback when Gemini fails"""
        print("DEBUG: Generating enhanced fallback response")
        
        # Extract key information from context
        context_words = context.lower().split()
        question_words = question.lower().split()
        
        # Find relevant terms
        relevant_terms = []
        for word in question_words:
            if len(word) > 3 and word in context_words:
                relevant_terms.append(word)
        
        # Extract paper information
        paper_match = re.search(r'Paper:\s*([^\n]+)', context)
        paper_title = paper_match.group(1) if paper_match else "the research"
        
        # Extract section information  
        section_match = re.search(r'Section:\s*([^,\n]+)', context)
        section = section_match.group(1) if section_match else "the study"
        
        # Build response based on question type
        question_lower = question.lower()
        
        if any(word in question_lower for word in ['what', 'define', 'explain']):
            if relevant_terms:
                response = f"According to {paper_title}, {question.strip('?')} involves {', '.join(relevant_terms[:3])}."
            else:
                response = f"Based on {section} in {paper_title}, the research addresses {question.strip('?')}."
        
        elif any(word in question_lower for word in ['how', 'method', 'approach']):
            response = f"The methodology described in {paper_title} shows that {question.strip('?')} through systematic analysis."
            
        elif any(word in question_lower for word in ['why', 'benefit', 'advantage']):
            response = f"According to {paper_title}, {question.strip('?')} provides advantages in the research context."
            
        else:
            response = f"Based on {paper_title}, the research provides insights about {question.strip('?')}."
        
        # Add relevant context if available
        if relevant_terms:
            response += f" Key aspects include {', '.join(relevant_terms[:2])}."
        
        return response

    def _extract_context_analysis(self, context: str) -> Dict[str, Any]:
        """Analyze context for fallback generation"""
        analysis = {
            'papers': [],
            'sections': [],
            'key_terms': [],
            'concepts': []
        }
        
        # Extract paper titles
        paper_matches = re.findall(r'Paper:\s*([^\n]+)', context)
        analysis['papers'] = [p.strip() for p in paper_matches]
        
        # Extract sections
        section_matches = re.findall(r'Section:\s*([^,\n]+)', context)
        analysis['sections'] = [s.strip() for s in section_matches]
        
        # Extract key terms
        content_text = re.sub(r'Paper:|Section:|Page:|Content:', '', context)
        words = re.findall(r'\b[a-zA-Z]{4,}\b', content_text.lower())
        word_freq = Counter(words)
        
        # Filter out common words and get key terms
        common_words = {'that', 'with', 'this', 'from', 'they', 'have', 'been', 'were', 'will', 'such', 'more', 'also', 'than', 'only', 'other', 'some', 'what', 'about', 'which', 'their', 'would', 'there', 'could', 'first', 'research', 'study', 'paper', 'analysis'}
        
        for word, count in word_freq.most_common(10):
            if word not in common_words and count > 1:
                analysis['key_terms'].append(word)
        
        return analysis