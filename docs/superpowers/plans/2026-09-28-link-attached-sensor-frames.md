# Link-Attached Sensor Frames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users place named sensor frames on links independently of joint origins, persist them, and export valid frames for future sensor types.

**Architecture:** Store type-neutral sensor records in `tree._sensors`, keyed to stable link IDs with a link-local pose. A focused sensor model validates and transforms records; the UI edits them in the link properties panel; the exporter resolves final link names and emits fixed frame links/joints. Module library capture/attach carries sensor records with owned links.

**Tech Stack:** Python, Flask project store, existing JavaScript/Three.js editor, Xacro/XML, unittest, Node tests.

**Spec:** `docs/superpowers/specs/2026-09-28-link-attached-sensor-frames-design.md`

## Global Constraints

- Keep the existing dirty `URDF_Exporter/core/web_ui.py`, untracked `tests/test_toolbar_groups.py`, and `Ogre.log` safe; isolate feature work in a Git worktree from current `main` including the approved toolbar changes only after those changes are accounted for.
- No new top-level toolbar button; retain existing button size, order, and style.
- Canonical pose is XYZ meters and RPY radians relative to owning link; UI uses millimeters and degrees.
- v1 exports frames only: no Gazebo plugins, simulated measurements, ROS bridge, or real-device driver.
- No sensor may silently disappear or reattach when a link is disabled, deleted, renamed, grouped, or replaced.

## Review Focus

- A sensor attached to a renamed root/base link must resolve through final export names, not the pre-export string. Task 4 tests this.
- A module instantiated twice with sensors must have disjoint link IDs and frame names. Task 5 tests this.
- Existing projects with no `_sensors` must export byte-equivalent robot topology and load without UI errors. Tasks 1 and 4 test this.
- Picking a point on a rotated link must store a link-local pose, not a world pose. Tasks 2 and 3 test this.
- Invalid or disabled parent links must fail save/export rather than produce broken fixed joints. Tasks 1 and 4 test this.

## File responsibilities

- Create `URDF_Exporter/standalone/sensor_frames.py`: schema validation, names, ID/pose operations, world-to-local math, export records.
- Create `URDF_Exporter/core/sensor_ui.js`: sensor list/editor, selection-only marker, pick-mode orchestration; rely on the existing editor APIs rather than reimplementing the viewer.
- Modify `URDF_Exporter/core/web_ui.py`: load UI asset and add Sensors section to link properties; route click/pick/undo into sensor UI.
- Modify `URDF_Exporter/standalone/server.py`: validate records in save/reload boundaries.
- Modify `URDF_Exporter/standalone/exporter.py` and `URDF_Exporter/core/Write.py`: emit fixed sensor frames after final name mapping, without physics/control geometry.
- Modify `URDF_Exporter/standalone/module_geometry.py`, `module_service.py`, `module_library.py`, `module_export.py`: preserve/remap sensor-owned records across library lifecycle and Xacro split.
- Add focused tests under `tests/` and update `README.md`/`QUICKSTART_KO.md` to state frames-only support.

---

### Task 1: Sensor records and persistence

**Files:** Create `URDF_Exporter/standalone/sensor_frames.py`; modify `URDF_Exporter/standalone/server.py`; test `tests/test_sensor_frames.py` and `tests/test_sensor_persistence.py`.

**Interfaces:** `validate_sensors(tree: dict) -> list[dict]`; `sensor_frame_name(name: str) -> str`; `create_sensor(tree: dict, parent_link_id: str, sensor_type: str, name: str) -> dict`; `update_sensor(tree: dict, sensor_id: str, changes: dict) -> dict`; `delete_sensor(tree: dict, sensor_id: str) -> dict`. Mutations return a deep-copied tree.

- [ ] Step 1: Write failing tests for empty legacy trees, two sensors on one link, unique IDs/frame names, disabled/missing parent, nonfinite pose, name collisions, save/reload, and exact mm/rad stored values.
- [ ] Step 2: Run `python -m unittest tests.test_sensor_frames tests.test_sensor_persistence -q`; expect missing API/validation failures.
- [ ] Step 3: Implement the five interfaces and call validation before `ProjectStore.save_workspace` and export mutations; preserve unknown tree metadata.
- [ ] Step 4: Re-run the focused tests and `python -m unittest discover -s tests -q`; expect pass.
- [ ] Step 5: Commit only Task 1 files: `feat: persist link-attached sensor records`.

### Task 2: Link-local pose conversion

**Files:** Modify `URDF_Exporter/standalone/sensor_frames.py`; test `tests/test_sensor_frames.py`.

**Interfaces:** `sensor_world_matrix(sensor: dict, link_world_matrix: list[float]) -> list[float]`; `set_sensor_world_point(sensor: dict, link_world_matrix: list[float], point_world_m: list[float]) -> dict`. Follow the existing row-major meter matrix convention; return a copied sensor and leave `rpy_rad` unchanged for point-only picks.

