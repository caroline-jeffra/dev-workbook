#!/usr/bin/env bash
# Regression tests for hooks/session-end.sh (SessionEnd) and the lock it shares with
# vault-pull.sh.
#
# Claude Code gives SessionEnd hooks 1.5 seconds by default and a plugin's own timeout does not
# raise it, so a foreground push over SSH was routinely cancelled. The hook now detaches: these
# cases check that it returns at once, that the background job still lands the push — even when
# the hook's process group is killed, as at teardown — and that maintenance runs before the commit
# rather than racing it.

. "$(dirname "$0")/lib.sh"
unset XDG_STATE_HOME   # the spool must land under the isolated HOME

printf '\033[1msession-end.sh\033[0m\n'

now() { python3 -c 'import time; print(time.time())'; }
elapsed_lt() { python3 -c 'import sys; sys.exit(0 if float(sys.argv[2]) - float(sys.argv[1]) < float(sys.argv[3]) else 1)' "$@"; }

# slow_remote <vault> <seconds> — make every push to the vault's remote take that long.
slow_remote() {
  local r
  r="$(git -C "$1" remote get-url origin)"
  printf '#!/bin/sh\nsleep %s\n' "$2" > "$r/hooks/pre-receive"
  chmod +x "$r/hooks/pre-receive"
}

# remote_head <vault> — the commit the remote's main points at.
remote_head() { git --git-dir="$(git -C "$1" remote get-url origin)" rev-parse main 2>/dev/null; }

