#!/usr/bin/env bash
# Regression tests for hooks/vault-push.sh (SessionEnd).
#
# These assert the behaviour the hook SHOULD have. Cases marked [T1.x] correspond to
# Pre-Release Plan tier-1 items and are EXPECTED TO FAIL until that item is fixed —
# they document the bug. Run with EXPECT_TIER1_FAILURES=0 once tier 1 is done.

. "$(dirname "$0")/lib.sh"

printf '\033[1mvault-push.sh\033[0m\n'

# ---------------------------------------------------------------------------
section 'Fail-open on missing preconditions (should already pass)'
# ---------------------------------------------------------------------------

run_hook_no_vault vault-push.sh
assert_eq 0 "$HOOK_RC" 'no vault configured: exit 0'
assert_empty "$HOOK_OUT" 'no vault configured: silent'

run_hook vault-push.sh "$TEST_TMP/does-not-exist"
assert_eq 0 "$HOOK_RC" 'vault path absent: exit 0'
assert_empty "$HOOK_OUT" 'vault path absent: silent'

v="$(build_vault plain --no-git)"
run_hook vault-push.sh "$v"
assert_eq 0 "$HOOK_RC" 'vault not a git repo: exit 0'
assert_empty "$HOOK_OUT" 'vault not a git repo: silent'

v="$(build_vault clean)"
before="$(commit_ct "$v")"
run_hook vault-push.sh "$v"
assert_eq 0 "$HOOK_RC" 'clean vault: exit 0'
assert_eq "$before" "$(commit_ct "$v")" 'clean vault: no empty commit'

v="$(build_vault garbage)"
run_hook vault-push.sh "$v" '{"not":"what it expects"'
assert_eq 0 "$HOOK_RC" 'garbage stdin: exit 0'

# ---------------------------------------------------------------------------
section 'Happy path'
# ---------------------------------------------------------------------------

v="$(build_vault happy)"
printf '# new\n' > "$v/Projects/added.md"
run_hook vault-push.sh "$v"
assert_eq 0 "$HOOK_RC" 'normal write: exit 0'
assert_contains "$(tracked "$v")" 'Projects/added.md' 'normal write: file committed'
assert_eq "" "$(gitq "$v" status --porcelain)" 'normal write: tree left clean'

# A note the user deleted with `git rm` is already staged and gone from the work tree. `git add`
# on it fails outright, which used to abort the whole commit and leave every change uncommitted.
v="$(build_vault push-staged-delete)"
printf '# old\n' > "$v/Projects/Old Index.md"
gitq "$v" add -A && gitq "$v" commit -qm 'add old' && gitq "$v" push -q
gitq "$v" rm -q "Projects/Old Index.md"
printf '# also edited\n' >> "$v/Projects/Note.md"
run_hook vault-push.sh "$v"
assert_not_contains "$(tracked "$v")" 'Old Index.md' 'staged deletion: committed'
assert_eq "" "$(gitq "$v" status --porcelain)" 'staged deletion: other edits committed with it'
assert_not_contains "$HOOK_OUT" 'could not stage' 'staged deletion: no staging error'

v="$(build_vault push-staged-only)"
gitq "$v" rm -q "Projects/Note.md"
run_hook vault-push.sh "$v"
assert_eq "" "$(gitq "$v" status --porcelain)" 'only a staged deletion: still committed'

# With -z, git reports a staged rename as two records, "R  new" then the bare old path. Parsing
# the old path as a status line cut its first three characters off, so every rename was reported
# as a path outside the known folders ("jects/Old/Note.md").
v="$(build_vault push-staged-rename)"
gitq "$v" mv Projects Resources
run_hook vault-push.sh "$v"
assert_eq "" "$(gitq "$v" status --porcelain)" 'staged rename: committed'
assert_not_contains "$HOOK_OUT" 'outside the vault' 'staged rename: old path not reported as unowned'

# Session-end output reaches no one, so what the hook reports is also recorded for the next start.
v="$(build_vault push-relay)"
printf 'x\n' > "$v/stray.txt"
run_hook vault-push.sh "$v"
assert_contains "$(cat "$v/.git/dev-workbook-warnings" 2>/dev/null)" 'stray.txt' \
  'a reported problem is recorded for the next session start'

v="$(build_vault push-version)"
printf '2.3.0\n' > "$v/Projects/.dev-workbook-version"
run_hook vault-push.sh "$v"
assert_contains "$(tracked "$v")" 'Projects/.dev-workbook-version' \
  'the plugin version record is committed, so other machines see it'

# ---------------------------------------------------------------------------
section '[T1.1] Must not commit files the plugin did not write'
# ---------------------------------------------------------------------------

v="$(build_vault secrets)"
printf 'AWS_SECRET=hunter2\n' > "$v/.env"
printf '# note\n' > "$v/Projects/legit.md"
run_hook vault-push.sh "$v"
assert_not_contains "$(tracked "$v")" '.env' '[T1.1] .env not committed'
assert_contains "$(tracked "$v")" 'Projects/legit.md' '[T1.1] legitimate note still committed'

