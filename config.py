from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    layout_provider: str = "ocr"  # Can be 'mock', 'pymupdf', 'ocr', 'azure', 'google', etc.
    pdf_path: str = "assets/Class8SampleCBSEQuestionAssignment.pdf"
    
    class Config:
        env_file = ".env"

config = Settings()
