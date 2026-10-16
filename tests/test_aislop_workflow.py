import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
# Read from the pin file so an automated pin bump does not break this suite.
PIN = (ROOT / ".aislop/fork-commit").read_text(encoding="ascii").strip()


def test_pin_is_exact_and_not_ignored():
    assert re.fullmatch(r"[0-9a-f]{40}", PIN)
    assert (ROOT / ".aislop/fork-commit").read_bytes() == (PIN + "\n").encode()
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", ".aislop/fork-commit"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 1


@pytest.mark.parametrize(
    ("content", "valid"),
    [
        (PIN + "\n", True),
        (" \t" + PIN + "\r\n", True),
        (None, False),
        ("", False),
        (PIN[:8], False),
        (PIN.upper(), False),
        ("g" * 40, False),
        (PIN + "\nINJECTED=true\n", False),
        (PIN + "\n" + PIN, False),
        (PIN[:20] + " " + PIN[20:], False),
    ],
)
def test_pin_validation(tmp_path, content, valid):
    workflow = yaml.safe_load((ROOT / ".github/workflows/lint.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["aislop"]["steps"]
        if step.get("name") == "Read aislop fork pin"
    )
    assert step["shell"] == "bash"
    (tmp_path / ".aislop").mkdir()
    if content is not None:
        (tmp_path / ".aislop/fork-commit").write_text(content)
    environment_file = tmp_path / "github-env"
    environment_file.touch()
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_ENV": str(environment_file)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is valid, result.stderr
    expected = f"AISLOP_FORK_COMMIT={PIN}\n" if valid else ""
    assert environment_file.read_text() == expected


def test_install_and_gate_contract():
    workflow = yaml.safe_load((ROOT / ".github/workflows/lint.yml").read_text())
    job = workflow["jobs"]["aislop"]
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Read aislop fork pin") < names.index(
        "Install the aislop fork build"
    )
    install = next(
        step for step in steps if step.get("name") == "Install the aislop fork build"
    )
    body = install["run"]
    assert '"$GITHUB_SERVER_URL/schoen/aislop.git"' in body
    assert '"$GITHUB_SERVER_URL" == "https://github.com"' in body
    assert "https://github.com/mtschoen/aislop.git" in body
    assert 'git clone "$repository" "$RUNNER_TEMP/aislop"' in body
    assert 'git -C "$RUNNER_TEMP/aislop" checkout "$AISLOP_FORK_COMMIT"' in body
    assert (
        'npx -y pnpm@10.28.0 --dir "$RUNNER_TEMP/aislop" install --frozen-lockfile'
        in body
    )
    for obsolete in ("npm install", "npm pack", "aislop-*.tgz"):
        assert obsolete not in body
    gate = steps[-1]
    assert gate["run"] == 'node "$RUNNER_TEMP/aislop/dist/cli.js" ci .'
    assert not gate.get("continue-on-error", False)
    assert not job.get("continue-on-error", False)
    configuration = yaml.safe_load((ROOT / ".aislop/config.yml").read_text())
    assert configuration["ci"]["failBelow"] == 100


@pytest.mark.parametrize(
    ("job_name", "pip_step_identifier"),
    [
        ("aislop", "Install pinned ruff"),
        ("validate-skills", "pip install skills-ref"),
        ("coverage", "pip install skills-ref"),
        ("ruff", "Install pinned ruff"),
    ],
    ids=[
        "pr69-aislop-baked-python",
        "pr69-validate-skills-baked-python",
        "pr69-coverage-baked-python",
        "pr69-ruff-baked-python",
    ],
)
def test_baked_python_environment_contract(job_name, pip_step_identifier):
    workflow = yaml.safe_load((ROOT / ".github/workflows/lint.yml").read_text())
    job = workflow["jobs"][job_name]
    steps = job["steps"]

    baked_step = next(step for step in steps if step.get("id") == "baked")
    assert "python" in baked_step["run"]

    setup_python = next(
        step
        for step in steps
        if step.get("uses", "").startswith("actions/setup-python")
    )
    assert setup_python.get("if") == "steps.baked.outputs.python != 'true'"

    preparation_step = next(
        step
        for step in steps
        if step.get("name") == "Prepare baked Python virtual environment"
    )
    assert preparation_step.get("if") == "steps.baked.outputs.python == 'true'"
    preparation_run = preparation_step.get("run", "")
    assert "python -m venv" in preparation_run
    assert "$GITHUB_PATH" in preparation_run

    pip_step_index = next(
        index
        for index, step in enumerate(steps)
        if pip_step_identifier in step.get("name", "")
        or pip_step_identifier in step.get("run", "")
    )
    preparation_step_index = steps.index(preparation_step)
    assert preparation_step_index < pip_step_index


@pytest.mark.parametrize("job_name", ["ruff", "aislop"])
def test_ruff_install_reads_the_pin_file(job_name):
    workflow = yaml.safe_load((ROOT / ".github/workflows/lint.yml").read_text())
    steps = workflow["jobs"][job_name]["steps"]
    install = next(
        step for step in steps if "Install pinned ruff" in step.get("name", "")
    )
    assert install["shell"] == "bash"
    assert install["run"] == 'pip install "ruff==$(cat ci/ruff-version)"'
