from __future__ import annotations

import importlib.util
import json
import os
import runpy
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import pytest
import tomllib

SCRIPT_PATH = Path(__file__).with_name("post-coverage-status.py")
WORKFLOW_PATH = SCRIPT_PATH.parent.parent / ".github" / "workflows" / "lint.yml"
PYPROJECT_PATH = SCRIPT_PATH.parent.parent / "pyproject.toml"
PRE_COMMIT_PATH = SCRIPT_PATH.parent.parent / "hooks" / "pre-commit"
AGENTS_PATH = SCRIPT_PATH.parent.parent / "AGENTS.md"


@pytest.fixture
def coverage_status_module():
    specification = importlib.util.spec_from_file_location(
        "post_coverage_status", SCRIPT_PATH
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_post_uses_urlopen_default_verified_context(
    monkeypatch: pytest.MonkeyPatch, coverage_status_module
) -> None:
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://gitea.example.test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    response = mock.Mock()
    urlopen = mock.Mock(return_value=response)
    monkeypatch.setattr(coverage_status_module.urllib.request, "urlopen", urlopen)

    coverage_status_module._post("success", "100% line coverage")

    assert urlopen.call_args.kwargs == {}
    response.read.assert_called_once_with()


def test_post_constructs_gitea_status_request(
    monkeypatch: pytest.MonkeyPatch, coverage_status_module
) -> None:
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://gitea.example.test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_RUN_ID", "456")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    urlopen = mock.Mock(return_value=mock.Mock())
    monkeypatch.setattr(coverage_status_module.urllib.request, "urlopen", urlopen)

    coverage_status_module._post("success", "87.35% line coverage")

    request = urlopen.call_args.args[0]
    assert request.full_url == (
        "https://gitea.example.test/api/v1/repos/owner/repository/statuses/abc123"
    )
    assert request.method == "POST"
    assert request.headers == {
        "Authorization": "token secret-token",
        "Content-type": "application/json",
    }
    assert json.loads(request.data) == {
        "context": "pr-crew/coverage",
        "state": "success",
        "description": "87.35% line coverage",
        "target_url": ("https://gitea.example.test/owner/repository/actions/runs/456"),
    }


def test_post_propagates_network_failure(
    monkeypatch: pytest.MonkeyPatch, coverage_status_module
) -> None:
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://gitea.example.test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr(
        coverage_status_module.urllib.request,
        "urlopen",
        mock.Mock(side_effect=urllib.error.URLError("offline")),
    )

    with pytest.raises(urllib.error.URLError, match="offline"):
        coverage_status_module._post("error", "coverage measurement failed")


def test_percent_from_coverage_json(tmp_path: Path, coverage_status_module) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"totals": {"percent_covered": 87.346}}))

    assert coverage_status_module._percent_from_coverage_json(str(report_path)) == (
        87.346
    )


def test_percent_from_cobertura_merges_duplicate_lines(
    tmp_path: Path, coverage_status_module
) -> None:
    first_report = tmp_path / "first.xml"
    first_report.write_text(
        """<coverage><packages><package><classes>
        <class filename="source.py"><lines>
        <line number="1" hits="0"/><line number="2" hits="1"/>
        </lines></class>
        </classes></package></packages></coverage>"""
    )
    second_report = tmp_path / "second.xml"
    second_report.write_text(
        """<coverage><packages><package><classes>
        <class filename="source.py"><lines><line number="1" hits="1"/></lines></class>
        <class filename="other.py"><lines><line number="1" hits="0"/></lines></class>
        </classes></package></packages></coverage>"""
    )
    ignored_directory = tmp_path / "bin"
    ignored_directory.mkdir()
    (ignored_directory / "ignored.xml").write_text("<not-coverage>")

    percent = coverage_status_module._percent_from_cobertura(
        [str(tmp_path / "**" / "*.xml")]
    )

    assert percent == pytest.approx(200 / 3)


def test_percent_from_cobertura_requires_matching_report(
    tmp_path: Path, coverage_status_module
) -> None:
    with pytest.raises(FileNotFoundError, match="no Cobertura XML matched"):
        coverage_status_module._percent_from_cobertura(
            [str(tmp_path / "missing-*.xml")]
        )


def test_percent_from_cobertura_requires_source_lines(
    tmp_path: Path, coverage_status_module
) -> None:
    report_path = tmp_path / "empty.xml"
    report_path.write_text("<coverage><class filename='source.py'/></coverage>")

    with pytest.raises(ValueError, match="no source lines"):
        coverage_status_module._percent_from_cobertura([str(report_path)])


@pytest.mark.parametrize(
    "percent", [float("nan"), float("inf"), float("-inf"), -0.01, 100.01]
)
def test_main_posts_error_for_invalid_coverage_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    coverage_status_module,
    percent: float,
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"totals": {"percent_covered": percent}}))
    post = mock.Mock()
    monkeypatch.setattr(coverage_status_module, "_post", post)

    result = coverage_status_module.main(
        ["post-coverage-status.py", "--coverage-json", str(report_path)]
    )

    assert result == 0
    post.assert_called_once_with("error", "coverage measurement failed")


