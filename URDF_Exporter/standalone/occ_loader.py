from __future__ import annotations

import importlib.util
import os
import site
import sys


_OCP_MODULE = None


def load_ocp():
    """Expose cadquery-ocp's native module as ``OCP`` on Windows.

    Some Python 3.13 installations package the native extension below a
    lowercase ``ocp`` directory without registering the uppercase module name.
    """

    global _OCP_MODULE
    if _OCP_MODULE is not None:
        return _OCP_MODULE
    try:
        import OCP  # type: ignore
        _OCP_MODULE = OCP
        return OCP
    except ImportError:
        pass

    candidates: list[str] = []
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    candidates.extend(path for path in sys.path if path)

    for site_packages in dict.fromkeys(candidates):
        ocp_dir = os.path.join(site_packages, "ocp")
        if not os.path.isdir(ocp_dir):
            continue
        for library_dir in (
            os.path.join(site_packages, "cadquery_ocp.libs"),
            os.path.join(site_packages, "vtk.libs"),
        ):
            if os.path.isdir(library_dir) and hasattr(os, "add_dll_directory"):
                os.add_dll_directory(library_dir)
        native = next(
            (
                os.path.join(ocp_dir, name)
                for name in os.listdir(ocp_dir)
                if name.startswith("OCP.") and name.endswith((".pyd", ".so"))
            ),
            None,
        )
        if not native:
            continue
        spec = importlib.util.spec_from_file_location("OCP", native)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["OCP"] = module
        _OCP_MODULE = module
        return module
    raise ModuleNotFoundError("OpenCascade native module could not be loaded")

