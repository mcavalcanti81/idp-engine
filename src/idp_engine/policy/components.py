"""Descoberta de componentes: todo diretório coberto por `layout.components` com um `service.yaml`."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

DESCRIPTOR = "service.yaml"


def discover(descriptor_paths: list[str], globs: tuple[str, ...]) -> list[str]:
    """Recebe os caminhos de todos os `service.yaml` do repo e devolve os diretórios de componente.

    >>> discover(["apps/a/service.yaml", "tools/x/service.yaml"], ("apps/*",))
    ['apps/a']
    """
    found = set()
    for path in descriptor_paths:
        p = PurePosixPath(path)
        if p.name != DESCRIPTOR:
            continue
        directory = str(p.parent)
        if any(fnmatch(directory, g.rstrip("/")) for g in globs):
            found.add(directory)
    return sorted(found)


def affected(components: list[str], changed_files: list[str] | None) -> list[str]:
    """Componentes tocados pelo diff. Sem diff conhecido (None), todos são afetados.

    Mudanças fora de qualquer componente (ex.: platform.yaml) também afetam todos,
    porque podem mudar nível de compliance ou versão do engine.
    """
    if changed_files is None:
        return list(components)
    hit = set()
    for f in changed_files:
        owners = [c for c in components if f == c or f.startswith(c + "/")]
        if not owners:
            return list(components)
        hit.update(owners)
    return [c for c in components if c in hit]
