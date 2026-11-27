#!/usr/bin/env bash
# Session-end step, run by session-end.sh: commit and push any pending vault changes once, at the
# end of the session. This is the counterpart to vault-pull.sh (SessionStart): the vault is pulled
# once at session start, written freely during the session, and flushed to the remote once here —
# the skills themselves never commit or push.
#
# Fails open on every path: if anything is missing or goes wrong, exit 0 with no output so a hook
# bug can never break the user's session teardown.

set -u

# Vault resolution is shared by every hook: env var, the dev-workbook config file, the legacy
# ~/.claude file, then the default. See lib.sh.
# shellcheck source=hooks/lib.sh
. "$(dirname "$0")/lib.sh" 2>/dev/null || exit 0
VAULT="$(resolve_vault)"

command -v git >/dev/null 2>&1 || exit 0

# Skip if the vault is not a git work tree (mirrors the skills' "skip if not a git repo").
git -C "$VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# --- Guards ------------------------------------------------------------------
# These are NOT fail-open cases. Fail-open covers a missing dependency (no git, no vault) —
# there, silence is correct. Here the vault is in a state where committing would destroy the
# user's in-progress work, so the hook declines and says why. Reporting is the whole point:
# a silent decline is indistinguishable from a silent commit.

# say <message> — one line to stdout, prefixed so it is attributable to this hook, and the same
# line in the warnings relay: session-end output reaches no one, so the next start reports it.
say() {
  local w
  printf 'dev-workbook: %s\n' "$1"
  [ -n "${DEVWB_NO_RELAY:-}" ] && return 0
  w="$(warnings_file "$VAULT")" && printf '%s\n' "$1" >> "$w" 2>/dev/null
  return 0
}

# An operation is in progress if git is holding any of these state files. Checked by
# `rev-parse --git-path` so this is correct inside a linked worktree or a submodule, where
# the state lives outside a literal .git directory.
in_progress=""
for state in MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD REVERT_HEAD; do
  p="$(git -C "$VAULT" rev-parse --git-path "$state" 2>/dev/null)" || continue
  [ -n "$p" ] || continue
  case "$p" in
    /*) ;;                     # already absolute
    *) p="$VAULT/$p" ;;        # --git-path may return a repo-relative path
  esac
  if [ -e "$p" ]; then
    case "$state" in
      MERGE_HEAD)                     in_progress="a merge" ;;
      rebase-merge|rebase-apply)      in_progress="a rebase" ;;
      CHERRY_PICK_HEAD)               in_progress="a cherry-pick" ;;
      REVERT_HEAD)                    in_progress="a revert" ;;
    esac
    break
  fi
done

if [ -n "$in_progress" ]; then
  say "vault has $in_progress in progress — not committing. Finish or abort it, then the next session will flush."
  exit 0
fi

# Unmerged paths, belt-and-braces. A conflicted merge is caught above by MERGE_HEAD, but a
# conflict can also be left behind after the state file is gone (e.g. a partly-resolved
# `git checkout --merge`), and committing one writes conflict markers into a note.
if [ -n "$(git -C "$VAULT" ls-files -u 2>/dev/null)" ]; then
  say "vault has unresolved conflicts — not committing. Resolve them, then the next session will flush."
  exit 0
fi

# Detached HEAD: a commit here is reachable from no branch, so the next checkout orphans it
# and gc eventually deletes it. The header says "never branch", so the only safe move is not
# to commit at all.
if ! git -C "$VAULT" symbolic-ref -q HEAD >/dev/null 2>&1; then
  say "vault is on a detached HEAD — not committing, since the commit would not be on any branch. Check out a branch to flush."
  exit 0
fi

# --- Work detection ----------------------------------------------------------

# Anything to do? Staged, unstaged, or untracked changes all count.
if [ -z "$(git -C "$VAULT" status --porcelain 2>/dev/null)" ]; then
  # Nothing new locally, but an earlier push may have failed — try to flush any unpushed commits.
  if [ -n "$(git -C "$VAULT" log '@{upstream}..HEAD' --oneline 2>/dev/null)" ]; then
    if ! retry_err="$(git -C "$VAULT" push 2>&1)"; then
      say "vault has unpushed commits from an earlier session and the retry failed: ${retry_err##*$'\n'}"
    fi
  fi
  exit 0
fi

# --- Selecting what to commit ------------------------------------------------
# Never `git add -A`. The vault is a directory on the user's disk, and anything sitting in it at
# session end is not necessarily something the plugin wrote or that the user wants published —
# a stray .env, a key, a scratch file. Two filters, both conservative:
#
#   1. Only paths the plugin's own conventions own (see is_owned_path). Anything else is
#      reported, not committed, so an unexpected file is surfaced rather than silently published.
#   2. Never anything matching a secret-shaped name, even inside an owned path. This list can
#      never be complete, which is why the vault also ships a .gitignore — but a partial guard
#      that catches the common cases beats none.
#
# core.quotepath=off is required throughout: without it git escapes non-ASCII bytes and quotes
# the whole path, so notes with em-dashes or arrows in their names never match.

# Paths deliberately not committed and not reported. Archived/ holds retired workspaces that are
# expendable by design; the plugin does not maintain them, so it neither publishes nor nags.
is_ignored_path() {
  case "$1" in
    Archived/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_owned_path() {
  case "$1" in
    Projects/*|Resources/*|Contributions/*|HouseStyles/*) return 0 ;;
    "Home.md"|"TasksArchive.md"|"WorkPlanning.md") return 0 ;;
    # Pre-2.0 names, until condense-vault renames them.
    "Tasks Archive.md"|"Work Planning.md") return 0 ;;
    *) return 1 ;;
  esac
}

# Secret-shaped basenames. Matched on the basename so a nested path cannot smuggle one through.
is_secret_path() {
  case "${1##*/}" in
    .env|.env.*|*.pem|*.key|*.p12|*.pfx|*.keystore) return 0 ;;
    id_rsa|id_dsa|id_ecdsa|id_ed25519) return 0 ;;
    .npmrc|.netrc|.pgpass|credentials|*.crt) return 0 ;;
    *) return 1 ;;
  esac
}

