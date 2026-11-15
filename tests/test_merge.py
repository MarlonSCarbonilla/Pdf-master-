"""Tests for PDF Merge (core/pdf_merge.py)."""
from tests.test_core_pages import (  # noqa: F401
    test_different_page_sizes_preserved,
    test_merge_cancel_leaves_no_output,
    test_merge_locked_needs_password,
    test_merge_order_and_content,
    test_merge_reports_bad_files,
)
