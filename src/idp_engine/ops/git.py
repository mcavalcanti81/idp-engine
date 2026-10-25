"""Leitura de histórico e publicação de commit + tag de release."""

from __future__ import annotations

import dagger
from dagger import dag

from . import GIT_IMAGE

RECORD_SEP = "\x1e"


def _git(repo: dagger.Directory) -> dagger.Container:
    return (
        dag.container()
        .from_(GIT_IMAGE)
        .with_exec(["apk", "add", "--no-cache", "git"])
        .with_directory("/repo", repo)
        .with_workdir("/repo")
        .with_exec(["git", "config", "--global", "--add", "safe.directory", "/repo"])
    )


async def last_tag(repo: dagger.Directory, pattern: str) -> str | None:
    # git describe sai com 128 quando não há tag; o Dagger trata 128 como erro mesmo com expect=ANY.
    out = await _git(repo).with_exec(
        ["sh", "-c", 'git describe --tags --abbrev=0 --match "$1" 2>/dev/null || true', "_", pattern]
    ).stdout()
    return out.strip() or None


async def commit_messages(repo: dagger.Directory, since: str | None, paths: list[str]) -> list[str]:
    rev = f"{since}..HEAD" if since else "HEAD"
    out = await _git(repo).with_exec(["git", "log", f"--format=%B{RECORD_SEP}", rev, "--", *paths]).stdout()
    return [m.strip() for m in out.split(RECORD_SEP) if m.strip()]


async def push_release(
    repo: dagger.Directory,
    files: dict[str, str],
    message: str,
    tags: list[str],
    repository: str,
    branch: str,
    token: dagger.Secret,
) -> str:
    """Grava os arquivos, cria um commit e as tags anotadas e envia tudo ao GitHub."""
    ctr = _git(repo).with_exec(["git", "config", "user.name", "plat-idplabs-release"]).with_exec(
        ["git", "config", "user.email", "release@plat-idplabs.local"]
    )
    for path, contents in files.items():
        ctr = ctr.with_new_file(f"/repo/{path}", contents)
    ctr = ctr.with_exec(["git", "add", *files.keys()]).with_exec(["git", "commit", "-m", message])
    for tag in tags:
        ctr = ctr.with_exec(["git", "tag", "-a", tag, "-m", tag])
    refs = " ".join([f"HEAD:refs/heads/{branch}", *[f"refs/tags/{t}" for t in tags]])
    ctr = ctr.with_secret_variable("GIT_TOKEN", token).with_exec(
        [
            "sh",
            "-c",
            f'git push "https://x-access-token:${{GIT_TOKEN}}@github.com/{repository}.git" {refs}',
        ]
    )
    return await ctr.with_exec(["git", "log", "--oneline", "-1"]).stdout()
