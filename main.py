import json
from config import config
from asset_exporter import AssetExporter
from layout_engine import LayoutFactory
from normalizer import Normalizer
from taxonomy_exporter import export_to_taxonomy


def main():
    print("=" * 72)
    print("  MICRO-PARSING PIPELINE — CBSE Science PDF")
    print("=" * 72)

    # ── Phase 1: Asset Extraction (DEPRECATED - moved to semantic cropping later) ──
    print("\n[Phase 1] Asset Extraction (Skipped: will be cropped semantically later)")

    # ── Phase 2: Layout Extraction (Factory Pattern) ───────────────
    print(f"\n[Phase 2] Layout Extraction  (provider: '{config.layout_provider}')")
    provider = LayoutFactory.get_provider(config.layout_provider)
    raw_layout = provider.extract_layout(config.pdf_path)
    total_raw = sum(len(p.get("blocks", [])) for p in raw_layout.get("pages", []))
    print(f"  → Raw layout contains {total_raw} blocks across "
          f"{len(raw_layout.get('pages', []))} pages.")

    print(f"\n[Phase 3] Semantic Normalization (3-pass engine)")
    normalizer = Normalizer()
    block_graph = normalizer.normalize(raw_layout)

    # ── Phase 4: Semantic Asset Cropping ───────────────────────────
    print(f"\n[Phase 4] Semantic Asset Cropping")
    asset_exporter = AssetExporter(config.pdf_path, "assets_output")
    block_graph = asset_exporter.export(block_graph)

    # ── Terminal Report ────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("  RE-ASSEMBLY REPORT (Pass 1)")
    print("─" * 72)
    if normalizer.reassembly_log:
        for entry in normalizer.reassembly_log:
            print(f"  ✓ {entry['question_id']}: merged {entry['fragments_merged']} "
                  f"fragments")
            print(f"    Preview: \"{entry['final_content_preview']}…\"")
    else:
        print("  (no fragmented questions detected)")

    print("\n" + "─" * 72)
    print("  VISUAL ANCHORING REPORT (Pass 2)")
    print("─" * 72)
    if normalizer.anchor_log:
        for entry in normalizer.anchor_log:
            print(f"  ✓ Label '{entry['label']}' → asset '{entry['matched_asset']}' "
                  f"(dist={entry['distance_pts']} pts, "
                  f"linked to {entry['linked_question']})")
    else:
        print("  (no figure labels detected in text)")

    print("\n" + "─" * 72)
    print("  DEDUPLICATION REPORT (Pass 3)")
    print("─" * 72)
    if normalizer.dedup_log:
        for entry in normalizer.dedup_log:
            print(f"  ✓ Merged '{entry['removed']}' into '{entry['kept']}' "
                  f"(IoU={entry['iou']})")
    else:
        print("  (no overlapping figures detected)")

    # ── Asset Classification Summary ──────────────────────────────
    from models import FigureBlock, TextBlock
    figures = [b for b in block_graph.blocks if isinstance(b, FigureBlock)]
    functional = [f for f in figures if f.is_functional]
    decorative = [f for f in figures if not f.is_functional]
    print("\n" + "─" * 72)
    print("  ASSET CLASSIFICATION SUMMARY")
    print("─" * 72)
    print(f"  Total figures: {len(figures)}")
    print(f"    Functional (referenced diagrams): {len(functional)}")
    for f in functional:
        print(f"      • {f.asset_id}  caption='{f.caption}'  "
              f"linked={f.related_question}")
    print(f"    Decorative (cartoon/noise):       {len(decorative)}")
    for f in decorative:
        print(f"      • {f.asset_id}")

    # ── Q10 Verification ──────────────────────────────────────────
    print("\n" + "─" * 72)
    print("  VERIFICATION: Question 10 ↔ Fig 5.17")
    print("─" * 72)
    q10_blocks = [b for b in block_graph.blocks
                  if isinstance(b, TextBlock) and b.question_id == "Q10"]
    fig517_assets = [b for b in block_graph.blocks
                     if isinstance(b, FigureBlock) and b.related_question == "Q10"]

    q10_ok = len(q10_blocks) == 1
    fig_ok = any(f.caption and "5.17" in f.caption for f in fig517_assets)
    content_ok = q10_ok and "5.17" in q10_blocks[0].content if q10_ok else False

    if q10_ok and fig_ok and content_ok:
        print("  ✅ PASS — Q10 is a single re-assembled block.")
        print(f"     Content mentions Fig 5.17: YES")
        print(f"     Figure asset linked to Q10: "
              f"{fig517_assets[0].asset_id} (caption='{fig517_assets[0].caption}')")
    else:
        print("  ❌ FAIL — Verification issues:")
        if not q10_ok:
            print(f"     Q10 block count = {len(q10_blocks)} (expected 1)")
        if not fig_ok:
            print(f"     No figure with caption containing '5.17' linked to Q10")
        if not content_ok:
            print(f"     Q10 content does not mention Fig 5.17")

    # ── Write blockgraph.json ─────────────────────────────────────
    output_path = "blockgraph.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(block_graph.model_dump_json(indent=2))

    # ── Write taxonomy_output.json ────────────────────────────────
    taxonomy = export_to_taxonomy(block_graph, pdf_path=config.pdf_path)
    taxonomy_path = "taxonomy_output.json"
    with open(taxonomy_path, "w", encoding="utf-8") as f:
        json.dump(taxonomy, f, indent=2, ensure_ascii=False)

    total_blocks = len(block_graph.blocks)
    print("\n" + "=" * 72)
    print(f"  Pipeline complete. Wrote {total_blocks} blocks → '{output_path}'")
    print(f"  Taxonomy exported → '{taxonomy_path}'")
    print("=" * 72)


if __name__ == "__main__":
    main()
