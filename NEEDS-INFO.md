# NEEDS-INFO

The explicit-model routing table is fixed in this iteration. The required
submodule conversion remains blocked by two constraints imposed on this run:

- A read-only `gh repo view` confirms that
  `mtschoen/skills-external-harness-routing` does not exist. The documented
  new-skill workflow requires creating that public repository and pushing the
  skill's initial commit before adding the relative-URL submodule. This run
  explicitly forbids push and fetch, so it cannot create a cloneable submodule
  remote. Either pre-create and populate the repository, or authorize a run
  that may perform the initial push.
- A correct conversion must add an `external-harness-routing` entry to
  `.gitmodules`, but `.gitmodules` is absent from this iteration's allowed file
  scope. The prompt directs the agent to write `NEEDS-INFO.md` instead of
  expanding scope. Include `.gitmodules` in the next run's allowed files.

Creating only a local gitlink would make the installer dry-run pass here while
leaving recursive CI checkout unable to clone the skill. The plain directory
is therefore left unchanged until the remote and file-scope blockers are
resolved.
