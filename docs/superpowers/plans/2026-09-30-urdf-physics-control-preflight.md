# URDF Physics, Mimic Control, and Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Inventor-derived link mass properties, prove gripper mimic actuation, and diagnose physical/collision problems before publishing URDF packages.

**Architecture:** Keep Inventor metadata units explicit at the adapter/import boundary; migrate only identifiable legacy Inventor projects. Build one candidate package in a staging directory, inspect its final meshes/URDF/control files, show a structured report, then publish it only after blocking errors are absent and warnings acknowledged. Exact collision probing uses FCL when available and otherwise says `not_checked`.

**Tech Stack:** Python 3, Flask, trimesh/numpy, ROS 2 Humble with `mock_components/GenericSystem` and Gazebo Classic, optional WSL FCL, embedded JavaScript UI, unittest.

**Spec:** `docs/superpowers/specs/2026-09-30-urdf-physics-control-preflight-design.md`

## Global Constraints

- Order is physical source fix, mimic runtime, then preflight/UI; complete each task's tests before the next task.
- Canonical internal units: kg, m, rad, kg·m². Manifest assembly transforms remain in declared assembly units (the Inventor adapter writes mm).
- Blocking physical errors preserve the previous successful export. Nonadjacent contacts warn; an unavailable exact checker is `not_checked`, never “clear.”
- Do not change editor button sizes/layout, sensor/module semantics, generated package paths, or unrelated dirty worktree files.
- No implicit unit guesses for arbitrary third-party manifests; migrate only source-tagged legacy Inventor data with a preserved raw manifest.
- Commit only newly introduced hunks. Several target files already contain the user's unstaged edits; if those hunks cannot be separated safely, leave the task changes uncommitted and report that fact.

## Review Focus

1. An old Inventor project whose raw manifest is missing must not be silently multiplied by 1000; Task 2 tests a blocking recovery diagnostic.
2. An already-correct or twice-loaded project must not be migrated twice; Task 2 tests idempotence and unchanged non-Inventor data.
3. A mimic chain with a negative multiplier and nonzero offset can exceed follower limits; Task 3 tests rejection and valid endpoint mapping.
4. A collision backend missing on Windows/WSL must not claim a clean start pose; Task 4 tests `not_checked` and distinguishes AABB-disjoint pairs.
5. A preflight failure, stale confirmation token, or publish failure must leave the previous `ros_ws` untouched; Task 5 tests all three.

---

### Task 1: Correct the Inventor metadata contract and aggregation regression

**Files:** Modify `URDF_Exporter/standalone/adapters/inventor.py:255-281`; inspect `URDF_Exporter/standalone/importers.py:570-598` and `URDF_Exporter/core/Structure.py:306-405`; create `tests/test_inventor_mass_units.py`; extend `tests/test_structure.py`.

**Interfaces:** Produces adapter `physical.center_of_mass` in manifest assembly units (mm for Inventor), while `physical.mass`, `volume_m3`, and `inertia` remain SI; generic importer converts the manifest COM to internal meters once.

- [ ] Write tests: mock Inventor COM at `(-11.9244988, 7.7089474, 92.1020752)` database cm and assert manifest COM in mm `(-119.244988, 77.089474, 921.020752)`; import it and assert internal meters `(-0.119244988, 0.077089474, 0.921020752)`. Add a rotated/translated multi-component link asserting its COM lies in the final baked-mesh bounds and inertia is symmetric/positive-definite.
- [ ] Run `\.venv\Scripts\python.exe -m unittest tests.test_inventor_mass_units tests.test_structure` and confirm the new regression fails for the current 1000× conversion.
- [ ] Change only the Inventor adapter's COM conversion from database cm to manifest mm; add an explicit `physical.center_of_mass_units: "mm"` marker for new adapter output. Preserve generic manifest behavior and unchanged physical inertia conversion.
- [ ] Run the focused tests, inspect one newly imported sample component's raw mesh bounds versus COM, and run `git diff --check` on touched files.
- [ ] Commit only Task 1 files after checking the index contains no unrelated changes.

