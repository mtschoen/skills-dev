skills-dev test report — 2026-05-29
═══════════════════════════════════════════

Status:   PASS (lint gate)
Mode:     close-the-gap (establishing the lint gate)
Git:      0320294 (lint-rollout — shellcheck fixes)

Lint:     ruff 0.15.15:   0 findings   (ruff check scripts/ tests/)
          ruff format:    0 to reformat (ruff format --check scripts/ tests/)
          shellcheck 0.11: 0 findings   (scripts/*.sh install-skills.sh tests/test-install.sh)
          aislop 0.9.4:   100/100 score, 0 issues, 2 files (npx aislop ci)
                          ci.failBelow 100 — fail-closed verified (umbrella slop
                          -> 91 -> exit 1; clean -> 100 -> exit 0; submodule slop
                          ignored). format+lint engines off (ruff owns those);
                          telemetry off.
          0 per-case suppressions
          0 documented exceptions

Scope:    Umbrella-owned code only. Each skill is its own git submodule/repo
          and owns its own lint gate, so submodule trees are excluded from the
          umbrella gate (see pyproject.toml [tool.ruff] exclude). The on-save
          PostToolUse hook still lints submodule files when edited from an
          umbrella session (fleet-wide on-save coverage); CI + the validate
          command stay scoped to scripts/ + tests/.

Tests:    47 collected, 43 pass, 4 pre-existing failures (NOT introduced here)
          The 4 failures are in tests/test_install_skills.py (install-skills.sh
          .gemini/.agents harness creation on Windows); confirmed present
          before the lint sweep by reverting it and re-running. Tracked as
          pre-existing baseline debt, surfaced here, out of scope for the
          lint rollout. Suggested follow-up: a separate task to fix
          install-skills.sh harness-dir creation (or confirm Windows-only).

Coverage: Not configured for umbrella Python — there is no coverage tool wired
          for scripts/ or tests/. This rollout established the LINT gate only.
          Adding coverage.py tracking would be a separate task.

Gate commands (tier 2 — the authoritative local check):
  ruff check scripts/ tests/
  ruff format --check scripts/ tests/
  shellcheck scripts/*.sh install-skills.sh tests/test-install.sh
  npx -y aislop@0.9.4 ci
