skills-dev test report - 2026-07-31
═══════════════════════════════════════════

Status:   PASS (lint gate + tests)
Mode:     maintain (skill refresh and legacy remote rename cleanup)
Git:      pre-change parent 8d741e2

Lint:     ruff 0.15.16:   0 findings   (ruff check scripts/ tests/)
          ruff format:    0 to reformat (ruff format --check scripts/ tests/)
          shellcheck 0.11: 0 findings   (scripts/*.sh install-skills.sh tests/test-install.sh;
                          verified locally on LF-normalized content — the Windows
                          working tree is CRLF via autocrlf, which trips SC1017
                          noise; CI's LF checkout is the authoritative run)
          aislop 0.14.0:  100/100 score, 0 issues, 5 supported files
                          (75 files scanned; aislop ci .)
                          ci.failBelow 100; format+lint engines off (ruff owns
                          those); telemetry off.
          0 per-case suppressions
          0 documented exceptions

Validate: scripts/validate_skills.py now also enforces a portability gate —
          no tracked file in the umbrella or any skill (dev files included)
          may reference machine-local paths (user memory notes, personal repo
          paths, absolute home dirs). Deny rules + exemptions live in the
          script; running-spikes' spike-note storage is the one exemption.

Scope:    Umbrella-owned code only. Each skill is its own git submodule/repo
          and owns its own lint gate, so submodule trees are excluded from the
          umbrella gate (see pyproject.toml [tool.ruff] exclude). The on-save
          PostToolUse hook still lints submodule files when edited from an
          umbrella session (fleet-wide on-save coverage); CI + the validate
          command stay scoped to scripts/ + tests/.

Tests:    88 collected, 87 pass, 1 skipped, 0 failures
          (python3 -m pytest tests/)
          The 4 pre-existing failures recorded in the 2026-05-29 report
          (install-skills.sh gemini-harness assertions) were fixed 2026-06-10:
          the tests asserted the old .gemini/skills path and pre-created the
          wrong harness dir; the script's actual destination is
          .gemini/config/skills with a dirname-based existence check.

Coverage: Not configured for umbrella Python — there is no coverage tool wired
          for scripts/ or tests/. Lint gate only. Adding coverage.py tracking
          would be a separate task.

Gate commands (tier 2 — the authoritative local check):
  ruff check scripts/ tests/
  ruff format --check scripts/ tests/
  shellcheck scripts/*.sh install-skills.sh tests/test-install.sh
  aislop ci .
