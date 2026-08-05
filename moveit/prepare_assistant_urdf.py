from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def prepare_assistant_urdf(
    source_path: Path,
    output_path: Path | None = None,
) -> dict:
    """Remove control-only XML that MoveIt Setup Assistant recreates."""
    source_path = Path(source_path)
    output_path = Path(output_path) if output_path is not None else source_path
    tree = ElementTree.parse(source_path)
    root = tree.getroot()
    removed_controls = 0
    removed_transmissions = 0
    removed_gazebo_plugins = 0

    for child in list(root):
        name = _local_name(child.tag)
        if name == "ros2_control":
            root.remove(child)
            removed_controls += 1
            continue
        if name == "transmission":
            root.remove(child)
            removed_transmissions += 1
            continue
        if name != "gazebo":
            continue

        for plugin in list(child):
            if _local_name(plugin.tag) != "plugin":
                continue
            filename = (plugin.get("filename") or "").lower()
            plugin_name = (plugin.get("name") or "").lower()
            if "ros2_control" in filename or plugin_name == "control":
                child.remove(plugin)
                removed_gazebo_plugins += 1
        if not list(child) and not (child.text or "").strip():
            root.remove(child)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ElementTree.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return {
        "source": str(source_path),
        "output": str(output_path),
        "removed_ros2_control": removed_controls,
        "removed_transmissions": removed_transmissions,
        "removed_gazebo_plugins": removed_gazebo_plugins,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("urdf", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = prepare_assistant_urdf(args.urdf, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
