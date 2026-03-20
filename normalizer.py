from models import BlockGraph, TextBlock, FigureBlock, HeaderBlock, BoundingBox
from typing import Dict, Any

class Normalizer:
    def normalize(self, raw_layout: Dict[str, Any]) -> BlockGraph:
        """Converts raw provider JSON into strict Pydantic BlockGraph models."""
        graph = BlockGraph()
        
        for page in raw_layout.get("pages", []):
            for b_dict in page.get("blocks", []):
                bbox_dict = b_dict.get("bbox", {})
                bbox = BoundingBox(
                    x0=bbox_dict.get("x0", 0.0),
                    y0=bbox_dict.get("y0", 0.0),
                    x1=bbox_dict.get("x1", 0.0),
                    y1=bbox_dict.get("y1", 0.0)
                )
                
                b_type = b_dict.get("type")
                if b_type == "header":
                    header = HeaderBlock(
                        bbox=bbox,
                        content=b_dict.get("text"),
                        functional=not b_dict.get("is_decorative", False)
                    )
                    graph.blocks.append(header)
                    
                elif b_type == "text":
                    text_block = TextBlock(
                        bbox=bbox,
                        content=b_dict.get("text"),
                        question_id=b_dict.get("question_id")
                    )
                    graph.blocks.append(text_block)
                    
                elif b_type == "figure":
                    figure_block = FigureBlock(
                        bbox=bbox,
                        asset_id=b_dict.get("asset_id", ""),
                        related_question=b_dict.get("linked_question_id")
                    )
                    graph.blocks.append(figure_block)
                    
        return graph
