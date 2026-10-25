"""Níveis de compliance cumulativos (ADR-0006, seção 3 de ci-cd-gitops-template.md)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Gate(str, Enum):
    BUILD = "build"
    TEST = "test"
    CONVENTIONS = "conventions"
    LINT = "lint"
    SECRETS = "secrets-scan"
    SAST = "sast"
    DEPENDENCY_SCAN = "dependency-scan"
    IMAGE_SCAN = "image-scan"
    SBOM = "sbom"


# Cada nível acrescenta gates ao anterior.
_ADDED_AT_LEVEL: dict[int, tuple[Gate, ...]] = {
    0: (Gate.BUILD, Gate.TEST),
    1: (Gate.CONVENTIONS, Gate.LINT, Gate.SECRETS, Gate.SAST),
    2: (Gate.DEPENDENCY_SCAN, Gate.IMAGE_SCAN, Gate.SBOM),
    3: (),  # proveniência SLSA e aprovação por ambiente: ainda não implementados no engine
}

# Severidade mínima de vulnerabilidade que reprova o gate, por nível.
_BLOCKING_SEVERITIES: dict[int, tuple[str, ...]] = {
    0: (),
    1: (),
    2: ("CRITICAL",),
    3: ("HIGH", "CRITICAL"),
}


def gates_for_level(level: int) -> list[Gate]:
    if level not in _ADDED_AT_LEVEL:
        raise ValueError(f"nível de compliance desconhecido: {level}")
    gates: list[Gate] = []
    for lvl in range(level + 1):
        gates.extend(_ADDED_AT_LEVEL[lvl])
    return gates


def blocking_severities(level: int) -> tuple[str, ...]:
    return _BLOCKING_SEVERITIES[level]


@dataclass(frozen=True)
class GateResult:
    component: str
    gate: Gate
    passed: bool
    detail: str = ""


def verdict(results: list[GateResult], mode: str) -> tuple[bool, str]:
    """Decide se o pipeline falha. Em `observe`/`warn` nunca falha; em `block` falha se algum gate reprovou."""
    failed = [r for r in results if not r.passed]
    if not failed:
        return True, "todos os gates passaram"
    summary = f"{len(failed)} gate(s) reprovado(s)"
    if mode == "block":
        return False, summary
    return True, f"{summary} (modo {mode}: não bloqueia)"


def render_summary(results: list[GateResult], level: int, mode: str) -> str:
    ok, message = verdict(results, mode)
    lines = [
        f"## plat-idplabs · check · nível {level} · modo {mode}",
        "",
        "| Componente | Gate | Resultado | Detalhe |",
        "|---|---|---|---|",
    ]
    for r in results:
        icon = "✅" if r.passed else "❌"
        detail = r.detail.replace("\n", " ").replace("|", "\\|")[:200]
        lines.append(f"| `{r.component}` | {r.gate.value} | {icon} | {detail} |")
    lines += ["", f"**{'Aprovado' if ok else 'Reprovado'}:** {message}"]
    return "\n".join(lines)
