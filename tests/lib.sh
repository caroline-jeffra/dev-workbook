#!/usr/bin/env bash
# Shared harness helpers. Sourced by each tests/test-*.sh.
#
# Every test runs against a throwaway vault under a temp dir. Nothing here may touch the user's
# real vault — build_vault always creates a fresh directory, and no helper accepts a path outside
# $TEST_TMP.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS="$REPO_ROOT/hooks"

PASS=0
FAIL=0
FAILED_NAMES=()


TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/dev-workbook-tests.XXXXXX")"
trap 'rm -rf "$TEST_TMP"' EXIT

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

ok() { PASS=$((PASS + 1)); printf '  \033[32mok\033[0m   %s\n' "$1"; }

nope() {
  FAIL=$((FAIL + 1))
  FAILED_NAMES+=("$1")
  printf '  \033[31mFAIL\033[0m %s\n' "$1"
  [ $# -gt 1 ] && printf '       %s\n' "$2"
  return 0
}

assert_eq() { # want, got, name
  if [ "$1" = "$2" ]; then ok "$3"; else nope "$3" "want [$1], got [$2]"; fi
}

assert_contains() { # haystack, needle, name
  case "$1" in
    *"$2"*) ok "$3" ;;
    *) nope "$3" "expected to contain [$2], got [$(printf '%s' "$1" | head -c 200)]" ;;
  esac
}

assert_not_contains() { # haystack, needle, name
  case "$1" in
    *"$2"*) nope "$3" "expected NOT to contain [$2]" ;;
    *) ok "$3" ;;
  esac
}

assert_empty() { # value, name
  if [ -z "$1" ]; then ok "$2"; else nope "$2" "expected empty, got [$(printf '%s' "$1" | head -c 200)]"; fi
}

assert_file_exists() { # path, name
  if [ -e "$1" ]; then ok "$2"; else nope "$2" "missing: $1"; fi
}

assert_file_absent() { # path, name
  if [ -e "$1" ]; then nope "$2" "should not exist: $1"; else ok "$2"; fi
}

# ---------------------------------------------------------------------------
# Vault fixtures
# ---------------------------------------------------------------------------

# build_vault <name> [--no-git] [--no-identity] [--no-remote] [--empty]
# Echoes the vault path. Default: a git repo with an identity, a bare remote, and one commit.
build_vault() {
  local name="$1"; shift
  local do_git=1 identity=1 remote=1 seed=1
  while [ $# -gt 0 ]; do
    case "$1" in
      --no-git) do_git=0 ;;
      --no-identity) identity=0 ;;
      --no-remote) remote=0 ;;
      --empty) seed=0 ;;
    esac
    shift
  done

  local v="$TEST_TMP/$name"
  mkdir -p "$v/Projects"
  printf '# Notes\n' > "$v/Projects/Note.md"

  if [ "$do_git" -eq 1 ]; then
    git -C "$v" init -q
    git -C "$v" symbolic-ref HEAD refs/heads/main
    if [ "$identity" -eq 1 ]; then
      git -C "$v" config user.email "test@example.invalid"
      git -C "$v" config user.name "Test"
    else
      # --no-identity must mean git can find NO identity, not merely none set on this repo.
      # Otherwise git falls back to the global config (CI runners and most developer machines
      # have one), the commit succeeds, and the test asserts against the wrong failure. Empty
      # strings are what git itself treats as unset for this purpose.
      git -C "$v" config user.email ""
      git -C "$v" config user.name ""
    fi
    # Never let a developer's global hooks or signing config perturb a fixture.
    git -C "$v" config commit.gpgsign false
    git -C "$v" config core.hooksPath /dev/null

    if [ "$seed" -eq 1 ] && [ "$identity" -eq 1 ]; then
      git -C "$v" add -A >/dev/null 2>&1
      git -C "$v" commit -qm "seed" >/dev/null 2>&1
    fi
    if [ "$remote" -eq 1 ]; then
      local r="$TEST_TMP/$name.remote.git"
      git init -q --bare "$r"
      # `git init --bare` names the initial branch from init.defaultBranch, which is unset on a
      # stock Linux box (so: master) and commonly `main` on a developer's machine. The fixture
      # above pins the working repo to `main`, so without this the bare HEAD dangles at
      # refs/heads/master, `git clone` of this remote checks nothing out, and any test that
      # clones it silently tests nothing. Pin both ends instead of inheriting global config.
      git --git-dir="$r" symbolic-ref HEAD refs/heads/main
      git -C "$v" remote add origin "$r"
      if [ "$seed" -eq 1 ] && [ "$identity" -eq 1 ]; then
        git -C "$v" push -q -u origin main >/dev/null 2>&1
      fi
    fi
  fi

  printf '%s' "$v"
}

# run_hook <hook-name> <vault-path> [stdin-payload]
# Captures combined output; sets HOOK_RC. Always isolates HOME so the config-file tier
# cannot pick up the developer's real ~/.claude/obsidian-vault.
run_hook() {
  local hook="$1" vault="$2" payload="${3-}"
  local fake_home="$TEST_TMP/home.$$"
  mkdir -p "$fake_home"
  HOOK_OUT="$(printf '%s' "$payload" \
    | env -u COPILOT_CLI HOME="$fake_home" DEVWB_VAULT="$vault" bash "$HOOKS/$hook" 2>&1)"
  HOOK_RC=$?
  return 0
}

# run_hook_no_vault <hook-name> — no env var, no config file, isolated HOME.
run_hook_no_vault() {
  local hook="$1"
  local fake_home="$TEST_TMP/home.novault.$$"
  mkdir -p "$fake_home"
  # shellcheck disable=SC2034  # consumed by the sourcing suite
  HOOK_OUT="$(printf '' | env -u DEVWB_VAULT HOME="$fake_home" bash "$HOOKS/$hook" 2>&1)"
  # shellcheck disable=SC2034  # consumed by the sourcing suite
  HOOK_RC=$?
  return 0
}

# Convenience git queries against a fixture vault.
gitq()      { git -C "$1" "${@:2}" 2>/dev/null; }
head_msg()  { git -C "$1" log -1 --format=%s 2>/dev/null; }
commit_ct() { git -C "$1" rev-list --count HEAD 2>/dev/null || echo 0; }
staged_ct() { git -C "$1" diff --cached --name-only 2>/dev/null | grep -c . | tr -d ' '; }
tracked()   { git -C "$1" ls-files 2>/dev/null; }

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

finish() {
  printf '\n'
  if [ "$FAIL" -eq 0 ]; then
    printf '\033[32m%d passed\033[0m\n' "$PASS"
    exit 0
  fi
  printf '\033[31m%d failed\033[0m, %d passed\n' "$FAIL" "$PASS"
  for n in "${FAILED_NAMES[@]}"; do printf '  - %s\n' "$n"; done
  exit 1
}
