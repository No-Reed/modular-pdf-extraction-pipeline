"""
Three-pass semantic normalizer for the micro-parsing pipeline.

Pass 1 — Semantic Re-assembly:   Merge fragmented OCR text blocks into complete questions.
Pass 2 — Visual Anchoring:       Classify figures as functional/decorative using label proximity.
Pass 3 — Geometric Deduplication: Merge overlapping figures (IoU > 0.80).
"""

import re
from typing import Dict, Any, List, Tuple, Optional
from models import BlockGraph, TextBlock, FigureBlock, HeaderBlock, BoundingBox


# ─── Regex patterns ───────────────────────────────────────────────
QUESTION_START_RE = re.compile(r'^(\d+)\.')
FIGURE_LABEL_RE = re.compile(r'Fig\.?\s*(\d+\.\d+)', re.IGNORECASE)
# Section headers that terminate question merging
# Works at block start (^) and as an inline search pattern
SECTION_HEADER_RE = re.compile(
    r'(?i)(?:^|\s)(?:Discover[,\s]|Science\s+Society|Inter-?\s*disciplinary|Projects\b)',
)
# Stricter pattern for inline splitting within a merged block
# Group 1 = section title, everything after = section body
INLINE_SECTION_RE = re.compile(
    r'\s+(Discover[,\s]+design[,\s]*and\s+debate)',
    re.IGNORECASE,
)
# Detects the start of a new bullet-point / activity in section content
# Matches at block start OR after sentence-ending punctuation (.?!)
BULLET_START_RE = re.compile(
    r'(?:^|(?<=[.?!])\s+)'
    r'(?:Collect |Imagine |Organise |Organize |Make your |'
    r'An electroscope|Design |Explore |Create )',
    re.IGNORECASE,
)


