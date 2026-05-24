#!/usr/bin/env python3
"""Tests for validate_skill_frontmatter.

Runs under pytest, or standalone: `python scripts/test_validate_skill_frontmatter.py`
(only dependency is PyYAML, same as the validator itself).
"""
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_skill_frontmatter as validator


def _gitmodules(paths):
    blocks = [
        f'[submodule "{path}"]\n\tpath = {path}\n\turl = ../skills-{path}.git\n'
        for path in paths
    ]
    return "".join(blocks)


def _good_skill(name):
    return f'---\nname: {name}\ndescription: "A valid one-line description."\n---\n\n# Title\n'


def _make_repo(skills, layout="root"):
    """Build a fake repo. skills: dict name -> one of:
        - SKILL.md content string  -> writes that SKILL.md
        - None                     -> empty dir (simulates a failed/missing checkout)
        - {"file": content, ...}   -> writes those files, no SKILL.md (a WIP submodule)
    """
    root = Path(tempfile.mkdtemp())
    (root / ".gitmodules").write_text(_gitmodules(list(skills)), encoding="utf-8")
    for name, content in skills.items():
        skill_dir = root / name
        if content is None:
            skill_dir.mkdir(parents=True, exist_ok=True)
        elif isinstance(content, dict):
            skill_dir.mkdir(parents=True, exist_ok=True)
            for filename, body in content.items():
                (skill_dir / filename).write_text(body, encoding="utf-8")
        else:
            target = skill_dir / ("skill-draft" if layout == "draft" else "") / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return root


# --- parse_submodule_paths ---

def test_parse_submodule_paths_reads_every_path():
    assert validator.parse_submodule_paths(_gitmodules(["foo", "bar-baz"])) == ["foo", "bar-baz"]


def test_parse_submodule_paths_empty_returns_empty_list():
    assert validator.parse_submodule_paths("") == []


# --- extract_frontmatter ---

def test_extract_frontmatter_returns_yaml_block():
    text = "---\nname: x\ndescription: hi\n---\n# Body\n"
    block = validator.extract_frontmatter(text)
    assert yaml.safe_load(block) == {"name": "x", "description": "hi"}


def test_extract_frontmatter_missing_delimiters_returns_none():
    assert validator.extract_frontmatter("# no frontmatter here\n") is None


def test_extract_frontmatter_handles_crlf():
    block = validator.extract_frontmatter("---\r\nname: x\r\ndescription: hi\r\n---\r\n")
    assert yaml.safe_load(block) == {"name": "x", "description": "hi"}


# --- validate_skill: the parsing failures it must catch ---

def test_good_skill_root_layout_has_no_errors():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    assert validator.validate_skill(repo, "alpha") == []


def test_good_skill_draft_layout_has_no_errors():
    repo = _make_repo({"alpha": _good_skill("alpha")}, layout="draft")
    assert validator.validate_skill(repo, "alpha") == []


def test_apostrophe_in_single_quoted_scalar_is_caught():
    # The regression: description: 'Use when you don't want it' — the inner
    # apostrophe terminates the single-quoted scalar and breaks YAML parsing.
    content = "---\nname: alpha\ndescription: 'Use when you don't want it to break'\n---\n# T\n"
    errors = validator.validate_skill(_make_repo({"alpha": content}), "alpha")
    assert errors, "expected a parse error for the apostrophe-in-single-quote bug"
    assert any("yaml" in e.lower() or "parse" in e.lower() for e in errors), errors


def test_flattened_block_scalar_is_caught():
    # A `>-` block indicator flattened onto one physical line is invalid YAML.
    content = "---\nname: alpha\ndescription: >- all on one line\n---\n# T\n"
    errors = validator.validate_skill(_make_repo({"alpha": content}), "alpha")
    assert errors, "expected a parse error for a flattened block scalar"


def test_missing_description_is_caught():
    content = "---\nname: alpha\n---\n# T\n"
    errors = validator.validate_skill(_make_repo({"alpha": content}), "alpha")
    assert any("description" in e for e in errors), errors


def test_empty_description_is_caught():
    content = '---\nname: alpha\ndescription: "   "\n---\n# T\n'
    errors = validator.validate_skill(_make_repo({"alpha": content}), "alpha")
    assert any("description" in e for e in errors), errors


def test_name_mismatch_is_caught():
    content = _good_skill("not-alpha")
    errors = validator.validate_skill(_make_repo({"alpha": content}), "alpha")
    assert any("name" in e for e in errors), errors


def test_missing_frontmatter_delimiters_is_caught():
    errors = validator.validate_skill(_make_repo({"alpha": "# no frontmatter\n"}), "alpha")
    assert any("frontmatter" in e.lower() for e in errors), errors


# --- validate_skill: checked-out-but-no-SKILL.md vs empty dir ---

def test_empty_submodule_dir_is_an_error():
    # An empty dir means the (recursive) checkout produced nothing — a broken
    # checkout must fail loudly, never pass vacuously.
    errors = validator.validate_skill(_make_repo({"alpha": None}), "alpha")
    assert errors, "an empty submodule dir must be flagged"
    assert any("check" in e.lower() for e in errors), errors


def test_wip_submodule_with_content_but_no_skill_md_is_skipped():
    # A real submodule that just isn't an authored skill yet (e.g. only a
    # HANDOFF.md). install-skills.sh skips these; the validator must not error.
    repo = _make_repo({"alpha": {"HANDOFF.md": "wip notes\n", "LICENSE": "x\n"}})
    assert validator.validate_skill(repo, "alpha") == []


# --- validate_repo / evaluate ---

def test_validate_repo_counts_validated_skills():
    repo = _make_repo({"alpha": _good_skill("alpha"), "beta": _good_skill("beta")})
    errors, validated, skipped = validator.validate_repo(repo)
    assert errors == []
    assert validated == 2
    assert skipped == []


def test_validate_repo_reports_skipped_wip_submodules():
    repo = _make_repo({
        "alpha": _good_skill("alpha"),
        "wip": {"HANDOFF.md": "notes\n"},
    })
    errors, validated, skipped = validator.validate_repo(repo)
    assert errors == []
    assert validated == 1
    assert skipped == ["wip"]


def test_evaluate_clean_repo_exits_zero():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    code, _lines = validator.evaluate(repo)
    assert code == 0


def test_evaluate_broken_repo_exits_one():
    bad = "---\nname: alpha\ndescription: 'don't'\n---\n"
    code, _lines = validator.evaluate(_make_repo({"alpha": bad}))
    assert code == 1


def test_evaluate_broken_checkout_empty_dirs_exits_one():
    code, _lines = validator.evaluate(_make_repo({"alpha": None, "beta": None}))
    assert code == 1


def test_evaluate_no_submodules_refuses_vacuous_pass():
    repo = Path(tempfile.mkdtemp())
    (repo / ".gitmodules").write_text("", encoding="utf-8")
    code, lines = validator.evaluate(repo)
    assert code == 2, "an empty submodule set must not pass — that hides a broken checkout"
    assert any("vacuous" in line.lower() for line in lines)


def _run_all():
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures.append((name, f"AssertionError: {exc}"))
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any error as a failure
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
