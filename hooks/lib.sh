# shellcheck shell=bash
# Shared helpers for every dev-workbook hook: path resolution, output formats, and the warnings
# relay. Source it; it defines functions only.
# hooks/dev_workbook_paths.py is the Python twin — keep the two in step (tests check they agree).
#
# Each path resolves in the same order:
#   1. an environment variable              (DEVWB_VAULT, then the pre-3.0 OBSIDIAN_VAULT / CODE_ROOT)
#   2. ${XDG_CONFIG_HOME:-~/.config}/dev-workbook/<name>, then the pre-3.0 .../claudesidion/<name>
#   3. the legacy ~/.claude/<name> file     (obsidian-vault / code-root)
#   4. a default                             (~/ObsidianVault / ~/code)
# The config files exist because interactive profile exports do not reach hook shells. Each is
# one line; surrounding whitespace is trimmed and a leading ~ or $HOME is expanded, because a
# hand-edited "~/Vault " would otherwise resolve to a path that does not exist and silently
# disable the plugin.

# read_path_file <file> — print the file's first line, trimmed and ~-expanded; fail if empty.
read_path_file() {
  local value
  [ -f "$1" ] || return 1
  value="$(head -n1 "$1" 2>/dev/null)"
  value="${value#"${value%%[![:space:]]*}"}"   # leading whitespace
  value="${value%"${value##*[![:space:]]}"}"   # trailing whitespace
  # shellcheck disable=SC2088,SC2016  # literal '~' and '$HOME' patterns, expanded by hand
  case "$value" in
    '~') value="$HOME" ;;
    '~/'*) value="$HOME/${value#\~/}" ;;
    '$HOME') value="$HOME" ;;
    '$HOME/'*) value="$HOME/${value#\$HOME/}" ;;
  esac
  [ -n "$value" ] || return 1
  printf '%s\n' "$value"
}

# resolve_path <env value> <config name> <legacy name> <default>
resolve_path() {
  local xdg="${XDG_CONFIG_HOME:-$HOME/.config}"
  if [ -n "$1" ]; then
    printf '%s\n' "$1"
  elif read_path_file "$xdg/dev-workbook/$2"; then
    :
  elif read_path_file "$xdg/claudesidion/$2"; then
    :
  elif read_path_file "$HOME/.claude/$3"; then
    :
  else
    printf '%s\n' "$4"
  fi
}

resolve_vault() { resolve_path "${DEVWB_VAULT:-${OBSIDIAN_VAULT:-}}" vault obsidian-vault "$HOME/ObsidianVault"; }
resolve_code_root() { resolve_path "${CODE_ROOT:-}" code-root code-root "$HOME/code"; }

# ---------------------------------------------------------------- output

# emit_context <text> — session-start context for the agent, in the harness's format, chosen by
# DEVWB_FORMAT: `claude` (default) prints Claude Code's hookSpecificOutput JSON, `cursor`
# prints {"additional_context": ...}, `plain` prints the text. JSON needs jq; without it the
# hook stays silent rather than erroring.
emit_context() {
  case "${DEVWB_FORMAT:-claude}" in
    plain)
      printf '%s\n' "$1" ;;
    cursor)
      command -v jq >/dev/null 2>&1 \
        && jq -n --arg ctx "$1" '{additional_context: $ctx}' 2>/dev/null ;;
    *)
      command -v jq >/dev/null 2>&1 \
        && jq -n --arg ctx "$1" \
          '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}' 2>/dev/null ;;
  esac
  return 0
}

# can_emit — true when emit_context can produce output, so a hook can skip work it could not report.
can_emit() { [ "${DEVWB_FORMAT:-claude}" = plain ] || command -v jq >/dev/null 2>&1; }

# ---------------------------------------------------------------- warnings relay

# Session-end output is shown to no one, so a hook that has something to say at exit also
# records it here, inside the vault's .git (never committed), and the next session start
# reports it. warnings_file <vault> prints the path, or fails for a vault that is not a repo.
warnings_file() {
  local dir
  dir="$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null)" || return 1
  [ -n "$dir" ] || return 1
  printf '%s/dev-workbook-warnings\n' "$dir"
}

# ---------------------------------------------------------------- background-session spool

# apply_spool <vault> [ending session id] — merge in the notes that finished background sessions
# staged with `dev-workbook stage` (see vault_spool.py), and print one line per thing worth
# reporting. Call it under the session-end lock. Without Python it does nothing: the spool waits.
apply_spool() {
  local py script
  script="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/..}/hooks/vault_spool.py"
  [ -f "$script" ] || return 0
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      "$py" "$script" apply "$1" "${2-}" 2>/dev/null
      return 0
    fi
  done
}

# ---------------------------------------------------------------- session-end lock

# The session-end work runs detached (see session-end.sh), so it can still be committing or
# pushing when the next session starts, or when a second session ends. This lock serialises
# them. It is a directory inside the vault's .git (mkdir is atomic; never committed) holding the
# owner's PID, so a lock whose owner died is recognised as stale and taken over.
end_lock_dir() {
  local dir
  dir="$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null)" || return 1
  [ -n "$dir" ] || return 1
  printf '%s/dev-workbook-end.lock\n' "$dir"
}

# end_lock_held <lock dir> — true while a live process owns the lock.
end_lock_held() {
  local pid
  [ -d "$1" ] || return 1
  pid="$(cat "$1/pid" 2>/dev/null)"
  # No pid yet: the owner is between mkdir and writing it. Treat as held.
  [ -n "$pid" ] || return 0
  kill -0 "$pid" 2>/dev/null
}

# acquire_end_lock <vault> <seconds> — take the lock for this process, waiting up to <seconds>
# for a live owner and taking over a dead one's. Fails if it is still held at the deadline.
acquire_end_lock() {
  local lock tries
  lock="$(end_lock_dir "$1")" || return 1
  tries=$(($2 * 5))
  while :; do
    if mkdir "$lock" 2>/dev/null; then
      printf '%s\n' "$$" > "$lock/pid"
      return 0
    fi
    if ! end_lock_held "$lock"; then
      rm -rf "$lock"
      continue
    fi
    [ "$tries" -gt 0 ] || return 1
    tries=$((tries - 1))
    sleep 0.2
  done
}

release_end_lock() {
  local lock
  lock="$(end_lock_dir "$1")" || return 0
  [ "$(cat "$lock/pid" 2>/dev/null)" = "$$" ] && rm -rf "$lock"
  return 0
}

# wait_end_lock <vault> <seconds> — wait for a running session end to finish. Fails on timeout.
wait_end_lock() {
  local lock tries
  lock="$(end_lock_dir "$1")" || return 0
  tries=$(($2 * 5))
  while end_lock_held "$lock"; do
    [ "$tries" -gt 0 ] || return 1
    tries=$((tries - 1))
    sleep 0.2
  done
  return 0
}
