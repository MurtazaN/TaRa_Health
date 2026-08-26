"""configure_tracing() must stay behaviour-neutral when tracing is off.

These tests never let the enabled path reach `set_tracer_provider` — doing so
would install a real `TracerProvider` into OpenTelemetry's global state and
leak into every other test in the suite. They probe the disabled path and the
latch that guards re-configuration instead.
"""
from __future__ import annotations

import pytest
from opentelemetry import trace

from tara import config
from tara.execution_tracing import tracer_setup


@pytest.fixture
def tracing_latch_reset(monkeypatch):
    """Isolate the settings cache and the module-level configured-latch."""
    monkeypatch.setenv("TARA_TRACING_ENABLED", "false")
    config.get_settings.cache_clear()
    tracer_setup._is_tracing_configured = False
    yield
    tracer_setup._is_tracing_configured = False
    config.get_settings.cache_clear()


def test_disabled_tracing_leaves_the_noop_provider_in_place(tracing_latch_reset):
    tracer_setup.configure_tracing()
    assert isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider)
    with tracer_setup.get_tracer().start_as_current_span("probe") as span:
        assert span.is_recording() is False


def test_disabled_call_does_not_latch_out_a_later_enable(tracing_latch_reset, monkeypatch):
    """Regression guard for the latch-ordering bug.

    The latch used to be set to True before the disabled check, so one call
    made while tracing was off permanently blocked every later call — even
    after tracing was turned on — with no error. Assert on the module-level
    flag directly: it is the cheapest guard, and it fails immediately if the
    early `global`-assignment is ever reintroduced.
    """
    tracer_setup.configure_tracing()
    assert tracer_setup._is_tracing_configured is False

    monkeypatch.setenv("TARA_TRACING_ENABLED", "true")
    config.get_settings.cache_clear()
    assert tracer_setup._is_tracing_configured is False
