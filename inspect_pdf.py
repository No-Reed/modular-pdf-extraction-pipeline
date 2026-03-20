import pymupdf
import json

doc = pymupdf.open('assets/Class8SampleCBSEQuestionAssignment.pdf')

images_info = []

for page_num in range(len(doc)):
    page = doc[page_num]
    
    # Get images
    image_list = page.get_images(full=True)
    for img_index, img in enumerate(image_list):
        xref = img[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]
        width = base_image["width"]
        height = base_image["height"]
        
        # Get bounding box of image on page if possible
        rects = page.get_image_rects(xref)
        bbox = [rects[0].x0, rects[0].y0, rects[0].x1, rects[0].y1] if rects else None
        
        images_info.append({
            "page": page_num + 1,
            "xref": xref,
            "width": width,
            "height": height,
            "ext": image_ext,
            "bbox": bbox,
            "size_bytes": len(image_bytes)
        })

print(json.dumps(images_info, indent=2))