v="$(build_vault keys)"
mkdir -p "$v/Projects"
printf -- '-----BEGIN PRIVATE KEY-----\n' > "$v/id_rsa"
printf 'x\n' > "$v/server.pem"
printf 'y\n' > "$v/api.key"
printf '# note\n' > "$v/Projects/legit.md"
run_hook vault-push.sh "$v"
t="$(tracked "$v")"
assert_not_contains "$t" 'id_rsa'    '[T1.1] id_rsa not committed'
assert_not_contains "$t" 'server.pem' '[T1.1] .pem not committed'
assert_not_contains "$t" 'api.key'   '[T1.1] .key not committed'

v="$(build_vault outside)"
printf 'scratch\n' > "$v/random-root-file.txt"
printf '# note\n' > "$v/Projects/legit.md"
run_hook vault-push.sh "$v"
assert_not_contains "$(tracked "$v")" 'random-root-file.txt' \
  '[T1.1] unexpected root file outside known subtrees not committed'

# Non-ASCII filenames: without core.quotepath=off git quotes and escapes the whole path,
# so every note with an em-dash or arrow in its name silently fails to match the allowlist.
v="$(build_vault nonascii)"
printf '# a\n' > "$v/Projects/Kestrel ↔ Osprey role differences.md"
printf '# b\n' > "$v/Projects/ACME-1656 review — billing joins.md"
run_hook vault-push.sh "$v"
t="$(gitq "$v" -c core.quotepath=off ls-files)"
assert_contains "$t" 'Osprey' '[T1.1] non-ASCII filename (arrow) committed'
assert_contains "$t" 'billing joins' '[T1.1] non-ASCII filename (em-dash) committed'

# A filename containing a newline must not split the loop or leak a partial path.
v="$(build_vault newlinename)"
printf '# odd\n' > "$v/Projects/we$(printf '\n')ird.md" 2>/dev/null || true
run_hook vault-push.sh "$v"
assert_eq 0 "$HOOK_RC" '[T1.1] newline in filename: exit 0, no loop break'

# Secret inside an owned subtree is still refused — the blocklist matches on basename.
v="$(build_vault nestedsecret)"
mkdir -p "$v/Projects/app"
printf 'TOKEN=abc\n' > "$v/Projects/app/.env"
printf '# note\n' > "$v/Projects/app/notes.md"
run_hook vault-push.sh "$v"
assert_not_contains "$(tracked "$v")" '.env' '[T1.1] secret nested in an owned path still refused'
assert_contains "$(tracked "$v")" 'Projects/app/notes.md' '[T1.1] sibling note in same dir still committed'
assert_contains "$HOOK_OUT" 'secret' '[T1.1] secret refusal is reported'

# HouseStyles/ (clean-docs profiles) is owned: its templates and profile.json are committed.
v="$(build_vault housestyles)"
mkdir -p "$v/HouseStyles/Acme"
printf '# PR\n' > "$v/HouseStyles/Acme/PullRequest.md"
printf '{"schema": 1}\n' > "$v/HouseStyles/Acme/profile.json"
run_hook vault-push.sh "$v"
assert_contains "$(tracked "$v")" 'HouseStyles/Acme/PullRequest.md' '[T1.1] HouseStyles/ template committed'
assert_contains "$(tracked "$v")" 'HouseStyles/Acme/profile.json' '[T1.1] HouseStyles/ profile.json committed'
assert_not_contains "$HOOK_OUT" 'HouseStyles' '[T1.1] HouseStyles/ is not reported as unowned'

# Archived/ is expendable: neither committed nor mentioned.
v="$(build_vault archived)"
mkdir -p "$v/Archived/old"
printf 'retired\n' > "$v/Archived/old/dead.md"
run_hook vault-push.sh "$v"
assert_not_contains "$(tracked "$v")" 'Archived/' '[T1.1] Archived/ not committed'
assert_empty "$HOOK_OUT" '[T1.1] Archived/ change is silent (expendable by design)'

# ---------------------------------------------------------------------------
section '[T1.2] Must not commit mid-merge / mid-rebase'
# ---------------------------------------------------------------------------

v="$(build_vault conflict)"
printf 'base\n' > "$v/Projects/f.md"; gitq "$v" add -A; gitq "$v" commit -qm base
gitq "$v" checkout -q -b other
printf 'other\n' > "$v/Projects/f.md"; gitq "$v" commit -qam other
gitq "$v" checkout -q main
printf 'main\n' > "$v/Projects/f.md"; gitq "$v" commit -qam main
gitq "$v" merge other >/dev/null 2>&1   # conflicts on purpose
assert_file_exists "$v/.git/MERGE_HEAD" '[T1.2] fixture is genuinely mid-merge'
before="$(commit_ct "$v")"
run_hook vault-push.sh "$v"
assert_eq "$before" "$(commit_ct "$v")" '[T1.2] mid-merge: no commit made'
assert_file_exists "$v/.git/MERGE_HEAD" '[T1.2] mid-merge: MERGE_HEAD preserved (abort still possible)'
assert_not_contains "$(gitq "$v" show HEAD:Projects/f.md)" '<<<<<<<' \
  '[T1.2] mid-merge: conflict markers not committed'
