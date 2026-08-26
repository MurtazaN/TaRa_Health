"""Calls a hosted text-generation model on Google Cloud Agent Platform.

The ONLY code path where document text may leave the device (§7). Used in
generation_mode 'agent_platform', or 'hybrid' with an explicit per-query opt-in.
Sends the MINIMUM payload: the system prompt plus one assembled user prompt —
never the corpus, and never at ingestion time.

LangChain is confined to this module so it stays as replaceable as the provider it
wraps. `vertexai=True` is passed EXPLICITLY on every Gemini construction:
LangChain's backend auto-detection falls back to the consumer Gemini Developer
API when no project is set, and that product is not covered by a GCP BAA. The
MaaS providers have no such field — they are Vertex-only by construction.

Every LangChain import is LAZY. In generation_mode 'local' this module is never
asked for a client, so the egress library must not be loaded merely because
`llm_client_interface` was imported.
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from tara.app_errors import AgentPlatformConfigError, AgentPlatformUnavailableError
from tara.config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

# Bounded retry. Transient failures are worth one or two more tries; an operator
# error is not worth any, and an unbounded loop would hang a request.
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_OPERATOR_STATUS_CODES = frozenset({400, 401, 403, 404, 409})


def _collect_retryable_error_types() -> tuple[type[BaseException], ...]:
    """Gather the transport failures that carry NO HTTP status (M5 §7.1).

    A DNS blip, a TLS reset, or a socket timeout arrives as a plain exception
    with no status attribute. Classifying by status alone would call that an
    operator error and refuse to retry it — telling the user to check their IAM
    permissions over a momentary network fault. The spec lists "connection
    error" as retryable, so the taxonomy needs types as well as status codes.
    """
    error_types: list[type[BaseException]] = [ConnectionError, TimeoutError]
    try:
        from google.auth.exceptions import TransportError as GoogleTransportError
    except ImportError:  # pragma: no cover - google-auth ships with the SDKs
        pass
    else:
        error_types.append(GoogleTransportError)
    try:
        # Installed transitively with langchain-google-genai; guarded anyway so a
        # slimmer install loses one transport class rather than failing to import.
        from httpx import TransportError as HttpxTransportError
    except ImportError:  # pragma: no cover - httpx ships with the SDKs
        pass
    else:
        error_types.append(HttpxTransportError)
    return tuple(error_types)


_RETRYABLE_ERROR_TYPES: tuple[type[BaseException], ...] = _collect_retryable_error_types()


@lru_cache
def _maas_model_names() -> frozenset[str]:
    """The MaaS model allowlist frozen into the installed langchain-google-vertexai.

    Imported LAZILY so generation_mode 'local' never pulls the egress library,
    and PRIVATELY because this allowlist is not part of the package's public API.
    test_maas_allowlist_import_still_resolves() guards it, so a package upgrade
    that moves these symbols fails CI instead of silently disabling the startup
    model check.
    """
    from langchain_google_vertexai.model_garden_maas._base import (
        _LLAMA_MODELS,
        _MISTRAL_MODELS,
    )

    return frozenset(_LLAMA_MODELS) | frozenset(_MISTRAL_MODELS)


def _configured_model_name() -> str:
    """The model id for the selected provider."""
    settings = get_settings()
    return {
        "gemini": settings.gemini_model,
        "llama": settings.llama_model,
        "mistral": settings.mistral_model,
    }[settings.agent_platform_provider]


@lru_cache
def _chat_model() -> "BaseChatModel":
    """Build the provider's chat model once, always in Agent Platform mode."""
    settings = get_settings()
    if settings.agent_platform_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            # EXPLICIT, never inferred: with this unset and no project, LangChain
            # routes to generativelanguage.googleapis.com — the consumer API.
            vertexai=True,
            project=settings.gcp_project,
            location=settings.gcp_location,
            timeout=settings.llm_timeout_seconds,
        )

    from langchain_google_vertexai.model_garden_maas import get_vertex_maas_model

    # The MaaS classes expose no `vertexai` flag — they are Vertex-only, so there
    # is no consumer-API fallback to pin here. `timeout` is passed on both paths:
    # without it a stalled call hangs the request forever (config.py §Timeouts).
    return get_vertex_maas_model(
        _configured_model_name(),
        project=settings.gcp_project,
        location=settings.gcp_location,
        timeout=settings.llm_timeout_seconds,
    )