class Normalizer:
    """Converts raw layout provider JSON into strict Pydantic BlockGraph models,
    then runs three sequential post-processing passes to resolve OCR artefacts."""

    def __init__(self) -> None:
        self.reassembly_log: List[Dict[str, Any]] = []
        self.anchor_log: List[Dict[str, Any]] = []
        self.dedup_log: List[Dict[str, Any]] = []

    # ──────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────
    def normalize(self, raw_layout: Dict[str, Any]) -> BlockGraph:
        """Main normalizer pipeline — build blocks then refine them."""

        # Step 0: Ingest raw blocks from the layout engine
        text_blocks, figure_blocks, header_blocks = self._ingest(raw_layout)

        # Pre-pass: Extract figure label anchors from RAW text blocks
        # (before re-assembly destroys precise label positions)
        label_anchors = self._extract_label_anchors(text_blocks)

        # Pass 1: Semantic Re-assembly (merge fragmented questions)
        text_blocks, reassembly_log = self._pass1_reassemble(text_blocks)

        # Pass 2: Visual Anchoring & Classification
        # Uses pre-reassembly anchors + post-reassembly question IDs
        figure_blocks, anchor_log = self._pass2_classify_figures(
            text_blocks, figure_blocks, label_anchors
        )

        # Pass 3: Geometric Deduplication (IoU)
        figure_blocks, dedup_log = self._pass3_deduplicate_figures(figure_blocks)

        # Pass 4: Re-merge scattered section content into activity blocks
        text_blocks = self._pass4_merge_section_content(text_blocks)

        # Pass 5: Spatial dedup for text blocks (95%+ bbox overlap)
        text_blocks = self._pass5_deduplicate_text_blocks(text_blocks)

        # Persist logs for the terminal report
        self.reassembly_log = reassembly_log
        self.anchor_log = anchor_log
        self.dedup_log = dedup_log

        # Assemble final graph in a stable order: headers → text → figures
        graph = BlockGraph()
        graph.blocks.extend(header_blocks)
        graph.blocks.extend(text_blocks)
        graph.blocks.extend(figure_blocks)
        return graph

    # ──────────────────────────────────────────────────────────────
    # Step 0 — Ingest raw layout into typed blocks
    # ──────────────────────────────────────────────────────────────
    def _ingest(
        self, raw_layout: Dict[str, Any]
    ) -> Tuple[List[TextBlock], List[FigureBlock], List[HeaderBlock]]:
        text_blocks: List[TextBlock] = []
        figure_blocks: List[FigureBlock] = []
        header_blocks: List[HeaderBlock] = []

        for page in raw_layout.get("pages", []):
            page_num = page.get("page_number", 0)
            for b_dict in page.get("blocks", []):
                bbox = self._make_bbox(b_dict.get("bbox", {}))
                b_type = b_dict.get("type")

                if b_type == "header":
                    header_blocks.append(HeaderBlock(
                        bbox=bbox,
                        page=page_num,
                        content=b_dict.get("text"),
                        functional=not b_dict.get("is_decorative", False),
                    ))

                elif b_type == "text":
                    text_blocks.append(TextBlock(
                        bbox=bbox,
                        page=page_num,
                        content=b_dict.get("text", ""),
                        question_id=b_dict.get("question_id"),
                    ))

                elif b_type == "figure":
                    figure_blocks.append(FigureBlock(
                        bbox=bbox,
                        page=page_num,
                        asset_id=b_dict.get("asset_id", ""),
                        related_question=b_dict.get("linked_question_id"),
                    ))

        return text_blocks, figure_blocks, header_blocks

    # ──────────────────────────────────────────────────────────────
    # Pass 1 — Semantic Re-assembly
    # ──────────────────────────────────────────────────────────────
    def _pass1_reassemble(
        self, text_blocks: List[TextBlock]
    ) -> Tuple[List[TextBlock], List[Dict[str, Any]]]:
        """Merge fragmented OCR text blocks into complete questions.

        Logic:
        • A block whose content matches  r'^(\\d+)\\.'  starts a new question.
        • All subsequent blocks that do NOT match the pattern are merged into
          the current question (text appended, bbox expanded).
        • Standalone non-question blocks that appear before the first question
          are kept as-is.
        """
        if not text_blocks:
            return text_blocks, []

        log: List[Dict[str, Any]] = []
        merged: List[TextBlock] = []
        current: Optional[TextBlock] = None
        merge_count = 0

        def _flush_current() -> None:
            """Flush the accumulated question block. Applies inline section
            splitting before appending to merged list."""
            nonlocal current, merge_count
            if current is None:
                return
            # Split inline section headers (e.g. "Discover, design")
            q_block, remainder = Normalizer._split_inline_section(current)
            if merge_count > 0 or remainder is not None:
                log.append({
                    "question_id": q_block.question_id,
                    "fragments_merged": merge_count + 1,
                    "final_content_preview": q_block.content[:120],
                })
            merged.append(q_block)
            if remainder is not None:
                merged.append(remainder)
            current = None
            merge_count = 0

        for block in text_blocks:
            stripped = block.content.strip()
            q_match = QUESTION_START_RE.match(stripped)
            is_section_header = bool(SECTION_HEADER_RE.match(stripped))

            if q_match:
                # Flush previously accumulated question
                _flush_current()

                # Start a new question accumulator
                q_num = q_match.group(1)
                current = TextBlock(
                    bbox=BoundingBox(
                        x0=block.bbox.x0, y0=block.bbox.y0,
                        x1=block.bbox.x1, y1=block.bbox.y1,
                    ),
                    content=block.content,
                    question_id=block.question_id or f"Q{q_num}",
                    page=block.page,
                )
                merge_count = 0

            elif is_section_header:
                # Section header terminates the current question
                _flush_current()
                # Emit the section header as a standalone block
                merged.append(block)

            elif current is not None:
                # Continuation / sub-part — merge into current question
                current.content += " " + block.content
                current.bbox = self._expand_bbox(current.bbox, block.bbox)
                merge_count += 1

            else:
                # Non-question block (after section header or before first Q)
                merged.append(block)

        # Flush last accumulated question
        _flush_current()

        return merged, log

    @staticmethod
    def _split_inline_section(block: TextBlock) -> Tuple[TextBlock, Optional[TextBlock]]:
        """If a question block contains an inline section header
        (e.g. 'Discover, design, and debate'), split the content.
        Returns (question_block, section_remainder_or_None).
        The section header is kept as the start of the remainder block."""
        m = INLINE_SECTION_RE.search(block.content)
        if not m:
            return block, None

        split_pos = m.start()
        q_content = block.content[:split_pos].strip()
        section_content = block.content[split_pos:].strip()

        if not section_content:
            return block, None

        # Truncate question block
        question = TextBlock(
            bbox=BoundingBox(
                x0=block.bbox.x0, y0=block.bbox.y0,
                x1=block.bbox.x1, y1=block.bbox.y1,
            ),
            content=q_content,
            question_id=block.question_id,
            page=block.page,
        )

        # Remainder = section header + body (will be split further by Pass 4)
        remainder = TextBlock(
            bbox=BoundingBox(
                x0=block.bbox.x0, y0=block.bbox.y0,
                x1=block.bbox.x1, y1=block.bbox.y1,
            ),
            content=section_content,
            question_id=None,
            page=block.page,
        )

        return question, remainder

    # ──────────────────────────────────────────────────────────────
    # Pass 4 — Re-merge section content into activity blocks
    # ──────────────────────────────────────────────────────────────
    def _pass4_merge_section_content(
        self, text_blocks: List[TextBlock]
    ) -> List[TextBlock]:
        """Re-group fragmented OCR blocks (after section headers) into
        logical activity/bullet-point entries.

        Rules:
        • Question blocks (question_id != None) pass through unchanged.
        • Non-question blocks are grouped: a new group starts when a block's
          content matches BULLET_START_RE or looks like a section header.
        • Tiny fragments (< 20 chars, no capital-letter start) merge into
          the previous group.
        """
        result: List[TextBlock] = []
        current_group: Optional[TextBlock] = None
        in_section = False  # True once we pass a section header

        for block in text_blocks:
            # Question blocks pass through, flush any group first
            if block.question_id is not None:
                if current_group is not None:
                    result.append(current_group)
                    current_group = None
                result.append(block)
                in_section = False
                continue

            # Detect section header start
            stripped = block.content.strip()
            is_section = bool(SECTION_HEADER_RE.search(stripped))
            is_bullet_start = bool(BULLET_START_RE.search(stripped))

            if is_section:
                # Flush previous group
                if current_group is not None:
                    result.append(current_group)
                    current_group = None
                in_section = True
                # Start new group with the section header
                current_group = TextBlock(
                    bbox=BoundingBox(
                        x0=block.bbox.x0, y0=block.bbox.y0,
                        x1=block.bbox.x1, y1=block.bbox.y1,
                    ),
                    content=stripped,
                    question_id=None,
                )

            elif in_section and is_bullet_start:
                # New bullet point = new group
                if current_group is not None:
                    result.append(current_group)
                current_group = TextBlock(
                    bbox=BoundingBox(
                        x0=block.bbox.x0, y0=block.bbox.y0,
                        x1=block.bbox.x1, y1=block.bbox.y1,
                    ),
                    content=stripped,
                    question_id=None,
                )

            elif in_section and current_group is not None:
                # Fragment — merge into current group
                current_group.content += " " + stripped
                current_group.bbox = self._expand_bbox(
                    current_group.bbox, block.bbox
                )

            else:
                # Not in a section, just pass through
                if current_group is not None:
                    result.append(current_group)
                    current_group = None
                result.append(block)

        if current_group is not None:
            result.append(current_group)

        # Second sweep: split any remaining multi-activity blocks inline
        final: List[TextBlock] = []
        for block in result:
            if block.question_id is not None:
                final.append(block)
                continue
            parts = self._split_on_bullets(block)
            final.extend(parts)

        return final

    @staticmethod
    def _split_on_bullets(block: TextBlock) -> List[TextBlock]:
        """Split a single text block into multiple blocks at bullet-start
        boundaries found within its content."""
        content = block.content
        # Find all bullet starts (skip position 0 since that's the block start)
        splits = [m.start() for m in BULLET_START_RE.finditer(content)]
        # Only keep splits that are not at position 0
        splits = [s for s in splits if s > 0]

        if not splits:
            return [block]

        parts: List[TextBlock] = []
        prev = 0
        for s in splits:
            chunk = content[prev:s].strip()
            if chunk:
                parts.append(TextBlock(
                    bbox=BoundingBox(
                        x0=block.bbox.x0, y0=block.bbox.y0,
                        x1=block.bbox.x1, y1=block.bbox.y1,
                    ),
                    content=chunk,
                    question_id=None,
                ))
            prev = s
        # Last chunk
        last = content[prev:].strip()
        if last:
            parts.append(TextBlock(
                bbox=BoundingBox(
                    x0=block.bbox.x0, y0=block.bbox.y0,
                    x1=block.bbox.x1, y1=block.bbox.y1,
                ),
                content=last,
                question_id=None,
            ))

        return parts if parts else [block]

    # ──────────────────────────────────────────────────────────────
    # Pass 5 — Spatial De-duplication for text blocks
    # ──────────────────────────────────────────────────────────────
    def _pass5_deduplicate_text_blocks(
        self, text_blocks: List[TextBlock]
    ) -> List[TextBlock]:
        """Merge text blocks with ≥ 95% overlapping bounding boxes.

        When two blocks have nearly identical coordinates (same page),
        keep the one with more content and discard the duplicate.
        """
        if len(text_blocks) < 2:
            return text_blocks

        removed: set = set()

        for i in range(len(text_blocks)):
            if i in removed:
                continue
            for j in range(i + 1, len(text_blocks)):
                if j in removed:
                    continue

                a, b = text_blocks[i], text_blocks[j]

                # Same-page check
                if a.page is not None and b.page is not None and a.page != b.page:
                    continue

                overlap = self._bbox_overlap_ratio(a.bbox, b.bbox)
                if overlap >= 0.95:
                    # Keep the block with more content (or the one with a question_id)
                    if a.question_id and not b.question_id:
                        removed.add(j)
                    elif b.question_id and not a.question_id:
                        removed.add(i)
                        break  # i is removed, move on
                    elif len(a.content) >= len(b.content):
                        removed.add(j)
                    else:
                        removed.add(i)
                        break

        return [tb for idx, tb in enumerate(text_blocks) if idx not in removed]

    @staticmethod
    def _bbox_overlap_ratio(a: BoundingBox, b: BoundingBox) -> float:
        """Compute the overlap ratio (intersection / smaller area)."""
        ix0 = max(a.x0, b.x0)
        iy0 = max(a.y0, b.y0)
        ix1 = min(a.x1, b.x1)
        iy1 = min(a.y1, b.y1)

        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0

        inter = (ix1 - ix0) * (iy1 - iy0)
        area_a = max((a.x1 - a.x0) * (a.y1 - a.y0), 1e-6)
        area_b = max((b.x1 - b.x0) * (b.y1 - b.y0), 1e-6)
        smaller = min(area_a, area_b)

        return inter / smaller

    # ──────────────────────────────────────────────────────────────
    # Pre-pass — Extract figure label anchor positions
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _extract_label_anchors(
        raw_text_blocks: List[TextBlock],
    ) -> List[Dict[str, Any]]:
        """Scan the RAW (pre-reassembly) text blocks for figure labels
        like "Fig. 5.17" and record their precise bounding boxes.

        Returns a list of dicts:
            { "label": "Fig. 5.17", "fig_id": "5.17", "bbox": BoundingBox }
        """
        anchors: List[Dict[str, Any]] = []
        for tb in raw_text_blocks:
            for m in FIGURE_LABEL_RE.finditer(tb.content):
                anchors.append({
                    "label": m.group(0),       # e.g. "Fig. 5.17"
                    "fig_id": m.group(1),       # e.g. "5.17"
                    "page": tb.page,            # page the label lives on
                    "bbox": BoundingBox(
                        x0=tb.bbox.x0, y0=tb.bbox.y0,
                        x1=tb.bbox.x1, y1=tb.bbox.y1,
                    ),
                })
        return anchors

    # ──────────────────────────────────────────────────────────────
    # Pass 2 — Visual Anchoring & Classification
    # ──────────────────────────────────────────────────────────────
    VERT_BUFFER = 100  # Maximum vertical gap (in PDF points) for label-figure linking

    def _pass2_classify_figures(
        self,
        text_blocks: List[TextBlock],
        figure_blocks: List[FigureBlock],
        label_anchors: List[Dict[str, Any]],
    ) -> Tuple[List[FigureBlock], List[Dict[str, Any]]]:
        """Link figure labels to the spatially nearest figure_block using
        the original (pre-reassembly) label positions.

        Rules:
        1. A figure can only link to a label within VERT_BUFFER points
           (measured between label bottom edge and figure top edge,
            or label top edge and figure bottom edge).
        2. Each figure binds to at most ONE label — the one with the
           smallest Euclidean distance.  Conflicts are resolved by
           keeping the closest match.
        3. The label's parent question_id is resolved from the
           post-reassembly text_blocks (which contain the merged text).
        """
        log: List[Dict[str, Any]] = []

        # Build a lookup: figure label string → parent question_id
        # (scan the POST-reassembly text which has question_ids assigned)
        label_to_question: Dict[str, Optional[str]] = {}
        for tb in text_blocks:
            for m in FIGURE_LABEL_RE.finditer(tb.content):
                label_to_question[m.group(0)] = tb.question_id

        # Phase A: Compute all valid (label, figure, distance) candidates
        # Valid = within vertical buffer
        Candidate = Tuple[int, int, float]  # (anchor_idx, figure_idx, distance)
        candidates: List[Candidate] = []

        for a_idx, anchor in enumerate(label_anchors):
            a_bbox: BoundingBox = anchor["bbox"]
            a_cx = (a_bbox.x0 + a_bbox.x1) / 2
            a_cy = (a_bbox.y0 + a_bbox.y1) / 2

            for f_idx, fb in enumerate(figure_blocks):
                # ── Same-page gate ──
                if anchor.get("page") is not None and fb.page is not None:
                    if anchor["page"] != fb.page:
                        continue

                fb_cx = (fb.bbox.x0 + fb.bbox.x1) / 2
                fb_cy = (fb.bbox.y0 + fb.bbox.y1) / 2

                # Vertical buffer: label bottom → figure top, OR figure bottom → label top
                vert_gap = min(
                    abs(a_bbox.y1 - fb.bbox.y0),  # label above figure
                    abs(fb.bbox.y1 - a_bbox.y0),  # figure above label
                )
                # Also allow overlap (figure contains label vertically)
                if not (vert_gap <= self.VERT_BUFFER
                        or (a_bbox.y0 >= fb.bbox.y0 and a_bbox.y1 <= fb.bbox.y1)
                        or (fb.bbox.y0 >= a_bbox.y0 and fb.bbox.y1 <= a_bbox.y1)):
                    continue

                dist = ((a_cx - fb_cx) ** 2 + (a_cy - fb_cy) ** 2) ** 0.5
                candidates.append((a_idx, f_idx, dist))

        # Phase B: Greedy assignment — sort by distance, assign each figure
        # to at most one label (closest wins)
        candidates.sort(key=lambda c: c[2])
        assigned_figures: Dict[int, int] = {}    # figure_idx → anchor_idx
        assigned_anchors: Dict[int, int] = {}    # anchor_idx → figure_idx

        for a_idx, f_idx, dist in candidates:
            if f_idx in assigned_figures:
                continue  # figure already claimed by a closer label
            if a_idx in assigned_anchors:
                continue  # this label already bound to a closer figure
            assigned_figures[f_idx] = a_idx
            assigned_anchors[a_idx] = f_idx

        # Phase C: Apply classifications
        for f_idx, a_idx in assigned_figures.items():
            anchor = label_anchors[a_idx]
            fb = figure_blocks[f_idx]
            fb.is_functional = True
            fb.purpose = "referenced_diagram"
            fb.caption = anchor["label"]
            fb.related_question = label_to_question.get(anchor["label"])

            dist = next(d for ai, fi, d in candidates if ai == a_idx and fi == f_idx)
            log.append({
                "label": anchor["label"],
                "matched_asset": fb.asset_id,
                "linked_question": fb.related_question,
                "distance_pts": round(dist, 1),
            })

        # Mark unlinked figures as decorative
        for f_idx, fb in enumerate(figure_blocks):
            if f_idx not in assigned_figures:
                fb.is_functional = False
                fb.purpose = "decorative"

        return figure_blocks, log

    # ──────────────────────────────────────────────────────────────
    # Pass 3 — Geometric Deduplication (IoU)
    # ──────────────────────────────────────────────────────────────
    def _pass3_deduplicate_figures(
        self, figure_blocks: List[FigureBlock]
    ) -> Tuple[List[FigureBlock], List[Dict[str, Any]]]:
        """Merge overlapping figure blocks when IoU > 0.80."""
        if len(figure_blocks) < 2:
            return figure_blocks, []

        log: List[Dict[str, Any]] = []
        removed: set = set()

        for i in range(len(figure_blocks)):
            if i in removed:
                continue
            for j in range(i + 1, len(figure_blocks)):
                if j in removed:
                    continue
                iou = self._compute_iou(figure_blocks[i].bbox, figure_blocks[j].bbox)
                if iou > 0.80:
                    # Keep i, merge j into i
                    fi, fj = figure_blocks[i], figure_blocks[j]

                    # Expand bbox to cover both
                    fi.bbox = self._expand_bbox(fi.bbox, fj.bbox)

                    # Preserve functional metadata
                    if fj.is_functional and not fi.is_functional:
                        fi.is_functional = True
                        fi.purpose = fj.purpose
                        fi.caption = fj.caption
                        fi.related_question = fj.related_question

                    removed.add(j)
                    log.append({
                        "kept": fi.asset_id,
                        "removed": fj.asset_id,
                        "iou": round(iou, 3),
                    })

        deduped = [fb for idx, fb in enumerate(figure_blocks) if idx not in removed]
        return deduped, log

    # ──────────────────────────────────────────────────────────────
    # Helper utilities
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _make_bbox(d: Dict[str, Any]) -> BoundingBox:
        return BoundingBox(
            x0=d.get("x0", 0.0), y0=d.get("y0", 0.0),
            x1=d.get("x1", 0.0), y1=d.get("y1", 0.0),
        )

    @staticmethod
    def _expand_bbox(a: BoundingBox, b: BoundingBox) -> BoundingBox:
        return BoundingBox(
            x0=min(a.x0, b.x0), y0=min(a.y0, b.y0),
            x1=max(a.x1, b.x1), y1=max(a.y1, b.y1),
        )

    @staticmethod
    def _compute_iou(a: BoundingBox, b: BoundingBox) -> float:
        inter_x0 = max(a.x0, b.x0)
        inter_y0 = max(a.y0, b.y0)
        inter_x1 = min(a.x1, b.x1)
        inter_y1 = min(a.y1, b.y1)

        if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
            return 0.0

        inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
        area_a = (a.x1 - a.x0) * (a.y1 - a.y0)
        area_b = (b.x1 - b.x0) * (b.y1 - b.y0)
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0
        return inter_area / union_area
