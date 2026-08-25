"""Calls a hosted text-generation model on Google Cloud Agent Platform.

The ONLY code path where document text may leave the device (§7). Used in
generation_mode 'agent_platform', or 'hybrid' with an explicit per-query opt-in.
Sends the MINIMUM payload: the system prompt plus one assembled user prompt —
never the corpus, and never at ingestion time.

LangChain is confined to this module so it stays as replaceable as the provider it
wraps. `vertexai=True` is passed EXPLICITLY on every construction: LangChain's
backend auto-detection falls back to the consumer Gemini Developer API when no
project is set, and that product is not covered by a GCP BAA.
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

# PRIVATE import: the MaaS allowlist is not part of langchain-google-vertexai's
# public API. test_maas_allowlist_import_still_resolves() guards it, so a package
# upgrade that moves these symbols fails CI instead of silently disabling the
# startup model check.
from langchain_google_vertexai.model_garden_maas._base import (  # noqa: E402
    _LLAMA_MODELS,
    _MISTRAL_MODELS,
)

_MAAS_MODEL_NAMES: frozenset[str] = frozenset(_LLAMA_MODELS) | frozenset(_MISTRAL_MODELS)


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

    return get_vertex_maas_model(
        _configured_model_name(),
        project=settings.gcp_project,
        location=settings.gcp_location,
    )


def _status_code_of(error: Exception) -> int | None:
    """Best-effort HTTP status from a Google or LangChain-wrapped error."""
    for attribute in ("code", "status_code", "grpc_status_code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


def _classify_failure(error: Exception) -> Exception:
    """Map an upstream failure onto our taxonomy, carrying NO user content.

    The message names the failure, the model, the project and the location —
    nothing derived from the prompt, because web_app renders str(exc) to the
    client. The original error is chained for local logs only.
    """
    settings = get_settings()
    context = (
        f"provider={settings.agent_platform_provider} model={_configured_model_name()} "
        f"project={settings.gcp_project} location={settings.gcp_location}"
    )
    status_code = _status_code_of(error)

    if type(error).__name__ == "DefaultCredentialsError":
        return AgentPlatformConfigError(
            f"No Application Default Credentials found ({context}). "
            f"Run 'gcloud auth application-default login', or attach a service account."
        )
    if status_code in _RETRYABLE_STATUS_CODES:
        return AgentPlatformUnavailableError(
            f"Agent Platform returned {status_code} after {_MAX_ATTEMPTS} attempts "
            f"({context}). This is transient; the same request may succeed later."
        )
    return AgentPlatformConfigError(
        f"Agent Platform rejected the request"
        f"{f' with {status_code}' if status_code else ''} ({context}). "
        f"Check credentials, IAM permissions, the model id, and the region."
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
    if model_name not in _MAAS_MODEL_NAMES:
        raise AgentPlatformConfigError(
            f"'{model_name}' is not a known Agent Platform MaaS model. "
            f"Known models: {', '.join(sorted(_MAAS_MODEL_NAMES))}."
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
                if _status_code_of(error) not in _RETRYABLE_STATUS_CODES:
                    raise _classify_failure(error) from error
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_backoff_seconds(attempt))
        # The loop body always assigns last_error before falling through here (the
        # only exit that isn't an early `return` or `raise` is exhausting the
        # retry budget, which requires at least one caught exception) — the
        # assert only narrows the type for mypy, it changes no behavior.
        assert last_error is not None
        raise _classify_failure(last_error) from last_error
