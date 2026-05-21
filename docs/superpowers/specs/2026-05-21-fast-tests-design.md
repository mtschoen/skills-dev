# Fast-Tests — Design Spec

**Status:** Draft awaiting user review. Working scaffold per `superpowers:brainstorming`. Distilled into the implementation plan header on handoff to `superpowers:writing-plans`, then deleted.

**Predecessor:** `~/skills-dev/fast-tests/HANDOFF.md` (committed in the `fast-tests` submodule; not deleted by this spec — it remains the source-of-record briefing material). The handoff was authored from the WindowStream session (April 2026) and is JVM/Android/.NET-heavy. This spec reorients toward the present empirical context (Python / liminal) while keeping equal language coverage.

## Goal

A standalone, installable Claude Code skill that steers agents toward fast integration-test loops without compromising the integration-tests-first philosophy. The skill exists to prevent the failure mode "tests are slow → agent silently replaces integration coverage with unit mocks → product breaks while suite passes."

Project-agnostic. Per-language references for Python, JVM, .NET. Fits the existing skill stack alongside `maintaining-full-coverage` (coverage axis), `smoke-test` (outer-loop verify), and the planned `escalate-over-improvise` (hack-avoidance partner).

## Voice and thesis

Principle-driven, project-agnostic, integration-tests-first. Same register as `wrap` and `pushback`: the body holds judgment, references hold detail. The skill explicitly defends integration tests against the easy escape hatch of replacing them with unit mocks when they're slow.

**Thesis paragraph (lives in SKILL.md):**

> Integration tests are the authoritative signal — they verify the product works. If they're slow, the answer is to **speed up the setup**, not to replace them with unit-level mocks that pretend to verify behavior. The bias toward unit testing assumes unit correctness implies system correctness; in practice the interesting bugs live at integration boundaries (DPI mismatches, launcher indirection, codec queues, protocol drift). None of those show up in unit tests. This skill reinforces that bias and gives the agent techniques to make integration tests cheap enough that they ARE the fast path.

## Frontmatter description (auto-loader trigger)

> Use when the agent observes slow test runs in this session (multi-minute wall clock, repeated re-runs blocking iteration, tests dominating the inner loop) OR when adding tests likely to slow the loop down (integration tests, sleeps/timeouts, external services, fixture-heavy setup). Steers toward fast integration-test loops by speeding up SETUP — never by replacing integration tests with unit mocks that fake the verify. Project-agnostic; per-language references for Python, JVM, .NET.

## Scope

**In scope:** test-loop wall clock — both the observable "this suite takes 5 minutes" reality and the preventable "let me add a sleep(5) here" failure mode.

**Out of scope:**

- Test correctness — that's `superpowers:test-driven-development`.
- Test coverage — that's `maintaining-full-coverage`.
- Post-change verify — that's `smoke-test`.
- Hardware-bound platform code that is genuinely untestable — escalate via `escalate-over-improvise` (planned partner skill).
- CI parallelism / sharding strategy — focus is on the developer's inner loop, not the build-server outer loop. Some references will note CI implications where relevant.

## SKILL.md body structure

Target length: ~250 lines. In line with `pushback` (260) and `wrap` (230).

Sections, top to bottom:

1. **Frontmatter** — description blurb from above.
2. **Title + thesis paragraph.**
3. **When to use / When NOT to use** — concrete triggers (matches description) and scope boundary (correctness, coverage, smoke-test verify, hardware-untestable code).
4. **The decision tree (actionable core).** Profile first, then route to the right lever:
   - Setup / fixtures heavy → shared fixtures + persistent environments
   - Cold cache / first-run downloads → pre-warming
   - Sequential / low CPU usage → parallelism
   - Specific slow test (sleep, timeout, network) → reduce timeout, virtual time, mock at *real* boundary
   - Process / resource leak → process cleanup
   - Mixed wall-clock-fast and wall-clock-slow suite → tiering
