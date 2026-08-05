from __future__ import annotations

from pathlib import Path

from URDF_Exporter.standalone.adapters.inventor import (
    INVENTOR_ASSEMBLY_EXTENSIONS,
    INVENTOR_DEPENDENCY_EXTENSIONS,
    INVENTOR_OPTIONAL_ASSEMBLY_EXTENSIONS,
    InventorAdapterError,
    convert_with_inventor,
)


NATIVE_ASSEMBLY_EXTENSIONS = INVENTOR_ASSEMBLY_EXTENSIONS
NATIVE_DEPENDENCY_EXTENSIONS = INVENTOR_DEPENDENCY_EXTENSIONS
SUPPORTED_NATIVE_EXTENSIONS = NATIVE_ASSEMBLY_EXTENSIONS | NATIVE_DEPENDENCY_EXTENSIONS


def _assembly_candidates(source_dir: Path) -> list[Path]:
    candidates = [
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in NATIVE_ASSEMBLY_EXTENSIONS
    ]
    extension_priority = {
        ".iam": 0,
        ".sldasm": 1,
        ".catproduct": 2,
        ".asm": 3,
        ".jt": 4,
        ".3dxml": 5,
        ".step": 6,
        ".stp": 6,
        ".prt": 7,
        ".x_t": 8,
        ".x_b": 8,
        ".sat": 9,
        ".sab": 9,
    }
    return sorted(
        candidates,
        key=lambda path: (
            len(path.relative_to(source_dir).parts),
            extension_priority.get(path.suffix.lower(), 99),
            path.name.casefold(),
        ),
    )


def prepare_native_assembly(source_dir: str, project_name: str) -> Path | None:
    """Convert a native assembly into Petasos Exchange + STL files when present."""
    root = Path(source_dir)
    if any(root.glob("*.petasos.json")):
        return None
    candidates = _assembly_candidates(root)
    if not candidates:
        return None
    candidate = candidates[0]
    try:
        return convert_with_inventor(candidate, root, project_name)
    except InventorAdapterError:
        if candidate.suffix.lower() in INVENTOR_OPTIONAL_ASSEMBLY_EXTENSIONS:
            return None
        raise


__all__ = [
    "InventorAdapterError",
    "NATIVE_ASSEMBLY_EXTENSIONS",
    "NATIVE_DEPENDENCY_EXTENSIONS",
    "SUPPORTED_NATIVE_EXTENSIONS",
    "prepare_native_assembly",
]
