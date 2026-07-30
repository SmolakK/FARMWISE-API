"""Backward-compatible imports for the packaged quality assessment module."""

from core.quality_assess import (
    DEFAULT_QUALITY_REPORT_DIR,
    assess_data_quality,
    bbox_intersects,
    persist_quality_report,
)

__all__ = [
    "DEFAULT_QUALITY_REPORT_DIR",
    "assess_data_quality",
    "bbox_intersects",
    "persist_quality_report",
]