5. **Principles (numbered, 6 of them):**
   1. Integration tests are the authoritative signal.
   2. Profile before optimizing.
   3. Speed up SETUP, not the test.
   4. Tier by wall clock, not unit-vs-integration.
   5. Restructure code, not the coverage gate.
   6. Mock at genuine external boundaries only — never at boundaries you own.
6. **Rationalization table** — same shape as `maintaining-full-coverage`. Defends against the agent's natural escape hatches. Sample rows:
   - "I'll mock this integration to make it fast" → mocks at boundaries you own fake the verify
   - "These tests are inherently slow" → profile first; the inherently-slow set is usually <10% of wall clock
   - "We'll skip integration tests in dev" → the 5-minute outer loop the user pays is now your problem too
   - "Slowness is just how this codebase is" → slowness is composable; each new sleep(5) compounds
   - "Add @pytest.mark.slow and skip them" → tag by wall clock, not by category; a 20ms integration test stays in the fast tier
7. **References pointer block** — links to each topic reference with a one-line description.
8. **Integration notes** — explicit one-liners per sibling skill (see §"Integration with sibling skills" below).

## References layout

```text
fast-tests/
  SKILL.md
  README.md
  HANDOFF.md                    # source briefing (kept for posterity)
  LICENSE
  evals/
    evals.json
    run.py
    grade.py
  references/
    profiling.md                # --durations, pyinstrument, gradle --profile, dotnet-trace
    parallelism.md              # pytest-xdist + dist modes, gradle parallel + JUnit, xUnit collections
    shared-fixtures.md          # scope=session, @TestInstance, Collection+IAsyncLifetime
    persistent-environments.md  # emulators, daemons, browsers, test hosts
    pre-warming.md              # pip/npm/gradle/nuget cache priming, SDK pre-install
    process-cleanup.md          # snapshot-then-kill-tree pattern, ppid tracking on Unix
    tiering.md                  # wall-clock-based tagging (NOT unit-vs-integration)
    restructure-over-exclude.md # reshape code to eliminate unreachable branches
    pitfalls.md                 # cross-cutting anti-patterns (mocking own boundaries, etc.)
  workspace/
    mock_repo/                  # deliberately-slow Python test suite the eval agent inspects
    # iteration logs (gitignored), per pushback's pattern
```

Matches `pushback/` layout: SKILL.md at repo root, `evals/` holds the harness scripts + `evals.json`, `workspace/mock_repo/` holds the canned slow-suite the eval agent reads (Read/Grep only, no edits).

Each topic reference has three sections inside: **Python / JVM / .NET**, with concrete snippets per language. Agent navigates by topic ("I need to parallelize") and finds its language section.

**Rejected alternative:** deeper `references/python/`, `references/jvm/`, `references/dotnet/` sub-directory layout (one file per topic × language = 18+ files). Topic-per-file with language sub-sections gives equal language coverage at lower surface area. Easy to refactor to the deeper layout later if topic files grow large.

**v1 fill-in priority:**

| Reference | v1 status | Source of content |
|---|---|---|
| `profiling.md` | Full | Search findings (pytest --durations, pyinstrument, importtime), JVM `--profile` + JFR, dotnet-trace |
| `parallelism.md` | Full | User's pytest-xdist input + search (distribution modes), JVM gradle parallel + JUnit 5 parallel, xUnit collections |
| `shared-fixtures.md` | Full | Search + handoff examples (Python session-scoped, xUnit Collection + IAsyncLifetime, JUnit @TestInstance + @BeforeAll) |
| `persistent-environments.md` | Full | Handoff's AVD lesson + .NET test host + browser reuse + Docker test containers |
| `process-cleanup.md` | Full | Handoff's snapshot-then-kill-tree pattern (WindowStream-validated), Unix equivalent |
| `pitfalls.md` | Full | Handoff + user's "fight the slow test, don't mock around it" + mocking-own-boundaries deep-dive |
| `pre-warming.md` | Skeleton + stub | Principle from handoff; concrete per-language steps fill in as projects surface needs |
| `tiering.md` | Skeleton + stub | Principle is firm; needs worked examples beyond the conceptual case |
| `restructure-over-exclude.md` | Skeleton + stub | Handoff has the Kotlin `while (isActive)` example; needs Python/.NET parallels |

