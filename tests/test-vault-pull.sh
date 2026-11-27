#!/usr/bin/env bash
# Regression tests for hooks/vault-pull.sh (SessionStart).
#
# The flush cases cover the failure this hook exists to backstop: vault-push.sh commits
# locally and then pushes, and session teardown can cancel it in the gap, stranding commits
# on this machine only. SessionStart has no teardown pressure, so the flush here is what
# actually gets them to the remote.

. "$(dirname "$0")/lib.sh"

printf '\033[1mvault-pull.sh\033[0m\n'

# strand <vault> <n> — make n local commits that the remote does not have.
strand() {
  local v="$1" n="$2" i
  for ((i = 1; i <= n; i++)); do
    printf 'stranded %s\n' "$i" >> "$v/Projects/Note.md"
    gitq "$v" commit -qam "vault: session updates 2026-01-0$i"
  done
}

unpushed_ct() { git -C "$1" rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0; }

# ---------------------------------------------------------------------------
section 'Fail-open on missing preconditions'
# ---------------------------------------------------------------------------

run_hook_no_vault vault-pull.sh
assert_eq 0 "$HOOK_RC" 'no vault configured: exit 0'

run_hook vault-pull.sh "$TEST_TMP/does-not-exist"
assert_eq 0 "$HOOK_RC" 'vault path absent: exit 0'
assert_empty "$HOOK_OUT" 'vault path absent: silent'

v="$(build_vault pull-plain --no-git)"
run_hook vault-pull.sh "$v"
assert_eq 0 "$HOOK_RC" 'vault not a git repo: exit 0'
assert_empty "$HOOK_OUT" 'vault not a git repo: silent'

assert_eq 0 "$([ -e "$v/.git/dev-workbook-hooks" ] && echo 1 || echo 0)" \
  'vault not a git repo: no heartbeat written'

# ---------------------------------------------------------------------------
section 'Heartbeat tells the skills the hooks are installed'
# ---------------------------------------------------------------------------

v="$(build_vault pull-heartbeat)"
run_hook vault-pull.sh "$v"
assert_eq 1 "$([ -s "$v/.git/dev-workbook-hooks" ] && echo 1 || echo 0)" 'heartbeat written inside .git'
assert_empty "$(git -C "$v" status --porcelain -- . ':!Projects/.dev-workbook-version')" 'heartbeat leaves the work tree clean'

# ---------------------------------------------------------------------------
section 'Stale-session guard: the plugin version is recorded at session start'
# ---------------------------------------------------------------------------

mine="$(sed -n 's/.*"version": *"\([0-9.]*\)".*/\1/p' "$HOOKS/../.claude-plugin/plugin.json")"

v="$(build_vault pull-version)"
run_hook vault-pull.sh "$v"
assert_eq "$mine" "$(cat "$v/Projects/.dev-workbook-version" 2>/dev/null)" 'records this plugin version'
assert_not_contains "$HOOK_OUT" 'maintenance is off' 'current plugin: no stale notice'

v="$(build_vault pull-newer)"
printf '99.0.0\n' > "$v/Projects/.dev-workbook-version"
run_hook vault-pull.sh "$v"
assert_eq '99.0.0' "$(cat "$v/Projects/.dev-workbook-version")" 'never lowers a newer record'
assert_contains "$HOOK_OUT" 'index maintenance is off' 'stale plugin: the session is told'

v="$(build_vault pull-version-local --no-git)"
run_hook vault-pull.sh "$v"
assert_eq "$mine" "$(cat "$v/Projects/.dev-workbook-version" 2>/dev/null)" 'local vault: version still recorded'
assert_empty "$HOOK_OUT" 'local vault: still silent'

# ---------------------------------------------------------------------------
section 'Recovery at session start: relay exit warnings, commit leftovers'
# ---------------------------------------------------------------------------

v="$(build_vault pull-relay)"
printf 'push was rejected\n' > "$v/.git/dev-workbook-warnings"
run_hook vault-pull.sh "$v"
assert_contains "$HOOK_OUT" 'push was rejected' 'the last exit warning is relayed'
assert_file_absent "$v/.git/dev-workbook-warnings" 'and relayed only once'

