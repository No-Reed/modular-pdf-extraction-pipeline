import pymupdf
import os

class PyMuPDFExtractor:
    def __init__(self, pdf_path: str, output_dir: str = "assets"):
        self.doc = pymupdf.open(pdf_path)
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def extract(self):
        saved_images = []
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]

            # 1. Render the page to a PNG image
            pix = page.get_pixmap(dpi=150)
            page_img_path = os.path.join(self.output_dir, f"page_{page_num + 1}.png")
            pix.save(page_img_path)

            # 2. Extract embedded images
            image_list = page.get_images(full=True)
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = self.doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Filter out giant background images if they cover the whole page
                width, height = base_image["width"], base_image["height"]
                if width > 2000 and height > 3000:
                    continue
                    
                img_filename = f"image_p{page_num + 1}_{xref}.{image_ext}"
                img_path = os.path.join(self.output_dir, img_filename)
                
                with open(img_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                saved_images.append({
                    "page": page_num + 1,
                    "xref": xref,
                    "file_path": img_path
                })
                
        return saved_images

if __name__ == "__main__":
    extractor = PyMuPDFExtractor("assets/Class8SampleCBSEQuestionAssignment.pdf", "assets")
    print(extractor.extract())
