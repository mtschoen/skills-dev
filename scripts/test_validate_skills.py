#!/usr/bin/env python3
"""Tests for validate_skills.

Fleet-logic tests inject a fake runner and need no external tools. Integration
tests invoke the real `agentskills` binary and are skipped if it isn't on PATH.

Runs under pytest, or standalone: python scripts/test_validate_skills.py
(no third-party dependency).
"""

import runpy
import shutil
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_skills as validator


def _gitmodules(paths):
    return "".join(
        f'[submodule "{p}"]\n\tpath = {p}\n\turl = ../skills-{p}.git\n' for p in paths
    )


def _good_skill(name):
    return f'---\nname: {name}\ndescription: "A valid one-line description."\n---\n\n# Title\n'


def _make_repo(skills):
    """skills: dict name -> SKILL.md text | None (empty dir) | dict (files, no SKILL.md)."""
    root = Path(tempfile.mkdtemp())
    (root / ".gitmodules").write_text(_gitmodules(list(skills)), encoding="utf-8")
    for name, content in skills.items():
        d = root / name
        if content is None:
            d.mkdir(parents=True, exist_ok=True)
        elif isinstance(content, dict):
            d.mkdir(parents=True, exist_ok=True)
            for filename, body in content.items():
                (d / filename).write_text(body, encoding="utf-8")
        else:
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(content, encoding="utf-8")
    return root


def _pass_runner(skill_dir):
    return (0, f"Valid skill: {skill_dir}")


def _fail_runner(skill_dir):
    return (1, f"Validation failed for {skill_dir}:\n - some rule violated")


# --- parse_submodule_paths ---


def test_parse_submodule_paths_reads_every_path():
    assert validator.parse_submodule_paths(_gitmodules(["foo", "bar-baz"])) == [
        "foo",
        "bar-baz",
    ]


def test_parse_submodule_paths_empty_returns_empty_list():
    assert validator.parse_submodule_paths("") == []


# --- validate_skill fleet logic (injected runner, no external tool) ---


def test_good_skill_passes():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    assert validator.validate_skill(repo, "alpha", runner=_pass_runner) == []


def test_invalid_skill_surfaces_runner_output():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    errors = validator.validate_skill(repo, "alpha", runner=_fail_runner)
    assert errors, "a non-zero runner exit must surface as errors"
    assert all(e.startswith("alpha:") for e in errors), errors
    assert any("some rule violated" in e for e in errors), errors


def test_empty_submodule_dir_is_an_error():
    repo = _make_repo({"alpha": None})
    errors = validator.validate_skill(repo, "alpha", runner=_pass_runner)
    assert errors and any("check" in e.lower() for e in errors), errors


def test_wip_submodule_with_content_but_no_skill_md_is_skipped():
    repo = _make_repo({"alpha": {"HANDOFF.md": "wip notes\n", "LICENSE": "x\n"}})
    assert validator.validate_skill(repo, "alpha", runner=_pass_runner) == []


# --- validate_repo / evaluate ---


def test_validate_repo_counts_validated_skills():
    repo = _make_repo({"alpha": _good_skill("alpha"), "beta": _good_skill("beta")})
    errors, validated, skipped = validator.validate_repo(repo, runner=_pass_runner)
    assert errors == [] and validated == 2 and skipped == []


def test_validate_repo_reports_skipped_wip():
    repo = _make_repo({"alpha": _good_skill("alpha"), "wip": {"HANDOFF.md": "n\n"}})
    errors, validated, skipped = validator.validate_repo(repo, runner=_pass_runner)
    assert errors == [] and validated == 1 and skipped == ["wip"]


def test_evaluate_clean_repo_exits_zero():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    code, _lines = validator.evaluate(repo, runner=_pass_runner)
    assert code == 0


def test_evaluate_invalid_repo_exits_one():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    code, _lines = validator.evaluate(repo, runner=_fail_runner)
    assert code == 1


def test_evaluate_broken_checkout_empty_dirs_exits_one():
    code, _lines = validator.evaluate(
        _make_repo({"alpha": None, "beta": None}), runner=_pass_runner
    )
    assert code == 1


def test_evaluate_no_submodules_refuses_vacuous_pass():
    repo = Path(tempfile.mkdtemp())
    (repo / ".gitmodules").write_text("", encoding="utf-8")
    code, lines = validator.evaluate(repo, runner=_pass_runner)
    assert code == 2, (
        "an empty submodule set must not pass - that hides a broken checkout"
    )
    assert any("vacuous" in line.lower() for line in lines)


