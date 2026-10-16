"""Tests for the on-save hook's ruff version pinning (ci/ruff-version)."""

import importlib.util
from pathlib import Path

import pytest

HOOK_PATH = (
    Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "ruff_on_save.py"
)
PIN_FILE = Path(__file__).resolve().parents[1] / "ci" / "ruff-version"


@pytest.fixture
def hook():
    spec = importlib.util.spec_from_file_location("ruff_on_save", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pinned_version_is_read_from_the_pin_file(hook, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert hook._pinned_ruff_version() == PIN_FILE.read_text().strip()


def test_uvx_is_preferred_with_the_pinned_version(hook, monkeypatch):
    monkeypatch.setattr(hook.shutil, "which", lambda name: f"/bin/{name}")
    assert hook._ruff_command("1.2.3") == (["/bin/uvx", "ruff@1.2.3"], None)


def test_path_ruff_with_the_wrong_version_is_skipped_with_a_warning(hook, monkeypatch):
    monkeypatch.setattr(
        hook.shutil, "which", lambda name: None if name == "uvx" else "/bin/ruff"
    )
    monkeypatch.setattr(hook, "_run", lambda *arguments: ("ruff 0.0.1", 0))
    command, warning = hook._ruff_command("1.2.3")
    assert command is None
    assert "0.0.1" in warning and "1.2.3" in warning


def test_path_ruff_with_the_pinned_version_is_used(hook, monkeypatch):
    monkeypatch.setattr(
        hook.shutil, "which", lambda name: None if name == "uvx" else "/bin/ruff"
    )
    monkeypatch.setattr(hook, "_run", lambda *arguments: ("ruff 1.2.3", 0))
    assert hook._ruff_command("1.2.3") == (["/bin/ruff"], None)


def test_unreadable_pin_runs_no_ruff(hook, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert hook._pinned_ruff_version() is None
    assert hook._ruff_command(None) == (None, None)
