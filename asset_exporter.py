"""
Asset Exporter — crops exact visual bounding boxes of figures from the PDF
and assigns them human-readable semantic names.
"""

import os
import pymupdf
from models import BlockGraph, FigureBlock

class AssetExporter:
    """
    AssetExporter is responsible for extracting physical visual figures from 
    the PDF using bounding boxes and saving them to disk.
    It supports 'human-in-the-loop' by respecting manually placed images in the output directory.
    """
    def __init__(self, pdf_path: str, output_dir: str = "assets_output"):
        self.pdf_path = pdf_path
        self.output_dir = output_dir

    def export(self, block_graph: BlockGraph) -> BlockGraph:
        """
        Iterates over FigureBlocks, crops their visual region from the PDF,
        saves the image with a semantic name, and updates the block's asset_id.
        """
        # Ensure output directory exists (do not delete old images, to preserve manual user overrides)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        
        doc = pymupdf.open(self.pdf_path)
        
        dec_counters = {}
        saved_count = 0
        
        for block in block_graph.blocks:
            if not isinstance(block, FigureBlock):
                continue
            
            # 1. Determine Semantic Name
            page_num = block.page or 1
            if block.related_question and block.caption:
                # E.g. "Q10_Fig._5.17"
                safe_cap = block.caption.replace(" ", "_")
                base_name = f"{block.related_question}_{safe_cap}"
            elif block.related_question:
                # E.g. "Q10_asset"
                base_name = f"{block.related_question}_asset"
            elif block.caption:
                # E.g. "Fig._5.18"
                safe_cap = block.caption.replace(" ", "_")
                base_name = safe_cap
            else:
                # E.g. "decorative_p2_1"
                c = dec_counters.get(page_num, 0) + 1
                dec_counters[page_num] = c
                base_name = f"decorative_p{page_num}_{c}"
                
            # 2. Check for manual override or crop from PDF
            # Check if there is already a manual override matching related_question
            manual_override = None
            if block.related_question:
                for f in os.listdir(self.output_dir):
                    if f.startswith(f"{block.related_question}_") and f.endswith((".png", ".jpeg", ".jpg")):
                        manual_override = f
                        break
            
            if manual_override:
                # Use the user's manually dropped file
                file_name = manual_override
                print(f"  → Found manual override for {block.related_question}: {file_name}")
            else:
                # Crop mathematically
                file_name = f"{base_name}.png"
                file_path = os.path.join(self.output_dir, file_name)
                
                if not os.path.exists(file_path):
                    page = doc[page_num - 1]
                    rect = pymupdf.Rect(block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1)
                    pix = page.get_pixmap(clip=rect, dpi=300)
                    pix.save(file_path)
                    saved_count += 1
            
            # 3. Update the blockgraph with the new asset_id
            block.asset_id = file_name

            
        doc.close()
        print(f"  → Cropped and saved {saved_count} semantically-named assets.")
        return block_graph