# --- has_content ---


def test_has_content_false_for_missing_dir():
    missing = Path(tempfile.mkdtemp()) / "not-there"
    assert not validator.has_content(missing)


# --- run_agentskills (real subprocess, stubbed PATH lookup) ---


def test_run_agentskills_raises_when_binary_missing():
    original_shutil = validator.shutil
    validator.shutil = types.SimpleNamespace(which=lambda _name: None)
    raised = False
    try:
        validator.run_agentskills(Path(tempfile.mkdtemp()))
    except RuntimeError:
        raised = True
    finally:
        validator.shutil = original_shutil
    assert raised, "a missing agentskills binary must fail loudly"


def test_run_agentskills_invokes_the_resolved_binary():
    # sys.executable stands in for the resolved binary: python exits non-zero
    # on the bogus "validate" script argument, exercising the subprocess path.
    original_shutil = validator.shutil
    validator.shutil = types.SimpleNamespace(which=lambda _name: sys.executable)
    try:
        code, output = validator.run_agentskills(Path(tempfile.mkdtemp()))
    finally:
        validator.shutil = original_shutil
    assert code != 0
    assert output


# --- check_description_brackets ---


def test_check_description_brackets_ignores_missing_description():
    repo = _make_repo({"alpha": "---\nname: alpha\n---\n\n# Title\n"})
    skill_md = validator.find_skill_md(repo / "alpha")
    assert validator.check_description_brackets("alpha", skill_md) == []


def test_check_description_brackets_flags_angle_brackets():
    skill = '---\nname: alpha\ndescription: "Uses <task> placeholders."\n---\n\n# T\n'
    repo = _make_repo({"alpha": skill})
    skill_md = validator.find_skill_md(repo / "alpha")
    errors = validator.check_description_brackets("alpha", skill_md)
    assert len(errors) == 1
    assert "angle brackets" in errors[0]


# --- check_frontmatter_xml_wellformedness ---


def test_xml_wellformedness_skips_dir_without_skill_md():
    skill_dir = Path(tempfile.mkdtemp())
    assert validator.check_frontmatter_xml_wellformedness(skill_dir, "alpha") == []


# --- validate_skill / validate_repo edge branches ---


def test_validate_skill_runner_failure_without_output_uses_fallback_message():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    errors = validator.validate_skill(repo, "alpha", runner=lambda _dir: (1, "  \n"))
    assert errors == ["alpha: skills-ref reported invalid (exit 1)"]


def test_validate_repo_without_gitmodules_is_an_error():
    errors, validated, skipped = validator.validate_repo(
        Path(tempfile.mkdtemp()), runner=_pass_runner
    )
    assert validated == 0 and skipped == []
    assert len(errors) == 1 and ".gitmodules" in errors[0]


# --- main ---


def test_main_prints_lines_and_exits_with_evaluate_code():
    original_evaluate = validator.evaluate
    validator.evaluate = lambda _root: (0, ["OK: all 1 skills valid"])
    exit_code = None
    try:
        validator.main()
    except SystemExit as exit_:
        exit_code = exit_.code
    finally:
        validator.evaluate = original_evaluate
    assert exit_code == 0


def test_script_entry_point_reports_a_missing_validator():
    original_which = shutil.which
    shutil.which = lambda _name: None
    try:
        try:
            runpy.run_path(str(Path(validator.__file__)), run_name="__main__")
        except RuntimeError as error:
            assert "agentskills" in str(error)
        else:
            raise AssertionError("entry point did not require agentskills")
    finally:
        shutil.which = original_which


# --- integration: the real agentskills binary (skipped if not installed) ---

_AGENTSKILLS = shutil.which("agentskills")


def test_integration_real_good_skill():
    if _AGENTSKILLS is None:
        print("SKIP test_integration_real_good_skill (agentskills not on PATH)")
        return
    repo = _make_repo({"alpha": _good_skill("alpha")})
    assert validator.validate_skill(repo, "alpha") == []


def test_integration_real_bad_skill_name_mismatch():
    if _AGENTSKILLS is None:
        print(
            "SKIP test_integration_real_bad_skill_name_mismatch (agentskills not on PATH)"
        )
        return
    repo = _make_repo({"alpha": _good_skill("not-alpha")})
    errors = validator.validate_skill(repo, "alpha")
    assert errors, "agentskills must reject a skill whose name != parent dir"


def _run_all():
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures.append((name, f"AssertionError: {exc}"))
            print(f"FAIL {name}: {exc}")
        except Exception as exc:
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
