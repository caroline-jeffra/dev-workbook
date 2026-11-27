#!/usr/bin/env bash
# SessionStart hook: remind that the weekly vault condense run (condense-vault skill) is due
# when the last run was more than 7 days ago (or has never happened) and there is work for it:
# stale content to condense, or workspace notes that break their format (lint findings) to
# reconcile. The skill stamps $VAULT/.condense-last-run with YYYY-MM-DD on every run.
#
# Fails open on every path: if anything is missing or goes wrong, exit 0 with no output.

set -u

# Vault resolution is shared by every hook: env var, the dev-workbook config file, the legacy
# ~/.claude file, then the default. See lib.sh.
# shellcheck source=hooks/lib.sh
. "$(dirname "$0")/lib.sh" 2>/dev/null || exit 0
VAULT="$(resolve_vault)"
[ -d "$VAULT" ] || exit 0
can_emit || exit 0

STAMP="$VAULT/.condense-last-run"
cutoff="$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '-7 days' +%Y-%m-%d 2>/dev/null)" || exit 0

if [ -f "$STAMP" ]; then
  last="$(head -n1 "$STAMP" 2>/dev/null | tr -cd '0-9-')"
  # Malformed stamp or recent enough: stay silent.
  case "$last" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) [ "$last" \< "$cutoff" ] || exit 0 ;;
    *) exit 0 ;;
  esac
  ctx="The weekly vault condense run is due (last run: ${last}). Mention this to the user and offer to run the condense-vault skill; do not start it unprompted."
  routine=yes
else
  ctx="The weekly vault condense run has never been recorded. Mention this to the user and offer to run the condense-vault skill; do not start it unprompted."
  routine=""
fi

# Format findings: notes that break the workspace note contract. The run's reconcile step fixes
# these whatever their age, so they are work for the run on a vault too young to have anything
# stale. Same interpreter discovery as vault-maintain.sh; any failure just means a count of 0.
lint_count=0
PY=""
for candidate in python3 python; do
  command -v "$candidate" >/dev/null 2>&1 && { PY="$candidate"; break; }
done
SCRIPT="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(dirname "$0")/..}}/hooks/vault_maintain.py"
if [ -n "$PY" ] && [ -f "$SCRIPT" ]; then
  lint_count="$("$PY" "$SCRIPT" --lint --count "$VAULT" 2>/dev/null | tr -cd '0-9')"
  lint_count="${lint_count:-0}"
fi
if [ "$lint_count" -gt 0 ] 2>/dev/null; then
  ctx="$ctx ${lint_count} workspace format finding(s) are waiting for its reconcile step."
fi

# A due stamp is necessary but not sufficient for the ROUTINE weekly nudge: if nothing is
# old enough to condense and nothing breaks the note formats, prompting produces a run that
# finds nothing. That happened weekly
# on a vault younger than the 3-month threshold.
#
# This gate deliberately does not apply when the run has NEVER been recorded. That message
# is how someone first learns the routine exists, and suppressing it on a young vault means
# they never hear about it at all.
#
# Bounded on purpose: `head -1` stops at the first hit, so this costs one match, not a full
# walk, and it never runs `git log` per file the way the skill itself does. Fails open — any
# error here means we simply do not prompt.
stale_cutoff="$(date -v-3m +%Y-%m-%d 2>/dev/null || date -d '-3 months' +%Y-%m-%d 2>/dev/null)"
if [ -n "$routine" ] && [ -n "$stale_cutoff" ]; then
  found=""
  [ "$lint_count" -gt 0 ] 2>/dev/null && found=yes
  # Oldest mtime in the vault. BSD and GNU `stat` take different flags — and crucially GNU
  # `stat` does NOT fail on the BSD form: it reads `%Sm` as a filename, writes an error to
  # stderr, and still exits 0. So `bsd || gnu` silently keeps the empty BSD result on Linux.
  # Pick by probing `stat` once on a known file and testing the OUTPUT, never the exit code.
  probe="$(stat -f '%Sm' -t '%Y-%m-%d' "$VAULT" 2>/dev/null)"
  case "$probe" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) stat_fmt=bsd ;;
    *) stat_fmt=gnu ;;
  esac

  if [ "$stat_fmt" = bsd ]; then
    oldest="$(find "$VAULT" -name '*.md' -not -path '*/.git/*' -not -path '*/.obsidian/*' \
      -exec stat -f '%Sm' -t '%Y-%m-%d' {} + 2>/dev/null | sort | head -n1)"
  else
    oldest="$(find "$VAULT" -name '*.md' -not -path '*/.git/*' -not -path '*/.obsidian/*' \
      -exec stat -c '%y' {} + 2>/dev/null | cut -d' ' -f1 | sort | head -n1)"
  fi

  case "$oldest" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
      [ "$(printf '%s\n%s\n' "$oldest" "$stale_cutoff" | sort | head -n1)" = "$oldest" ] \
        && [ "$oldest" != "$stale_cutoff" ] && found=yes ;;
  esac
  [ -n "$found" ] || exit 0
fi

emit_context "$ctx"

exit 0
