# shellcheck shell=bash
#
# Shared clean-room plumbing for skill audit harnesses.
#
# Source this from a skill's own harness; it is a library, not a runnable
# script. It owns the part of a headless eval that is identical for every
# skill: constructing a session that contains the skill under test and as
# little of the operator's machine as possible.
#
# Why this exists as shared code: an eval run in the operator's own
# environment measures skill-plus-environment, not the skill. Every headless
# session otherwise inherits that operator's SessionStart hooks, their whole
# installed skill set in its system prompt, their MCP servers and their memory
# files. Each of the traps handled below silently produces a plausible result
# rather than an error, which is what makes them worth centralizing - wrap
# spent three attempts and about $0.25 of wasted runs finding them.
#
# Usage:
#   . "$UMBRELLA/scripts/clean-room.sh"
#   clean_room_require_outside_home "$OUTDIR"
#   clean_room_use_config_dir "$MY_AUDIT_CONFIG_DIR"   # optional
#   clean_room_build_args clean "$REPO_ROOT"
#   claude -p "${CLEAN_ROOM_ARGS[@]}" "$(clean_room_invocation "$prompt")"
#
# clean_room_build_args sets two globals: the CLEAN_ROOM_ARGS array of CLI
# flags, and CLEAN_ROOM_NS, the namespace the skill answers to.

# A native claude.exe cannot resolve the POSIX paths git-bash deals in, so
# paths handed to it - or compared against ones it reports - go through here
# first. Off Windows there is nothing to convert and cygpath does not exist.
clean_room_canonical_path() {
	if command -v cygpath >/dev/null 2>&1; then
		cygpath -m "$1" 2>/dev/null || printf '%s' "$1"
	else
		printf '%s' "$1"
	fi
}

clean_room_under_home() {
	local path home
	path="$(clean_room_canonical_path "$1" | tr '[:upper:]' '[:lower:]')"
	home="$(clean_room_canonical_path "$HOME" | tr '[:upper:]' '[:lower:]')"
	case "$path/" in "$home"/*) return 0 ;; esac
	return 1
}

# Memory files are found by walking from the session's cwd up to $HOME, so a
# fixture anywhere under home inherits the operator's home-level CLAUDE.md and
# AGENTS.md. On Windows the default mktemp root (%TEMP%) is itself under home,
# so the default is the broken case. No config-dir choice fixes this, because
# the leak arrives through cwd discovery. Refuse rather than report a room we
# did not get.
clean_room_require_outside_home() {
	local dir="$1"
	clean_room_under_home "$dir" || return 0
	echo "error: clean-room fixtures cannot live under $HOME - memory files" >&2
	echo "       there reach the session through cwd discovery." >&2
	echo "       Re-run with a fixture root outside home." >&2
	exit 2
}

# Point the session at a scratch config directory, so eval memory lands there
# instead of in the operator's real corpus. Echoes the sessions root, since
# harnesses that read transcripts need it.
#
# The path must be host-native: git-bash hands a POSIX path straight to a
# native .exe, which cannot resolve it. The CLI does not complain - it
# silently uses an empty config and every turn dies "Not logged in".
clean_room_use_config_dir() {
	local dir
	dir="$(clean_room_canonical_path "$1")"
	export CLAUDE_CONFIG_DIR="$dir"
	printf '%s/projects' "$dir"
}

# A plugin-delivered skill is invoked as /<namespace>:<skill>. The namespace is
# the plugin directory's basename; the skill name comes from SKILL.md's
# frontmatter, falling back to that same basename when unset. The two are
# usually equal and differ exactly when a checkout is not named after its
# skill - a worktree, or a second clone.
clean_room_skill_namespace() {
	basename "$(clean_room_canonical_path "$1")"
}

clean_room_skill_name() {
	local dir name
	dir="$(clean_room_canonical_path "$1")"
	name="$(sed -n '/^---[[:space:]]*$/,/^---[[:space:]]*$/{s/^name:[[:space:]]*//p;}' \
		"$dir/SKILL.md" 2>/dev/null | head -n 1 | tr -d '"'"'"' \r')"
	printf '%s' "${name:-$(clean_room_skill_namespace "$dir")}"
}

# Rewrite a prompt's bare skill invocation into the namespaced form the clean
# room actually answers to. A bare token resolves to nothing without erroring:
# the session improvises a plausible answer from the skill's one-line
# description, which reads like a pass while testing nothing.
clean_room_invocation() {
	local prompt="$1"
	printf '%s' "${prompt//"/$CLEAN_ROOM_SKILL"/"/$CLEAN_ROOM_NS:$CLEAN_ROOM_SKILL"}"
}

# mode: "clean" (the skill alone) or "control" (the same room, no skill).
# skill_dir: the skill's repo root, required for "clean", ignored for "control".
clean_room_build_args() {
	local mode="$1" skill_dir="${2:-}"

	# --setting-sources project drops user-level settings, and with them the
	# operator's hooks and every user-installed skill. --strict-mcp-config
	# drops user-scope MCP servers.
	CLEAN_ROOM_ARGS=(--setting-sources project --strict-mcp-config)
	CLEAN_ROOM_NS=""
	CLEAN_ROOM_SKILL=""

	if [ "$mode" = "control" ]; then
		return 0
	fi
	if [ "$mode" != "clean" ]; then
		echo "error: clean_room_build_args: unknown mode '$mode'" >&2
		return 2
	fi

	local dir
	dir="$(clean_room_canonical_path "$skill_dir")"
	# --plugin-dir takes the checkout itself: a directory holding a SKILL.md
	# with no skills/ subdirectory loads as a single-skill plugin (Claude Code
	# >= 2.1.142), so there is nothing to assemble first.
	if [ ! -f "$dir/SKILL.md" ]; then
		echo "error: no SKILL.md at $dir" >&2
		return 1
	fi
	CLEAN_ROOM_NS="$(clean_room_skill_namespace "$dir")"
	CLEAN_ROOM_SKILL="$(clean_room_skill_name "$dir")"
	CLEAN_ROOM_ARGS+=(--plugin-dir "$dir")
}

# What this does NOT strip: the operator's ~/.claude/CLAUDE.md and any global
# AGENTS.md it imports still reach the session, because settings sources do not
# govern memory files. Removing those needs clean_room_use_config_dir plus a
# fixture root outside home - both, not either.