assert_contains "$HOOK_OUT" 'merge' '[T1.2] mid-merge: says why it declined'

# A CLEAN merge in progress has no unmerged paths at all — MERGE_HEAD is the only signal.
# Without the state-file check the hook would silently conclude someone else's merge.
v="$(build_vault cleanmerge)"
printf 'a\n' > "$v/Projects/f.md"; gitq "$v" add -A; gitq "$v" commit -qm base
gitq "$v" checkout -q -b other
printf 'b\n' > "$v/Projects/g.md"; gitq "$v" add -A; gitq "$v" commit -qm o
gitq "$v" checkout -q main
printf 'c\n' > "$v/Projects/h.md"; gitq "$v" add -A; gitq "$v" commit -qm m
gitq "$v" merge --no-commit --no-ff other >/dev/null 2>&1
assert_eq 0 "$(gitq "$v" ls-files -u | grep -c . | tr -d ' ')" \
  '[T1.2] clean-merge fixture has no unmerged paths (status codes alone would miss it)'
before="$(commit_ct "$v")"
run_hook vault-push.sh "$v"
assert_eq "$before" "$(commit_ct "$v")" '[T1.2] clean merge in progress: no commit made'
assert_contains "$HOOK_OUT" 'merge' '[T1.2] clean merge in progress: says why'

v="$(build_vault cherry)"
printf 'x\n' > "$v/Projects/f.md"; gitq "$v" add -A; gitq "$v" commit -qm base
gitq "$v" checkout -q -b side
printf 'y\n' > "$v/Projects/f.md"; gitq "$v" commit -qam side
gitq "$v" checkout -q main
printf 'z\n' > "$v/Projects/f.md"; gitq "$v" commit -qam main
gitq "$v" cherry-pick side >/dev/null 2>&1
before="$(commit_ct "$v")"
run_hook vault-push.sh "$v"
assert_eq "$before" "$(commit_ct "$v")" '[T1.2] mid-cherry-pick: no commit made'

# ---------------------------------------------------------------------------
section '[T1.3] Must not commit on detached HEAD'
# ---------------------------------------------------------------------------

v="$(build_vault detached)"
printf 'second\n' > "$v/Projects/Note.md"; gitq "$v" commit -qam second
gitq "$v" checkout -q HEAD~1
printf '# written while detached\n' > "$v/Projects/orphan.md"
run_hook vault-push.sh "$v"
assert_empty "$(gitq "$v" symbolic-ref -q HEAD)" '[T1.3] fixture is genuinely detached'
assert_not_contains "$(tracked "$v")" 'orphan.md' \
  '[T1.3] detached HEAD: nothing committed to a dangling commit'
assert_contains "$HOOK_OUT" 'detached' '[T1.3] detached HEAD: says why it declined'

# ---------------------------------------------------------------------------
section '[T1.7] Failed commit must not leave the tree staged'
# ---------------------------------------------------------------------------

v="$(build_vault noidentity --no-identity --empty)"
printf '# note\n' > "$v/Projects/Note.md"
run_hook vault-push.sh "$v"
assert_eq 0 "$HOOK_RC" '[T1.7] no git identity: still exits 0'
assert_eq 0 "$(staged_ct "$v")" '[T1.7] no git identity: index left unstaged'
assert_contains "$HOOK_OUT" 'identity' '[T1.7] no git identity: says what went wrong'

# ---------------------------------------------------------------------------
section '[T1.8] Push failures must be surfaced'
# ---------------------------------------------------------------------------

v="$(build_vault noremote --no-remote)"
printf '# note\n' > "$v/Projects/added.md"
run_hook vault-push.sh "$v"
assert_contains "$(tracked "$v")" 'Projects/added.md' '[T1.8] no remote: commit still made locally'
assert_eq 0 "$HOOK_RC" '[T1.8] no remote: exit 0'

v="$(build_vault diverged)"
# Remote moves ahead of us, so our push is rejected non-fast-forward.
clone="$TEST_TMP/diverged.clone"
git clone -q "$TEST_TMP/diverged.remote.git" "$clone"
git -C "$clone" config user.email t@e.invalid; git -C "$clone" config user.name T
git -C "$clone" config commit.gpgsign false; git -C "$clone" config core.hooksPath /dev/null
# The clone must actually have the seed commit checked out, or "the remote moves ahead" below
# is a no-op and the push under test succeeds instead of being rejected.
[ -e "$clone/Projects/Note.md" ] || nope '[T1.8] diverged fixture: clone checked out' "clone is empty"
printf 'theirs\n' > "$clone/Projects/theirs.md"
git -C "$clone" add -A; git -C "$clone" commit -qm theirs; git -C "$clone" push -q
printf '# ours\n' > "$v/Projects/ours.md"
run_hook vault-push.sh "$v"
assert_contains "$HOOK_OUT" 'push' '[T1.8] diverged remote: push failure surfaced'

finish