v="$(build_vault pull-relay-pre3)"
printf 'old name rejected\n' > "$v/.git/claudesidion-warnings"
run_hook vault-pull.sh "$v"
assert_contains "$HOOK_OUT" 'old name rejected' 'a pre-3.0 warnings file is relayed too'
assert_file_absent "$v/.git/claudesidion-warnings" 'and removed'

v="$(build_vault pull-leftover)"
printf 'left behind\n' >> "$v/Projects/Note.md"
run_hook vault-pull.sh "$v"
assert_contains "$HOOK_OUT" 'not yet committed' 'leftover changes are reported'
assert_eq "" "$(gitq "$v" status --porcelain -- Projects/Note.md)" 'leftover changes are committed'
assert_eq 0 "$(unpushed_ct "$v")" 'and pushed'
assert_file_absent "$v/.git/dev-workbook-warnings" 'start-time commit messages are not relayed again'

v="$(build_vault pull-leftover-unowned)"
printf 'x\n' > "$v/stray.txt"
run_hook vault-pull.sh "$v"
assert_not_contains "$HOOK_OUT" 'not yet committed' 'a change outside the owned folders triggers nothing'

for fmt in plain cursor; do
  v="$(build_vault "pull-format-$fmt")"
  out="$(env HOME="$TEST_TMP/home.$$" DEVWB_VAULT="$v" DEVWB_FORMAT="$fmt" bash "$HOOKS/vault-pull.sh" 2>&1)"
  case "$fmt" in
    plain)  assert_contains "$out" 'Vault pulled to latest' 'plain format prints text' ;;
    cursor) assert_contains "$out" '"additional_context"' 'cursor format prints additional_context' ;;
  esac
done

# Copilot CLI reads only a top-level additionalContext, and Codex drops output that has one, so
# the shape follows the harness: COPILOT_CLI=1 picks copilot, anything else keeps Claude Code's.
v="$(build_vault pull-format-copilot)"
out="$(env -u DEVWB_FORMAT HOME="$TEST_TMP/home.$$" DEVWB_VAULT="$v" COPILOT_CLI=1 bash "$HOOKS/vault-pull.sh" 2>&1)"
assert_eq 'top' "$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("top" if set(d) == {"additionalContext"} else sorted(d))' 2>/dev/null)" \
  'under Copilot CLI: only a top-level additionalContext'
v="$(build_vault pull-format-default)"
out="$(env -u DEVWB_FORMAT -u COPILOT_CLI HOME="$TEST_TMP/home.$$" DEVWB_VAULT="$v" bash "$HOOKS/vault-pull.sh" 2>&1)"
assert_eq 'hso' "$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("hso" if set(d) == {"hookSpecificOutput"} else sorted(d))' 2>/dev/null)" \
  'elsewhere: only hookSpecificOutput (Claude Code, Codex)'
v="$(build_vault pull-format-explicit)"
out="$(env HOME="$TEST_TMP/home.$$" DEVWB_VAULT="$v" COPILOT_CLI=1 DEVWB_FORMAT=plain bash "$HOOKS/vault-pull.sh" 2>&1)"
assert_contains "$out" 'Vault pulled to latest' 'DEVWB_FORMAT wins over detection'

# ---------------------------------------------------------------------------
section 'Flushing commits stranded by a cancelled SessionEnd push'
# ---------------------------------------------------------------------------

v="$(build_vault pull-stranded)"
strand "$v" 2
assert_eq 2 "$(unpushed_ct "$v")" 'fixture: two commits are unpushed'
run_hook vault-pull.sh "$v"
assert_eq 0 "$HOOK_RC" 'stranded commits: exit 0'
assert_eq 0 "$(unpushed_ct "$v")" 'stranded commits are pushed to the remote'
assert_contains "$HOOK_OUT" 'stranded' 'the flush is reported, not silent'
assert_contains "$HOOK_OUT" '2' 'the report names how many commits were flushed'

v="$(build_vault pull-clean)"
run_hook vault-pull.sh "$v"
assert_eq 0 "$HOOK_RC" 'nothing stranded: exit 0'
assert_not_contains "$HOOK_OUT" 'stranded' 'nothing stranded: no flush claimed'
assert_contains "$HOOK_OUT" 'pulled to latest' 'nothing stranded: still reports the pull'

