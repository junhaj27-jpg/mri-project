from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


def _catalog_path(base_dir: Path) -> Path:
    return base_dir / "sample_data" / "model_catalog.json"


def load_model_catalog(base_dir: Path) -> dict[str, Any]:
    path = _catalog_path(base_dir)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def filter_model_catalog(
    catalog: dict[str, Any],
    body_region: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    filtered = copy.deepcopy(catalog)
    normalized_region = body_region.upper() if body_region else None
    normalized_mode = mode.upper() if mode else None

    stacks = []
    for stack in catalog.get("stacks", []):
        stack_regions = [region.upper() for region in stack.get("body_regions", [])]
        stack_mode = str(stack.get("mode", "")).upper()
        region_matches = (
            normalized_region is None
            or normalized_region in stack_regions
            or "PUBLIC_DEMO" in stack_regions
        )
        mode_matches = normalized_mode is None or stack_mode == normalized_mode
        if region_matches and mode_matches:
            stacks.append(copy.deepcopy(stack))

    filtered["stacks"] = stacks
    filtered["selected_body_region"] = normalized_region or "ALL"
    filtered["selected_mode"] = normalized_mode or "ALL"
    filtered["stack_count"] = len(stacks)
    filtered["model_count"] = sum(len(stack.get("models", [])) for stack in stacks)
    return filtered
