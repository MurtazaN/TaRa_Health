"""Config contracts (design §3.2, §3.5): egress-requires-credential validator,
embed-dim sanity, side-effect-free settings cache, and derived paths."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from tara.config import Settings, ensure_data_dirs


def _settings(**overrides) -> Settings:
    # _env_file=None isolates the test from the developer's local .env.
    return Settings(_env_file=None, **overrides)


@pytest.mark.unit
def test_local_mode_needs_no_gcp_project():
    # Nothing egresses in local mode, so demanding a project would be theatre.
    s = _settings(generation_mode="local", gcp_project="", phi_egress_acknowledged=False)
    assert s.generation_mode == "local"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_require_a_gcp_project(mode):
    with pytest.raises(ValidationError, match="TARA_GCP_PROJECT"):
        _settings(generation_mode=mode, gcp_project="", phi_egress_acknowledged=True)


@pytest.mark.unit
def test_blank_gcp_project_is_treated_as_missing():
    with pytest.raises(ValidationError, match="TARA_GCP_PROJECT"):
        _settings(generation_mode="agent_platform", gcp_project="   ",
                  phi_egress_acknowledged=True)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_require_acknowledgement(mode):
    with pytest.raises(ValidationError, match="TARA_PHI_EGRESS_ACKNOWLEDGED"):
        _settings(generation_mode=mode, gcp_project="my-project",
                  phi_egress_acknowledged=False)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_accept_project_and_acknowledgement(mode):
    s = _settings(generation_mode=mode, gcp_project="my-project",
                  phi_egress_acknowledged=True)
    assert s.generation_mode == mode
    assert s.gcp_location == "us-central1"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["agent_platform", "hybrid"])
def test_egress_modes_refuse_to_start_with_redaction_disabled(mode):
    """The third egress precondition, alongside the project and the acknowledgement.

    redact_phi() is a documented no-op when phi_redaction_enabled is false: it
    warns once and returns the text unchanged. AgentPlatformClient relies on it
    for every payload, so an operator who left the flag off after local
    debugging would send complete, unredacted excerpts to Google with nothing
    but a startup warning. Refuse to start instead.
    """
    with pytest.raises(ValidationError):
        _settings(generation_mode=mode, gcp_project="my-project",
                  phi_egress_acknowledged=True, phi_redaction_enabled=False)


@pytest.mark.unit
def test_local_mode_allows_redaction_to_be_disabled():
    # Nothing egresses in local mode, so the flag stays a developer convenience.
    settings = _settings(generation_mode="local", gcp_project="",
                         phi_egress_acknowledged=False, phi_redaction_enabled=False)
    assert settings.phi_redaction_enabled is False


@pytest.mark.unit
def test_embed_model_is_pinned_by_revision():
    # An unpinned model silently changes the vector space between installs.
    s = _settings()
    assert s.embed_model == "Qwen/Qwen3-Embedding-0.6B"
    assert len(s.embed_model_revision) == 40  # a full git SHA


@pytest.mark.unit
def test_embed_dim_must_be_positive():
    with pytest.raises(ValidationError, match="EMBED_DIM"):
        _settings(embed_dim=0)


@pytest.mark.unit
def test_local_openai_base_url_appends_v1_and_strips_trailing_slash():
    s = _settings(lmstudio_host="http://localhost:1234/")
    assert s.local_openai_base_url == "http://localhost:1234/v1"


@pytest.mark.unit
def test_get_settings_is_cached_and_side_effect_free(tmp_path, monkeypatch):
    from tara import config

    data_dir = tmp_path / "nope"
    monkeypatch.setenv("TARA_DATA_DIR", str(data_dir))
    config.get_settings.cache_clear()
    try:
        s1 = config.get_settings()
        s2 = config.get_settings()
        assert s1 is s2  # cached
        assert not data_dir.exists()  # factory created no directories
        ensure_data_dirs(s1)
        assert (data_dir / "blobs").exists()  # explicit call does
    finally:
        config.get_settings.cache_clear()
