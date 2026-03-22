# Modular PDF Extraction Pipeline

This repository implements a three-phase micro-parsing pipeline for CBSE Science PDFs, designed specifically to parse complex multi-column documents into structured curriculum taxonomy JSONs.

## 💡 Evaluated Solutions & Architectural Reasoning

Before arriving at this architecture, three distinct approaches were evaluated:

1. **Pure Native Extraction (PyMuPDF / PDFMiner)**
   - *Rejected.* Native libraries sequentially read text streams, effectively extracting a disconnected "word soup" on 2-column layouts. They fundamentally lose the spatial layout awareness required to geometrically link specific questions to their nearby functional diagrams.

2. **Multimodal LLMs (GPT-4o / Vision / Gemini)**
   - *Rejected.* While highly capable of reasoning, Vision LLMs suffer from high latency, significant API costs at scale, and critical GDPR/privacy compliance risks (sending proprietary curriculum PDFs to external servers). Furthermore, LLMs possess a severe tendency to hallucinate coordinates, summarize content, or paraphrase rather than strictly extracting verbatim text strings.

3. **Selected Path: Hybrid Layout Engine + Spatial Heuristics**
   - *Selected.* By integrating **PyMuPDF** (for high-resolution raw page renders) with **PaddleOCR** (for exact spatial bounding boxes) and a custom **3-Pass Normalization Engine** (using Regex matching, Euclidean distance anchoring, and geometric IoU deduplication), this approach provides a **100% local, mathematically deterministic, and privacy-compliant** JSON graph ready for immediate RAG integration.

## Architecture

1. **Phase 1: Layout Extraction**: Uses a config-driven Factory Pattern incorporating `PaddleOCR` to gather precise visual bounding boxes for every line of text across complex columns.
2. **Phase 2: Semantic Normalization**: Runs a multi-pass heuristic engine to re-assemble fragmented text vertically, locate semantic anchors (e.g. "Fig. 5.17"), and link visual blocks to functional questions based on spatial proximity.
3. **Phase 3: Semantic Asset Cropping**: Screenshots accurate visual regions of composite diagrams directly from the PDF renderer and saves them with human-readable semantic formats (e.g. `Q10_Fig_5.17.png`), respecting manual human-in-the-loop file overrides.
4. **Phase 4: Taxonomy Exporting**: Restructures the flat spatial graph into a strictly nested Hierarchical Curriculum Taxonomy JSON document.

## Installation

```bash
python -m venv .venv
source .venv/Scripts/activate  # On Windows PowerShell
pip install -r requirements.txt
```

## Running the Pipeline

Execute the pipeline using:
```bash
python main.py
```

This will:
- Parse `assets/Class8SampleCBSEQuestionAssignment.pdf`
- Run PaddleOCR to extract local text bounding boxes
- Normalize layout into Pydantic models (BlockGraph)
- Semantically crop functional embedded diagrams to `assets_output/`
- Generate `taxonomy_output.json` directly linked to generated images

## Exception Handling
If the PDF is corrupted, `PyMuPDFExtractor` instantiation (`fitz.open`) will raise a `fitz.fitz_error` or `RuntimeError`. In a production setup, we would wrap Phase 1 execution in a `try...except` block, log the parsing failure, and gracefully exit or fallback depending on requirements.

## 🚀 Future Product Roadmap

While the spatial heuristic logic operates deterministically, it inherently relies on regex patterns and geometric distance calculations. To further improve robustness across a wider variance of textbook publishers and formatting edge cases, the **immediate next milestone** is replacing the heuristic regex engine with a localized, quantized instance of **LayoutLMv3**. By fine-tuning LayoutLMv3, the pipeline will achieve zero-shot generalizability for semantic classification without sacrificing the privacy and cost benefits of a local architecture.
