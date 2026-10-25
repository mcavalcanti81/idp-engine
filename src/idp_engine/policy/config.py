"""Leitura e validação do `platform.yaml` (kind: Repository) e do `service.yaml` (kind: Service)."""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

API_VERSION = "plat-idplabs/v1"
MODES = ("observe", "warn", "block")


class ConfigError(ValueError):
    """Arquivo de configuração inválido. A mensagem lista todos os problemas encontrados."""


@dataclass(frozen=True)
class Environment:
    name: str
    namespace: str
    cluster: str = "in-cluster"
    auto_promote: bool = False
    approvers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComponentOverride:
    path: str
    level: int | None = None


@dataclass(frozen=True)
class RepositoryConfig:
    system: str
    owner: str
    level: int
    mode: str
    engine_version: str
    component_globs: tuple[str, ...]
    environments_repo: str
    environments: tuple[Environment, ...]
    overrides: tuple[ComponentOverride, ...] = field(default=())

    def level_for(self, component_path: str) -> int:
        for override in self.overrides:
            if override.path.rstrip("/") == component_path.rstrip("/") and override.level is not None:
                return override.level
        return self.level


@dataclass(frozen=True)
class ServiceDescriptor:
    name: str
    owner: str
    system: str
    type: str
    pipeline_template: str

    @property
    def stack(self) -> str:
        """Stack do engine que constrói o componente: `python-api/release@v1` → `python`."""
        return self.pipeline_template.split("/", 1)[0].split("-", 1)[0]


def _require(data: dict, path: str, errors: list[str]):
    node = data
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            errors.append(f"campo obrigatório ausente: {path}")
            return None
        node = node[key]
    return node


def _check_header(data: object, kind: str, errors: list[str]) -> dict:
    if not isinstance(data, dict):
        raise ConfigError(f"esperado um mapa YAML com kind: {kind}")
    if data.get("apiVersion") != API_VERSION:
        errors.append(f"apiVersion deve ser {API_VERSION}, veio {data.get('apiVersion')!r}")
    if data.get("kind") != kind:
        errors.append(f"kind deve ser {kind}, veio {data.get('kind')!r}")
    return data


def parse_repository(text: str) -> RepositoryConfig:
    errors: list[str] = []
    data = _check_header(yaml.safe_load(text), "Repository", errors)

    system = _require(data, "metadata.system", errors)
    owner = _require(data, "metadata.owner", errors)
    level = _require(data, "spec.compliance.level", errors)
    mode = data.get("spec", {}).get("compliance", {}).get("mode", "block")
    engine_version = _require(data, "spec.engine.version", errors)
    globs = _require(data, "spec.layout.components", errors) or []
    envs_repo = _require(data, "spec.delivery.environmentsRepo", errors)
    raw_envs = _require(data, "spec.delivery.environments", errors) or []

    if level is not None and level not in (0, 1, 2, 3):
        errors.append(f"spec.compliance.level deve ser 0, 1, 2 ou 3, veio {level!r}")
    if mode not in MODES:
        errors.append(f"spec.compliance.mode deve ser um de {MODES}, veio {mode!r}")
    if engine_version in ("latest", "main"):
        errors.append("spec.engine.version precisa ser uma versão fixa (ex.: v0.1.0), não 'latest'/'main'")

    environments = []
    for env in raw_envs:
        if not isinstance(env, dict) or "name" not in env or "namespace" not in env:
            errors.append(f"ambiente inválido (precisa de name e namespace): {env!r}")
            continue
        environments.append(
            Environment(
                name=env["name"],
                namespace=str(env["namespace"]).replace("{system}", str(system)),
                cluster=env.get("cluster", "in-cluster"),
                auto_promote=bool(env.get("autoPromote", False)),
                approvers=tuple(env.get("approvers", ())),
            )
        )

    overrides = tuple(
        ComponentOverride(path=o["path"], level=o.get("compliance", {}).get("level"))
        for o in data.get("spec", {}).get("overrides", {}).get("components", [])
    )

    if errors:
        raise ConfigError("platform.yaml inválido:\n- " + "\n- ".join(errors))

    return RepositoryConfig(
        system=system,
        owner=owner,
        level=level,
        mode=mode,
        engine_version=engine_version,
        component_globs=tuple(globs),
        environments_repo=envs_repo,
        environments=tuple(environments),
        overrides=overrides,
    )


def parse_service(text: str) -> ServiceDescriptor:
    errors: list[str] = []
    data = _check_header(yaml.safe_load(text), "Service", errors)
    values = {
        "name": _require(data, "metadata.name", errors),
        "owner": _require(data, "metadata.owner", errors),
        "system": _require(data, "metadata.system", errors),
        "type": _require(data, "spec.type", errors),
        "pipeline_template": _require(data, "spec.pipelineTemplate", errors),
    }
    if errors:
        raise ConfigError("service.yaml inválido:\n- " + "\n- ".join(errors))
    return ServiceDescriptor(**values)
