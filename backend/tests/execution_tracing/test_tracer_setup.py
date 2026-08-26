"""configure_tracing() must stay behaviour-neutral off, and correct when on.

No test here lets a real `TracerProvider` reach OpenTelemetry's global state —
`set_tracer_provider` is a one-way install that would leak into every other
test in the suite. The enabled path is covered by patching
`trace.set_tracer_provider` with a recorder, and the provider's own shape is
asserted against `_build_tracer_provider()` directly.
"""
from __future__ import annotations

import warnings

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from tara import config
from tara.execution_tracing import tracer_setup


@pytest.fixture
def tracing_latch_reset(monkeypatch):
    """Isolate the settings cache and the module-level configured-latch."""
    monkeypatch.setenv("TARA_TRACING_ENABLED", "false")
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    tracer_setup._is_tracing_configured = False
    yield
    tracer_setup._is_tracing_configured = False
    config.get_settings.cache_clear()


@pytest.fixture
def installed_providers(monkeypatch):
    """Capture what `configure_tracing()` would install, installing nothing.

    A real `set_tracer_provider()` call is global and irreversible for the
    process, so the enabled path can only be covered safely by intercepting it.
    """
    captured: list[trace.TracerProvider] = []
    monkeypatch.setattr(trace, "set_tracer_provider", captured.append)
    yield captured


def _shutdown_all(tracer_providers) -> None:
    """Stop the batch worker threads a built provider started."""
    for tracer_provider in tracer_providers:
        tracer_provider.shutdown()


# ---- disabled path ----


def test_disabled_tracing_leaves_the_noop_provider_in_place(tracing_latch_reset):
    tracer_setup.configure_tracing()
    assert isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider)
    with tracer_setup.get_tracer().start_as_current_span("probe") as span:
        assert span.is_recording() is False


def test_disabled_call_does_not_latch_out_a_later_enable(
    tracing_latch_reset, installed_providers, monkeypatch
):
    """Regression guard for the latch-ordering bug.

    The latch used to be set to True before the disabled check, so one call
    made while tracing was off permanently blocked every later call — even
    after tracing was turned on — with no error. The second half turns tracing
    on and calls `configure_tracing()` AGAIN: asserting only on the flag
    without that second call would be an assertion about a call never made.
    """
    tracer_setup.configure_tracing()
    assert tracer_setup._is_tracing_configured is False
    assert installed_providers == []

    monkeypatch.setenv("TARA_TRACING_ENABLED", "true")
    config.get_settings.cache_clear()
    tracer_setup.configure_tracing()

    assert tracer_setup._is_tracing_configured is True
    assert len(installed_providers) == 1
    _shutdown_all(installed_providers)


# ---- provider construction ----


def test_build_tracer_provider_carries_the_configured_service_name(tracing_latch_reset, monkeypatch):
    monkeypatch.setenv("TARA_SERVICE_NAME", "tara-probe")
    config.get_settings.cache_clear()
    tracer_provider = tracer_setup._build_tracer_provider(config.get_settings())
    try:
        assert tracer_provider.resource.attributes["service.name"] == "tara-probe"
    finally:
        tracer_provider.shutdown()


def test_build_tracer_provider_attaches_one_batching_exporter_at_the_endpoint(
    tracing_latch_reset, monkeypatch
):
    """One batch processor, exporting to the configured endpoint.

    Batching rather than simple export is what keeps instrumentation off the
    request's critical path, so the processor type is part of the contract.
    """
    monkeypatch.setenv("TARA_OTLP_ENDPOINT", "http://probe-collector:6006/v1/traces")
    config.get_settings.cache_clear()
    tracer_provider = tracer_setup._build_tracer_provider(config.get_settings())
    try:
        span_processors = tracer_provider._active_span_processor._span_processors
        assert len(span_processors) == 1
        assert isinstance(span_processors[0], BatchSpanProcessor)
        exporter = span_processors[0].span_exporter
        assert exporter._endpoint == "http://probe-collector:6006/v1/traces"
    finally:
        tracer_provider.shutdown()


# ---- enabled path ----


def test_enabled_tracing_installs_a_provider(tracing_latch_reset, installed_providers, monkeypatch):
    monkeypatch.setenv("TARA_TRACING_ENABLED", "true")
    config.get_settings.cache_clear()

    tracer_setup.configure_tracing()

    assert len(installed_providers) == 1
    assert isinstance(installed_providers[0], TracerProvider)
    assert tracer_setup._is_tracing_configured is True
    _shutdown_all(installed_providers)


def test_configure_tracing_is_idempotent(tracing_latch_reset, installed_providers, monkeypatch):
    """The docstring promises idempotence; a second install would abandon the
    first provider's exporter and batch worker thread rather than replace it.
    """
    monkeypatch.setenv("TARA_TRACING_ENABLED", "true")
    config.get_settings.cache_clear()

    tracer_setup.configure_tracing()
    tracer_setup.configure_tracing()
    tracer_setup.configure_tracing()

    assert len(installed_providers) == 1
    _shutdown_all(installed_providers)


# ---- tracing-without-redaction warning ----


def test_tracing_without_redaction_warns_loudly(
    tracing_latch_reset, installed_providers, monkeypatch, caplog
):
    """`redact_phi()` degrades to identity when redaction is off, so this
    combination puts raw text on spans. It is sanctioned for synthetic-data
    debugging and must NOT refuse — but it must be impossible to miss.
    """
    monkeypatch.setenv("TARA_TRACING_ENABLED", "true")
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "false")
    config.get_settings.cache_clear()

    with pytest.warns(UserWarning, match="TARA_PHI_REDACTION_ENABLED=false"):
        tracer_setup.configure_tracing()

    assert "TARA_PHI_REDACTION_ENABLED=false" in caplog.text
    assert len(installed_providers) == 1  # warned, not refused
    _shutdown_all(installed_providers)


def test_tracing_with_redaction_on_does_not_warn(
    tracing_latch_reset, installed_providers, monkeypatch
):
    monkeypatch.setenv("TARA_TRACING_ENABLED", "true")
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()

    with warnings.catch_warnings(record=True) as raised_warnings:
        warnings.simplefilter("always")
        tracer_setup.configure_tracing()

    assert [str(warning.message) for warning in raised_warnings] == []
    assert len(installed_providers) == 1
    _shutdown_all(installed_providers)