- [ ] Step 1: Write failing test for a translated/rotated parent: world pick converts to the expected local XYZ, independent orientation remains unchanged, and original joint/tree are not mutated.
- [ ] Step 2: Run `python -m unittest tests.test_sensor_frames -q`; expect missing conversion API.
- [ ] Step 3: Implement rigid-transform composition/inversion using the project math helpers, rejecting singular/nonfinite matrices.
- [ ] Step 4: Re-run focused and full Python suites; expect pass.
- [ ] Step 5: Commit: `feat: resolve sensor poses relative to links`.

### Task 3: Editor controls and selected-only 3D marker

**Files:** Create `URDF_Exporter/core/sensor_ui.js`; modify `URDF_Exporter/core/web_ui.py`; test `tests/test_sensor_ui.cjs` and browser fixture.

**Interfaces:** `SensorEditor.renderLinkSection(node, host)`; `SensorEditor.select(sensorId)`; `SensorEditor.clearSelection()`; `SensorEditor.pickWorldPoint(pointMm)`; `SensorEditor.renderMarker()`. Use existing tree save/history and viewer selection hooks; show numeric XYZ(mm) and RPY(°).

- [ ] Step 1: Write failing Node tests for selection hiding prior marker, unit conversion, add/edit/delete history, and pick mode not modifying joint data. Add browser acceptance checklist for link properties, point selection, Escape, and numeric-only edit.
- [ ] Step 2: Run `node --test tests/test_sensor_ui.cjs`; expect missing editor API.
- [ ] Step 3: Implement compact collapsible link section and sensor properties without toolbar changes; bind to existing point-picking and link-world transforms.
- [ ] Step 4: Run Node and full Python suites, then exercise disposable browser fixture with at least two sensors and screenshot the selected marker; expect only selected marker visible.
- [ ] Step 5: Commit: `feat: edit sensor frames in link properties`.

### Task 4: URDF/Xacro frame export

**Files:** Modify `URDF_Exporter/standalone/sensor_frames.py`, `URDF_Exporter/standalone/exporter.py`, `URDF_Exporter/core/Write.py`; test `tests/test_sensor_export.py`.

**Interfaces:** `resolved_sensor_frames(tree: dict, export_name_map: dict) -> list[dict]`; `write_sensor_frames(xacro_path: Path, resolved: list[dict]) -> None`. Each record resolves its parent link from `export_name_map['links']` and produces one visual-free massless frame link and one fixed joint; collision with generated link/joint names is a hard error.

- [ ] Step 1: Write failing real-Xacro expansion tests for multiple frames, root rename, mm→m/rad origin, invalid parent, no sensor case, and absence of sensor inertial/STL/ros2_control entries.
- [ ] Step 2: Run `python -m unittest tests.test_sensor_export -q`; expect missing frames.
- [ ] Step 3: Resolve names only after `standardize_names`; write frames into the main robot Xacro before module split; keep generated package install inclusion correct.
- [ ] Step 4: Re-run focused and full Python suites; expect pass.
- [ ] Step 5: Commit: `feat: export fixed sensor frames`.

### Task 5: Reusable module lifecycle

**Files:** Modify `URDF_Exporter/standalone/module_geometry.py`, `module_library.py`, `module_service.py`, `module_export.py`; test `tests/test_sensor_modules.py`.

**Interfaces:** Extend existing module payload with `sensors: list[dict]`; on attach regenerate sensor IDs, prefix names, map owner IDs; on replace remove only owned old sensors; on undo restore snapshot. Module Xacro must own or invoke sensor frames with instance prefixes.

- [ ] Step 1: Write failing capture/import/two-instance/replacement/undo/Xacro tests showing sensor ownership and no duplicated frame names.
- [ ] Step 2: Run `python -m unittest tests.test_sensor_modules -q`; expect lost or colliding sensors.
- [ ] Step 3: Extend module payload validation and lifecycle remapping; integrate split Xacro references rather than leaving unprefixed module-owned frames in main Xacro.
- [ ] Step 4: Re-run focused and full Python suites; expect pass.
- [ ] Step 5: Commit: `feat: carry sensors with reusable modules`.

### Task 6: Documentation and end-to-end verification

**Files:** Modify `README.md`, `QUICKSTART_KO.md`; create `docs/superpowers/verification/2026-09-28-sensor-frames.md`; tests existing suites.

**Interfaces:** Document frame-only capability and out-of-scope measurement output; show add/pick/edit/export flow.

- [ ] Step 1: Add acceptance fixture covering older project load, two sensors on one link, renamed parent, saved/reloaded pose, generated Xacro expansion, and no sensor data topics.
- [ ] Step 2: Run Python and Node full suites plus `git diff --check`; record exact counts and any WSL/ROS runtime limitation.
- [ ] Step 3: Verify the UI against a disposable project without touching the user's current robot; document screenshot and workflow.
- [ ] Step 4: Commit docs and verification: `docs: explain sensor frame workflow and limits`.

After implementation, run one whole-branch review, fix Important/Critical findings with failing tests, and present integration options. Do not push or merge without the user's choice.
