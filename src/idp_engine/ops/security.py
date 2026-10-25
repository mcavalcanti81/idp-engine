"""Scanners de segurança. Cada função devolve um container pronto para `run_gate`."""

from __future__ import annotations

import dagger
from dagger import dag

from . import GITLEAKS_IMAGE, SYFT_IMAGE, TRIVY_IMAGE

ANY = dagger.ReturnType.ANY


def secrets_scan(src: dagger.Directory) -> dagger.Container:
    return (
        dag.container()
        .from_(GITLEAKS_IMAGE)
        .with_mounted_directory("/src", src)
        .with_exec(["gitleaks", "dir", "/src", "--no-banner", "--redact"], expect=ANY)
    )


def _trivy() -> dagger.Container:
    return (
        dag.container()
        .from_(TRIVY_IMAGE)
        .with_mounted_cache("/root/.cache/trivy", dag.cache_volume("trivy-cache"))
    )


def _severity_args(severities: tuple[str, ...]) -> list[str]:
    # Sem severidade bloqueante, o scan só reporta (exit 0).
    if not severities:
        return ["--exit-code", "0"]
    return ["--exit-code", "1", "--severity", ",".join(severities), "--ignore-unfixed"]


def dependency_scan(src: dagger.Directory, severities: tuple[str, ...]) -> dagger.Container:
    return (
        _trivy()
        .with_mounted_directory("/src", src)
        .with_exec(["trivy", "fs", "--scanners", "vuln", "--quiet", *_severity_args(severities), "/src"], expect=ANY)
    )


def image_scan(image: dagger.Container, severities: tuple[str, ...]) -> dagger.Container:
    return (
        _trivy()
        .with_mounted_file("/image.tar", image.as_tarball())
        .with_exec(["trivy", "image", "--quiet", *_severity_args(severities), "--input", "/image.tar"], expect=ANY)
    )


def sbom(image: dagger.Container) -> dagger.Container:
    return (
        dag.container()
        .from_(SYFT_IMAGE)
        .with_mounted_file("/image.tar", image.as_tarball())
        .with_exec(
            ["/syft", "scan", "oci-archive:/image.tar", "-o", "spdx-json=/sbom.spdx.json", "-q"],
            expect=ANY,
        )
    )