### Task 2: Recover the user's already-saved Inventor project safely

**Files:** Create `URDF_Exporter/standalone/physical_migration.py` and `tests/test_physical_migration.py`; modify `URDF_Exporter/standalone/server.py` at `ProjectStore` load/export boundaries and `URDF_Exporter/standalone/importers.py:570-598` only for explicit unit-marker parsing; extend `tests/test_standalone.py`.

**Interfaces:** `repair_legacy_inventor_com(state: dict, project_dir: Path) -> tuple[dict, list[dict]]` returns an updated copy and diagnostic records. It uses `sources/inventor-import.petasos.json` only when `source.adapter` identifies the Petasos Inventor adapter, source `physical.provenance == "inventor_mass_properties"`, and the legacy unit marker is absent; it updates `state.inertial` and matching `state.parts[*].physical`, stamps `state.physical_com_schema = 2`, and never alters the robot tree, link poses, or STL files.

- [ ] Write tests with a preserved legacy manifest containing COM `-0.119244988 m` and saved COM `-0.000119244988 m`; assert corrected in-memory COM, identical tree/visual transforms, and no second correction. Test correct new-format and third-party manifests unchanged; missing legacy manifest yields an error record and no guessed correction.
- [ ] Run `\.venv\Scripts\python.exe -m unittest tests.test_physical_migration` and observe the new test fail.
- [ ] Implement the narrow provenance-based migration and invoke it before export/validation, persisting the schema marker only with a successful project save. Ensure the current `standalone_projects/new_robot` sample can be repaired from its preserved raw Inventor manifest without redoing the user's robot-tree edits.
- [ ] Run the focused tests and a read-only export to a temporary output root; compare `link_7`/`link_8` COMs to their full-detail local mesh bounds and verify inertia eigenvalues are positive. Do not overwrite the user's current export during this check.
- [ ] Commit only Task 2 files after checking the index.

### Task 3: Make mimic control and MoveIt groups match actual actuation

**Files:** Modify `URDF_Exporter/core/Write.py:176-241`, `URDF_Exporter/standalone/exporter.py` controller selection/validation, and `moveit/generate_smoke_config.py`; create `tests/test_mimic_control_export.py` and `moveit/check_mimic_runtime.py`.

**Interfaces:** `validate_mimic_control(joints: dict, groups: list[dict]) -> list[dict]` returns actionable error records for follower-in-controller, cycles, missing driver, and mapped-limit conflicts. URDF `<mimic>` persists; `ros2_control` follower has state plus backend-supported mimic parameters, but is not an independent controller command target. Generated MoveIt/Gazebo controller lists include the driver, not the follower.

- [ ] Write tests for `joint_8 = -joint_7 + 0.002`, mapping both driver limit endpoints inside follower limits; reject an incompatible follower range and an explicitly user-assigned controller containing `joint_8`. An automatically generated default group excludes the follower and produces an informational diagnostic. Assert exported URDF, `.trans`, SRDF, and both controller YAMLs agree on the driven degree of freedom.
- [ ] Run `\.venv\Scripts\python.exe -m unittest tests.test_mimic_control_export` and confirm failure before implementation.
- [ ] Implement backend-specific mimic metadata and controller filtering/validation using Humble GenericSystem/Gazebo Classic behavior. Filter only generated default groups; reject conflicting explicit user groups with a correction message. Keep existing non-mimic controller exports unchanged.
- [ ] Add a headless ROS 2 Humble smoke script: launch the mock control stack, command only `joint_7`, read `/joint_states`, and assert `joint_8` follows multiplier/offset within tolerance. Run it in Ubuntu 22.04 if the runtime is available; record `unverified` with the precise missing prerequisite otherwise. Run static tests regardless.
- [ ] Commit only Task 3 files after focused tests and static Xacro/YAML validation.

### Task 4: Produce a deterministic physical/collision preflight report

**Files:** Create `URDF_Exporter/standalone/export_preflight.py`, optional WSL FCL helper under `moveit/`, and `tests/test_export_preflight.py`; inspect final STL/URDF artifacts produced by `URDF_Exporter/standalone/exporter.py`.

