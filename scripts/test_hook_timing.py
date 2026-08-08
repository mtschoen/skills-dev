#!/usr/bin/env python3
"""Tests for hook-timing.py (the on-save hook timing log aggregator).

The module filename contains a dash, so it cannot be imported by name; it is
loaded by path via importlib. The log path is a module-level constant, so
tests monkeypatch it at a tmp_path file.
"""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "hook-timing.py"
_spec = importlib.util.spec_from_file_location("hook_timing", _MODULE_PATH)
hook_timing = importlib.util.module_from_spec(_spec)
sys.modules["hook_timing"] = hook_timing
_spec.loader.exec_module(hook_timing)


@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    """Point the module's LOG constant at an empty tmp_path location."""
    path = tmp_path / "hook-timing.jsonl"
    monkeypatch.setattr(hook_timing, "LOG", path)
    return path


def _write_samples(path, samples):
    text = "".join(json.dumps(sample) + "\n" for sample in samples)
    path.write_text(text, encoding="utf-8")


def _run_main(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["hook-timing.py", *argv])
    hook_timing.main()
    return capsys.readouterr().out


# --- percentile ---


def test_percentile_empty_is_zero():
    assert hook_timing.percentile([], 50) == 0.0


def test_percentile_single_value():
    assert hook_timing.percentile([42.0], 95) == 42.0


def test_percentile_interpolates_between_neighbors():
    assert hook_timing.percentile([0.0, 100.0], 25) == 25.0


def test_percentile_sorts_unsorted_input():
    assert hook_timing.percentile([100.0, 0.0], 50) == 50.0


# --- load ---


def test_load_missing_log_returns_empty(log_file):
    assert hook_timing.load() == []


def test_load_skips_blank_and_malformed_lines(log_file):
    log_file.write_text(
        '{"tool": "ruff", "ms": 10}\n\nnot json\n{"tool": "shellcheck", "ms": 20}\n',
        encoding="utf-8",
    )
    rows = hook_timing.load()
    assert [row["tool"] for row in rows] == ["ruff", "shellcheck"]


def test_load_recent_slices_from_the_end(log_file):
    _write_samples(log_file, [{"ms": index} for index in range(10)])
    rows = hook_timing.load(recent=3)
    assert [row["ms"] for row in rows] == [7, 8, 9]


# --- main ---


def test_main_reset_removes_log(log_file, monkeypatch, capsys):
    _write_samples(log_file, [{"tool": "ruff", "ms": 1}])
    out = _run_main(monkeypatch, capsys, "--reset")
    assert not log_file.exists()
    assert "reset" in out


def test_main_reset_without_log_still_reports(log_file, monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys, "--reset")
    assert "reset" in out


def test_main_without_samples_reports_empty_log(log_file, monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys)
    assert "no timing samples" in out


def test_main_summary_groups_by_tool(log_file, monkeypatch, capsys):
    _write_samples(
        log_file,
        [
            {"tool": "ruff", "ms": 100},
            {"tool": "ruff", "ms": 300},
            {"tool": "shellcheck", "ms": 50},
            {"ms": 10},  # no tool key -> grouped under "?"
        ],
    )
    out = _run_main(monkeypatch, capsys)
    assert "ruff" in out
    assert "shellcheck" in out
    assert "?" in out
    assert "ALL" in out
    assert "4 samples shown" in out


def test_main_recent_flag_limits_summary(log_file, monkeypatch, capsys):
    _write_samples(log_file, [{"tool": "ruff", "ms": 10}] * 5)
    out = _run_main(monkeypatch, capsys, "--recent", "2")
    assert "2 samples shown" in out


def test_script_entry_point_reads_a_disposable_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", classmethod(lambda _path_class: tmp_path))
    monkeypatch.setattr(sys, "argv", ["hook-timing.py"])

    runpy.run_path(str(_MODULE_PATH), run_name="__main__")

    assert "no timing samples" in capsys.readouterr().out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
