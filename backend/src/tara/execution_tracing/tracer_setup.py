"""Installs the OpenTelemetry tracer provider once per process.

Tracing is opt-in because a span carries the user's question and retrieved
document text. Instrumentation is vendor-neutral OpenTelemetry, so the viewing
backend (Phoenix by default, Langfuse as a documented swap) is an endpoint
change rather than a code change — the same rule `LLMClient` follows for models.

Two safeguards live here rather than at the call sites:

- Configuration is serialized under a lock. The latch is check-then-act, and
  concurrent callers would otherwise each build a `BatchSpanProcessor`, leaving
  N-1 abandoned worker threads and HTTP sessions behind.
- Tracing with PHI redaction switched off is announced loudly. `redact_phi()`
  degrades to identity in that combination, so raw text reaches spans.
"""
from __future__ import annotations

import logging
import threading
import warnings

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from tara.config import Settings, get_settings

_TRACER_NAME = "tara"
_tracing_configuration_lock = threading.Lock()
_is_tracing_configured = False
_logger = logging.getLogger(__name__)

UNREDACTED_TRACING_WARNING = (
    "TARA_TRACING_ENABLED=true with TARA_PHI_REDACTION_ENABLED=false: span "
    "attributes will carry RAW text, including any protected health "
    "information in the question, the answer, and the retrieved document "
    "text. Sanctioned only for local debugging on synthetic data — set "
    "TARA_PHI_REDACTION_ENABLED=true before tracing real documents."
)


def _build_tracer_provider(settings: Settings) -> TracerProvider:
    """Build a tracer provider exporting to the configured OTLP endpoint.

    Split out from `configure_tracing()` so the provider's shape — service
    name, one batching processor, exporter endpoint — is testable without
    installing anything into OpenTelemetry's global state.
    """
    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name}),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)),
    )
    return tracer_provider


def _warn_when_tracing_without_redaction(settings: Settings) -> None:
    """Announce the one combination in which spans carry raw text.

    Deliberately a warning, not a refusal: `.env.example` sanctions disabling
    redaction for local debugging on synthetic data, and tracing is exactly
    what a developer wants on while doing that. Emitted twice — a log record
    and a `warnings.warn` — because `redact_phi()`'s own one-per-process
    warning is easy to miss, and this pairing is the one that leaks.
    """
    if settings.phi_redaction_enabled:
        return
    _logger.error(UNREDACTED_TRACING_WARNING)
    warnings.warn(UNREDACTED_TRACING_WARNING, stacklevel=2)


def configure_tracing() -> None:
    """Install the tracer provider. Idempotent; a no-op when tracing is disabled.

    Called from the composition root rather than at import time, so importing
    the package never opens a network exporter. The whole body runs under a
    lock, so a concurrent second caller waits rather than building a second
    exporter it would then abandon.
    """
    global _is_tracing_configured
    with _tracing_configuration_lock:
        if _is_tracing_configured:
            return

        settings = get_settings()
        if not settings.tracing_enabled:
            return

        _warn_when_tracing_without_redaction(settings)
        trace.set_tracer_provider(_build_tracer_provider(settings))
        _is_tracing_configured = True


def get_tracer() -> trace.Tracer:
    """Return the application tracer.

    Safe before `configure_tracing()`: OpenTelemetry returns a no-op tracer, so
    instrumented code never has to check whether tracing is enabled.
    """
    return trace.get_tracer(_TRACER_NAME)
