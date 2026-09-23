from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Callable

from URDF_Exporter.standalone.importers import ImportFailure


GENERATED_TREE_KEYS = {
    "_standalone",
    "_empty",
    "_project_name",
    "_preview_transforms",
    "_preview_units_per_meter",
    "_preview_up_axis",
    "_cad_snap_features",
    "_mesh_revision",
}

COMPONENT_REFERENCE_KEYS = {
    "component",
    "parent_component",
    "child_component",
}


def _normalized_path(part: dict[str, Any]) -> str:
    value = part.get("assembly_path")
    if not isinstance(value, list) or not value:
        return ""
    return "/".join(str(item).strip().casefold() for item in value if str(item).strip())


def _normalized_value(part: dict[str, Any], key: str) -> str:
    value = str(part.get(key) or "").strip()
    return value.casefold()


def _unique_index(
    parts: list[dict[str, Any]],
    available: set[int],
    key_function: Callable[[dict[str, Any]], str],
) -> dict[str, int]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index in available:
        key = key_function(parts[index])
        if key:
            grouped[key].append(index)
    return {
        key: indices[0]
        for key, indices in grouped.items()
        if len(indices) == 1
    }


def match_reimported_parts(
    previous_parts: list[dict[str, Any]],
    fresh_parts: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], list[str], list[str]]:
    """Match old component names to freshly imported component names.

    Stable assembly paths are preferred. Exact component names are next, then
    manifest part IDs and source filenames. Each key must be unique on both
    sides so an ambiguous CAD assembly is never merged silently.
    """

    old_available = set(range(len(previous_parts)))
    new_available = set(range(len(fresh_parts)))
    matches: dict[int, int] = {}
    methods: dict[int, str] = {}
    strategies: list[tuple[str, Callable[[dict[str, Any]], str]]] = [
        ("assembly_path", _normalized_path),
        ("name", lambda part: _normalized_value(part, "name")),
        ("part_id", lambda part: _normalized_value(part, "part_id")),
        ("source_file", lambda part: _normalized_value(part, "source_file")),
    ]

    for method, key_function in strategies:
        old_index = _unique_index(previous_parts, old_available, key_function)
        new_index = _unique_index(fresh_parts, new_available, key_function)
        for key in sorted(old_index.keys() & new_index.keys()):
            old_position = old_index[key]
            new_position = new_index[key]
            matches[old_position] = new_position
            methods[old_position] = method
            old_available.remove(old_position)
            new_available.remove(new_position)

    component_mapping = {
        str(previous_parts[old_index].get("name")): str(
            fresh_parts[new_index].get("name")
        )
        for old_index, new_index in matches.items()
    }
    match_methods = {
        str(previous_parts[old_index].get("name")): methods[old_index]
        for old_index in matches
    }
    removed = [
        str(previous_parts[index].get("name") or previous_parts[index].get("part_id"))
        for index in sorted(old_available)
    ]
    added = [
        str(fresh_parts[index].get("name") or fresh_parts[index].get("part_id"))
        for index in sorted(new_available)
    ]
    return component_mapping, match_methods, removed, added


def _replace_component_references(value: Any, mapping: dict[str, str], key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            item_key: _replace_component_references(item_value, mapping, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        if key == "components":
            return [mapping.get(str(item), str(item)) for item in value]
        return [_replace_component_references(item, mapping, key) for item in value]
    if isinstance(value, str) and key in COMPONENT_REFERENCE_KEYS:
        return mapping.get(value, value)
    return value


def _part_changed(previous: dict[str, Any], fresh: dict[str, Any]) -> bool:
    previous_digest = str(previous.get("source_sha256") or "")
    fresh_digest = str(fresh.get("source_sha256") or "")
    if previous_digest and fresh_digest and previous_digest != fresh_digest:
        return True
    for key in ("position_mm", "rotation_rpy", "physical"):
        if previous.get(key) != fresh.get(key):
            return True
    return False


def merge_reimported_state(
    previous_state: dict[str, Any],
    fresh_state: dict[str, Any],
    edited_tree: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep user link/joint edits while replacing imported CAD-derived data."""

    previous_parts = previous_state.get("parts") or []
    fresh_parts = fresh_state.get("parts") or []
    previous_tree = edited_tree or previous_state.get("tree")
    if not isinstance(previous_tree, dict) or not previous_tree.get("name"):
        raise ImportFailure("보존할 기존 편집 트리가 올바르지 않습니다.")
    if not previous_parts or not fresh_parts:
        raise ImportFailure("기존 부품과 업데이트 부품 정보를 비교할 수 없습니다.")

    mapping, methods, removed, added = match_reimported_parts(
        previous_parts,
        fresh_parts,
    )
    if removed or added:
        details = []
        if removed:
            details.append("기존에서 사라짐: " + ", ".join(removed[:8]))
        if added:
            details.append("새로 추가됨: " + ", ".join(added[:8]))
        raise ImportFailure(
            "이번 버전의 CAD 업데이트는 동일한 부품 구성을 안전하게 매칭할 때만 "
            "편집 내용을 보존합니다. " + " / ".join(details)
        )

    merged_tree = _replace_component_references(
        copy.deepcopy(previous_tree),
        mapping,
    )
    fresh_tree = fresh_state.get("tree") or {}
    for key in GENERATED_TREE_KEYS:
        if key in fresh_tree:
            merged_tree[key] = copy.deepcopy(fresh_tree[key])
        else:
            merged_tree.pop(key, None)

    fresh_by_name = {
        str(part.get("name")): part for part in fresh_parts
    }
    previous_by_name = {
        str(part.get("name")): part for part in previous_parts
    }
    changed = []
    unchanged = []
    for old_name, new_name in mapping.items():
        target = changed if _part_changed(
            previous_by_name[old_name],
            fresh_by_name[new_name],
        ) else unchanged
        target.append(new_name)

    reimport_report = {
        "matched_parts": len(mapping),
        "changed_parts": sorted(changed),
        "unchanged_parts": sorted(unchanged),
        "renamed_parts": {
            old_name: new_name
            for old_name, new_name in mapping.items()
            if old_name != new_name
        },
        "match_methods": methods,
        "preserved_link_groups": True,
        "preserved_joints": True,
    }
    report = copy.deepcopy(fresh_state.get("report") or fresh_tree.get("_import_report") or {})
    warnings = list(report.get("warnings") or [])
    warnings.append({
        "severity": "info",
        "code": "cad_reimport_preserved_edits",
        "message": (
            f"CAD 업데이트 완료: {len(mapping)}개 부품을 다시 연결하고 "
            "기존 링크 그룹과 조인트 편집을 유지했습니다."
        ),
    })
    report["warnings"] = warnings
    report["reimport"] = reimport_report
    merged_tree["_import_report"] = report
    merged_tree["_reimport_report"] = reimport_report

    result = copy.deepcopy(fresh_state)
    result["tree"] = merged_tree
    result["report"] = report
    active_workspace = (
        previous_state.get("active_workspace_name")
        or previous_tree.get("_active_workspace_name")
    )
    if active_workspace:
        result["active_workspace_name"] = active_workspace
        merged_tree["_active_workspace_name"] = active_workspace
    return result
