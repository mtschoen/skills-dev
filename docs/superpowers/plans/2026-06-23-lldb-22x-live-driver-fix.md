# Handoff: lldb 22.x cannot be driven by the live-session driver

Status: open. Mitigations landed; the driver-side fix is the remaining work.
Best picked up on llamabox (Arch, lldb 22.1.6, Python 3.14) where it reproduces.

## TL;DR

Running `using-a-debugger/scripts/setup-debuggers.py` on llamabox installed
lldb 22.1.6, which un-skipped the live end-to-end test `test_cli_e2e_lldb`.
That test then failed: the persistent-session driver cannot drive upstream LLVM
lldb 22.x. The driver works fine on older lldb (verified passing on lldb 9.0.0).

## What already landed (commit e4ae57c on skills-using-a-debugger)

- The lldb caveat in `README.md` and `references/tooling-setup.md` was broadened
  from "Windows LLVM lldb" to "lldb 22.x, any OS" (confirmed on Windows and
  Linux).
- `scripts/dbgsession/test_cli_e2e.py` now skips `test_cli_e2e_lldb` when the
  lldb major version is >= 22 (helper `_lldb_major`, which parses the upstream
  `lldb version N.M` string and returns None for Apple's `lldb-NNNN` scheme).
  So the suite is honest-green on lldb 22.x; the real driver bug is NOT fixed.

This handoff is the remaining driver-side work to actually drive lldb 22.x.

## Symptom and reproduction

On a host with lldb >= 22 and clang++:

```bash
# from the using-a-debugger submodule root
cd scripts/dbgsession
python -m pytest test_cli_e2e.py::test_cli_e2e_lldb -q   # remove the >=22 skip first
```

Observed: the `start` subcommand subprocess times out (15 s in the test; the
driver's own port-file wait is 10 s, `_PORT_WAIT_SECONDS` in
`scripts/dbg-session.py`). So the server child never reached "ready" - it did
not write its `port` file in time.

To watch it directly, drive the CLI by hand:

```bash
python scripts/dbg-session.py start --debugger lldb --session h -- ./hello
python scripts/dbg-session.py send  --session h "break hello.cpp:3"
python scripts/dbg-session.py stop  --session h
```

## Suspected cause and code pointers

Two candidate failure points, in order of where the timeout was observed:

1. **Server start / readiness** - `run_server_child` in
   `scripts/dbgsession/server.py` calls `backend.start()` (spawn lldb) BEFORE
   `Server.serve_forever()` writes the port file. If `start()` stalls, the port
   file never appears and the parent `start` command times out. The lldb
   `start()` is `scripts/dbgsession/backends/lldb_cli.py` `start()` - it spawns
   `lldb --no-use-colors <program>` via `open_transport(argv, "pipe")`
   (`scripts/dbgsession/transport.py`). Check whether `--no-use-colors` is still
   a valid lldb 22.x flag, and whether `open_transport` blocks reading initial
   output that lldb 22.x emits differently (prompt/banner change).

2. **The marker-sync handshake** - even if start succeeds, every command gates on
   a token. `LldbCliBackend._run_sync` / `_run_exec`
   (`scripts/dbgsession/backends/lldb_cli.py`, lines ~41-64) write the real
   command followed by `script print("@@DBGn@@")` and then `read_until` a line
   that exactly equals `@@DBGn@@`. If lldb 22.x buffers or reformats `script`
   output (e.g. does not emit the printed token as its own flushed line), the
   gate never matches and each `send` times out (`_TIMEOUT = 30.0`). This is the
   mechanism the broadened caveat describes; it is suspected but unconfirmed for
   lldb 22.x on Linux.

## Investigation plan

1. Reproduce by hand: launch `lldb --no-use-colors ./hello` in a terminal, then
   type `script print("@@X@@")` and observe exactly what (and when) lldb 22.x
   writes to stdout. Compare against lldb < 22 (e.g. a CLion-bundled lldb 9).
2. Confirm which of the two candidates fires: add temporary stderr logging in
   `run_server_child` around `backend.start()` and in `LldbCliBackend.start()`
   to see whether the port file delay is in spawn/transport-open or later.
3. If it is the marker handshake: find an lldb 22.x-stable synchronization signal
   (e.g. a settings change to force flush, a different end-of-command marker, or
   reading lldb's own prompt instead of a `script print` token).
4. If it is a flag/banner change: fix the `start()` argv and/or the initial
   transport drain for lldb 22.x.

## Acceptance criteria

- `test_cli_e2e_lldb` passes on lldb 22.x (remove or invert the `>=22` skip in
  `scripts/dbgsession/test_cli_e2e.py`), and still passes on lldb < 22.
- The live driver `start` / `break` / `run` / `local` / `stop` round-trip works
  against lldb 22.1.6 on llamabox.
- Narrow the lldb-22.x caveat in `README.md` and `references/tooling-setup.md`
  to whatever residual limitation remains (or remove it if fully fixed).

## Related context

- Driver design and the three backend families: `using-a-debugger/README.md`
  ("Support matrix") and `references/interactive-sessions.md`.
- The caveat text to update lives in `using-a-debugger/README.md`
  ("lldb caveats") and `references/tooling-setup.md` ("lldb health-check").