Skeleton-stub references include a heading per language with a one-line "TODO: fill in when project surfaces a concrete example" so pointers from SKILL.md don't 404.

## Integration with sibling skills

Block in SKILL.md (~12 lines):

- **`maintaining-full-coverage`** — orthogonal axes. Speed never licenses skipping tests. *Tiering* in fast-tests means "run less often in the dev inner loop," never "omit from the suite" — the full suite still runs in CI, pre-commit, and before claiming done; coverage stays 100%. Both skills agree on the same lever from opposite directions: restructure code, don't exclude. Both reject mocking-own-boundaries (fake coverage *and* fake speed).
- **`smoke-test`** — orthogonal layers (outer-loop verify vs. inner-loop test wall clock). No overlap. Shares the "tests passing ≠ product working" thesis; cite, don't duplicate.
- **`escalate-over-improvise`** (handoff exists, not yet built) — partner skill for when no fast-tests lever fits. Reaching for `[ExcludeFromCodeCoverage]` on a slow class, hard-coding an emulator-specific shortcut, swapping a real component for a mock just to skip its setup cost — that's hack territory. Escalate, don't ship.
- **`superpowers:test-driven-development`** — upstream. Fast-tests assumes tests exist; this skill doesn't decide when to write them.
- **`superpowers:dispatching-parallel-agents`** — edge case: parallel-agent fan-outs sharing a persistent emulator/daemon need coordination (port/PID conflicts). The persistent-environments reference covers this in one paragraph.

**Explicit anti-coordination patterns to call out** (in `pitfalls.md` and a one-paragraph note in SKILL.md):

- Don't let speed pressure drive *which* tests get written — that's `maintaining-full-coverage`'s fight.
- Don't let speed pressure drive whether smoke-test runs — it's cheap regardless.
- Don't let "make this faster" silently become "make this fake-pass" — escalate the moment that temptation surfaces.

## Evals / validation

**Harness pattern:** clone `pushback/evals/` — `evals.json` + `run.py` (invokes `claude -p`) + `grade.py` (LLM-judged assertions) + `workspace/mock_repo/` with deliberately slow Python tests (no fixture scoping, no xdist, sleeps, redundant setup).

**Configurations per scenario:**

- **with_skill** — SKILL.md prepended to the prompt.
- **without_skill** — baseline.

**Variance:** n≥3 runs per (scenario × config). Per saved feedback (`feedback_no_iteration_on_n1.md`), do not iterate on SKILL.md content from n=1 results — cell-level swings may be pure noise.

**Tool restrictions:** agent gets Read/Grep/Glob only — can inspect the mock repo but cannot edit. Same as pushback. `--disable-slash-commands` so other installed skills can't interfere.

**Universal assertion (applies to every response):** `no_hallucinated_claims` — no fabricated file paths, durations, library APIs, or coverage numbers. Per saved feedback (`feedback_hallucination_check.md`).

**Scenario list (10):**

| # | Name | Bucket | Tests… |
|---|---|---|---|
| 0 | `profile-first` | Decision tree | Agent gets "tests take 5 min" → proposes profiling before jumping to a fix |
| 1 | `setup-amortization` | Lever | 30-test suite with 3s per-test setup → agent proposes `scope="session"` / Collection fixture |
| 2 | `parallelization-opportunity` | Lever | Slow sequential suite, low CPU during runs → agent recognizes parallelization as a lever (xdist for Python, gradle parallel + JUnit for JVM, xUnit collections for .NET); distribution-mode nuance is bonus, core assertion is *recognized the lever* |
| 3 | `pre-warming` | Lever | Parallel-agent fan-out is slow because each agent downloads SDK images cold → agent proposes priming the cache once |
| 4 | `dont-mock-own-boundaries` | Anti-pattern | User asks "mock the DB wrapper to speed it up" → agent pushes back, offers persistent-testcontainer / pre-warmed db state instead |
| 5 | `tiering-not-skipping` | Anti-pattern | User: "let's @pytest.mark.slow and skip them in dev" → agent clarifies tiering = run-less-often in inner loop; full suite still runs in CI / pre-commit; coverage stays 100% |
| 6 | `delete-slow-integration` | Anti-pattern | User: "unit tests cover it, drop the integration test" → agent rejects (integration is authoritative) |
| 7 | `restructure-over-exclude` | Anti-pattern | Uncovered branch from `while (isActive) { delay() }` style code → agent restructures to `while (true)` instead of adding coverage exclusion |
| 8 | `slow-test-surgery` | Lever | One specific test sleeps 30s → agent identifies the sleep, proposes virtual time or boundary mock |
| 9 | `negative-case` | False-positive guard | Suite already runs in 8s; user asks an unrelated question → agent must NOT propose fast-tests interventions unprompted |

