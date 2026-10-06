"""Repair center-of-mass units in projects saved by the old Inventor adapter."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path


def _same_vector(actual, expected) -> bool:
    try:
        return len(actual) == len(expected) == 3 and all(
            math.isfinite(float(value))
            and math.isclose(float(value), float(reference), rel_tol=1e-6, abs_tol=1e-9)
            for value, reference in zip(actual, expected)
        )
    except (TypeError, ValueError):
        return False


def repair_legacy_inventor_com(state: dict, project_dir: Path) -> tuple[dict, list[dict]]:
    """Return a corrected copy only for identifiable pre-fix Inventor data."""

    result = copy.deepcopy(state)
    if result.get("physical_com_schema", 0) >= 2:
        return result, []
    report = result.get("report") or {}
    if report.get("source_application") != "Autodesk Inventor":
        return result, []

    source_path = Path(project_dir) / "sources" / "inventor-import.petasos.json"
    if not source_path.is_file():
        # A third-party upload can claim Inventor as its source application;
        # only direct adapter imports are known to have the historical bug.
        other_manifests = list((Path(project_dir) / "sources").glob("*.petasos.json"))
        if (other_manifests or
                report.get("import_mode") not in {"inventor_safe", "inventor_direct"}):
            return result, []
        return result, [{
            "code": "legacy_inventor_manifest_missing",
            "severity": "error",
            "message": "기존 Inventor 물성값을 복구할 원본 매니페스트가 없습니다.",
        }]
    try:
        manifest = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return result, [{
            "code": "legacy_inventor_manifest_invalid",
            "severity": "error",
            "message": "기존 Inventor 물성 원본을 읽을 수 없습니다.",
        }]
    adapter = str((manifest.get("source") or {}).get("adapter") or "")
    if not adapter.startswith("petasos-inventor-"):
        return result, []

    saved_inertial = result.get("inertial") or {}
    raw_parts = manifest.get("parts") or []
    changes: dict[str, list[float]] = {}
    diagnostics: list[dict] = []
    for raw_part in raw_parts:
        part_id = raw_part.get("id")
        physical = raw_part.get("physical") or {}
        if physical.get("provenance") != "inventor_mass_properties":
            continue
        if physical.get("center_of_mass_units") == "mm":
            continue
        if physical.get("center_of_mass_units") not in (None, "m"):
            diagnostics.append({
                "code": "legacy_inventor_unit_unknown",
                "severity": "error",
                "targets": [part_id],
                "message": "원본 무게중심 단위를 확인할 수 없습니다.",
            })
            continue
        raw_center = physical.get("center_of_mass")
        saved = saved_inertial.get(part_id)
        if not isinstance(saved, dict) or not isinstance(raw_center, list) or len(raw_center) != 3:
            diagnostics.append({
                "code": "legacy_inventor_part_missing",
                "severity": "error",
                "targets": [part_id],
                "message": "저장된 부품 물성과 원본을 연결할 수 없습니다.",
            })
            continue
        if _same_vector(saved.get("center_of_mass"), raw_center):
            continue
        if not _same_vector(saved.get("center_of_mass"), [float(value) / 1000 for value in raw_center]):
            diagnostics.append({
                "code": "legacy_inventor_center_modified",
                "severity": "error",
                "targets": [part_id],
                "message": "저장된 무게중심이 기존 오류 형태와 달라 자동 복구하지 않았습니다.",
            })
            continue
        changes[part_id] = [float(value) for value in raw_center]

    if diagnostics:
        return copy.deepcopy(state), diagnostics
    for part_id, center in changes.items():
        result["inertial"][part_id]["center_of_mass"] = center
    for part in result.get("parts") or []:
        part_id = part.get("part_id")
        if part_id in changes and isinstance(part.get("physical"), dict):
            part["physical"]["center_of_mass"] = list(changes[part_id])
    result["physical_com_schema"] = 2
    return result, []
