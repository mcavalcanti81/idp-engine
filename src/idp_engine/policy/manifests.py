"""Edição do `kustomization.yaml` base na release: fixa a imagem por digest."""

from __future__ import annotations

import yaml


def pin_image(kustomization_text: str, image_name: str, new_name: str, digest: str) -> str:
    """Grava `images: [{name, newName, digest}]`, substituindo uma entrada existente para `image_name`."""
    data = yaml.safe_load(kustomization_text) or {}
    images = [i for i in data.get("images", []) if i.get("name") != image_name]
    images.append({"name": image_name, "newName": new_name, "digest": digest})
    data["images"] = images
    return yaml.safe_dump(data, sort_keys=False)
