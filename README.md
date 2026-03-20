# Modular PDF Extraction Pipeline

This repository implements a three-phase micro-parsing pipeline for CBSE Science PDFs.

## Architecture

1. **Phase 1: Asset Extraction (`extractor.py`)**: Uses PyMuPDF to convert PDF pages to PNG and extract embedded images to the `assets/` directory.
2. **Phase 2: Mock Layout Extraction (`layout_engine.py`)**: Uses a config-driven Factory Pattern to extract layout data. The `MockProvider` returns a hardcoded layout representing Q10 mapping to Fig 5.17 and a decorative cartoon header.
3. **Phase 3: Normalization (`normalizer.py`, `models.py`)**: Converts the mock raw dictionary into strictly-typed Pydantic classes (`BlockGraph`, `TextBlock`, `FigureBlock`, `HeaderBlock`).

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
- Generate PNGs and extract embedded images to `assets/`
- Run the mock provider layout extraction
- Normalize to Pydantic objects and generate `blockgraph.json`

## Exception Handling
If the PDF is corrupted, `PyMuPDFExtractor` instantiation (`fitz.open`) will raise a `fitz.fitz_error` or `RuntimeError`. In a production setup, we would wrap Phase 1 execution in a `try...except` block, log the parsing failure, and gracefully exit or fallback depending on requirements.
