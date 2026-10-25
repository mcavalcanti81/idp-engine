"""Um módulo por ecossistema. O componente escolhe a stack em `spec.pipelineTemplate` do service.yaml."""

from __future__ import annotations

from . import python

STACKS = {"python": python}


def get(stack: str):
    if stack not in STACKS:
        raise ValueError(f"stack '{stack}' ainda não suportada pelo engine (disponíveis: {sorted(STACKS)})")
    return STACKS[stack]
