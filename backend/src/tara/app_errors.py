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


class AgentPlatformConfigError(RuntimeError):
    """Agent Platform is misconfigured — missing or expired credentials, wrong
    project, insufficient permission, or an unknown/retired model. An operator must
    fix it; retrying will not help. Maps to HTTP 500.

    Carries no user content: web_app renders str(exc) straight to the client."""


class AgentPlatformUnavailableError(RuntimeError):
    """Agent Platform was over quota or unavailable after bounded retry. The same
    request may succeed later. Maps to HTTP 503.

    Carries no user content: web_app renders str(exc) straight to the client."""