# A local-only vault has no upstream at all. The flush must not claim anything, and must not
# turn a legitimate offline vault into an error.
v="$(build_vault pull-noremote --no-remote)"
run_hook vault-pull.sh "$v"
assert_eq 0 "$HOOK_RC" 'no remote: exit 0'
assert_not_contains "$HOOK_OUT" 'stranded' 'no remote: no flush claimed'

# An unreachable remote must be reported as still-local, never as flushed — the whole point is
# that the user learns their notes are not backed up.
v="$(build_vault pull-deadremote)"
strand "$v" 1
gitq "$v" remote set-url origin "$TEST_TMP/no-such-remote.git"
run_hook vault-pull.sh "$v"
assert_eq 0 "$HOOK_RC" 'unreachable remote: exit 0'
assert_eq 1 "$(unpushed_ct "$v")" 'unreachable remote: commit stays local'
assert_contains "$HOOK_OUT" 'remain local-only' 'unreachable remote: reported as not backed up'

# The flush pushes the whole branch, so it only does so when every unpushed commit is the
# plugin's own. A commit the user made and chose not to push is theirs to publish.
v="$(build_vault pull-foreign)"
strand "$v" 1
printf 'mine\n' >> "$v/Projects/Note.md"
gitq "$v" commit -qam "wip: not ready to share"
run_hook vault-pull.sh "$v"
assert_eq 2 "$(unpushed_ct "$v")" 'a user commit on the branch: nothing pushed'
assert_contains "$HOOK_OUT" 'did not make' 'a user commit on the branch: reported'

# A plugin commit that somehow carries a secret-shaped file is never pushed.
v="$(build_vault pull-secret)"
printf 'K=1\n' > "$v/Projects/.ENV"
gitq "$v" add -A && gitq "$v" commit -qm "vault: session updates 2026-01-01"
run_hook vault-pull.sh "$v"
assert_eq 1 "$(unpushed_ct "$v")" 'an unpushed secret-shaped file: nothing pushed'
assert_contains "$HOOK_OUT" 'look like secrets' 'an unpushed secret-shaped file: reported'


section 'Unmanaged folders'

# Another machine widens the list and pushes it: after the pull, this machine says so and does not
# sync the new folder until it is approved here.
v="$(build_vault pull-unmanaged)"
other="$TEST_TMP/pull-unmanaged.other"
git clone -q "$TEST_TMP/pull-unmanaged.remote.git" "$other"
gitq "$other" config user.email t@example.invalid
gitq "$other" config user.name T
mkdir -p "$other/Private"
printf '{"unmanaged": ["Private"]}\n' > "$other/.dev-workbook.json"
printf '# p\n' > "$other/Private/P.md"
gitq "$other" add -A && gitq "$other" commit -qm "list Private" && gitq "$other" push -q origin main
run_hook vault-pull.sh "$v"
assert_contains "$HOOK_OUT" 'does not sync yet: Private' 'a pulled list: the unapproved folder is reported'
assert_contains "$HOOK_OUT" 'dev-workbook unmanaged --approve Private' 'a pulled list: the command names the folder'

# Before approval, a local change in that folder is neither committed nor pushed at session start.
printf 'local only\n' >> "$v/Private/P.md"
run_hook vault-pull.sh "$v"
assert_contains "$(git -C "$v" status --porcelain -- Private)" 'Private/P.md' 'unapproved: a local change is left uncommitted'
git -C "$v" checkout -q -- Private

"$REPO_ROOT/bin/dev-workbook" unmanaged --vault "$v" --approve >/dev/null
run_hook vault-pull.sh "$v"
assert_not_contains "$HOOK_OUT" 'does not sync yet' 'once approved: no notice'

# A change left uncommitted in an approved folder is committed at session start like any owned path.
printf 'more\n' >> "$v/Private/P.md"
run_hook vault-pull.sh "$v"
assert_eq "" "$(git -C "$v" status --porcelain -- Private)" 'an approved folder: a leftover change is committed'

finish
