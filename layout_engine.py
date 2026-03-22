from abc import ABC, abstractmethod
from typing import Dict, Any

class LayoutProvider(ABC):
    @abstractmethod
    def extract_layout(self, pdf_path: str) -> Dict[str, Any]:
        """Extracts the document layout and returns a raw dictionary representation."""
        pass

class MockProvider(LayoutProvider):
    def extract_layout(self, pdf_path: str) -> Dict[str, Any]:
        # Hardcoded JSON response representing raw layout data
        # Specifically highlighting requirements: Q10 to Figure 5.17 and non-functional cartoon header
        return {
            "pages": [
                {
                    "page_number": 1,
                    "blocks": [
                        {
                            "type": "header",
                            "bbox": {"x0": 50, "y0": 20, "x1": 550, "y1": 100},
                            "text": "Fun Cartoon Header",
                            "is_decorative": True  # Non-functional header
                        },
                        {
                            "type": "text",
                            "bbox": {"x0": 50, "y0": 150, "x1": 550, "y1": 200},
                            "text": "10. In Figure 5.17, forces A and B are exerted on a block. Predict the direction of motion.",
                            "question_id": "Q10"
                        },
                        {
                            "type": "figure",
                            "bbox": {"x0": 100, "y0": 210, "x1": 400, "y1": 400},
                            "asset_id": "image_p1_15.jpeg",
                            "caption": "Figure 5.17",
                            "linked_question_id": "Q10"
                        }
                    ]
                }
            ]
        }

class PyMuPDFProvider(LayoutProvider):
    def extract_layout(self, pdf_path: str) -> Dict[str, Any]:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        layout_data = {"pages": []}
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("blocks")
            images = page.get_image_info()
            
            page_dict = {
                "page_number": page_num + 1,
                "blocks": []
            }
            
            # Extract Text Blocks
            for b_idx, b in enumerate(blocks):
                x0, y0, x1, y1, text, block_no, block_type = b
                if block_type == 0:  # Text block
                    bbox = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                    text_content = text.strip()
                    if not text_content:
                        continue
                        
                    if y1 < 100 and len(text_content) < 50 and "\n" not in text_content:
                        page_dict["blocks"].append({
                            "type": "header",
                            "bbox": bbox,
                            "text": text_content,
                            "is_decorative": False
                        })
                    else:
                        page_dict["blocks"].append({
                            "type": "text",
                            "bbox": bbox,
                            "text": text_content
                        })
            
            # Extract Image / Figure Blocks explicitly
            for img_info in images:
                x0, y0, x1, y1 = img_info["bbox"]
                bbox = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                page_dict["blocks"].append({
                    "type": "figure",
                    "bbox": bbox,
                    "asset_id": f"temp_p{page_num + 1}_idx{b_idx}_{img_info.get('number', 0)}"
                })
                    
            layout_data["pages"].append(page_dict)
            
        return layout_data

