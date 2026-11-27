#!/usr/bin/env bash
# Session-end step: refresh derived metadata and regenerate indexes for any vault
# workspace that opts in with a `.vault-config.json`.
#
# session-end.sh runs it BEFORE vault-push.sh, so the regenerated indexes are
# committed in the same commit as the notes that changed them.
#
# This never deletes or moves a file and never edits a note body — it only fills
# in derived frontmatter and rewrites generated index notes. See
# hooks/vault_maintain.py for the guarantees.
#
# Fails open on every path: if anything is missing or goes wrong, exit 0 with no
# output so a hook bug can never break the user's session teardown.

set -u

# Vault resolution is shared by every hook: env var, the dev-workbook config file, the legacy
# ~/.claude file, then the default. See lib.sh.
# shellcheck source=hooks/lib.sh
. "$(dirname "$0")/lib.sh" 2>/dev/null || exit 0
VAULT="$(resolve_vault)"
[ -d "$VAULT" ] || exit 0

# Python 3 is required. If it is absent, do nothing rather than failing loudly —
# the vault stays valid, the indexes are simply not refreshed this session.
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || exit 0

SCRIPT="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(dirname "$0")/..}}/hooks/vault_maintain.py"
[ -f "$SCRIPT" ] || exit 0

# The script fails open internally too; the redirect and `|| true` are belt and
# braces so a crash can never block the session-end push that follows.
"$PY" "$SCRIPT" "$VAULT" 2>/dev/null || true

exit 0
