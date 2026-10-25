"""Conventional Commits, bump SemVer e formato de tag (ADR-0006, seção 4)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

_HEADER = re.compile(r"^(?P<type>[a-z]+)(\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<subject>.+)$")
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_BRANCH = re.compile(r"^(feat|fix|chore|docs|refactor|test|ci|perf|build|release)/[a-z0-9][a-z0-9._-]*$")

TYPES = ("feat", "fix", "chore", "docs", "refactor", "test", "ci", "perf", "build", "style", "revert")
INITIAL_VERSION = "0.1.0"


class Bump(IntEnum):
    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3


@dataclass(frozen=True)
class Commit:
    type: str
    scope: str | None
    subject: str
    breaking: bool


def parse_commit(message: str) -> Commit | None:
    """Interpreta a mensagem de commit. Devolve None se não segue Conventional Commits."""
    header, _, body = message.strip().partition("\n")
    m = _HEADER.match(header.strip())
    if not m or m["type"] not in TYPES:
        return None
    breaking = bool(m["breaking"]) or "BREAKING CHANGE:" in body
    return Commit(type=m["type"], scope=m["scope"], subject=m["subject"], breaking=breaking)


def is_valid_title(title: str) -> bool:
    return parse_commit(title) is not None


def is_valid_branch(branch: str) -> bool:
    return branch in ("main", "master") or bool(_BRANCH.match(branch))


def bump_for(commits: list[Commit]) -> Bump:
    bump = Bump.NONE
    for c in commits:
        if c.breaking:
            return Bump.MAJOR
        if c.type == "feat":
            bump = max(bump, Bump.MINOR)
        elif c.type in ("fix", "perf"):
            bump = max(bump, Bump.PATCH)
    return bump


def next_version(current: str | None, bump: Bump) -> str | None:
    """Próxima versão. `current=None` significa que o componente nunca foi liberado."""
    if bump is Bump.NONE:
        return None
    if current is None:
        return INITIAL_VERSION
    m = _SEMVER.match(current)
    if not m:
        raise ValueError(f"versão atual não é SemVer: {current!r}")
    major, minor, patch = (int(x) for x in m.groups())
    if bump is Bump.MAJOR:
        # Antes da 1.0.0, breaking change sobe o minor (convenção SemVer para 0.x).
        return f"{major}.{minor + 1}.0" if major == 0 else f"{major + 1}.0.0"
    if bump is Bump.MINOR:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def tag_name(component: str, version: str, single_component: bool) -> str:
    """`v1.4.0` em repo de um componente; `<componente>/v1.4.0` em monorepo."""
    return f"v{version}" if single_component else f"{component}/v{version}"


def tag_pattern(component: str, single_component: bool) -> str:
    return "v*" if single_component else f"{component}/v*"


def version_from_tag(tag: str) -> str:
    return tag.rsplit("/", 1)[-1].removeprefix("v")


def changelog_entry(version: str, date: str, commits: list[Commit]) -> str:
    sections = {"Quebra de compatibilidade": [], "Novidades": [], "Correções": []}
    for c in commits:
        line = f"- {c.subject}" + (f" ({c.scope})" if c.scope else "")
        if c.breaking:
            sections["Quebra de compatibilidade"].append(line)
        elif c.type == "feat":
            sections["Novidades"].append(line)
        elif c.type in ("fix", "perf"):
            sections["Correções"].append(line)
    out = [f"## {version} — {date}", ""]
    for title, lines in sections.items():
        if lines:
            out += [f"### {title}", "", *lines, ""]
    return "\n".join(out)
