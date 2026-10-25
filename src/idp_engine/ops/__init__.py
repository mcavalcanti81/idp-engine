"""Operações com IO (containers, registry, git). Decisões ficam em `policy/`."""

from __future__ import annotations

import dagger

TRIVY_IMAGE = "aquasec/trivy:0.58.1"
GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.21.2"
SYFT_IMAGE = "anchore/syft:v1.18.1"
GIT_IMAGE = "alpine:3.20"


async def run_gate(ctr: dagger.Container) -> tuple[bool, str]:
    """Executa o container e devolve (passou?, últimas linhas da saída)."""
    ctr = await ctr.sync()
    code = await ctr.exit_code()
    out = (await ctr.stdout()) + (await ctr.stderr())
    tail = " ".join(out.strip().splitlines()[-3:])
    return code == 0, tail if code != 0 else "ok"
