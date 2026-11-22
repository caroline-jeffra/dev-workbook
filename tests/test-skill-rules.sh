#!/usr/bin/env bash
# The manage-project-workspaces skill is split into a router plus reference files. This suite pins
# every rule of the v3.5.0 skill to exactly one home (tests/skill-rules.tsv), keeps the router
# within its byte budget and the frozen router text identical to v3.5.0, and mutation-tests
# the checks themselves. The logic is in tests/skill_rules.py.
#
# Usage: tests/test-skill-rules.sh [--self-test]

. "$(dirname "$0")/lib.sh"

CHECK="$REPO_ROOT/tests/skill_rules.py"
split=(--split)

# run_check <subcommand> <name> — one ok/FAIL line for a checker whose output lists the failures.
run_check() {
  local out rc
  out="$(python3 "$CHECK" "$1" "${split[@]}" 2>&1)"
  rc=$?
  case "$out" in
    SKIP*) ok "$2 (skipped: $out)"; return 0 ;;
  esac
  if [ "$rc" -eq 0 ]; then ok "$2"; else nope "$2" "$(printf '%s' "$out" | head -n 8)"; fi
}

if [ "${1-}" = "--self-test" ]; then
  section 'the checks fail when a rule is deleted (mutation self-test)'
  run_check selftest 'deleting one sentence per destination file turns the rules check red'
  finish
fi

section 'every rule has exactly one home'
run_check rules 'each phrase is in exactly one file, the one the inventory names'
run_check orphans 'every paragraph and bullet of v3.5.0 is covered by an inventory row'

section 'the router'
run_check frozen 'match table, index_notes, trial rule and Step 1b are identical to v3.5.0'
run_check budget 'the router body is within 8192 bytes'
run_check fences 'every code block of the v3.5.0 skill survives verbatim'

section 'the mutation self-test'
run_check selftest 'deleting one sentence per destination file turns the rules check red'

finish
