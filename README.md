# Petasos URDF Exporter

[English](README.md) | [한국어](README.ko.md)

<img width="1024" height="531" alt="Petasos URDF Exporter editor" src="https://github.com/user-attachments/assets/bf6df849-92bf-4627-af39-4d254a0eda39" />

[Watch the usage tutorial](https://youtu.be/H9movJFO4Fs)

**Turn CAD assemblies into editable robot models and ROS 2 packages.**

Petasos is a local, browser-based robot editor for importing CAD assemblies,
organizing links and joints, inspecting robot motion, and exporting URDF/Xacro
description packages. Its latest A4 development version also adds reusable robot
modules, link-attached sensor frames, and physical/collision checks before export.

## Version coverage

This README covers the A4 development version published to GitHub `main` on
October 7, 2026. The A4 capabilities described below are included in this repository.

## CAD import and robot editing

- Connect to an open Autodesk Inventor assembly or select an original IAM file
  so Inventor can resolve its referenced IPT parts.
- Import STEP/STP, BREP, IGES/IGS, STL, or a `*.petasos.json` assembly.
- Select parts in the 3D viewer, group them into links, and connect parent and
  child links in the robot structure tree.
- Set the ground plane, world origin, joint types, axes, limits, and dynamics.
- Save and restore named editing sessions.
- Reimport updated CAD geometry and part positions while preserving matched
  link groups, names, joint settings, and ground-plane settings. Automatic
  updates stop if added or removed parts prevent a complete match.

For native assembly formats from other CAD applications, export a STEP file
that preserves the assembly structure before importing it into Petasos.

## Latest A4 development capabilities

### 3D alignment and motion editing

- Align faces on different links with matching or opposing normals.
- Mate selected parent and child connection faces to reposition the child link group.
- Adjust joint axes and zero positions, with an option to cancel a zero-position edit.
- Align the joint frame toward world axes while preserving its physical motion axis.
- Preview revolute, continuous, and prismatic motion, and inspect isolated parts or links.
- Switch the editor interface between English and Korean.

### Mimic joints and controllers

Configure a driving joint, multiplier, and offset for a mimic follower, then
preview their coupled motion:

```text
follower_position = multiplier × driver_position + offset
```

The motion preview supports negative multipliers and nonzero offsets. Export
validates mimic relationships and controller membership so a follower is not
commanded as an independent joint. Controller configuration supports trajectory
and gripper workflows for the ROS 2 Humble target. A Humble
`GripperActionController` requires a single driving joint with position and
velocity state interfaces; mimic followers remain dependent joints.

### Materials and physical properties

Use the searchable material library to assign a material to parts or drag a
material card onto a link to apply it to the entire group. Add custom materials
with a name, density, and color, or retain the original CAD material.

Density-based assignments update physical properties when the required volume
or reference data is available. The editor shows an estimated mass where it can;
parts without sufficient physical data need review. The A4 exporter also repairs
legacy Inventor center-of-mass data from the original import metadata when that
metadata is available.

### Reusable robot modules

Manually select links and internal joints with Ctrl+click or area selection,
define a module, and save it to a local library. Mount the saved module on another
parent link using a unique prefix, or replace an existing module while retaining
its mounting joint settings and transform.

- Edit module mounting XYZ/RPY and move the module as a unit.
- Transfer library entries through ZIP import/export.
- Undo mounting, replacement, and mounting-transform edits within the server session.
- Export module contents as separate Xacro files included by the main robot Xacro.
- Carry module-owned sensor frames with library and export operations.

The initial implementation supports connected end structures with a single
mounting joint. Root modules, mobile bases, and nested modules are not supported.
Replacement does not automatically align a new tool's TCP. Stop ROS, replace the
module, re-export, and review MoveIt configuration before launching again.

### Link-attached sensor frames

Add Depth Camera, RGB Camera, LiDAR, IMU, or Generic sensor records to a link.
Enter mounting XYZ in millimeters and RPY in degrees, or pick a position on the
3D surface. Inspect the selected sensor's axes and move it to another link while
preserving its world mounting pose.

Each sensor exports a meshless, massless `<name>_frame` link and a fixed joint.
Sensors are saved with the project and included in reusable modules.

This feature creates **URDF/TF mounting frames**. Gazebo sensor plugins, image or
point-cloud streams, IMU topics, and hardware drivers require separate setup.

### Physical and collision checks before export

The editor prepares a candidate package and shows diagnostics before replacing
the final output.

| Check | What it reports |
|---|---|
| Mass | Nonfinite or nonpositive values |
| Center of mass | Values outside the link's visual-mesh bounds |
| Inertia | Invalid or non-positive-definite tensors |
| Physical-data source | Low-confidence STL or fallback properties |
| Collision geometry | Simplification ratio and mesh contacts at the start pose |
| Collision backend | Overlapping candidates that could not be checked exactly |

Physical errors block finalization. Warnings and unchecked items require
acknowledgment. If preparation or validation fails, the previous successful
export is preserved. Successful exports include the diagnostic report at
`analysis/export_preflight.json` inside the description package.

Collision simplification checks the serialized STL for closed surfaces, consistent
face orientation, retained bounds/volume, and retained connected components. If
these checks fail, the exporter uses the original collision mesh. Existing source
geometry problems remain visible as warnings; simplification does not repair them.

Re-exporting MoveIt updates the current controller definitions, module planning
groups, joint limits, and zero/home states. Compatible user tuning and collision
exclusions are retained. Previous settings are backed up under
`ros_ws/.petasos-previous/`; settings that cannot be safely retained are reported
for review. `ros_ws/moveit_settings_diff.json` records the changes.

Exact mesh collision checks use `python-fcl` when available. Without it,
overlapping candidates are marked **not checked**. Checks cover the configured
start pose and do not establish collision freedom throughout the robot's motion.

## ROS 2, RViz, and MoveIt workflow

Generate a ROS 2 Humble description package for RViz, or choose the MoveIt
workspace output to include a configuration package. The WSL2 workflow supports:

1. Synchronizing and launching the exported model in RViz.
2. Opening MoveIt Setup Assistant to configure planning groups, controllers,
   and the self-collision matrix.
3. Checking the generated configuration, normalizing relevant YAML numeric
   parameters, building the workspace, and launching the demo.
4. Running an automatic planning and demo-controller motion check.

Module replacements or robot structure changes still require a MoveIt review.
The demo workflow does not configure a physical robot's hardware drivers.

## Getting started

The Windows launchers provide the main local workflow. On a new computer, extract
the project folder completely and run:

```text
setup_petasos.cmd
```

The setup helper checks Python and the project environment, Inventor integration,
and the WSL2 / Ubuntu 22.04 / ROS 2 Humble tools used for RViz and MoveIt.
Installation steps may require confirmation or a restart.

Then start the editor:

```text
start_petasos.cmd
```

If the browser does not open automatically, visit `http://127.0.0.1:5050/`.
Closing the command window stops the local server.

## Basic workflow

1. Import an assembly or restore a saved session.
2. Set the model orientation, ground plane, and world origin.
3. Group parts into links and connect joints.
4. Configure axes, limits, dynamics, and motion.
5. In A4, add materials, mimic relationships, reusable modules, or sensor frames as needed.
6. Choose the output type and generate the package; in A4, review preflight diagnostics.
7. Inspect the result in RViz and complete the optional MoveIt setup and checks.

## Output and local storage

| Location | Contents |
|---|---|
| `export/ros_ws/src/` | ROS 2 packages when workspace output is selected |
| Description package `urdf/` and `meshes/` | Robot URDF/Xacro and mesh assets |
| Description package `urdf/modules/` | Separate module Xacro files in A4 |
| Description package `analysis/` | Export diagnostics and analysis |
| `standalone_projects/` | Local saved projects |
| `standalone_modules/` | Local reusable module library in A4 |

Local project, module-library, and generated export directories are excluded from Git.

## Project structure

- `URDF_Exporter/standalone`: local server, CAD import, project storage, and export
- `URDF_Exporter/core`: robot structure, exporter code, and editor interface
- `moveit`: MoveIt configuration checks and WSL launch helpers
- `tools`: Windows, WSL2, and ROS 2 setup helpers
- `tests`: automated regression tests
- `examples` and `schemas`: assembly exchange examples and format schemas

## Attribution and license

Parts of the Fusion 360 export code are derived from
[syuntoku14/fusion2urdf](https://github.com/syuntoku14/fusion2urdf), created by
Toshinori Kitamura and distributed under the MIT License.

Copyright for code newly written or extended in Petasos belongs to the Petasos
contributors. See [LICENSE](LICENSE) for the full license terms.
