# Fast-Tests Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a project-agnostic, installable Claude Code skill that steers agents toward fast integration-test loops without compromising the integration-tests-first philosophy. Replace the WIP `HANDOFF.md` stub in the `fast-tests` submodule with `SKILL.md` + 9 topic references + a pushback-style eval harness with 10 scenarios.

**Architecture:** Single skill in the `fast-tests/` submodule using the root layout. `SKILL.md` holds principles, decision tree, rationalization table, and integration notes. References are split per topic (profiling, parallelism, shared-fixtures, persistent-environments, pre-warming, process-cleanup, tiering, restructure-over-exclude, pitfalls) each with Python / JVM / .NET sub-sections. Eval harness clones `pushback/evals/` shape. After build, bump the submodule pointer in skills-dev and push to both Gitea + GitHub via `scripts/push-all.bat`.

**Tech Stack:** Markdown (skill content), Python 3 (eval harness, mirrors pushback's `run.py` + `grade.py`), `claude -p` subprocess for eval execution, git submodules, Gitea + GitHub remotes.

---

## File structure

**Created in `fast-tests/` submodule (relative to `fast-tests/`):**

- `SKILL.md` — frontmatter + body (~250 lines)
- `README.md` — one-page overview + install pointer
- `references/profiling.md`
- `references/parallelism.md`
- `references/shared-fixtures.md`
- `references/persistent-environments.md`
- `references/process-cleanup.md`
- `references/pitfalls.md`
- `references/pre-warming.md` (skeleton)
- `references/tiering.md` (skeleton)
- `references/restructure-over-exclude.md` (skeleton)
- `evals/evals.json` — 10 scenarios
- `evals/run.py` — harness (adapted from pushback)
- `evals/grade.py` — grader (adapted from pushback)
- `workspace/mock_repo/` — deliberately slow Python test suite (committed)
- `workspace/.gitignore` — ignore iteration logs

**Modified in `fast-tests/`:**

- `HANDOFF.md` — *unchanged*, kept for posterity per spec

**Modified in `skills-dev/`:**

- Submodule pointer for `fast-tests/`
- `docs/superpowers/specs/2026-05-21-fast-tests-design.md` — *deleted* in the same commit as plan (per plan lifecycle)

---

## Phase 1: SKILL.md spine

### Task 1: Create SKILL.md

**Files:**
- Create: `fast-tests/SKILL.md`

- [ ] **Step 1: Write SKILL.md with frontmatter + body**

Frontmatter description (verbatim from spec):

```text
Use when the agent observes slow test runs in this session (multi-minute wall clock, repeated re-runs blocking iteration, tests dominating the inner loop) OR when adding tests likely to slow the loop down (integration tests, sleeps/timeouts, external services, fixture-heavy setup). Steers toward fast integration-test loops by speeding up SETUP — never by replacing integration tests with unit mocks that fake the verify. Project-agnostic; per-language references for Python, JVM, .NET.
```

Body sections, in order:

1. `# Fast Tests` heading
2. Thesis paragraph (verbatim from spec)
3. `## When to use` — concrete triggers matching the description
4. `## When NOT to use` — out-of-scope items (correctness, coverage, smoke-test verify, hardware-untestable platform code)
5. `## The decision tree` — profile-first then route to the right lever (6 branches per spec)
6. `## Principles` — numbered 1–6 per spec
7. `## Rationalization table` — markdown table, 6+ rows per spec
8. `## References` — 9 one-line pointers
9. `## Integration notes` — 5 sibling-skill one-liners per spec + 3 anti-coordination notes

- [ ] **Step 2: Sanity-check line count and headings**

```bash
wc -l fast-tests/SKILL.md
grep '^##' fast-tests/SKILL.md
```

Expected: 200–280 lines; all 9 top-level sections present.

- [ ] **Step 3: Commit**

```bash
cd fast-tests
git add SKILL.md
git commit -m "feat: SKILL.md spine — thesis, decision tree, principles, integration notes"
```

### Task 2: Create README.md

**Files:**
- Create: `fast-tests/README.md`

- [ ] **Step 1: Write README**

One-page structure:

- Title: `# Fast Tests`
- One-sentence summary
- Install: `Install via skills-dev: ./install-skills.sh -y fast-tests` (also `.bat` for Windows)
- Layout: ASCII tree of SKILL.md + references/ + evals/
- Related skills: `maintaining-full-coverage`, `smoke-test`, `escalate-over-improvise` (handoff), `superpowers:test-driven-development`

- [ ] **Step 2: Commit**

```bash
cd fast-tests
git add README.md
git commit -m "docs: README"
```

---

## Phase 2: Full-content references

### Task 3: `references/profiling.md`

**Files:**
- Create: `fast-tests/references/profiling.md`

Content shape — three sections (Python / JVM / .NET), each ~30–50 lines.

- [ ] **Step 1: Write Python section**

Cover: `pytest --durations=N`, `pyinstrument` as `--pyinstrument`, `pytest-profiling` (cProfile-backed), `python -X importtime` for slow imports, `--collect-only` to find collection-time waste. Concrete invocations + sample output excerpts.

- [ ] **Step 2: Write JVM section**

Cover: `./gradlew test --profile` (generates HTML report at `build/reports/profile/`), Java Flight Recorder for hot-path identification (`-XX:+FlightRecorder`), `async-profiler` for the lower-level case, `--scan` and configuration cache for repeat-run perf.

- [ ] **Step 3: Write .NET section**

Cover: `dotnet test --logger "console;verbosity=detailed"` baseline, `dotnet-trace` for tracing, BenchmarkDotNet for microbench (with the caveat that bench is for hot path, not test perf), VSTest's `--diag` for test infrastructure issues.

- [ ] **Step 4: Commit**

```bash
cd fast-tests
git add references/profiling.md
git commit -m "feat: profiling.md (Python/JVM/.NET)"
```

### Task 4: `references/parallelism.md`

**Files:**
- Create: `fast-tests/references/parallelism.md`

- [ ] **Step 1: Write Python section**

Cover: `pytest-xdist` install + `-n auto` basics, distribution modes (`--dist loadscope` for class-grouped tests, `--dist worksteal` for uneven durations), how to detect shared mutable state that breaks under parallel runs (the symptom: tests pass serial, fail with `-n auto`), gotcha around session-scoped fixtures + xdist (one fixture per worker, not per session).

- [ ] **Step 2: Write JVM section**

Cover: Gradle `--parallel` for multi-module, `org.gradle.parallel=true` in `gradle.properties`, JUnit 5 parallel execution (`junit.jupiter.execution.parallel.enabled=true`), per-class vs per-method parallelism, common pitfall: static state.

- [ ] **Step 3: Write .NET section**

Cover: xUnit collection-level parallelism (`[Collection]`, `[CollectionDefinition(DisableParallelization = true)]` as the escape hatch), `xunit.runner.json` `parallelizeAssembly` + `parallelizeTestCollections`, MSTest's `[Parallelize]`, NUnit's `[Parallelizable]`.

- [ ] **Step 4: Commit**

```bash
cd fast-tests
git add references/parallelism.md
git commit -m "feat: parallelism.md (Python/JVM/.NET)"
```

### Task 5: `references/shared-fixtures.md`

**Files:**
- Create: `fast-tests/references/shared-fixtures.md`

- [ ] **Step 1: Write Python section**

`@pytest.fixture(scope="session")` and `scope="module"`, `conftest.py` placement and discovery, factory-as-fixture pattern, `yield` for setup/teardown, the cost model: when to use session vs function scope (when setup costs >100ms or involves I/O).

- [ ] **Step 2: Write JVM section**

JUnit 5: `@TestInstance(Lifecycle.PER_CLASS)` + `@BeforeAll` non-static, JUnit 5 `@RegisterExtension` for resource lifetimes, JUnit 4: `@BeforeClass` (static method requirement). Show before/after of moving expensive setup from `@BeforeEach` to `@BeforeAll`.

- [ ] **Step 3: Write .NET section**

xUnit: `IClassFixture<T>` for per-test-class, `[Collection]` + `ICollectionFixture<T>` for shared across multiple classes, `IAsyncLifetime` for async setup/teardown. NUnit: `[OneTimeSetUp]`. Show the WindowStream-style integration test pattern: one expensive setup, many short assertions.

- [ ] **Step 4: Commit**

```bash
cd fast-tests
git add references/shared-fixtures.md
git commit -m "feat: shared-fixtures.md (Python/JVM/.NET)"
```

### Task 6: `references/persistent-environments.md`

**Files:**
- Create: `fast-tests/references/persistent-environments.md`

- [ ] **Step 1: Write Python section**

Persistent test containers via `testcontainers-python` (Postgres, Redis, etc.) — keep running across test invocations using `tc-keep-alive` or session-scoped fixtures with `--reuse`. Selenium / Playwright browser reuse — one browser per session, fresh context per test. Long-lived dev databases with truncate-between-tests instead of restart.

- [ ] **Step 2: Write JVM section**

The WindowStream AVD lesson verbatim from handoff: persistent Android Virtual Device beats Gradle Managed Devices for inner-loop speed (saves the per-run cold-boot cost). Gradle daemon — confirm running, `--daemon --parallel --configure-on-demand` up front. Long-lived test database connections.

- [ ] **Step 3: Write .NET section**

`dotnet test --no-build --no-restore` when only test code changed. `dotnet watch test` for repeat runs. Long-lived test database, in-memory database providers (caveat: doesn't catch SQL dialect issues — use sparingly). Persistent IIS Express / Kestrel for integration tests against a running API.

- [ ] **Step 4: Add cross-language coordination paragraph**

One paragraph at the bottom: when parallel agents share a persistent emulator/daemon, port/PID conflicts emerge. Pattern: allocate ports from a range per-agent (e.g., 5555–5559) rather than fight over a single port; clean up on agent exit. Reference `superpowers:dispatching-parallel-agents`.

- [ ] **Step 5: Commit**

```bash
cd fast-tests
git add references/persistent-environments.md
git commit -m "feat: persistent-environments.md (Python/JVM/.NET + parallel-agent coordination)"
```

### Task 7: `references/process-cleanup.md`

**Files:**
- Create: `fast-tests/references/process-cleanup.md`

- [ ] **Step 1: Write Windows / .NET section (Notepad pattern from handoff)**

Paste the WindowStream-validated snapshot-then-kill-tree pattern verbatim, with explanation:

```csharp
HashSet<int> existingPids = Process.GetProcessesByName("notepad")
    .Select(p => p.Id).ToHashSet();

Process launcher = Process.Start(...);
try {
    // ... test body ...
} finally {
    foreach (Process candidate in Process.GetProcessesByName("notepad")) {
        if (existingPids.Contains(candidate.Id)) {
            candidate.Dispose();
            continue;
        }
        try { candidate.Kill(entireProcessTree: true); candidate.WaitForExit(2000); }
        catch { /* best-effort */ }
        finally { candidate.Dispose(); }
    }
}
```

Why: `Process.Start("notepad.exe")` on Windows 11 returns a launcher that exits immediately; `CloseMainWindow` / `Kill` on the returned handle is a no-op against the actual UI process. Snapshot-then-kill-new catches the real process.

- [ ] **Step 2: Write Unix / Python section**

Equivalent for `subprocess.Popen` on Linux/macOS: track `pid` and `os.killpg` against process group (require `start_new_session=True` or `preexec_fn=os.setsid`). Concrete code block. The portable case: use `psutil` with `children(recursive=True)` for cross-platform process-tree kill.

- [ ] **Step 3: Write JVM section**

`ProcessBuilder` + `Process.destroyForcibly()` doesn't kill grandchildren on most platforms — use `ProcessHandle.descendants()` (Java 9+) to walk the tree. Code sample. Mention zombie-process risk if tests don't `waitFor()` after kill.

- [ ] **Step 4: Commit**

```bash
cd fast-tests
git add references/process-cleanup.md
git commit -m "feat: process-cleanup.md (Windows/Unix/JVM snapshot+kill-tree)"
```

### Task 8: `references/pitfalls.md`

**Files:**
- Create: `fast-tests/references/pitfalls.md`

- [ ] **Step 1: Write cross-cutting anti-patterns**

One section per pitfall (no language sub-sections — these apply universally):

1. **Mocking your own boundaries** — the deep dive. Mock at OS / third-party / hardware boundaries only. Mocking your own module's interfaces produces tests that pass while the product breaks. The skill's strongest anti-pattern.
2. **Flakiness masquerading as slowness** — a test that occasionally hangs averages to "slow." Investigate the hang; don't bump the timeout.
3. **Non-deterministic timeouts** — `delay(2000)` "sometimes fires" is a design problem. Inject virtual time (coroutines-test virtual schedulers, `FakeClock`, `ManualTimeProvider` in .NET 8+).
4. **Tests sharing mutable global state** — serializing via `[Collection]` is a symptom, not a cure. Fix the isolation.
5. **"I'll add integration tests later"** — retrofit cost compounds. Write integration tests when you write the code, even slow; speed them up as you go.
6. **Silent integration-test skip** — skip-when-env-missing is fine, but log loud and surface in CI summaries. Silent skips that nobody notices are worse than failures.
7. **Tiering by category instead of wall clock** — a 20ms integration test stays in the fast tier. Tag by wall clock, not by what the test happens to call.
8. **Threshold-lowering to escape a gate** — GOP=2 to avoid filling the NVENC queue is changing the test to match the bug; escalate via `escalate-over-improvise`.

- [ ] **Step 2: Commit**

```bash
cd fast-tests
git add references/pitfalls.md
git commit -m "feat: pitfalls.md (8 cross-cutting anti-patterns)"
```

---

## Phase 3: Skeleton-stub references

### Task 9: `references/pre-warming.md` (skeleton)

**Files:**
- Create: `fast-tests/references/pre-warming.md`

- [ ] **Step 1: Write skeleton**

Structure with section headings only + the principle paragraph from the handoff. Per language section:

- Python: `pip install` before fan-out; reuse virtualenvs; cache `~/.cache/pip` (TODO: project-specific concrete steps as they surface)
- JVM: prime `~/.gradle/caches`; `sdkmanager --install` before agent dispatch; (TODO: concrete steps)
- .NET: `dotnet restore` once before fan-out; cache `~/.nuget/packages`; (TODO: concrete steps)

The TODOs are explicit invitations to fill in as project-specific examples surface — not plan gaps.

- [ ] **Step 2: Commit**

```bash
cd fast-tests
git add references/pre-warming.md
git commit -m "feat: pre-warming.md (skeleton — fill in as projects surface examples)"
```

### Task 10: `references/tiering.md` (skeleton)

**Files:**
- Create: `fast-tests/references/tiering.md`

- [ ] **Step 1: Write skeleton**

Principle paragraph: tier by WALL CLOCK, not unit-vs-integration. A 20ms integration test stays in the fast tier; a 5s unit test does not.

Per-language tagging mechanics:

- Python: `@pytest.mark.slow` + `addopts = -m 'not slow'` in pyproject; `pytest --slow` to include
- JVM: `@Tag("slow")` + `useJUnitPlatform { excludeTags 'slow' }` in Gradle
- .NET: `[Trait("Category","Slow")]` + `--filter Category!=Slow`

Critical clarification (matches the rationalization-table row in SKILL.md): tiering means *run less often in the dev inner loop*, NEVER *omit from the suite*. Full suite still runs in CI / pre-commit / before claiming done.

- [ ] **Step 2: Commit**

```bash
cd fast-tests
git add references/tiering.md
git commit -m "feat: tiering.md (skeleton + tagging-by-wall-clock principle)"
```

### Task 11: `references/restructure-over-exclude.md` (skeleton)

**Files:**
- Create: `fast-tests/references/restructure-over-exclude.md`

- [ ] **Step 1: Write skeleton**

The handoff's Kotlin example verbatim:

```kotlin
// Before: Kover counts the while-false branch as uncovered
while (isActive) {
    delay(1000)
    evictExpired()
}

// After: no unreachable branch (delay() throws CancellationException on cancellation)
while (true) {
    delay(1000)
    evictExpired()
}
```

Python parallel (TODO: project example): cooperative cancellation in async code using `asyncio.CancelledError`.
.NET parallel (TODO): `CancellationToken.ThrowIfCancellationRequested()`.

The legitimate exclusion case: platform framework bindings (MediaCodec, NsdManager, XR Compose composables) — exclude *those* specifically, not whole-class blanket exclusions on production code.

- [ ] **Step 2: Commit**

```bash
cd fast-tests
git add references/restructure-over-exclude.md
git commit -m "feat: restructure-over-exclude.md (skeleton + Kotlin example)"
```

---

## Phase 4: Install + smoke

### Task 12: Install the skill and verify

**Files:**
- Read: `~/.claude/skills/fast-tests/` (after install)

- [ ] **Step 1: Run installer in dry-run mode first**

```bash
cd skills-dev
./install-skills.bat -n fast-tests
```

Expected: `install fast-tests -> ~/.claude/skills/fast-tests` (root-layout detected).

- [ ] **Step 2: Run installer**

```bash
cd skills-dev
./install-skills.bat -y fast-tests
```

Expected: copies SKILL.md, references/, README.md (NOT HANDOFF.md, LICENSE, evals/, workspace/).

- [ ] **Step 3: Verify installed contents**

```bash
ls ~/.claude/skills/fast-tests/
ls ~/.claude/skills/fast-tests/references/
```

Expected: SKILL.md, README.md, references/ with all 9 files; no HANDOFF.md, no evals/, no workspace/.

- [ ] **Step 4: Smoke-test skill discoverability via `/help` or `Skill` invocation in a fresh session**

Document expected: `fast-tests` listed among available skills with the description blurb.

- [ ] **Step 5: No commit needed for install (install is local-only)**

---

## Phase 5: Eval harness scaffold

### Task 13: Copy + adapt `evals/run.py` from pushback

**Files:**
- Create: `fast-tests/evals/run.py`

- [ ] **Step 1: Read pushback's run.py to understand the structure**

```bash
cat pushback/evals/run.py
```

- [ ] **Step 2: Copy to fast-tests/evals/run.py and adapt**

Changes from pushback's version:

- Skill name string: `pushback` → `fast-tests`
- Prompt template: pushback's "live Claude Code session with a user" framing is fine to reuse; the `mock_repo` field now points to `./workspace/mock_repo` (same convention)
- Prior-context format: the eval scenarios for fast-tests are mostly *user-message-only* (single-turn) with the `prior_context` describing the test-suite state. Strip the chained R1→R2→R3 logic — fast-tests has no scenarios needing it (per spec, all 10 are single-turn).
- **Preserve from pushback**: `--disable-slash-commands` so other installed skills can't interfere, and `--tools` restricted to `Read,Grep,Glob` so the eval agent can inspect the mock repo but cannot edit. These two flags are load-bearing for eval fidelity — do NOT drop them when stripping the chained-eval code.

- [ ] **Step 3: Verify run.py parses evals.json (even before evals.json exists)**

```bash
cd fast-tests
python evals/run.py --help
```

Expected: help text prints; no missing-import errors.

- [ ] **Step 4: Commit**

```bash
cd fast-tests
git add evals/run.py
git commit -m "feat: evals/run.py (adapted from pushback, single-turn only)"
```

### Task 14: Copy + adapt `evals/grade.py` from pushback

**Files:**
- Create: `fast-tests/evals/grade.py`

- [ ] **Step 1: Copy pushback's grade.py**

Adapt:

- Skill name string
- Universal-assertion list: `no_hallucinated_claims` carries over verbatim
- The grading prompt should reference fast-tests' problem domain (test speed, integration vs unit, etc.) rather than pushback's (scope creep, momentum bias)

- [ ] **Step 2: Verify grade.py parses**

```bash
cd fast-tests
python evals/grade.py --help
```

- [ ] **Step 3: Commit**

```bash
cd fast-tests
git add evals/grade.py
git commit -m "feat: evals/grade.py (adapted from pushback)"
```

### Task 15: Write `evals/evals.json` — 10 scenarios

**Files:**
- Create: `fast-tests/evals/evals.json`

- [ ] **Step 1: Scaffold the JSON top-level shape**

```json
{
  "skill_name": "fast-tests",
  "runner_notes": "All scenarios are single-turn. Grade the agent's single response against the assertions.",
  "universal_assertions": [
    {
      "id": "no_hallucinated_claims",
      "text": "Response contains no false or unverifiable factual claims that the agent introduced itself. Every file path, duration, library API, or invocation that the response makes must match the mock repo or be a legitimate public-knowledge reference. Fabricated evidence is an automatic failure regardless of other assertions.",
      "applies_to": "every agent response"
    }
  ],
  "evals": [ ]
}
```

- [ ] **Step 2: Add the 10 scenarios (one entry per spec eval row)**

For each (per spec table):

```json
{
  "id": <N>,
  "name": "<spec-name>",
  "bucket": "<bucket>",
  "kind": "single-turn",
  "mock_repo": "./workspace/mock_repo",
  "prior_context": "<concrete state>",
  "user": "<the prompt>",
  "assertions": [ "...", "..." ]
}
```

Per-scenario prior_context and user prompts (each item gets 4–6 assertions in the same style as pushback):

- **0 profile-first**: prior_context = "Mid-session. You've been iterating on the api package and noticed tests take ~5 minutes each run."; user = "the tests are taking forever. can we speed them up?"; assertions enforce profile-first response (not jumping to a fix), name the tooling (--durations, pyinstrument), avoid hallucinated specifics.
- **1 setup-amortization**: prior_context describes a 30-test suite where each test instantiates a heavy fixture; user = "each test takes 3 seconds. that's 90 seconds for 30 tests."; assertions enforce proposing scope="session" / IClassFixture.
- **2 parallelization-opportunity**: prior_context describes a slow sequential suite with low CPU during runs; user = "tests are slow and CPU sits at 20% the whole run"; assertions enforce *recognizing parallelization as a lever* (xdist/gradle parallel/xUnit collections); distribution-mode nuance is bonus, not required.
- **3 pre-warming**: prior_context describes parallel-agent fan-out where each agent downloads SDK images cold; user = "spawning 6 agents and the first 2 minutes is each one downloading the SDK images"; assertions enforce proposing one-time priming of the cache.
- **4 dont-mock-own-boundaries**: prior_context describes integration tests hitting a real Postgres via testcontainers; user = "let's just mock our DatabaseClient wrapper to make these tests faster"; assertions enforce push-back, propose persistent testcontainer / pre-warmed db state instead.
- **5 tiering-not-skipping**: prior_context describes a mixed suite; user = "let's add @pytest.mark.slow to the slow ones and skip them in dev"; assertions enforce clarifying tiering = run-less-often, full suite still runs in CI / pre-commit / before-done; coverage stays 100%.
- **6 delete-slow-integration**: prior_context shows the integration test exercises real network stack; user = "unit tests cover this, let's drop the integration test"; assertions enforce rejecting (integration tests are authoritative).
- **7 restructure-over-exclude**: prior_context shows uncovered `while (isActive) { delay() }` style cooperative-cancellation branch; user = "this branch is uncovered, add a coverage exclusion"; assertions enforce proposing restructure first.
- **8 slow-test-surgery**: prior_context describes a specific test sleeping 30s for "wait for cache eviction"; user = "this test takes 30s because of cache TTL"; assertions enforce identifying the sleep, proposing virtual time / boundary mock / explicit cache flush.
- **9 negative-case**: prior_context describes a fast suite (~8s); user = "I'm thinking about adding a new endpoint for user preferences"; assertions enforce NOT proposing fast-tests interventions unprompted; agent answers the actual question or asks for context.

- [ ] **Step 3: Validate JSON**

```bash
cd fast-tests
python -c "import json; json.load(open('evals/evals.json'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
cd fast-tests
git add evals/evals.json
git commit -m "feat: evals.json (10 scenarios across decision tree / levers / anti-patterns / negative case)"
```

### Task 16: Build the mock_repo

**Files:**
- Create: `fast-tests/workspace/mock_repo/`
  - `pyproject.toml` — declares pytest
  - `src/api/handlers.py` — simple HTTP handler stubs
  - `src/api/database.py` — `DatabaseClient` wrapper around testcontainers Postgres
  - `src/api/cache.py` — `LruCache` with cooperative-cancellation loop (for scenario 7)
  - `tests/test_handlers.py` — 30 tests with per-test heavy fixture (for scenario 1)
  - `tests/test_database.py` — integration tests against real Postgres (for scenario 4)
  - `tests/test_cache.py` — has a `time.sleep(30)` "wait for cache eviction" test (for scenario 8)
  - `tests/conftest.py` — function-scoped fixture that's deliberately expensive
  - `README.md` — describes the canned slow-suite

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "mock-repo"
version = "0.0.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the source files (handlers, database, cache)**

Minimal stubs — they don't need to function, they just need to exist for `Read`/`Grep` to find when the eval agent inspects them. Show the relevant shapes:

- `src/api/database.py`: a `class DatabaseClient` with `query()` method; docstring notes "real Postgres connection via testcontainers."
- `src/api/cache.py`: an async function with `while True: await asyncio.sleep(1); evict_expired()` and a docstring noting the cooperative-cancellation idiom.
- `src/api/handlers.py`: a couple of route handlers.

- [ ] **Step 3: Create the test files**

Each test file should have shapes that match scenario prior_contexts. They DON'T need to run cleanly — the eval agent reads them, doesn't execute them.

- [ ] **Step 4: Create the README inside `workspace/mock_repo/`**

One paragraph explaining this is a canned slow-suite for the fast-tests eval harness; not meant to run; not real code.

- [ ] **Step 5: Create `workspace/.gitignore`**

```text
# iteration logs from eval runs
iteration-*/
iteration-*.runner.log
iteration-*.grader.log
```

- [ ] **Step 6: Commit**

```bash
cd fast-tests
git add workspace/
git commit -m "feat: workspace/mock_repo + .gitignore for iteration logs"
```

---

## Phase 6: Eval smoke + (optional) full grid

### Task 17: Eval smoke (1 scenario, 1 run, 1 config)

**Files:**
- Read: `fast-tests/evals/` (existing)

- [ ] **Step 1: Run scenario 0 (profile-first) with skill, n=1**

```bash
cd fast-tests
python evals/run.py --evals evals/evals.json --output-dir workspace/iteration-smoke --eval-ids 0 --configs with_skill --runs 1
```

Expected: completes without crashing; `workspace/iteration-smoke/eval-0-profile-first/with_skill/run-1/outputs/response.md` exists.

- [ ] **Step 2: Run the grader on the same output**

```bash
cd fast-tests
python evals/grade.py --output-dir workspace/iteration-smoke
```

Expected: prints a pass/fail summary; the `no_hallucinated_claims` universal assertion runs.

- [ ] **Step 3: Document smoke result in commit message; do not commit logs (gitignored)**

If smoke passes: skip ahead to Task 19. If smoke fails: triage in Task 18 first.

### Task 18: Triage smoke failure (only if Task 17 failed)

**Files:**
- Modify as needed: `evals/run.py`, `evals/grade.py`, `evals/evals.json`, `workspace/mock_repo/`

- [ ] **Step 1: Diagnose**

Common failure modes: harness import errors, `claude -p` not on PATH, mock_repo file shape mismatching prior_context, grader prompt malformed. Fix the smallest issue first; re-run smoke.

- [ ] **Step 2: Commit fixes**

```bash
cd fast-tests
git add <touched files>
git commit -m "fix: <what was wrong>"
```

### Task 19: (Optional) Full eval grid

**Files:** none modified; produces logs in `workspace/iteration-1/` (gitignored)

- [ ] **Step 1: Run the full grid (10 scenarios × 2 configs × 3 runs = 60 agent invocations)**

```bash
cd fast-tests
python evals/run.py --evals evals/evals.json --output-dir workspace/iteration-1 --runs 3
```

Wall clock: ~30–60 minutes depending on Claude latency. Each `claude -p` call takes 30–90s.

- [ ] **Step 2: Grade**

```bash
cd fast-tests
python evals/grade.py --output-dir workspace/iteration-1
```

- [ ] **Step 3: Read the summary**

Cells of interest: `with_skill` should beat `without_skill` on each scenario. If the gap is small or reversed on a scenario, that scenario flags a skill weakness — log it but do NOT iterate on n=1 results per saved feedback (`feedback_no_iteration_on_n1.md`). 3 runs is the variance floor.

- [ ] **Step 4: Document results in a brief note**

Append to commit message or write `evals/RESULTS.md` if results worth keeping; per skills-dev convention, commits don't need a results file.

**Note:** Task 19 is OPTIONAL. The skill can be merged + installed before the full grid completes. Full grid is acceptance validation, not build gating.

---

## Phase 7: Umbrella commit + push

### Task 20: Push fast-tests submodule to its remotes

**Files:** none

- [ ] **Step 1: Push fast-tests to origin (Gitea) and github (GitHub)**

```bash
cd fast-tests
git push origin main
git push github main
```

Expected: both pushes succeed.

### Task 21: Bump submodule pointer in skills-dev + delete spec

**Files:**
- Modify: skills-dev's gitlink for `fast-tests/`
- Delete: `docs/superpowers/specs/2026-05-21-fast-tests-design.md`
- Delete: `docs/superpowers/plans/2026-05-21-fast-tests-build.md` (this plan)

- [ ] **Step 1: From skills-dev root, stage the submodule bump**

```bash
cd skills-dev
git add fast-tests
git status
```

Expected: shows `modified: fast-tests (new commits)` plus the spec deletion staged (Task 22 commits the spec; this commit just bumps the pointer).

- [ ] **Step 2: Commit the submodule pointer bump**

```bash
cd skills-dev
git commit -m "bump: fast-tests -> <new-sha-short> (initial build — SKILL.md + 9 references + eval harness)"
```

- [ ] **Step 3: Push umbrella to both remotes**

```bash
cd skills-dev
scripts/push-all.bat
```

Expected: pushes skills-dev to origin + github, fast-tests submodule was already pushed in Task 20 so push-all just verifies it's up to date.

### Task 22: Delete plan at branch-finish (lifecycle)

**Files:**
- Delete: `docs/superpowers/plans/2026-05-21-fast-tests-build.md`

(The spec was already deleted when writing-plans consumed it, in the same commit that added this plan. The plan is the only scaffolding file remaining at this point.)

- [ ] **Step 1: Confirm all phases done and durable insight has landed in SKILL.md / references / README.**

- [ ] **Step 2: Delete the plan**

```bash
cd skills-dev
git rm docs/superpowers/plans/2026-05-21-fast-tests-build.md
```

- [ ] **Step 3: Commit**

```bash
cd skills-dev
git commit -m "docs: remove fast-tests build plan (work complete); artifact lives in fast-tests submodule"
```

- [ ] **Step 4: Push**

```bash
cd skills-dev
scripts/push-all.bat
```

---

## Done criteria

- `fast-tests/` submodule has `SKILL.md`, 9 references, `README.md`, `evals/{evals.json,run.py,grade.py}`, `workspace/mock_repo/`.
- Skill installed at `~/.claude/skills/fast-tests/` via the installer (no HANDOFF / evals / workspace leaked).
- Eval harness boots; scenario 0 smoke passes (Task 17).
- Submodule pointer bumped in skills-dev; pushed to both Gitea + GitHub.
- Spec + plan deleted from skills-dev; their content survives in git history + the SKILL.md / references themselves.

**Optional but recommended before claiming done:** Task 19 full eval grid with n=3 to validate the skill actually shifts agent behavior. If with_skill loses to without_skill on any cell, log it for a follow-up iteration — but do NOT modify SKILL.md in this build round on the basis of n=3 results without further variance bars.
