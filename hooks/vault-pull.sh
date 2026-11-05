#!/usr/bin/env bash
# SessionStart hook: pull the vault to latest once per session (startup|resume),
# so the whole session works from the latest remote state. Paired with vault-push.sh (SessionEnd),
# which commits and pushes once at the end: the skills themselves never pull, commit, or push.
#
# Fails open on every path: if anything is missing or goes wrong, exit 0 with no output so a
# hook bug can never delay or break the session.

set -u

# Vault resolution is shared by every hook: env var, the dev-workbook config file, the legacy
# ~/.claude file, then the default. See lib.sh.
# shellcheck source=hooks/lib.sh
. "$(dirname "$0")/lib.sh" 2>/dev/null || exit 0
VAULT="$(resolve_vault)"

stranded=""

# claim_version — record this plugin's version in the vault (Projects/.dev-workbook-version) so
# that a session started before an upgrade, on this machine or another, finds a newer version
# recorded when it exits and leaves the indexes alone. Prints a notice when this session is the
# stale one. Needs Python; without it the guard is simply not armed.
claim_version() {
  local py script
  script="${CLAUDE_PLUGIN_ROOT:-$(dirname "$0")/..}/hooks/vault_maintain.py"
  [ -f "$script" ] || return 0
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      "$py" "$script" --claim "$VAULT" 2>/dev/null
      return 0
    fi
  done
}

# Need git; if absent, stay silent.
command -v git >/dev/null 2>&1 || exit 0

# Skip if the vault is not a git work tree (mirrors the skills' "skip if not a git repo"). A local
# vault still gets its version claimed: a stale session on this machine is the same hazard.
if ! git -C "$VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  [ -d "$VAULT" ] && claim_version >/dev/null
  exit 0
fi

# Heartbeat: tells the skills the sync hooks are installed and ran this session, so they leave
# git to the hooks. Without a fresh one — a harness with no hooks — the skills sync themselves.
# It lives inside .git, so it is never committed or synced to another machine.
git_dir="$(git -C "$VAULT" rev-parse --absolute-git-dir 2>/dev/null)" \
  && date +%Y-%m-%dT%H:%M:%S > "$git_dir/dev-workbook-hooks" 2>/dev/null

# --- Wait for a session end still running in the background --------------------
# session-end.sh commits and pushes detached, so a quick relaunch can get here first. Hold the
# same lock for the rest of this hook: committing leftovers or pulling under a running commit
# would collide on git's index lock. The wait is bounded below this hook's own timeout; if it
# runs out, carry on as before rather than delay the session.
locked=""
acquire_end_lock "$VAULT" 12 && locked=1

# --- Relay what the last session's exit had to say -----------------------------
# Session-end output reaches no one, so vault-push.sh records its warnings and they are reported
# here, once. Control characters are stripped: the text ends up in the agent's context.
# A session that ended under the pre-3.0 name wrote claudesidion-warnings; relay that too.
relayed=""
if wf="$(warnings_file "$VAULT")"; then
  for f in "$wf" "${wf%/*}/claudesidion-warnings"; do
    [ -s "$f" ] || continue
    relayed="${relayed:+$relayed }$(tr '\n' ' ' < "$f" | tr -d '\000-\037')"
    rm -f "$f"
  done
  [ -n "$relayed" ] && relayed="The last session's exit hook reported: $relayed"
fi

# --- Commit what a previous session left uncommitted ----------------------------
# A harness with no session-end event (or a cancelled one) leaves the session's writes
# uncommitted. Commit them now, before pulling, through the same owned-paths-only rules as the
# exit hook. Its messages are reported directly rather than relayed to the next session.
leftover=""
if [ -n "$(git -C "$VAULT" status --porcelain -- Projects Resources Contributions Home.md TasksArchive.md WorkPlanning.md 2>/dev/null)" ]; then
  before="$(git -C "$VAULT" rev-parse HEAD 2>/dev/null)"
  said="$(DEVWB_NO_RELAY=1 bash "$(dirname "$0")/vault-push.sh" </dev/null 2>/dev/null \
    | sed 's/^dev-workbook: //' | tr '\n' ' ' | tr -d '\000-\037')"
  if [ "$(git -C "$VAULT" rev-parse HEAD 2>/dev/null)" != "$before" ]; then
    leftover="Committed vault changes that were not yet committed (left by an earlier session, or made outside one)."
  fi
  leftover="${leftover}${said:+ ${said% }}"
  leftover="${leftover# }"
fi

# --- Flush stranded commits ---------------------------------------------------
# The SessionEnd push hook commits locally, then pushes over the network. Session teardown can
# cancel it in the gap between the two, leaving commits that exist only on this machine — the
# exact "user believes work is backed up when it is not" failure this plugin exists to prevent.
# SessionStart has no teardown pressure, so a flush here reliably recovers whatever the last exit
# stranded. Push before the pull below: these commits are already on the branch, so sending them
# first keeps the subsequent --ff-only honest instead of racing a remote that moved on.
if [ -n "$(git -C "$VAULT" log '@{upstream}..HEAD' --oneline 2>/dev/null)" ]; then
  n="$(git -C "$VAULT" rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo some)"
  if git -C "$VAULT" push >/dev/null 2>&1; then
    stranded="Pushed ${n} vault commit(s) stranded by a previous session's cancelled exit hook."
  else
    stranded="Vault has ${n} unpushed commit(s) from a previous session and the retry failed; they remain local-only."
  fi
fi

if git -C "$VAULT" pull --ff-only >/dev/null 2>&1; then
  short="$(git -C "$VAULT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  status="Vault pulled to latest (${short})."
else
  status="Vault pull failed (offline, no remote, or non-fast-forward); working from local state."
fi

# --- Merge in notes from background sessions that have ended ---------------------
# A background session cannot write the vault directly (see vault_spool.py), so it spools its
# notes; its own exit hook normally applies them. This catches a session whose exit hook never
# ran or ended without naming itself. After the pull, so the merge is against the latest notes;
# this session's exit commits the result.
spooled=""
if [ -n "$locked" ]; then
  spooled="$(apply_spool "$VAULT" | tr '\n' ' ' | tr -d '\000-\037')"
  spooled="${spooled% }"
fi

# After the pull, so the comparison is against the version other machines recorded.
stale="$(claim_version)"
[ -n "$locked" ] && release_end_lock "$VAULT"

emit_context "${relayed:+$relayed }${leftover:+$leftover }${stranded:+$stranded }${status}${spooled:+ $spooled}${stale:+ $stale}"

exit 0