**Liminal as a real-world signal (not a formal eval cell):** once the parallel liminal test-speed session lands findings, replay its starting state through the harness as scenario 10. That's the "did the skill actually help the agent the user wanted it for" check, separate from the canned evals.

## Implementation notes

Building this skill requires:

1. **Repo creation.** Per `skills-dev/CLAUDE.md`, every new skill needs its own repo. The submodule already exists (`fast-tests/`), already on Gitea + GitHub, currently containing only `HANDOFF.md` + `LICENSE`. The build adds `SKILL.md`, `README.md`, `evals/`, `references/` directly to that submodule.
2. **Root layout.** New skills use the root layout (SKILL.md at repo root, NOT under `skill-draft/`). Per `skills-dev/CLAUDE.md`. Installer detects layout.
3. **Build order:**
   - SKILL.md first (the spine).
   - Fully-written references next (profiling, parallelism, shared-fixtures, persistent-environments, process-cleanup, pitfalls).
   - Skeleton-stub references (pre-warming, tiering, restructure-over-exclude).
   - Evals harness (copy pushback structure, adapt scenarios + mock repo).
   - README.md (one-page overview + install pointer).
4. **Install + smoke-test:** run `./install-skills.{sh,bat} -y fast-tests` after each material edit so the installed copy at `~/.claude/skills/fast-tests/` matches dev. Per `feedback_install_after_skill_edit.md`.
5. **Submodule-pointer bump:** after the skill repo lands changes, bump the submodule pointer in `skills-dev` and push via `scripts/push-all.{sh,bat}`.
6. **Eval execution:** running the full eval grid (10 scenarios × 2 configs × n≥3) requires foreground agent calls — background subagents can't Bash per `feedback_subagent_bash.md`.

## Out-of-scope reminders

The plan-writing session must NOT expand scope without asking:

- **No CI / build-server parallelism strategy.** Inner loop only.
- **No test framework migration.** If pytest/xunit/JUnit is in use, work with it; don't propose a new framework.
- **No language-runtime upgrades.** Suggesting "upgrade to Python 3.13 for free perf" is out of scope.
- **No coverage-tool migration.** The skill works with whatever coverage tooling the repo uses.
- **No deep dive into specific platforms beyond Python / JVM / .NET in v1.** Browser-only suites (Playwright, Cypress) get one-paragraph mentions in references where naturally relevant; Go / Rust / etc. are deferred to later versions.

## File index

- This spec: `docs/superpowers/specs/2026-05-21-fast-tests-design.md`
- Source briefing: `fast-tests/HANDOFF.md` (in the `fast-tests` submodule)
- Existing skill stack: `maintaining-full-coverage/`, `smoke-test/`, `wrap/`, `pushback/` (all submodules)
- Eval reference: `pushback/evals/` (the harness pattern to clone)
- Project conventions: `skills-dev/CLAUDE.md` (root layout, submodule workflow, installer)
- User memory pointers: `feedback_no_iteration_on_n1.md`, `feedback_hallucination_check.md`, `feedback_install_after_skill_edit.md`, `feedback_subagent_bash.md` (all in `~/.claude/projects/C--Users-mtsch-skills-dev/memory/`)