class OCRLayoutProvider(LayoutProvider):
    """Uses PaddleOCR to extract text from image-based PDFs and PyMuPDF for figures."""
    
    def extract_layout(self, pdf_path: str) -> Dict[str, Any]:
        import pymupdf
        from paddleocr import PaddleOCR
        import os
        import re
        from config import config
        
        doc = pymupdf.open(pdf_path)
        ocr = PaddleOCR(use_angle_cls=False, lang='en')
        layout_data = {"pages": []}
        
        # Regex to detect numbered questions: can be "10. ", "2_ ", etc., due to OCR errors
        question_re = re.compile(config.extraction_profile.layout_question_regex)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_width = page.rect.width
            page_height = page.rect.height
            
            page_dict = {
                "page_number": page_num + 1,
                "blocks": []
            }
            
            # --- TEXT EXTRACTION via OCR ---
            # Render page to a temporary high-res image for OCR
            pix = page.get_pixmap(dpi=400)
            img_width, img_height = pix.width, pix.height
            temp_img_path = os.path.join("assets", f"_ocr_temp_p{page_num + 1}.png")
            pix.save(temp_img_path)
            
            # Run PaddleOCR on the rendered page image
            result = ocr.ocr(temp_img_path)
            
            # Scale factors: OCR coordinates are in pixel space, convert to PDF points
            scale_x = page_width / img_width
            scale_y = page_height / img_height
            
            # PaddleOCR returns [[[x,y],...], ('text', conf)]
            if result and result[0]:
                raw_lines = result[0]
                # Sort results top-to-bottom by y-coordinate for reading order
                raw_lines.sort(key=lambda r: r[0][0][1])
                
                # Pass 1: Group adjacent text fragments into merged paragraphs
                merged_paragraphs = []
                VERT_TOLERANCE = 15  # Max vertical distance (in points) between lines to merge
                
                for bbox_coords, (text, confidence) in raw_lines:
                    if confidence < 0.2:
                        continue
                    
                    text_content = text.strip()
                    if not text_content:
                        continue
                    
                    ocr_x0 = min(p[0] for p in bbox_coords)
                    ocr_y0 = min(p[1] for p in bbox_coords)
                    ocr_x1 = max(p[0] for p in bbox_coords)
                    ocr_y1 = max(p[1] for p in bbox_coords)
                    
                    pdf_x0 = ocr_x0 * scale_x
                    pdf_y0 = ocr_y0 * scale_y
                    pdf_x1 = ocr_x1 * scale_x
                    pdf_y1 = ocr_y1 * scale_y
                    
                    current_box = {
                        "x0": pdf_x0, "y0": pdf_y0,
                        "x1": pdf_x1, "y1": pdf_y1,
                        "text": text_content
                    }
                    
                    # Try to merge with the previous paragraph if vertically close
                    # Also ensure they are roughly in the same column (x0 alignment)
                    # And never merge a new question into a previous paragraph.
                    is_new_question = bool(question_re.match(current_box["text"]))
                    
                    if merged_paragraphs:
                        last_box = merged_paragraphs[-1]
                        y_dist = current_box["y0"] - last_box["y1"]
                        x_dist = abs(current_box["x0"] - last_box["x0"])
                        
                        if not is_new_question and y_dist < VERT_TOLERANCE and x_dist < 150:
                            last_box["x0"] = min(last_box["x0"], current_box["x0"])
                            last_box["y0"] = min(last_box["y0"], current_box["y0"])
                            last_box["x1"] = max(last_box["x1"], current_box["x1"])
                            last_box["y1"] = max(last_box["y1"], current_box["y1"])
                            last_box["text"] += " " + current_box["text"]
                        else:
                            merged_paragraphs.append(current_box)
                    else:
                        merged_paragraphs.append(current_box)
                    
            # Pass 2: Categorize the merged paragraphs and add to final blocks
            for para in merged_paragraphs:
                bbox = {
                    "x0": round(para["x0"], 2), "y0": round(para["y0"], 2),
                    "x1": round(para["x1"], 2), "y1": round(para["y1"], 2)
                }
                text_content = para["text"]
                
                # Check for question categorization using lenient regex
                matches = question_re.findall(text_content)
                question_id = None
                if matches:
                    question_id = f"Q{matches[0]}"
                
                if bbox["y1"] < 80 and len(text_content) < 60 and not question_id:
                    page_dict["blocks"].append({
                        "type": "header",
                        "bbox": bbox,
                        "text": text_content,
                        "is_decorative": False
                    })
                else:
                    block_data = {
                        "type": "text",
                        "bbox": bbox,
                        "text": text_content
                    }
                    if question_id:
                        block_data["question_id"] = question_id
                    
                    page_dict["blocks"].append(block_data)
            
            # Clean up temp image
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
            
            # --- FIGURE EXTRACTION via PyMuPDF (with noise filtering & clustering) ---
            images = page.get_image_info()
            raw_figure_boxes = []
            for img_info in images:
                x0, y0, x1, y1 = img_info["bbox"]
                width = x1 - x0
                height = y1 - y0
                
                min_size = config.extraction_profile.min_figure_size
                if width < min_size or height < min_size:
                    continue
                if width > page_width * 0.95 and height > page_height * 0.95:
                    continue
                
                raw_figure_boxes.append({"x0": round(x0, 2), "y0": round(y0, 2),
                                         "x1": round(x1, 2), "y1": round(y1, 2)})
            
            # Cluster adjacent/overlapping figure boxes (distance < 20pts)
            merged_boxes = []
            while raw_figure_boxes:
                box = raw_figure_boxes.pop(0)
                merged = True
                while merged:
                    merged = False
                    for i in range(len(raw_figure_boxes) - 1, -1, -1):
                        other = raw_figure_boxes[i]
                        bx0, by0 = box["x0"] - 20, box["y0"] - 20
                        bx1, by1 = box["x1"] + 20, box["y1"] + 20
                        
                        if not (other["x1"] < bx0 or other["x0"] > bx1 or
                                other["y1"] < by0 or other["y0"] > by1):
                            box["x0"] = min(box["x0"], other["x0"])
                            box["y0"] = min(box["y0"], other["y0"])
                            box["x1"] = max(box["x1"], other["x1"])
                            box["y1"] = max(box["y1"], other["y1"])
                            raw_figure_boxes.pop(i)
                            merged = True
                merged_boxes.append(box)

            for idx, bbox in enumerate(merged_boxes):
                page_dict["blocks"].append({
                    "type": "figure",
                    "bbox": bbox,
                    "asset_id": f"temp_p{page_num + 1}_idx{idx}"
                })
            
            layout_data["pages"].append(page_dict)
        
        return layout_data

class LayoutFactory:
    @staticmethod
    def get_provider(provider_type: str) -> LayoutProvider:
        if provider_type.lower() == "mock":
            return MockProvider()
        elif provider_type.lower() == "pymupdf":
            return PyMuPDFProvider()
        elif provider_type.lower() == "ocr":
            return OCRLayoutProvider()
        else:
            raise ValueError(f"Unsupported layout provider type: {provider_type}")
