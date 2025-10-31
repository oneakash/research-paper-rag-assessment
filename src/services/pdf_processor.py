from PyPDF2 import PdfReader
import PyPDF2
import re
from typing import List, Dict, Any

def extract_text_with_sections(pdf_path: str) -> Dict[str, Any]:
    """Extract text with section awareness and metadata"""
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        # Extract metadata
        metadata = extract_paper_metadata(pdf_reader)
        
        # Extract text with sections
        full_text = ""
        pages_text = {}
        
        for page_num, page in enumerate(pdf_reader.pages, 1):
            page_text = page.extract_text()
            pages_text[page_num] = page_text
            full_text += f"\n--- Page {page_num} ---\n" + page_text
        
        # Identify sections
        sections = identify_sections(full_text, pages_text)
        
        # Create intelligent chunks
        chunks = create_semantic_chunks(sections, pages_text)
        
        return {
            "metadata": metadata,
            "sections": sections,
            "chunks": chunks,
            "total_pages": len(pdf_reader.pages)
        }

def extract_paper_metadata(pdf_reader) -> Dict[str, Any]:
    """Extract paper metadata (title, authors, year)"""
    metadata = {
        "title": None,
        "authors": [],
        "year": None,
        "doi": None
    }
    
    # Try to get from PDF metadata
    if pdf_reader.metadata:
        metadata["title"] = pdf_reader.metadata.get("/Title", "")
        metadata["authors"] = pdf_reader.metadata.get("/Author", "").split(",") if pdf_reader.metadata.get("/Author") else []
    
    # Extract from first page text (fallback)
    if len(pdf_reader.pages) > 0:
        first_page = pdf_reader.pages[0].extract_text()
        
        # Extract title (usually first large text)
        title_match = re.search(r'^(.+?)(?:\n.*?(?:Abstract|ABSTRACT))', first_page, re.MULTILINE | re.DOTALL)
        if title_match and not metadata["title"]:
            metadata["title"] = title_match.group(1).strip()
        
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', first_page)
        if year_match:
            metadata["year"] = int(year_match.group(0))
        
        # Extract DOI
        doi_match = re.search(r'doi[:\s]*(10\.\d+/[^\s]+)', first_page, re.IGNORECASE)
        if doi_match:
            metadata["doi"] = doi_match.group(1)
    
    return metadata

def identify_sections(full_text: str, pages_text: Dict[int, str]) -> Dict[str, Dict]:
    """Identify paper sections with page locations"""
    sections = {}
    
    section_patterns = {
        "Abstract": r'(?:ABSTRACT|Abstract)\s*\n',
        "Introduction": r'(?:INTRODUCTION|Introduction|1\.\s*Introduction)\s*\n',
        "Methods": r'(?:METHODS|Methods|METHODOLOGY|Methodology|2\.\s*(?:Methods|Methodology))\s*\n',
        "Results": r'(?:RESULTS|Results|3\.\s*Results)\s*\n',
        "Discussion": r'(?:DISCUSSION|Discussion|4\.\s*Discussion)\s*\n',
        "Conclusion": r'(?:CONCLUSION|Conclusion|CONCLUSIONS|Conclusions)\s*\n',
        "References": r'(?:REFERENCES|References|Bibliography)\s*\n'
    }
    
    for section_name, pattern in section_patterns.items():
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            start_pos = match.start()
            
            # Find which page this section starts on
            page_num = find_page_for_position(start_pos, pages_text)
            
            sections[section_name] = {
                "start_position": start_pos,
                "page": page_num,
                "found": True
            }
    
    return sections

def find_page_for_position(position: int, pages_text: Dict[int, str]) -> int:
    """Find which page a text position corresponds to"""
    current_pos = 0
    for page_num, page_text in pages_text.items():
        current_pos += len(page_text) + len(f"\n--- Page {page_num} ---\n")
        if position <= current_pos:
            return page_num
    return 1

def create_semantic_chunks(sections: Dict, pages_text: Dict[int, str]) -> List[Dict]:
    """Create intelligent chunks preserving semantic context"""
    chunks = []
    
    for page_num, page_text in pages_text.items():
        # Determine section for this page
        section = determine_page_section(page_num, sections)
        
        # Split page into paragraphs
        paragraphs = page_text.split('\n\n')
        
        current_chunk = ""
        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit, save current chunk
            if len(current_chunk) + len(paragraph) > 1000 and current_chunk:
                chunks.append({
                    "text": current_chunk.strip(),
                    "page": page_num,
                    "section": section,
                    "word_count": len(current_chunk.split())
                })
                current_chunk = paragraph
            else:
                current_chunk += "\n\n" + paragraph if current_chunk else paragraph
        
        # Add remaining chunk
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "page": page_num,
                "section": section,
                "word_count": len(current_chunk.split())
            })
    
    return chunks

def determine_page_section(page_num: int, sections: Dict) -> str:
    """Determine which section a page belongs to"""
    current_section = "Unknown"
    
    for section_name, section_info in sections.items():
        if section_info.get("found") and section_info.get("page", 999) <= page_num:
            current_section = section_name
    
    return current_section

def extract_text_with_pages(pdf_path):
    reader = PdfReader(pdf_path)
    chunks = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text and text.strip():
            chunks.append({
                "text": text.strip(),
                "page": page_num
            })
    return chunks