def _status_code_of(error: Exception) -> int | None:
    """Best-effort HTTP status from a Google or LangChain-wrapped error."""
    for attribute in ("code", "status_code", "grpc_status_code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


def _is_retryable_failure(error: Exception) -> bool:
    """Whether the taxonomy says this failure may succeed on a later attempt.

    Type first, then status: a transport failure never carries a status code, so
    a status-only test would silently classify it as an operator error.
    """
    if isinstance(error, _RETRYABLE_ERROR_TYPES):
        return True
    return _status_code_of(error) in _RETRYABLE_STATUS_CODES


def _classify_failure(error: Exception) -> Exception:
    """Map an upstream failure onto our taxonomy, carrying NO user content.

    The message names the failure class, the model, the project and the location
    — nothing derived from the prompt, and never the upstream error's own text,
    because web_app renders str(exc) to the client and Google errors routinely
    echo the request body. The original error is chained for local logs only.
    """
    settings = get_settings()
    context = (
        f"provider={settings.agent_platform_provider} model={_configured_model_name()} "
        f"project={settings.gcp_project} location={settings.gcp_location}"
    )
    status_code = _status_code_of(error)
    operator_remedy = "Check credentials, IAM permissions, the model id, and the region."

    if type(error).__name__ == "DefaultCredentialsError":
        return AgentPlatformConfigError(
            f"No Application Default Credentials found ({context}). "
            f"Run 'gcloud auth application-default login', or attach a service account."
        )
    if status_code in _OPERATOR_STATUS_CODES:
        return AgentPlatformConfigError(
            f"Agent Platform rejected the request with {status_code} ({context}). "
            f"{operator_remedy}"
        )
    if _is_retryable_failure(error):
        # Transport failures have no status; name the exception CLASS instead,
        # which identifies the fault without quoting the upstream message.
        failure_label = (
            f"status {status_code}" if status_code is not None else type(error).__name__
        )
        return AgentPlatformUnavailableError(
            f"Agent Platform was unavailable ({failure_label}) after {_MAX_ATTEMPTS} "
            f"attempts ({context}). This is transient; the same request may succeed later."
        )
    # Fail closed: an unrecognised failure is treated as an operator error, so it
    # surfaces once at 500 rather than being retried blindly against an unknown fault.
    unknown_label = f"{type(error).__name__}"
    if status_code is not None:
        unknown_label = f"{unknown_label}, status {status_code}"
    return AgentPlatformConfigError(
        f"Agent Platform failed with an unrecognised error ({unknown_label}) "
        f"({context}). {operator_remedy}"
    )


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 0.5s, 1.0s. Patched to 0 in tests."""
    return 0.5 * (2 ** (attempt - 1))


def verify_generation_model() -> None:
    """Reject an unknown or retired model at startup, with no network call (M5 §7.3).

    Only MaaS providers are checkable offline: their names come from a frozen
    allowlist in the package. Gemini ids are not enumerable locally, so a bad one
    surfaces on first use instead.
    """
    settings = get_settings()
    if settings.agent_platform_provider == "gemini":
        return
    model_name = _configured_model_name()
    known_model_names = _maas_model_names()
    if model_name not in known_model_names:
        raise AgentPlatformConfigError(
            f"'{model_name}' is not a known Agent Platform MaaS model. "
            f"Known models: {', '.join(sorted(known_model_names))}."
        )


class AgentPlatformClient:
    """LLMClient backed by Google Cloud Agent Platform (Gemini or MaaS)."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        messages = [("system", system_prompt), ("human", user_prompt)]
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                # .content is typed str | list[...] on a LangChain message; this app
                # sends text-only prompts, so coerce rather than silence the checker.
                return str(_chat_model().invoke(messages).content)
            except Exception as error:  # noqa: BLE001 - re-raised as our taxonomy
                last_error = error
                if not _is_retryable_failure(error):
                    raise _classify_failure(error) from error
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_backoff_seconds(attempt))
        # The loop body always assigns last_error before falling through here (the
        # only exit that isn't an early `return` or `raise` is exhausting the
        # retry budget, which requires at least one caught exception) — the
        # assert only narrows the type for mypy, it changes no behavior.
        assert last_error is not None
        raise _classify_failure(last_error) from last_error
