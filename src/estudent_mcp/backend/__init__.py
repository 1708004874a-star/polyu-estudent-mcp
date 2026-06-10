"""Backend adapters for talking to eStudent.

`EStudentBackend` is the stable interface the tool layer depends on. Today only
`PlaywrightBackend` (scheme A) implements it; a future `HybridBackend` (scheme C:
Playwright login + httpx data fetch) can drop in without touching the tools.
"""

from .base import EStudentBackend

__all__ = ["EStudentBackend"]
