---
name: check-memory
description: Use when about to act on a topic the notes corpus may already cover, or when the user asks what memory exists about something - searches the shared notes corpus for relevant facts, with an optional per-project narrowing flag. Triggers include "check memory", "do we have a note on", "what do we know about", and any moment you are about to hand-roll something that smells previously-solved. Requires the `replica` CLI to be installed and pointed at the notes corpus.
---

# Check memory

The notes corpus is a shared, flat directory of one-fact-per-file markdown
notes, managed by the `replica` CLI (the schoen-lab `replica` package, part of
[schoen-lab](https://github.com/mtschoen/schoen-lab)). `replica memory recall`
ranks the corpus against a query and returns the matching notes' names and
descriptions.

## Setup

Confirm the CLI is installed before doing anything else:

```bash
command -v replica >/dev/null || { echo "replica not found - install the replica CLI before proceeding" >&2; exit 1; }
```

If `replica` is missing, tell the user and stop - do not guess at the corpus
contents from memory of past sessions.

## Searching

Search the whole corpus:

```bash
replica memory recall "<topic>"
```

This is unscoped by default - it ranks every note in the corpus, not just
ones related to the current project. There is no automatic project detection
from the working directory today.

To narrow the search to notes explicitly tagged as relevant to one project,
pass its slug:

```bash
replica memory recall "<topic>" --project <slug>
```

`<slug>` is the project's tracked identifier (e.g. `schoen-lab`; check
project-tracker if one is installed and the slug is unclear).

**Important caveat:** `--project` only returns notes that carry explicit
project-affinity frontmatter (`applies_to` or `projects`), and that tagging
has not been backfilled across the existing corpus yet - most notes are
currently untagged and so are invisible to `--project`, by design (it fails
closed rather than guessing). A `--project` search returning nothing is
**not** evidence the corpus lacks a relevant note - re-run the unscoped
search before concluding there's nothing to find.

## Reporting

Report which notes matched and what they say. If nothing matched (in either
mode), say so plainly - a silent miss is what this skill exists to prevent.
