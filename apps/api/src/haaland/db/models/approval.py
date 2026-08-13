"""Approval is defined in remediation.py alongside its parent table — kept as
a re-export here so `db.models.approval` matches the docs/07 file listing."""

from __future__ import annotations

from haaland.db.models.remediation import Approval

__all__ = ["Approval"]