**Interfaces:** `inspect_candidate(description_dir: Path, moveit_dir: Path | None, backend: CollisionBackend | None) -> dict` returns `{"status", "diagnostics", "summary"}`. Each diagnostic has `code`, `severity`, `targets`, `observed`, `expected`, and `action`; `CollisionBackend.contacts(mesh_a, mesh_b, transform_a, transform_b) -> bool` is exact or returns an explicit unavailable condition.

- [ ] Write tests for nonfinite/nonpositive mass, COM outside full-detail visual bounds, non-positive-definite inertia, and STL fallback provenance. Add a small two-link overlap fixture, a fixed-adjacent exception, disjoint AABBs, and a backend-unavailable case; assert named pair warnings versus `not_checked`.
- [ ] Run `\.venv\Scripts\python.exe -m unittest tests.test_export_preflight` and confirm failure.
- [ ] Implement physical checks from final link-local visual mesh and URDF inertial XML; derive start-pose transforms from URDF joints and initial values, using broadphase bounds plus an available exact FCL narrowphase. If no exact backend runs, label the affected candidate pairs `not_checked`; do not report a false collision-free result. Record collision-mesh decimation ratio as informational.
- [ ] Run focused tests, then inspect the repaired `new_robot` candidate in a temporary directory. Verify the known fixed `link_6`–`Camera_link` contact is exempt as adjacent, while deliberate nonadjacent fixture contact is named.
- [ ] Commit only Task 4 files after verification.

### Task 5: Stage, review, and safely publish the diagnosed export

**Files:** Modify `URDF_Exporter/standalone/exporter.py:1590-1840`, `URDF_Exporter/standalone/server.py:984-1024,1240-1275`, and export-screen sections of `URDF_Exporter/core/web_ui.py`; create `tests/test_export_transaction.py`; extend `tests/test_standalone.py` and `tests/test_i18n.py`.

**Interfaces:** `ProjectStore.prepare_export(...) -> dict` creates a candidate under the chosen export root and returns a short-lived opaque token plus Task 4 report. `ProjectStore.commit_export(token: str, acknowledge_warnings: bool) -> dict` checks token/revision, refuses blocking errors, requires acknowledgment for warnings/unchecked collision probes, promotes the staged package with recoverable backup/restore on failure, and preserves `/save` compatibility by routing legacy callers through the same checks.

- [ ] Write tests proving a known-valid old `ros_ws` remains byte-for-byte intact after physical error, stale token, cancellation, and injected publish failure; valid acknowledged candidate publishes the expected path and writes `analysis/export_preflight.json`. Test API JSON severity/targets and UI visibility, warning acknowledgment, and unchanged button dimensions.
- [ ] Run `\.venv\Scripts\python.exe -m unittest tests.test_export_transaction` and confirm failure.
- [ ] Implement staging and transactional promotion using explicit, validated paths within the selected export root. Avoid deleting the current output before the candidate passes. Bind the token to the current project/tree revision; clean only abandoned stages owned by this operation.
- [ ] Render the compact physical/collision table in the existing export flow, with blocking errors and explicit warning acknowledgment. Headless callers receive the identical structured report. Add Korean/English strings through existing i18n conventions.
- [ ] Run focused and exporter suites, Xacro expansion, `moveit/validate_moveit_config.py` against the candidate, and `git diff --check`; distinguish unrelated pre-existing dirty-worktree test failures from regressions. Commit only Task 5 files after verification.

## Final verification

- [ ] Repeat the user's `new_robot` export into a separate temporary output root; confirm `link_7`/`link_8` COMs are inside their mesh bounds, mimic follower is absent from independent controller lists, and the preflight report is visible and saved.
- [ ] Run the Humble mimic runtime smoke if available and report the actual result; do not present static validation as live execution.
- [ ] Review the full diff against the spec, preserving all unrelated user changes and generated artifacts; summarize any remaining `not_checked` diagnostics honestly.
