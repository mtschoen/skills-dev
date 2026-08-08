# NEEDS-INFO

The skill content for `external-harness-routing` is authored and committed
(commit `a1d64a1`) as a plain directory at `external-harness-routing/`, with
all fleet gates green (agentskills validate, markdownlint, validate_skills.py,
ruff, shellcheck, pytest 188 passed, aislop ci 0 findings). What remains is
the repo's documented submodule conversion, which this run cannot perform
because it forbids push/fetch and other outward actions. Blocking questions:

- The new-skill workflow (AGENTS.md "Adding a new skill", steps 2-8) requires
  creating the public GitHub repo `mtschoen/skills-external-harness-routing`,
  pushing an initial commit, and running `git submodule add
  ../skills-external-harness-routing.git external-harness-routing`. This run
  may not push or create remote repos. Should the operator run those steps
  after merging this branch (the committed directory is conversion-ready:
  move the files into the new repo, `git rm` the plain dir here, then
  `submodule add`), or should a follow-up pr-crew run with network write
  access do the conversion?
- The skill name `external-harness-routing` is inferred from the branch name
  (`agent/3608-skill-idea-external-harness-rout`). Confirm the name before
  the repo is created, since the repo name (`skills-external-harness-routing`)
  is derived from it and is hard to change later.
- Until the conversion happens, `install-skills.sh` will not pick up the new
  skill (the installer only ships submodule dirs, not plain directories), so
  the dry-run check in step 6 of the workflow was not applicable here.
