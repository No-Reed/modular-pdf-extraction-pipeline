"""
Taxonomy Exporter — converts a flat BlockGraph into a nested
Hierarchical Curriculum Taxonomy dictionary.

Output structure:
  {board: {grade: {chapter: {section: [question_strings]}}}}
"""

import os
import re
from typing import Optional

from models import BlockGraph, TextBlock, FigureBlock, HeaderBlock

# Arabic → Roman numeral lookup (classes 1-12)
_ROMAN = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
    11: "XI", 12: "XII",
}

# Regex to detect class/grade from filename (e.g. "Class10")
_CLASS_RE = re.compile(r'[Cc]lass\s*(\d+)')

# Regex to detect Educational Board from filename
_BOARD_RE = re.compile(r'(CBSE|ICSE|State)', re.IGNORECASE)


def _detect_grade(pdf_path: str, fallback: str) -> str:
    """Extract grade from pdf filename, e.g. 'Class8...' → 'Class VIII'."""
    basename = os.path.basename(pdf_path)
    m = _CLASS_RE.search(basename)
    if m:
        num = int(m.group(1))
        roman = _ROMAN.get(num, str(num))
        return f"Class {roman}"
    return fallback


def _detect_board(pdf_path: str, fallback: str) -> str:
    """Extract board from pdf filename, e.g. '...CBSE...' → 'CBSE Board'."""
    basename = os.path.basename(pdf_path)
    m = _BOARD_RE.search(basename)
    if m:
        return f"{m.group(1).upper()} Board"
    return fallback


def _extract_chapter_name(block_graph: BlockGraph) -> str:
    """Find the HeaderBlock containing 'Chapter' and format it with underscores."""
    for block in block_graph.blocks:
        if isinstance(block, HeaderBlock) and block.content:
            if "chapter" in block.content.lower():
                # Replace spaces, hyphens, and en-dashes with underscores
                return re.sub(r'[\s\-–]+', '_', block.content.strip())
    return "Unknown_Chapter"


def export_to_taxonomy(
    block_graph: BlockGraph,
    pdf_path: str = "",
    board: str = "CBSE Board",
    grade: str = "Class VIII",
    section: str = "Assignment",
) -> dict:
    """Convert a BlockGraph into a nested curriculum taxonomy dict.

    Args:
        block_graph: The normalised block graph.
        pdf_path:    Path to the source PDF (used for auto-detecting board/grade).
        board:       Fallback board name if auto-detection fails.
        grade:       Fallback grade string if auto-detection fails.
        section:     Key for the question list (default "Assignment").

    Returns:
        Nested dict: {board: {grade: {chapter: {section: [questions]}}}}
    """

    # ── Auto-detect board & grade from filename ───────────────────
    if pdf_path:
        board = _detect_board(pdf_path, board)
        grade = _detect_grade(pdf_path, grade)

    # ── Chapter name from headers ─────────────────────────────────
    chapter_name = _extract_chapter_name(block_graph)

    # ── Build question_id → asset_id lookup from figures ──────────
    question_to_asset: dict[str, str] = {}
    for block in block_graph.blocks:
        if isinstance(block, FigureBlock) and block.related_question:
            question_to_asset[block.related_question] = block.asset_id

    # ── Assemble the question list ────────────────────────────────
    questions: list[str] = []
    for block in block_graph.blocks:
        if isinstance(block, TextBlock) and block.question_id:
            text = block.content.strip()
            asset_id = question_to_asset.get(block.question_id)
            
            # If a visual asset is linked to this question, append it
            if asset_id:
                text += f" [Linked Asset: {asset_id}]"
                
            questions.append(text)

    # ── Build nested taxonomy ─────────────────────────────────────
    return {
        board: {
            grade: {
                chapter_name: {
                    section: questions,
                }
            }
        }
    }
