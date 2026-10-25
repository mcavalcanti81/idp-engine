"""Stack Python: projeto com pyproject.toml e uv.lock, testes em pytest."""

from __future__ import annotations

import dagger
from dagger import dag

UV_IMAGE = "ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim"
ANY = dagger.ReturnType.ANY


def _base(src: dagger.Directory) -> dagger.Container:
    return (
        dag.container()
        .from_(UV_IMAGE)
        .with_mounted_cache("/root/.cache/uv", dag.cache_volume("uv-cache"))
        .with_env_variable("UV_LINK_MODE", "copy")
        .with_directory("/src", src, exclude=[".venv", "**/__pycache__"])
        .with_workdir("/src")
    )


def test(src: dagger.Directory) -> dagger.Container:
    return _base(src).with_exec(["uv", "sync", "--frozen"]).with_exec(["uv", "run", "pytest", "-q"], expect=ANY)


def lint(src: dagger.Directory) -> dagger.Container:
    return _base(src).with_exec(["uvx", "ruff@0.8.4", "check", "."], expect=ANY)


def sast(src: dagger.Directory) -> dagger.Container:
    return _base(src).with_exec(
        ["uvx", "bandit@1.8.0", "-r", ".", "-q", "-x", "./tests,./.venv"], expect=ANY
    )
