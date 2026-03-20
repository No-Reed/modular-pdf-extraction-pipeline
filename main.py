import json
from config import config
from extractor import PyMuPDFExtractor
from layout_engine import LayoutFactory
from normalizer import Normalizer

def main():
    print("Starting Micro-Parsing Pipeline...")
    
    # Phase 1: Asset Extraction
    print("\n[Phase 1] Asset Extraction")
    extractor = PyMuPDFExtractor(config.pdf_path, "assets")
    saved_images = extractor.extract()
    print(f"Extracted {len(saved_images)} embedded images and page renderings.")

    # Phase 2: Mock Layout Extraction & Factory Pattern
    print(f"\n[Phase 2] Layout Extraction using provider '{config.layout_provider}'")
    provider = LayoutFactory.get_provider(config.layout_provider)
    raw_layout = provider.extract_layout(config.pdf_path)
    print(f"Extracted raw layout data: {json.dumps(raw_layout, indent=2)}")

    # Phase 3: Normalization
    print("\n[Phase 3] Normalization into strict BlockGraph models")
    normalizer = Normalizer()
    block_graph = normalizer.normalize(raw_layout)
    
    # Validation & Dump
    output_path = "blockgraph.json"
    with open(output_path, "w", encoding="utf-8") as f:
        # Pydantic json() dumps the model matching our strict definitions
        f.write(block_graph.model_dump_json(indent=2))
    
    print(f"\nPipeline execution successful. Generated '{output_path}'.")

if __name__ == "__main__":
    main()
