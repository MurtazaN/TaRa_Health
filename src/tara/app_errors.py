"""Application-wide error types — every failed contract the app can surface.

Collected in one kernel module so the API layer's exception→HTTP mapping
(web_app.py) imports a single place, and so a module that raises an error never
has to import the module that owns another one. Imports nothing from tara.
"""
from __future__ import annotations


class UploadError(ValueError):
    """An upload failed boundary validation (extension, size, or page count).
    Raised by upload_validation and source_kind_detection; maps to HTTP 400."""


class IngestionError(RuntimeError):
    """Ingestion failed after validation (e.g. extraction produced no text).
    Raised by the ingestion pipeline; maps to HTTP 400."""


class IndexMismatchError(RuntimeError):
    """The configured embedding model/dim differs from what the vector index was
    built with (design §3.2) — serving queries would return garbage distances, so
    the app refuses and requires a re-index. Maps to HTTP 409."""
