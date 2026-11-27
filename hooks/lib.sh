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

# An inherited GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE (Claude Code started from inside a git hook,
# say) would point every `git -C "$VAULT"` below at some other repository, and the hooks would
# commit and push that one. The vault is always addressed by its path, so drop them.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES \
  GIT_COMMON_DIR GIT_NAMESPACE GIT_PREFIX

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

# absolute_path <path> — expand a leading ~ or $HOME, and print it only if it is absolute. A
# relative path would resolve against the hook's working directory — the repo the user opened —
# so a repo could hand the hooks a "vault" of its own to maintain and commit.
absolute_path() {
  local value="$1"
  # shellcheck disable=SC2088,SC2016  # literal '~' and '$HOME' patterns, expanded by hand
  case "$value" in
    '~') value="$HOME" ;;
    '~/'*) value="$HOME/${value#\~/}" ;;
    '$HOME') value="$HOME" ;;
    '$HOME/'*) value="$HOME/${value#\$HOME/}" ;;
  esac
  case "$value" in
    /*) printf '%s\n' "$value" ;;
    *) return 1 ;;
  esac
}

resolve_vault() {
  local v
  v="$(resolve_path "${DEVWB_VAULT:-${OBSIDIAN_VAULT:-}}" vault obsidian-vault "$HOME/ObsidianVault")"
  absolute_path "$v" || printf "%s\n" /dev/null/dev-workbook-vault-path-must-be-absolute
}
resolve_code_root() {
  local v
  v="$(resolve_path "${CODE_ROOT:-}" code-root code-root "$HOME/code")"
  absolute_path "$v" || printf '%s\n' "$HOME/code"
}

# ---------------------------------------------------------------- what the hooks publish

# Paths the plugin's conventions own; the session commit takes nothing else. Keep in step with
# OWNED_DIRS / OWNED_FILES in vault_spool.py.
is_owned_path() {
  case "$1" in
    Projects/*|Resources/*|Contributions/*|HouseStyles/*) return 0 ;;
    "Home.md"|"TasksArchive.md"|"WorkPlanning.md") return 0 ;;
    # Pre-2.0 names, until condense-vault renames them.
    "Tasks Archive.md"|"Work Planning.md") return 0 ;;
    *) return 1 ;;
  esac
}

# Secret-shaped basenames, never committed even inside an owned path. Matched on the lowercased
# basename: macOS file systems are case-insensitive, so `.ENV` and `KEY.PEM` are the same files.
# The list can never be complete — the vault's .gitignore is the other half of this guard.
is_secret_path() {
  local base
  base="$(printf '%s' "${1##*/}" | tr '[:upper:]' '[:lower:]')"
  case "$base" in
    .env|.env.*|.envrc|*.env) return 0 ;;
    *.pem|*.key|*.p12|*.pfx|*.keystore|*.jks|*.ppk|*.gpg|*.asc|*.kdbx|*.crt|*.der) return 0 ;;
    id_rsa*|id_dsa*|id_ecdsa*|id_ed25519*)
      case "$base" in *.pub) return 1 ;; *) return 0 ;; esac ;;
    .npmrc|.pypirc|.netrc|.pgpass|.git-credentials|.htpasswd|credentials|credentials.*) return 0 ;;
    secret|secrets|secret.*|secrets.*|*.secret|*.secrets|*-secret.*|*-secrets.*|*_secret.*|*_secrets.*) return 0 ;;
    *) return 1 ;;
  esac
}

# unpushed_range <vault> — the rev-list arguments for the commits a push would send.
unpushed_range() {
  if git -C "$1" rev-parse -q --verify '@{upstream}' >/dev/null 2>&1; then
    printf '%s\n' '@{upstream}..HEAD'
  else
    printf '%s\n' 'HEAD' '--not' '--remotes'
  fi
}

# push_blocker <vault> — print why the hooks must not push, or nothing when they may. The hooks
# push a whole branch, so they only do it when every unpushed commit is one the plugin made
# (its session commit or condense-vault's) and none of them adds a secret-shaped file. A commit
# the user made and has not pushed is theirs to publish.
push_blocker() {
  local range foreign secret path
  # shellcheck disable=SC2207  # fixed, whitespace-free words from unpushed_range
  range=($(unpushed_range "$1"))
  foreign="$(git -C "$1" log --format='%h %s' "${range[@]}" 2>/dev/null \
    | grep -cv -e '^[0-9a-f]* vault: session updates' -e '^[0-9a-f]* condense vault:')"
  if [ "${foreign:-0}" -gt 0 ]; then
    printf '%s\n' "the branch has ${foreign} unpushed commit(s) dev-workbook did not make — review and push them yourself (git -C \"$1\" log @{upstream}..HEAD)."
    return 0
  fi
  secret=""
  while IFS= read -r -d '' path; do
    [ -n "$path" ] || continue
    is_secret_path "$path" && secret="${secret:+$secret }$path"
  done < <(git -C "$1" -c core.quotepath=off log -z --no-renames --diff-filter=d --format= --name-only "${range[@]}" 2>/dev/null)
  if [ -n "$secret" ]; then
    printf '%s\n' "an unpushed commit adds file(s) that look like secrets: ${secret} — not pushing. Remove them from history before pushing."
  fi
  return 0
}

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
  # No pid yet: the owner is between mkdir and writing it, so treat it as held — unless the
  # directory is over a minute old, when its owner died in that gap and will never write one.
  if [ -z "$pid" ]; then
    [ -n "$(find "$1" -maxdepth 0 -mmin +1 2>/dev/null)" ] && return 1
    return 0
  fi
  kill -0 "$pid" 2>/dev/null
}

# take_stale_lock <lock dir> — remove a lock whose owner is dead, without racing another waiter
# doing the same. The stale lock is first renamed aside (atomic: only one waiter wins); if what
# was renamed turns out not to be the dead owner's lock — another waiter took over in between —
# it is put back.
take_stale_lock() {
  local dead aside
  dead="$(cat "$1/pid" 2>/dev/null)"
  aside="$1.stale.$$"
  mv "$1" "$aside" 2>/dev/null || return 0
  if [ "$(cat "$aside/pid" 2>/dev/null)" = "$dead" ]; then
    rm -rf "$aside"
  else
    mv "$aside" "$1" 2>/dev/null || rm -rf "$aside"
  fi
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
      take_stale_lock "$lock"
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

# net_git <seconds> <git args…> — run git, stopped after <seconds>. A push or pull over a stalled
# connection can otherwise hang for minutes: in a SessionStart hook that is a frozen session start,
# and in the detached session end it holds the end lock, so every session start meanwhile waits
# out its full lock wait. Give it output redirected to a file or /dev/null, never a pipe: a
# transport child (ssh) that outlives git would keep a pipe open. Returns git's status, or
# non-zero when stopped.
net_git() {
  local secs="$1" pid watcher rc
  shift
  git "$@" &
  pid=$!
  ( sleep "$secs" && kill "$pid" ) </dev/null >/dev/null 2>&1 &
  watcher=$!
  wait "$pid"
  rc=$?
  kill "$watcher" 2>/dev/null
  return "$rc"
}

# PUSH_TIMEOUT — how long one push may take. The callers in a hook with a deadline lower it.
# shellcheck disable=SC2034  # read by vault-push.sh, which sources this file
PUSH_TIMEOUT="${DEVWB_PUSH_TIMEOUT:-20}"
