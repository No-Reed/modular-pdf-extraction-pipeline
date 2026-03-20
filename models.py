from typing import List, Union, Optional
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

class BaseBlock(BaseModel):
    block_type: str
    bbox: BoundingBox

class TextBlock(BaseBlock):
    block_type: str = "text_block"
    content: str
    question_id: Optional[str] = None

class FigureBlock(BaseBlock):
    block_type: str = "figure_block"
    asset_id: str
    related_question: Optional[str] = None

class HeaderBlock(BaseBlock):
    block_type: str = "header_block"
    functional: bool = True  # Added so we can tag non-functional cartoons
    content: Optional[str] = None

class BlockGraph(BaseModel):
    blocks: List[Union[TextBlock, FigureBlock, HeaderBlock]] = Field(default_factory=list)
