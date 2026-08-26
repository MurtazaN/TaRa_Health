"""Installs the OpenTelemetry tracer provider once per process.

Tracing is opt-in because a span carries the user's question and retrieved
document text. Instrumentation is vendor-neutral OpenTelemetry, so the viewing
backend (Phoenix by default, Langfuse as a documented swap) is an endpoint
change rather than a code change — the same rule `LLMClient` follows for models.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from tara.config import get_settings

_TRACER_NAME = "tara"
_is_tracing_configured = False


def configure_tracing() -> None:
    """Install the tracer provider. Idempotent; a no-op when tracing is disabled.

    Called from the composition root rather than at import time, so importing
    the package never opens a network exporter.
    """
    global _is_tracing_configured
    if _is_tracing_configured:
        return
    _is_tracing_configured = True

    settings = get_settings()
    if not settings.tracing_enabled:
        return

    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name}),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)),
    )
    trace.set_tracer_provider(tracer_provider)


def get_tracer() -> trace.Tracer:
    """Return the application tracer.

    Safe before `configure_tracing()`: OpenTelemetry returns a no-op tracer, so
    instrumented code never has to check whether tracing is enabled.
    """
    return trace.get_tracer(_TRACER_NAME)
