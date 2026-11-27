#!/usr/bin/env bash
# Regression tests for hooks/vault-condense-reminder.sh (SessionStart).
#
# The cutoff line is the reason this suite exists:
#
#   date -v-7d ... || date -d '-7 days' ...
#
# The first branch is BSD (macOS), the second GNU (Linux). Only one of them ever runs on any
# given machine, so on macOS the GNU branch had never been executed at all. These tests assert
# the *observable behaviour* on whichever platform is running, and CI runs them on both — that
# pairing, not any single run, is what covers both branches.

. "$(dirname "$0")/lib.sh"

printf '\033[1mvault-condense-reminder.sh\033[0m\n'

STAMP_NAME='.condense-last-run'

# Dates relative to today, computed the same dual way the hook does, so the fixtures stay
# correct on both platforms.
days_ago() { # n
  date -v-"$1"d +%Y-%m-%d 2>/dev/null || date -d "-$1 days" +%Y-%m-%d 2>/dev/null
}

# A fixture vault carrying a genuinely stale file. The routine weekly prompt is gated on
# something actually being old enough to condense, so a fixture without one tests the gate
# rather than the stamp logic it means to test. Pass --fresh for the gate's own tests.
stamp_vault() { # name, stamp-contents [--fresh]
  local v; v="$(build_vault "$1" --no-git)"
  printf '%s\n' "$2" > "$v/$STAMP_NAME"
  if [ "${3-}" != "--fresh" ]; then
    : > "$v/Projects/ancient.md"
    touch -t 202501010000 "$v/Projects/ancient.md" 2>/dev/null \
      || touch -d '2025-01-01' "$v/Projects/ancient.md" 2>/dev/null
  fi
  printf '%s' "$v"
}

# The hook emits SessionStart JSON; treat a mention of the skill as "it prompted".
prompted() { case "$HOOK_OUT" in *condense-vault*) return 0 ;; *) return 1 ;; esac; }

section 'The date cutoff resolves on this platform'

cutoff="$(days_ago 7)"
case "$cutoff" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ok 'a 7-day cutoff is computable here' ;;
  *) nope 'a 7-day cutoff is computable here' "got [$cutoff]" ;;
esac

section 'Fail-open on missing preconditions'

run_hook_no_vault vault-condense-reminder.sh
assert_eq 0 "$HOOK_RC" 'no vault configured: exit 0'
assert_empty "$HOOK_OUT" 'no vault configured: silent'

run_hook vault-condense-reminder.sh "$TEST_TMP/nope"
assert_eq 0 "$HOOK_RC" 'vault path absent: exit 0'
assert_empty "$HOOK_OUT" 'vault path absent: silent'

section 'Stamp age decides whether it prompts'

v="$(stamp_vault stale "$(days_ago 30)")"
run_hook vault-condense-reminder.sh "$v"
assert_eq 0 "$HOOK_RC" 'stale stamp: exit 0'
if prompted; then ok 'stamp 30 days old: prompts'; else nope 'stamp 30 days old: prompts' "got [$HOOK_OUT]"; fi
assert_contains "$HOOK_OUT" "$(days_ago 30)" 'stale stamp: names the last-run date'

# Codex and Copilot set PLUGIN_ROOT; a hook must find the plugin's scripts through it when
# CLAUDE_PLUGIN_ROOT is absent, not fall back to its own directory.
fake_root="$TEST_TMP/plugin-root"
mkdir -p "$fake_root/hooks"
printf 'print(7)\n' > "$fake_root/hooks/vault_maintain.py"
out="$(env -u CLAUDE_PLUGIN_ROOT -u DEVWB_FORMAT -u COPILOT_CLI PLUGIN_ROOT="$fake_root" HOME="$TEST_TMP/home.$$" DEVWB_VAULT="$v" bash "$HOOKS/vault-condense-reminder.sh" 2>&1)"
assert_contains "$out" '7 workspace format finding' 'PLUGIN_ROOT locates the plugin when CLAUDE_PLUGIN_ROOT is unset'

v="$(stamp_vault fresh "$(days_ago 1)")"
run_hook vault-condense-reminder.sh "$v"
if prompted; then nope 'stamp 1 day old: stays silent' "got [$HOOK_OUT]"; else ok 'stamp 1 day old: stays silent'; fi

v="$(stamp_vault today "$(days_ago 0)")"
run_hook vault-condense-reminder.sh "$v"
if prompted; then nope "stamp dated today: stays silent" "got [$HOOK_OUT]"; else ok 'stamp dated today: stays silent'; fi

# The boundary. 8 days is unambiguously past a 7-day cutoff on either platform; 7 days exactly
# is the off-by-one and is deliberately not asserted, since `<` against the cutoff makes it
# silent and that is a judgement call rather than a bug.
v="$(stamp_vault eightdays "$(days_ago 8)")"
run_hook vault-condense-reminder.sh "$v"
if prompted; then ok 'stamp 8 days old: prompts'; else nope 'stamp 8 days old: prompts' "got [$HOOK_OUT]"; fi