def test_main_posts_rounded_coverage_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coverage_status_module, capsys
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"totals": {"percent_covered": 87.346}}))
    post = mock.Mock()
    monkeypatch.setattr(coverage_status_module, "_post", post)

    result = coverage_status_module.main(
        ["post-coverage-status.py", "--coverage-json", str(report_path)]
    )

    assert result == 0
    post.assert_called_once_with("success", "87.35% line coverage")
    assert capsys.readouterr().out == (
        "posted pr-crew/coverage success: 87.35% line coverage\n"
    )


def test_main_posts_error_when_measurement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coverage_status_module, capsys
) -> None:
    post = mock.Mock()
    monkeypatch.setattr(coverage_status_module, "_post", post)

    result = coverage_status_module.main(
        ["post-coverage-status.py", "--coverage-json", str(tmp_path / "missing.json")]
    )

    assert result == 0
    post.assert_called_once_with("error", "coverage measurement failed")
    assert "coverage measurement failed:" in capsys.readouterr().err


def test_main_posts_error_when_coverage_step_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coverage_status_module
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"totals": {"percent_covered": 100}}))
    monkeypatch.setenv("COVERAGE_STEP_OUTCOME", "failure")
    post = mock.Mock()
    monkeypatch.setattr(coverage_status_module, "_post", post)

    result = coverage_status_module.main(
        ["post-coverage-status.py", "--coverage-json", str(report_path)]
    )

    assert result == 0
    post.assert_called_once_with("error", "coverage step failed")


def test_main_reads_cobertura_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coverage_status_module
) -> None:
    report_path = tmp_path / "coverage.xml"
    report_path.write_text(
        """<coverage><class filename="source.py"><lines>
        <line number="1" hits="1"/>
        </lines></class></coverage>"""
    )
    post = mock.Mock()
    monkeypatch.setattr(coverage_status_module, "_post", post)

    result = coverage_status_module.main(
        ["post-coverage-status.py", "--cobertura", str(report_path)]
    )

    assert result == 0
    post.assert_called_once_with("success", "100.0% line coverage")


def test_entry_point_executes_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"totals": {"percent_covered": 91.5}}))
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://gitea.example.test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr(
        sys,
        "argv",
        ["post-coverage-status.py", "--coverage-json", str(report_path)],
    )
    urlopen = mock.Mock(return_value=mock.Mock())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    with pytest.raises(SystemExit) as exit_information:
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

    assert exit_information.value.code == 0
    request = urlopen.call_args.args[0]
    assert json.loads(request.data)["description"] == "91.5% line coverage"


def test_help_entry_point_returns_promptly() -> None:
    completed_process = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )

    assert completed_process.returncode == 0
    assert "--coverage-json" in completed_process.stdout


def test_failed_step_entry_point_posts_error_in_bounded_subprocess(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"totals": {"percent_covered": 100}}))
    captured_request_path = tmp_path / "captured-request.json"
    shim_directory = tmp_path / "python-shim"
    shim_directory.mkdir()
    (shim_directory / "sitecustomize.py").write_text(
        """import os
import urllib.request


class Response:
    def read(self):
        return b""


def capture_urlopen(request):
    with open(os.environ["CAPTURED_REQUEST_PATH"], "wb") as captured_request:
        captured_request.write(request.data)
    return Response()


urllib.request.urlopen = capture_urlopen
"""
    )
    environment = os.environ.copy()
    environment.update(
        {
            "CAPTURED_REQUEST_PATH": str(captured_request_path),
            "COVERAGE_STEP_OUTCOME": "failure",
            "GITHUB_REPOSITORY": "owner/repository",
            "GITHUB_SERVER_URL": "https://gitea.example.test",
            "GITHUB_SHA": "abc123",
            "GITHUB_TOKEN": "secret-token",
            "PYTHONPATH": str(shim_directory),
        }
    )

    completed_process = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--coverage-json", str(report_path)],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=5,
    )

    assert completed_process.returncode == 0
    assert "coverage step did not succeed: failure" in completed_process.stderr
    assert json.loads(captured_request_path.read_text())["state"] == "error"


def test_workflow_covers_and_lints_publisher() -> None:
    workflow = WORKFLOW_PATH.read_text()

    assert "pytest tests/ scripts/ ci/ --cov=scripts --cov=ci" in workflow
    assert "ruff check scripts/ tests/ ci/" in workflow
    assert "ruff format --check scripts/ tests/ ci/" in workflow


def test_local_ruff_gate_and_documentation_include_publisher() -> None:
    pre_commit = PRE_COMMIT_PATH.read_text()
    agents = AGENTS_PATH.read_text()

    assert '"${RUFF[@]}" check scripts/ tests/ ci/' in pre_commit
    assert '"${RUFF[@]}" format --check scripts/ tests/ ci/' in pre_commit
    assert "ruff check scripts/ tests/ ci/" in pre_commit
    assert "ruff format --check scripts/ tests/ ci/" in pre_commit
    assert "ruff check scripts/ tests/ ci/" in agents
    assert "ruff format --check scripts/ tests/ ci/" in agents


def test_workflow_passes_coverage_step_outcome_to_publisher() -> None:
    workflow = WORKFLOW_PATH.read_text()

    assert "id: coverage" in workflow
    assert "COVERAGE_STEP_OUTCOME: ${{ steps.coverage.outcome }}" in workflow


def test_coverage_configuration_omits_test_modules() -> None:
    configuration = tomllib.loads(PYPROJECT_PATH.read_text())

    assert configuration["tool"]["coverage"]["run"]["omit"] == [
        "scripts/test_*.py",
        "ci/test_*.py",
    ]
