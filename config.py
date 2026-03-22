from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
from typing import List

class ExtractionProfile(BaseModel):
    # Regexes for parsing items
    question_regex: str = r'^(\d+)\.'
    layout_question_regex: str = r'(?:^|\s)(\d+)[._]\s'
    figure_label_regex: str = r'Fig\.?\s*(\d+\.\d+)'
    
    # Section header exact matches
    decorative_headers: List[str] = ["Discover", "Science Society", "Inter-disciplinary", "Projects"]
    
    # Inline section split regex
    inline_section_regex: str = r'\s+(Discover[,\s]+design[,\s]*and\s+debate)'
    
    # Bullet start tracking
    bullet_start_regex: str = (
        r'(?:^|(?<=[.?!])\s+)'
        r'(?:Collect |Imagine |Organise |Organize |Make your |'
        r'An electroscope|Design |Explore |Create )'
    )
    
    # Layout and Deduplication thresholds
    min_figure_size: int = 50
    vert_buffer: int = 100

class Settings(BaseSettings):
    layout_provider: str = "ocr"  # Can be 'mock', 'pymupdf', 'ocr', 'azure', 'google', etc.
    pdf_path: str = "assets/Class8SampleCBSEQuestionAssignment.pdf"
    
    # Global extraction profile for the pipeline
    extraction_profile: ExtractionProfile = Field(default_factory=ExtractionProfile)
    
    class Config:
        env_file = ".env"

config = Settings()