# wait_pushed <vault> <old remote head> — poll until the remote moves and the lock is free.
wait_pushed() {
  local i lock
  lock="$(git -C "$1" rev-parse --absolute-git-dir)/dev-workbook-end.lock"
  for ((i = 0; i < 100; i++)); do
    if [ "$(remote_head "$1")" != "$2" ] && [ ! -d "$lock" ]; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

detach_env() { env HOME="$TEST_TMP/home.$$" DEVWB_VAULT="$1" "${@:2}"; }
mkdir -p "$TEST_TMP/home.$$"

# ---------------------------------------------------------------------------
section 'Fail-open on missing preconditions'
# ---------------------------------------------------------------------------

run_hook_no_vault session-end.sh
assert_eq 0 "$HOOK_RC" 'no vault configured: exit 0'
assert_empty "$HOOK_OUT" 'no vault configured: silent'

run_hook session-end.sh "$TEST_TMP/does-not-exist"
assert_eq 0 "$HOOK_RC" 'vault path absent: exit 0'
assert_empty "$HOOK_OUT" 'vault path absent: silent'

v="$(build_vault end-plain --no-git)"
run_hook session-end.sh "$v"
assert_eq 0 "$HOOK_RC" 'vault not a git repo: exit 0'

# ---------------------------------------------------------------------------
section 'Foreground: maintenance runs before the commit, not beside it'
# ---------------------------------------------------------------------------

v="$(build_vault end-fg)"
mkdir -p "$v/Projects/Alpha/Notes"
printf '{"project": "alpha", "topics": {}}\n' > "$v/Projects/Alpha/.vault-config.json"
printf -- '---\ntype: note\nstatus: reference\n---\n\n# A note\n' > "$v/Projects/Alpha/Notes/ANote.md"
run_hook session-end.sh "$v"
assert_eq 0 "$HOOK_RC" 'foreground: exit 0'
assert_eq "" "$(gitq "$v" status --porcelain)" 'the regenerated indexes are in the session commit'
assert_contains "$(tracked "$v")" 'Projects/Alpha/TopicIndex.md' 'the index is committed'
assert_eq "$(gitq "$v" rev-parse HEAD)" "$(remote_head "$v")" 'foreground: pushed'
assert_file_absent "$(gitq "$v" rev-parse --absolute-git-dir)/dev-workbook-end.lock" 'the lock is released'

# ---------------------------------------------------------------------------
section '--detach: returns at once, the push still lands'
# ---------------------------------------------------------------------------

v="$(build_vault end-detach)"
slow_remote "$v" 3
printf 'written this session\n' >> "$v/Projects/Note.md"
old="$(remote_head "$v")"
t0="$(now)"
detach_env "$v" bash "$HOOKS/session-end.sh" --detach </dev/null >/dev/null 2>&1
t1="$(now)"
if elapsed_lt "$t0" "$t1" 1; then ok 'returns well inside the 1.5s budget'; else nope 'returns well inside the 1.5s budget' "took $t0 → $t1"; fi
if wait_pushed "$v" "$old"; then ok 'the background job pushes'; else nope 'the background job pushes'; fi
assert_eq "" "$(gitq "$v" status --porcelain -- Projects)" 'the session is committed'

# The hook's stdout must not be held open by the background job, or Claude Code waits on it.
v="$(build_vault end-pipe)"
slow_remote "$v" 3
printf 'written this session\n' >> "$v/Projects/Note.md"
old="$(remote_head "$v")"
t0="$(now)"
out="$(detach_env "$v" bash "$HOOKS/session-end.sh" --detach </dev/null 2>&1)"
t1="$(now)"
if elapsed_lt "$t0" "$t1" 1; then ok 'a captured stdout is released at once'; else nope 'a captured stdout is released at once'; fi
assert_empty "$out" '--detach prints nothing'
wait_pushed "$v" "$old" >/dev/null

# Teardown signals the hook's process group. The job runs in its own and must survive it.
v="$(build_vault end-killpg)"
slow_remote "$v" 2
printf 'written this session\n' >> "$v/Projects/Note.md"
old="$(remote_head "$v")"
detach_env "$v" python3 -c '
import os, signal, subprocess, sys
os.setpgrp()
subprocess.run(["bash", sys.argv[1], "--detach"], stdin=subprocess.DEVNULL,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
os.killpg(0, signal.SIGTERM)
' "$HOOKS/session-end.sh"
if wait_pushed "$v" "$old"; then ok 'the push survives SIGTERM to the hook process group'; else nope 'the push survives SIGTERM to the hook process group'; fi

# A push failure in the background has no stdout to go to; it reaches the next session start.
v="$(build_vault end-relay)"
git -C "$v" remote set-url origin "$TEST_TMP/no-such-remote.git"
printf 'written this session\n' >> "$v/Projects/Note.md"
detach_env "$v" bash "$HOOKS/session-end.sh" --detach </dev/null >/dev/null 2>&1
wf="$(gitq "$v" rev-parse --absolute-git-dir)/dev-workbook-warnings"
for ((i = 0; i < 50; i++)); do [ -s "$wf" ] && break; sleep 0.2; done
assert_contains "$(cat "$wf" 2>/dev/null)" 'push failed' 'a failed background push is relayed to the next start'

# ---------------------------------------------------------------------------
section 'The session-end lock'
# ---------------------------------------------------------------------------

# A live session end holds the lock: the next start waits for it instead of colliding.
v="$(build_vault lock-live)"
lock="$(gitq "$v" rev-parse --absolute-git-dir)/dev-workbook-end.lock"
# Started from a subshell so it is reparented and reaped on exit: a zombie still answers kill -0.
holder="$(sleep 1 >/dev/null 2>&1 & echo $!)"
mkdir "$lock" && printf '%s\n' "$holder" > "$lock/pid"
t0="$(now)"
run_hook vault-pull.sh "$v"
t1="$(now)"
if elapsed_lt "$t0" "$t1" 0.7; then nope 'session start waits for a running session end'; else ok 'session start waits for a running session end'; fi
assert_contains "$HOOK_OUT" 'pulled to latest' 'and then pulls'
assert_file_absent "$lock" 'the dead holder'"'"'s lock is cleared'

# A lock left by a process that no longer exists is taken over, not waited on.
v="$(build_vault lock-stale)"
lock="$(gitq "$v" rev-parse --absolute-git-dir)/dev-workbook-end.lock"
sh -c 'exit 0' &
dead=$!
wait "$dead"
mkdir "$lock" && printf '%s\n' "$dead" > "$lock/pid"
printf 'written this session\n' >> "$v/Projects/Note.md"
t0="$(now)"
run_hook session-end.sh "$v"
t1="$(now)"
if elapsed_lt "$t0" "$t1" 5; then ok 'a stale lock is not waited on'; else nope 'a stale lock is not waited on'; fi
assert_eq "" "$(gitq "$v" status --porcelain -- Projects)" 'a stale lock does not block the commit'
assert_file_absent "$lock" 'the stale lock is released afterwards'

# ---------------------------------------------------------------------------
section 'Background-session spool'
# ---------------------------------------------------------------------------

# stage_note <vault> <session> <pid> <path> <text> — what a background session does: stage a note
# with the dev-workbook command, then write the staged copy.
stage_note() {
  local work
  work="$(detach_env "$1" CLAUDE_CODE_SESSION_ID="$2" CLAUDE_PID="$3" \
    python3 "$HOOKS/../bin/dev-workbook" stage "$4" 2>/dev/null)"
  [ -n "$work" ] && printf '%s' "$5" > "$work"
}

# The ending session names itself on stdin; its spool goes into its own exit commit, even though
# its process (here, this shell) is still alive when the hook runs.
v="$(build_vault end-spool)"
stage_note "$v" bg-session-1 "$$" Projects/Alpha/Notes/FromBackground.md $'# From background\n'
old="$(remote_head "$v")"
printf '{"session_id":"bg-session-1","hook_event_name":"SessionEnd"}' \
  | detach_env "$v" bash "$HOOKS/session-end.sh" --detach >/dev/null 2>&1
if wait_pushed "$v" "$old"; then ok 'the spool lands in the exit push'; else nope 'the spool lands in the exit push'; fi
assert_contains "$(tracked "$v")" 'Projects/Alpha/Notes/FromBackground.md' 'the staged note is committed'
assert_file_absent "$TEST_TMP/home.$$/.local/state/dev-workbook/spool/bg-session-1" 'the applied spool is removed'
wf="$(gitq "$v" rev-parse --absolute-git-dir)/dev-workbook-warnings"
assert_contains "$(cat "$wf" 2>/dev/null)" 'applied 1 note(s) from background session' 'the next start is told'

# A session whose exit never applied its spool is caught by the next start, once its process is gone.
v="$(build_vault start-spool)"
sh -c 'exit 0' &
gone=$!
wait "$gone"
stage_note "$v" bg-session-2 "$gone" Projects/Alpha/Notes/Orphan.md $'# Orphan\n'
stage_note "$v" bg-session-3 "$$" Projects/Alpha/Notes/StillRunning.md $'# Running\n'
run_hook vault-pull.sh "$v"
assert_file_exists "$v/Projects/Alpha/Notes/Orphan.md" 'session start applies an ended session'"'"'s spool'
assert_contains "$HOOK_OUT" 'applied 1 note(s) from background session' 'and says so'
assert_file_absent "$v/Projects/Alpha/Notes/StillRunning.md" 'but not a running session'"'"'s'

finish