to_commit=()
skipped_unowned=()
skipped_secret=()

# Owned paths whose change is already fully staged (a blank worktree column, e.g. a `git rm`).
# They need no `git add` — which fails outright on a staged deletion, since the path is in
# neither the work tree nor the index — but they are still part of the commit.
staged_only=()

# classify <path> <worktree status> — route one concrete file path into one of the buckets.
classify() {
  local path="$1" wt="${2:-}"
  [ -n "$path" ] || return 0
  if is_ignored_path "$path"; then
    return 0
  elif is_secret_path "$path"; then
    skipped_secret+=("$path")
  elif is_owned_path "$path"; then
    if [ "$wt" = " " ]; then
      staged_only+=("$path")
    else
      to_commit+=("$path")
    fi
  else
    skipped_unowned+=("$path")
  fi
}

# -z gives NUL-delimited entries, immune to newlines in filenames. Status codes are the first
# two characters; the path follows after a space. A rename or copy is two entries, "R  new" and
# then the bare old path, which carries no status and must not be parsed as one; the old side's
# removal is already staged and goes into the commit with the new side.
#
# --untracked-files=all is essential: the default collapses a wholly-untracked directory into a
# single "?? dir/" entry, so a secret inside a new directory would never be inspected and the
# whole directory would be staged. Asking for every file means every file gets classified.
while IFS= read -r -d '' entry; do
  classify "${entry:3}" "${entry:1:1}"
  case "${entry:0:1}" in
    R|C) IFS= read -r -d '' _ ;;
  esac
done < <(git -C "$VAULT" -c core.quotepath=off status --porcelain -z --untracked-files=all 2>/dev/null)

if [ "${#skipped_secret[@]}" -gt 0 ]; then
  say "not committing ${#skipped_secret[@]} file(s) that look like secrets: ${skipped_secret[*]}"
  say "if one of these belongs in the vault, add it to the vault's .gitignore or commit it yourself."
fi
if [ "${#skipped_unowned[@]}" -gt 0 ]; then
  say "not committing ${#skipped_unowned[@]} path(s) outside the vault's known folders: ${skipped_unowned[*]}"
fi

if [ "${#to_commit[@]}" -eq 0 ] && [ "${#staged_only[@]}" -eq 0 ]; then
  # Nothing the plugin owns changed. Still flush any unpushed commits from an earlier session.
  if [ -n "$(git -C "$VAULT" log '@{upstream}..HEAD' --oneline 2>/dev/null)" ]; then
    if ! retry_err="$(git -C "$VAULT" push 2>&1)"; then
      say "vault has unpushed commits from an earlier session and the retry failed: ${retry_err##*$'\n'}"
    fi
  fi
  exit 0
fi

# --- Commit and push ---------------------------------------------------------
# Single-line message, no body and no attribution trailer, on the current branch. Never branch.
#
# Failure here is reported, never swallowed. The whole point of this hook is that the user's notes
# reach the remote; a hook that fails silently leaves them believing work is backed up when it is
# not. That is the failure this plugin exists to prevent, so it is the one failure it must never
# reproduce.

date_stamp="$(date +%Y-%m-%d 2>/dev/null || echo session)"

if [ "${#to_commit[@]}" -gt 0 ] && ! add_err="$(git -C "$VAULT" add -- "${to_commit[@]}" 2>&1)"; then
  say "could not stage vault changes: ${add_err%%$'\n'*}"
  exit 0
fi

if ! commit_err="$(git -C "$VAULT" commit -m "vault: session updates ${date_stamp}" 2>&1)"; then
  # Leaving the index staged is itself a change the user did not ask for: their next manual
  # `git commit` would sweep up whatever this hook staged. Unwind to the state we found.
  [ "${#to_commit[@]}" -eq 0 ] || git -C "$VAULT" reset -q -- "${to_commit[@]}" >/dev/null 2>&1 || true

  case "$commit_err" in
    *"Author identity unknown"*|*"tell me who you are"*|*"empty ident"*)
      say "vault changes are NOT committed: git has no author identity configured."
      say "fix with: git -C \"$VAULT\" config user.name 'Your Name' && git -C \"$VAULT\" config user.email you@example.com"
      ;;
    *)
      say "vault changes are NOT committed: ${commit_err%%$'\n'*}"
      ;;
  esac
  exit 0
fi

# Push. A missing remote is a legitimate local-only vault, not a fault — stay quiet. A rejected
# or failed push against a configured remote means the commit exists only on this machine, which
# the user needs to know about.
if git -C "$VAULT" remote >/dev/null 2>&1 && [ -n "$(git -C "$VAULT" remote 2>/dev/null)" ]; then
  if ! push_err="$(git -C "$VAULT" push 2>&1)"; then
    case "$push_err" in
      *"rejected"*|*"fetch first"*|*"non-fast-forward"*)
        say "vault committed locally but the push was REJECTED — the remote has work you do not have."
        say "resolve with: git -C \"$VAULT\" pull --rebase   (your commit is safe locally until then)"
        ;;
      *)
        say "vault committed locally but the push failed: ${push_err##*$'\n'}"
        ;;
    esac
  fi
fi

exit 0
