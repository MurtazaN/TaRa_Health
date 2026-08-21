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
def test_local_mode_needs_no_hosted_key():
    s = _settings(model_mode="local", hosted_api_key="")
    assert s.model_mode == "local"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["hosted", "hybrid"])
def test_egress_modes_require_a_hosted_key(mode):
    with pytest.raises(ValidationError, match="TARA_HOSTED_API_KEY"):
        _settings(model_mode=mode, hosted_api_key="")


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["hosted", "hybrid"])
def test_egress_modes_accept_a_hosted_key(mode):
    s = _settings(model_mode=mode, hosted_api_key="sk-secret")
    assert s.model_mode == mode


@pytest.mark.unit
def test_blank_hosted_key_is_treated_as_missing():
    # Whitespace-only must not count as a credential.
    with pytest.raises(ValidationError):
        _settings(model_mode="hosted", hosted_api_key="   ")


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
