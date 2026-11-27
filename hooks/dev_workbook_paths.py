"""Shared path resolution for dev-workbook's Python tools — the twin of hooks/lib.sh.

Each path resolves in the same order as the hooks:

  1. an explicit argument, then an environment variable  (DEVWB_VAULT, then the pre-3.0
     OBSIDIAN_VAULT / CODE_ROOT)
  2. ${XDG_CONFIG_HOME:-~/.config}/dev-workbook/<name>, then the pre-3.0 .../claudesidion/<name>
  3. the legacy ~/.claude/<name> file                     (obsidian-vault / code-root)
  4. a default                                            (~/ObsidianVault / ~/code)

A config file is one line; surrounding whitespace is trimmed and a leading `~` or `$HOME` is
expanded, as it is in an environment value. A configured path that is still relative is refused:
it would resolve against the working directory — the repo the user opened — so the vault resolves
to REFUSED, a path that can never exist. Keep this and lib.sh in step: the tests check they agree.
"""

from __future__ import annotations

import os
from pathlib import Path


REFUSED = Path("/dev/null/dev-workbook-vault-path-must-be-absolute")


def expand(raw: str) -> Path:
    """A leading `~` or `$HOME` expanded, as lib.sh's absolute_path does."""
    home = str(Path.home())
    if raw == "~" or raw == "$HOME":
        return Path(home)
    if raw.startswith("~/"):
        return Path(home) / raw[2:]
    if raw.startswith("$HOME/"):
        return Path(home) / raw[6:]
    return Path(raw)


def config_dir(name: str = "dev-workbook") -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".config") / name


def read_path_file(path: Path) -> Path | None:
    """The path a one-line config file names, or None when it is missing or blank."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[:1]
    except (OSError, UnicodeDecodeError):
        return None
    raw = lines[0].strip() if lines else ""
    if not raw:
        return None
    return expand(raw)


def _resolve(explicit: str | None, envs: tuple[str, ...], name: str, legacy: str,
             default: str, refused: Path) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    found = next((expand(os.environ[env]) for env in envs if os.environ.get(env, "")), None)
    found = (found
             or read_path_file(config_dir() / name)
             or read_path_file(config_dir("claudesidion") / name)
             or read_path_file(Path.home() / ".claude" / legacy)
             or Path.home() / default)
    return found if found.is_absolute() else refused


def resolve_vault(explicit: str | None = None) -> Path:
    return _resolve(explicit, ("DEVWB_VAULT", "OBSIDIAN_VAULT"), "vault", "obsidian-vault",
                    "ObsidianVault", REFUSED)


def resolve_code_root(explicit: str | None = None) -> Path:
    return _resolve(explicit, ("CODE_ROOT",), "code-root", "code-root", "code", Path.home() / "code")


def _source(envs: tuple[str, ...], name: str, legacy: str) -> str:
    if any(os.environ.get(env, "") for env in envs):
        return "env"
    if read_path_file(config_dir() / name):
        return "config"
    if read_path_file(config_dir("claudesidion") / name):
        return "legacy-config"
    if read_path_file(Path.home() / ".claude" / legacy):
        return "legacy"
    return "default"


def vault_source() -> str:
    """Which tier of `resolve_vault` (no explicit argument) supplied the vault — see `code_root_source`."""
    return _source(("DEVWB_VAULT", "OBSIDIAN_VAULT"), "vault", "obsidian-vault")


def code_root_source() -> str:
    """Which tier of `resolve_code_root` supplied the code root, in the same order as `_resolve`:
    `env`, `config`, `legacy-config` (the pre-3.0 claudesidion dir), `legacy` (~/.claude/code-root)
    or `default`."""
    return _source(("CODE_ROOT",), "code-root", "code-root")
