"""Entradas públicas do engine. Só orquestram: regras em `policy/`, IO em `ops/` e `stacks/`."""

from __future__ import annotations

import datetime
from typing import Annotated

import dagger
from dagger import Doc, Ignore, function, object_type

from . import stacks
from .ops import git, run_gate, security
from .policy import compliance, components, config, manifests, versioning
from .policy.compliance import Gate, GateResult

SourceDir = Annotated[
    dagger.Directory,
    Doc("Raiz do repositório (com platform.yaml)"),
    Ignore([".venv", "**/.venv", "**/__pycache__", "**/.pytest_cache"]),
]


class PipelineFailed(Exception):
    """Gate reprovado em modo block."""


async def _load(source: dagger.Directory) -> tuple[config.RepositoryConfig, dict[str, config.ServiceDescriptor]]:
    repo = config.parse_repository(await source.file("platform.yaml").contents())
    descriptor_paths = await source.glob(f"**/{components.DESCRIPTOR}")
    services = {}
    for path in components.discover(descriptor_paths, repo.component_globs):
        services[path] = config.parse_service(await source.file(f"{path}/{components.DESCRIPTOR}").contents())
    if not services:
        raise config.ConfigError(f"nenhum componente encontrado em {list(repo.component_globs)}")
    return repo, services


@object_type
class IdpEngine:
    """Pipeline portátil do plat-idplabs: `check` no PR, `release` no merge."""

    @function
    async def check(
        self,
        source: SourceDir,
        branch: Annotated[str, Doc("Branch do PR, para validar a convenção de nome")] = "",
        title: Annotated[str, Doc("Título do PR, para validar Conventional Commits")] = "",
        changed: Annotated[str, Doc("Arquivos alterados no PR, um por linha. Vazio = todos os componentes")] = "",
    ) -> str:
        """Valida o repositório e roda os gates do nível de compliance em cada componente afetado."""
        repo, services = await _load(source)
        changed_files = [f for f in changed.splitlines() if f.strip()] or None
        targets = components.affected(sorted(services), changed_files)

        results: list[GateResult] = []
        for path in targets:
            svc = services[path]
            level = repo.level_for(path)
            gates = compliance.gates_for_level(level)
            severities = compliance.blocking_severities(level)
            stack = stacks.get(svc.stack)
            src = source.directory(path)

            if Gate.CONVENTIONS in gates:
                problems = []
                if branch and not versioning.is_valid_branch(branch):
                    problems.append(f"branch '{branch}' fora do padrão <tipo>/<descricao>")
                if title and not versioning.is_valid_title(title):
                    problems.append(f"título '{title}' fora de Conventional Commits")
                results.append(GateResult(svc.name, Gate.CONVENTIONS, not problems, "; ".join(problems) or "ok"))

            image = src.docker_build()
            checks: list[tuple[Gate, dagger.Container]] = [
                (Gate.TEST, stack.test(src)),
                (Gate.LINT, stack.lint(src)),
                (Gate.SAST, stack.sast(src)),
                (Gate.SECRETS, security.secrets_scan(src)),
                (Gate.DEPENDENCY_SCAN, security.dependency_scan(src, severities)),
                (Gate.IMAGE_SCAN, security.image_scan(image, severities)),
                (Gate.SBOM, security.sbom(image)),
            ]

            if Gate.BUILD in gates:
                try:
                    await image.sync()
                    results.append(GateResult(svc.name, Gate.BUILD, True, "ok"))
                except dagger.ExecError as e:
                    results.append(GateResult(svc.name, Gate.BUILD, False, e.stderr[-300:]))
                    continue  # sem imagem, os gates seguintes não fazem sentido

            for gate, ctr in checks:
                if gate in gates:
                    passed, detail = await run_gate(ctr)
                    results.append(GateResult(svc.name, gate, passed, detail))

        summary = compliance.render_summary(results, repo.level, repo.mode)
        ok, _ = compliance.verdict(results, repo.mode)
        if not ok:
            raise PipelineFailed(summary)
        return summary

    @function
    async def release(
        self,
        source: Annotated[dagger.Directory, Doc("Raiz do repositório, COM o diretório .git e as tags")],
        repository: Annotated[str, Doc("owner/repo no GitHub, ex.: mcavalcanti81/idp-exemplo-api")],
        registry_user: Annotated[str, Doc("Usuário do registry")] = "",
        registry_token: Annotated[dagger.Secret | None, Doc("Token do registry (packages:write)")] = None,
        git_token: Annotated[dagger.Secret | None, Doc("Token com contents:write para commit e tag")] = None,
        registry: str = "ghcr.io",
        branch: str = "main",
        platform: Annotated[str, Doc("Plataforma da imagem")] = "linux/amd64",
        dry_run: Annotated[bool, Doc("Calcula versões e constrói, sem publicar nem enviar tag")] = False,
    ) -> str:
        """Calcula a versão de cada componente, publica a imagem, fixa o digest no overlay e cria a tag."""
        _, services = await _load(source)
        single = len(services) == 1
        owner = repository.split("/", 1)[0].lower()
        today = datetime.date.today().isoformat()

        files: dict[str, str] = {}
        tags: list[str] = []
        report: list[str] = []

        for path, svc in services.items():
            current_tag = await git.last_tag(source, versioning.tag_pattern(svc.name, single))
            messages = await git.commit_messages(source, current_tag, [path, f"deploy/{svc.name}"])
            commits = [c for c in map(versioning.parse_commit, messages) if c]
            current = versioning.version_from_tag(current_tag) if current_tag else None
            version = versioning.next_version(current, versioning.bump_for(commits))
            if version is None:
                report.append(f"- `{svc.name}`: nada a liberar desde {current_tag or 'o início'}")
                continue

            tag = versioning.tag_name(svc.name, version, single)
            image_repo = f"{registry}/{owner}/{svc.name}"
            image = (
                source.directory(path)
                .docker_build(platform=dagger.Platform(platform))
                .with_label("org.opencontainers.image.source", f"https://github.com/{repository}")
                .with_label("org.opencontainers.image.version", version)
            )

            if dry_run:
                await image.sync()
                digest = "sha256:dry-run"
            else:
                if registry_token is None or git_token is None:
                    raise ValueError("release real exige registry_token e git_token (ou use --dry-run)")
                ref = await image.with_registry_auth(registry, registry_user, registry_token).publish(
                    f"{image_repo}:{version}"
                )
                digest = ref.rsplit("@", 1)[-1]

            kustomization = f"deploy/{svc.name}/base/kustomization.yaml"
            files[kustomization] = manifests.pin_image(
                await source.file(kustomization).contents(), svc.name, image_repo, digest
            )
            changelog_path = f"{path}/CHANGELOG.md"
            existing = await source.file(changelog_path).contents() if changelog_path in await source.glob(changelog_path) else ""
            entry = versioning.changelog_entry(version, today, commits)
            files[changelog_path] = f"{entry}\n{existing}"
            tags.append(tag)
            report.append(f"- `{svc.name}`: {current or '—'} → **{version}** · tag `{tag}` · `{image_repo}@{digest}`")

        if tags and not dry_run:
            message = f"chore(release): {', '.join(tags)} [skip ci]"
            await git.push_release(source, files, message, tags, repository, branch, git_token)

        header = "## plat-idplabs · release" + (" (dry-run)" if dry_run else "")
        return "\n".join([header, "", *report])
