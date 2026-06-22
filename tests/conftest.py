"""Shared fixtures. Put sample documents (a benefits summary, a lab report, an
EOB, etc.) under tests/fixtures/ to drive the eval harness.
"""
import pytest


@pytest.fixture
def fixtures_dir():
    from pathlib import Path
    return Path(__file__).parent / "fixtures"