section 'Missing or malformed stamps'

v="$(build_vault nostamp --no-git)"
run_hook vault-condense-reminder.sh "$v"
assert_eq 0 "$HOOK_RC" 'no stamp: exit 0'
if prompted; then ok 'no stamp at all: prompts'; else nope 'no stamp at all: prompts' "got [$HOOK_OUT]"; fi
assert_contains "$HOOK_OUT" 'never been recorded' 'no stamp: says it has never run'

for bad in 'not-a-date' '2026-13' '' 'last tuesday'; do
  v="$(stamp_vault "bad$(printf '%s' "$bad" | tr -cd 'a-z0-9')" "$bad")"
  run_hook vault-condense-reminder.sh "$v"
  assert_eq 0 "$HOOK_RC" "malformed stamp [$bad]: exit 0"
  if prompted; then
    nope "malformed stamp [$bad]: stays silent" "got [$HOOK_OUT]"
  else
    ok "malformed stamp [$bad]: stays silent"
  fi
done

section 'Output is well-formed for the harness'

if command -v jq >/dev/null 2>&1; then
  v="$(stamp_vault jsoncheck "$(days_ago 30)")"
  run_hook vault-condense-reminder.sh "$v"
  if printf '%s' "$HOOK_OUT" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' >/dev/null 2>&1; then
    ok 'prompt output is valid SessionStart JSON'
  else
    nope 'prompt output is valid SessionStart JSON' "got [$HOOK_OUT]"
  fi
  if printf '%s' "$HOOK_OUT" | jq -e '.hookSpecificOutput.additionalContext | length > 0' >/dev/null 2>&1; then
    ok 'prompt output carries additionalContext'
  else
    nope 'prompt output carries additionalContext' "got [$HOOK_OUT]"
  fi
else
  ok 'JSON shape tests skipped (jq not installed)'
  ok 'JSON shape tests skipped (jq not installed)'
fi

section 'Staleness gate: an overdue stamp alone is not enough'

# The stamp says "7 days since a run", but the reminder should only speak if there is
# actually something old enough to condense. A vault younger than the 3-month threshold
# prompted weekly for a run that could only ever find nothing.

v="$(stamp_vault gate_fresh "$(days_ago 90)" --fresh)"
run_hook vault-condense-reminder.sh "$v"
assert_eq 0 "$HOOK_RC" 'overdue stamp, nothing stale: exit 0'
if prompted; then
  nope 'overdue stamp but nothing stale: stays silent' "got [$HOOK_OUT]"
else
  ok 'overdue stamp but nothing stale: stays silent'
fi

# ...but it must still fire when something genuinely is stale, or the gate has just
# disabled the reminder outright.
v="$(stamp_vault gate_stale "$(days_ago 90)")"
run_hook vault-condense-reminder.sh "$v"
if prompted; then
  ok 'overdue stamp and a stale file: prompts'
else
  nope 'overdue stamp and a stale file: prompts' "got [$HOOK_OUT]"
fi

section 'Format findings are work for the run too'

# The reconcile step fixes notes that break the workspace formats whatever their age, so a
# vault with nothing stale but a broken note still has work for the run.

v="$(stamp_vault gate_lint "$(days_ago 90)" --fresh)"
mkdir -p "$v/Projects/Demo/Log"
printf '{"project":"demo","topics":{}}' > "$v/Projects/Demo/.vault-config.json"
printf -- '---\ntype: log\ndate: 2026-10-01\n---\n\n# 2026-10-01\n\n- **Did:** x\n- **Next:** y\n' \
  > "$v/Projects/Demo/Log/2026-10-01.md"
run_hook vault-condense-reminder.sh "$v"
assert_eq 0 "$HOOK_RC" 'overdue stamp, lint finding: exit 0'
if prompted; then
  ok 'overdue stamp, nothing stale, a format finding: prompts'
else
  nope 'overdue stamp, nothing stale, a format finding: prompts' "got [$HOOK_OUT]"
fi
assert_contains "$HOOK_OUT" 'format finding' 'the prompt names the format findings'

v="$(stamp_vault lint_fresh "$(days_ago 1)")"
mkdir -p "$v/Projects/Demo/Log"
printf '{"project":"demo","topics":{}}' > "$v/Projects/Demo/.vault-config.json"
printf -- '---\ntype: log\n---\n\n- **Next:** y\n' > "$v/Projects/Demo/Log/2026-10-01.md"
run_hook vault-condense-reminder.sh "$v"
if prompted; then
  nope 'format findings alone do not override a recent stamp' "got [$HOOK_OUT]"
else
  ok 'format findings alone do not override a recent stamp'
fi

finish
