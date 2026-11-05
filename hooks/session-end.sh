#!/usr/bin/env bash
# SessionEnd hook: merge in notes background sessions spooled (vault_spool.py), refresh the indexes
# (vault-maintain.sh), then commit and push (vault-push.sh).
#
# One hook rather than two because Claude Code runs an event's hooks in parallel: as two hooks,
# the push could commit while maintenance was still rewriting frontmatter, leaving those edits
# for the next session.
#
# With --detach it returns at once and does the work in the background. Claude Code gives all
# SessionEnd hooks 1.5 seconds by default, a plugin's per-hook timeout does not raise that, and a
# push to a remote over SSH alone takes about that long — so a foreground push was routinely
# killed mid-flight ("Hook cancelled"), stranding the commit until the next session start. The
# background job runs in its own process group, detached from the hook's stdin and stdout, so
# the teardown neither waits for it nor takes it down. If it is killed anyway, nothing is lost:
# the next session start commits what is uncommitted and pushes what is unpushed.
#
# Without --detach (the `dev-workbook end` command) it runs in the foreground and prints what
# vault-push.sh reports.
#
# Fails open on every path: exit 0, whatever happens.

set -u

here="$(cd "$(dirname "$0")" && pwd)" || exit 0

if [ "${1-}" = "--detach" ]; then
  # The hook's input names the session that is ending, so its own spool is applied now rather
  # than at the next start. Read before detaching: the background job gets no stdin.
  if [ ! -t 0 ]; then
    DEVWB_SESSION_ID="$(head -c 65536 | tr -d '\n' \
      | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([A-Za-z0-9._-]*\)".*/\1/p')"
    export DEVWB_SESSION_ID
  fi
  # Job control puts the background job in a process group of its own, so a signal sent to the
  # hook's group at teardown does not reach it. nohup covers the SIGHUP of a closing terminal.
  set -m
  nohup bash "$here/session-end.sh" </dev/null >/dev/null 2>&1 &
  exit 0
fi

# shellcheck source=hooks/lib.sh
. "$here/lib.sh" 2>/dev/null || exit 0
VAULT="$(resolve_vault)"

# Serialise with a session end that is still running, e.g. a second session closed right after
# the first. Its commit has to land before this one reads the tree. On timeout, go ahead: the
# worst case is a commit that fails on git's own index lock, and the next session start retries.
locked=""
if git -C "$VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  acquire_end_lock "$VAULT" 60 && locked=1
fi

# Spooled notes go in first, so maintenance and the commit treat them like any other edit. What
# the merge has to say is printed and relayed to the next start, like vault-push.sh's warnings.
if [ -n "$locked" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    printf 'dev-workbook: %s\n' "$line"
    w="$(warnings_file "$VAULT")" && printf '%s\n' "$line" >> "$w" 2>/dev/null
  done < <(apply_spool "$VAULT" "${DEVWB_SESSION_ID:-}")
fi

bash "$here/vault-maintain.sh" </dev/null 2>/dev/null
bash "$here/vault-push.sh" </dev/null 2>/dev/null

[ -n "$locked" ] && release_end_lock "$VAULT"
exit 0
