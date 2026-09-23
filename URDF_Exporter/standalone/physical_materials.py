# -*- coding: utf-8 -*-
"""Physical-material editing and density-based mass-property overrides."""

from __future__ import annotations

import copy
import math
import re
from typing import Any


DEFAULT_PHYSICAL_MATERIALS = {
    "aluminum_6061": {
        "name": "알루미늄 6061", "density": 2700.0,
        "rgba": "0.720 0.750 0.780 1.000", "category": "금속", "builtin": True,
    },
    "aluminum_7075": {
        "name": "알루미늄 7075", "density": 2810.0,
        "rgba": "0.680 0.710 0.750 1.000", "category": "금속", "builtin": True,
    },
    "aluminum_5052": {
        "name": "알루미늄 5052", "density": 2680.0,
        "rgba": "0.760 0.780 0.800 1.000", "category": "금속", "builtin": True,
    },
    "steel": {
        "name": "일반 강철", "density": 7850.0,
        "rgba": "0.420 0.450 0.480 1.000", "category": "금속", "builtin": True,
    },
    "stainless_steel": {
        "name": "스테인리스강 304", "density": 8000.0,
        "rgba": "0.620 0.650 0.670 1.000", "category": "금속", "builtin": True,
    },
    "stainless_steel_316": {
        "name": "스테인리스강 316", "density": 8000.0,
        "rgba": "0.660 0.680 0.700 1.000", "category": "금속", "builtin": True,
    },
    "titanium_grade_5": {
        "name": "티타늄 Grade 5", "density": 4430.0,
        "rgba": "0.500 0.530 0.570 1.000", "category": "금속", "builtin": True,
    },
    "magnesium_az31": {
        "name": "마그네슘 AZ31", "density": 1770.0,
        "rgba": "0.730 0.740 0.690 1.000", "category": "금속", "builtin": True,
    },
    "copper": {
        "name": "구리", "density": 8960.0,
        "rgba": "0.720 0.330 0.160 1.000", "category": "금속", "builtin": True,
    },
    "brass": {
        "name": "황동", "density": 8500.0,
        "rgba": "0.750 0.600 0.180 1.000", "category": "금속", "builtin": True,
    },
    "bronze": {
        "name": "청동", "density": 8800.0,
        "rgba": "0.560 0.350 0.160 1.000", "category": "금속", "builtin": True,
    },
    "zinc": {
        "name": "아연", "density": 7140.0,
        "rgba": "0.550 0.600 0.620 1.000", "category": "금속", "builtin": True,
    },
    "lead": {
        "name": "납", "density": 11340.0,
        "rgba": "0.280 0.300 0.330 1.000", "category": "금속", "builtin": True,
    },
    "tungsten": {
        "name": "텅스텐", "density": 19300.0,
        "rgba": "0.240 0.260 0.280 1.000", "category": "금속", "builtin": True,
    },
    "abs": {
        "name": "ABS", "density": 1040.0,
        "rgba": "0.160 0.180 0.200 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pom": {
        "name": "POM · 아세탈", "density": 1410.0,
        "rgba": "0.900 0.900 0.860 1.000", "category": "플라스틱", "builtin": True,
    },
    "nylon_6": {
        "name": "나일론 6", "density": 1130.0,
        "rgba": "0.840 0.820 0.720 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "polycarbonate": {
        "name": "폴리카보네이트 · PC", "density": 1200.0,
        "rgba": "0.720 0.820 0.900 0.850", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "acrylic": {
        "name": "아크릴 · PMMA", "density": 1180.0,
        "rgba": "0.780 0.880 0.920 0.800", "category": "플라스틱", "builtin": True,
    },
    "hdpe": {
        "name": "고밀도 폴리에틸렌 · HDPE", "density": 950.0,
        "rgba": "0.920 0.920 0.900 1.000", "category": "플라스틱", "builtin": True,
    },
    "polypropylene": {
        "name": "폴리프로필렌 · PP", "density": 900.0,
        "rgba": "0.820 0.850 0.860 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pvc": {
        "name": "PVC", "density": 1400.0,
        "rgba": "0.450 0.480 0.500 1.000", "category": "플라스틱", "builtin": True,
    },
    "ptfe": {
        "name": "PTFE · 테플론", "density": 2200.0,
        "rgba": "0.940 0.940 0.900 1.000", "category": "플라스틱", "builtin": True,
    },
    "pla": {
        "name": "PLA", "density": 1240.0,
        "rgba": "0.300 0.650 0.850 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pla_plus": {
        "name": "PLA+ · Tough PLA", "density": 1240.0,
        "rgba": "0.220 0.580 0.820 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pla_cf": {
        "name": "PLA-CF · 탄소섬유 PLA", "density": 1300.0,
        "rgba": "0.100 0.110 0.120 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "wood_pla": {
        "name": "Wood PLA · 목분 혼합", "density": 1200.0,
        "rgba": "0.620 0.410 0.210 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "petg": {
        "name": "PETG", "density": 1270.0,
        "rgba": "0.250 0.700 0.650 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "petg_cf": {
        "name": "PETG-CF · 탄소섬유 PETG", "density": 1350.0,
        "rgba": "0.090 0.120 0.120 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pctg": {
        "name": "PCTG", "density": 1230.0,
        "rgba": "0.280 0.700 0.760 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "asa": {
        "name": "ASA", "density": 1070.0,
        "rgba": "0.300 0.330 0.360 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "abs_cf": {
        "name": "ABS-CF · 탄소섬유 ABS", "density": 1100.0,
        "rgba": "0.080 0.090 0.100 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "hips": {
        "name": "HIPS", "density": 1040.0,
        "rgba": "0.880 0.880 0.830 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "tpu": {
        "name": "TPU", "density": 1210.0,
        "rgba": "0.320 0.320 0.350 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "tpe": {
        "name": "TPE", "density": 1100.0,
        "rgba": "0.240 0.260 0.300 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pa6_cf": {
        "name": "PA6-CF · 탄소섬유 나일론", "density": 1150.0,
        "rgba": "0.100 0.110 0.115 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pa6_gf": {
        "name": "PA6-GF · 유리섬유 나일론", "density": 1300.0,
        "rgba": "0.330 0.360 0.350 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pa12_filament": {
        "name": "PA12 · 나일론 12 필라멘트", "density": 1010.0,
        "rgba": "0.820 0.800 0.690 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pc_abs": {
        "name": "PC-ABS", "density": 1150.0,
        "rgba": "0.220 0.240 0.270 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pva_support": {
        "name": "PVA · 수용성 서포트", "density": 1230.0,
        "rgba": "0.870 0.820 0.650 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "bvoh_support": {
        "name": "BVOH · 수용성 서포트", "density": 1140.0,
        "rgba": "0.800 0.760 0.620 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pei_ultem": {
        "name": "PEI · ULTEM", "density": 1270.0,
        "rgba": "0.760 0.520 0.100 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "peek": {
        "name": "PEEK", "density": 1300.0,
        "rgba": "0.650 0.520 0.260 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pps": {
        "name": "PPS", "density": 1350.0,
        "rgba": "0.420 0.390 0.300 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "pps_cf": {
        "name": "PPS-CF · 탄소섬유 PPS", "density": 1450.0,
        "rgba": "0.070 0.080 0.085 1.000", "category": "3D 프린팅 · 필라멘트", "builtin": True,
    },
    "photopolymer_resin": {
        "name": "표준 광경화 레진", "density": 1150.0,
        "rgba": "0.760 0.500 0.760 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "abs_like_resin": {
        "name": "ABS-Like 레진", "density": 1100.0,
        "rgba": "0.380 0.420 0.480 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "tough_resin": {
        "name": "Tough · 내충격 레진", "density": 1100.0,
        "rgba": "0.260 0.480 0.760 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "flexible_resin": {
        "name": "Flexible · 탄성 레진", "density": 1050.0,
        "rgba": "0.180 0.200 0.240 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "high_temp_resin": {
        "name": "High Temp · 내열 레진", "density": 1200.0,
        "rgba": "0.620 0.300 0.180 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "castable_resin": {
        "name": "Castable · 주조용 레진", "density": 1100.0,
        "rgba": "0.460 0.200 0.680 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "water_washable_resin": {
        "name": "수세척 레진", "density": 1100.0,
        "rgba": "0.400 0.720 0.760 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "dental_model_resin": {
        "name": "덴탈 모델 레진", "density": 1170.0,
        "rgba": "0.820 0.650 0.480 1.000", "category": "3D 프린팅 · 레진", "builtin": True,
    },
    "pa12_powder": {
        "name": "PA12 분말 · SLS/MJF", "density": 1010.0,
        "rgba": "0.820 0.820 0.780 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "pa11_powder": {
        "name": "PA11 분말 · SLS", "density": 1030.0,
        "rgba": "0.760 0.780 0.720 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "tpu_powder": {
        "name": "TPU 분말 · SLS", "density": 1100.0,
        "rgba": "0.280 0.290 0.320 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "pp_powder": {
        "name": "PP 분말 · SLS", "density": 900.0,
        "rgba": "0.840 0.860 0.840 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "metal_print_316l": {
        "name": "316L · 금속 출력", "density": 8000.0,
        "rgba": "0.610 0.640 0.670 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "metal_print_alsi10mg": {
        "name": "AlSi10Mg · 금속 출력", "density": 2670.0,
        "rgba": "0.700 0.730 0.760 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "metal_print_ti6al4v": {
        "name": "Ti-6Al-4V · 금속 출력", "density": 4430.0,
        "rgba": "0.490 0.520 0.560 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "metal_print_inconel_718": {
        "name": "Inconel 718 · 금속 출력", "density": 8190.0,
        "rgba": "0.500 0.520 0.500 1.000", "category": "3D 프린팅 · 분말/금속", "builtin": True,
    },
    "carbon_fiber_composite": {
        "name": "탄소섬유 복합재 · CFRP", "density": 1600.0,
        "rgba": "0.080 0.090 0.100 1.000", "category": "복합재·탄성체", "builtin": True,
    },
    "glass_fiber_composite": {
        "name": "유리섬유 복합재 · GFRP", "density": 1850.0,
        "rgba": "0.600 0.680 0.620 1.000", "category": "복합재·탄성체", "builtin": True,
    },
    "rubber": {
        "name": "일반 고무", "density": 1100.0,
        "rgba": "0.080 0.080 0.080 1.000", "category": "복합재·탄성체", "builtin": True,
    },
    "silicone_rubber": {
        "name": "실리콘 고무", "density": 1070.0,
        "rgba": "0.720 0.720 0.750 1.000", "category": "복합재·탄성체", "builtin": True,
    },
    "polyurethane": {
        "name": "폴리우레탄 · PU", "density": 1200.0,
        "rgba": "0.650 0.480 0.160 1.000", "category": "복합재·탄성체", "builtin": True,
    },
    "plywood": {
        "name": "합판", "density": 600.0,
        "rgba": "0.650 0.450 0.240 1.000", "category": "기타", "builtin": True,
    },
}


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _rgba(value: Any) -> str:
    parts = str(value or "").replace(",", " ").split()
    if len(parts) not in {3, 4}:
        return "0.700 0.700 0.700 1.000"
    try:
        numbers = [min(1.0, max(0.0, float(part))) for part in parts]
    except ValueError:
        return "0.700 0.700 0.700 1.000"
    if len(numbers) == 3:
        numbers.append(1.0)
    return " ".join(f"{number:.3f}" for number in numbers)


def _urdf_material_name(key: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(key or "material"))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_") or "material"
    if cleaned[0].isdigit():
        cleaned = "material_" + cleaned
    return "petasos_" + cleaned[:64]


def ensure_material_editor_data(state: dict, tree: dict | None = None) -> dict:
    """Attach serialisable material-editor metadata to an editor tree."""
    target = tree if isinstance(tree, dict) else state.get("tree", {})
    if not isinstance(target, dict):
        return target

    library = target.get("_physical_materials")
    if not isinstance(library, dict):
        library = copy.deepcopy(DEFAULT_PHYSICAL_MATERIALS)
    else:
        for key, material in DEFAULT_PHYSICAL_MATERIALS.items():
            existing = library.setdefault(key, copy.deepcopy(material))
            # Category is not user-editable. Keep older saved projects aligned
            # with the current grouped library without overwriting a user's
            # custom name, density, or colour edits.
            if isinstance(existing, dict) and existing.get("builtin", True):
                existing["category"] = material.get("category", "기타")
    target["_physical_materials"] = library

    assignments = target.get("_component_material_assignments")
    if not isinstance(assignments, dict):
        assignments = {}
    target["_component_material_assignments"] = assignments

    snapshots = target.get("_component_physical")
    if not isinstance(snapshots, dict):
        snapshots = {}
    for component, physical in (state.get("inertial") or {}).items():
        if not isinstance(physical, dict):
            continue
        snapshot = snapshots.setdefault(component, {})
        for field in ("mass", "density", "volume_m3", "provenance", "confidence"):
            if field in physical:
                snapshot[field] = copy.deepcopy(physical[field])
        mass = _positive_number(snapshot.get("mass"))
        density = _positive_number(snapshot.get("density"))
        if _positive_number(snapshot.get("volume_m3")) is None and mass and density:
            snapshot["volume_m3"] = mass / density
    target["_component_physical"] = snapshots
    return target


def apply_material_overrides(
    inertial: dict,
    visual_materials: dict,
    colors: dict,
    edited_tree: dict,
) -> list[str]:
    """Apply selected density overrides before link-level rigid-body aggregation."""
    library = edited_tree.get("_physical_materials") or {}
    assignments = edited_tree.get("_component_material_assignments") or {}
    snapshots = edited_tree.get("_component_physical") or {}
    warnings: list[str] = []

    for component, key in assignments.items():
        if not key:
            continue
        material = library.get(key)
        physical = inertial.get(component)
        if not isinstance(material, dict) or not isinstance(physical, dict):
            continue
        density = _positive_number(material.get("density"))
        if density is None:
            warnings.append(f"{component}: 지정한 재질의 밀도가 올바르지 않습니다.")
            continue

        snapshot = snapshots.get(component) if isinstance(snapshots, dict) else {}
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        original_mass = _positive_number(physical.get("mass"))
        volume_m3 = _positive_number(snapshot.get("volume_m3"))
        if volume_m3 is None:
            volume_m3 = _positive_number(physical.get("volume_m3"))
        if volume_m3 is None:
            reference_density = (
                _positive_number(snapshot.get("density"))
                or _positive_number(physical.get("density"))
            )
            if original_mass and reference_density:
                volume_m3 = original_mass / reference_density
        if volume_m3 is None or original_mass is None:
            warnings.append(
                f"{component}: CAD 체적 또는 기준 밀도가 없습니다. 조립품을 다시 가져오세요."
            )
            continue

        new_mass = volume_m3 * density
        scale = new_mass / original_mass
        physical["mass"] = new_mass
        physical["inertia"] = [
            float(value) * scale for value in physical.get("inertia", [0.0] * 6)
        ]
        physical["density"] = density
        physical["volume_m3"] = volume_m3
        physical["material_override"] = str(key)
        physical["provenance"] = "material_density_override"

        urdf_name = _urdf_material_name(str(key))
        visual_materials[component] = {"material": urdf_name}
        colors[urdf_name] = _rgba(material.get("rgba"))

    return warnings
