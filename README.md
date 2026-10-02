# Petasos URDF Exporter

[English](README.md) | [한국어](README.ko.md)

<img width="1024" height="531" alt="Petasos URDF Exporter editor" src="https://github.com/user-attachments/assets/bf6df849-92bf-4627-af39-4d254a0eda39" />

[Watch the usage tutorial](https://youtu.be/H9movJFO4Fs)

Petasos imports CAD assemblies, lets you edit robot links and joints, and exports URDF packages for ROS 2.

## Features

- Connect directly to Autodesk Inventor IAM/IPT assemblies or import files
- Import STEP, BREP, IGES, and STL files
- Select parts in 3D, group them into links, and connect or reset joints
- Set the ground plane and world origin
- Generate robot description packages for ROS 2 Humble
- Configure, validate, and launch optional MoveIt packages
- Synchronize and launch RViz through WSL2
- Save and restore named editing sessions
- Reimport updated CAD while preserving existing link and joint edits

## Getting started

On a new computer, run the setup script to check and install the required environment:

```text
setup_petasos.cmd
```

Once setup is complete, start the editor:

```text
start_petasos.cmd
```

If your browser does not open automatically, visit `http://127.0.0.1:5050/`.
Closing the command window also stops the Petasos server.

## Basic workflow

1. Import a CAD assembly or restore a saved editing session.
2. Check the model orientation, ground plane, and origin in the 3D viewer.
3. Group parts into links in the structure tree.
4. Set connection points on the parent and child links, then connect their joint.
5. Configure joint types, axes, limits, and dynamics.
6. Choose an output type and click **Generate URDF** (`URDF 생성`).
7. Run RViz or MoveIt checks from the results screen.

## Supported inputs

- Autodesk Inventor: direct IAM/IPT connection
- CAD exchange formats: STEP, STP, BREP, IGES, IGS
- Meshes: STL
- Petasos assembly exchange format: `*.petasos.json`

For native assembly formats from other CAD applications, export a STEP file that
preserves the assembly structure, then import it into Petasos.

## Updating CAD

After changing geometry or part positions in your CAD application, click
**Update CAD** (`CAD 업데이트`) at the top of the editor and select the updated
STEP/CAD file. Petasos matches corresponding parts, preserves link groups, link
and joint names, joint settings, and ground-plane settings, and applies the new
geometry, physical properties, and CAD positions.

The initial version applies updates automatically only when every part in the
original and updated assemblies can be matched. If parts have been added or
removed, the update stops without changing the existing project.

## Output structure

By default, ROS 2 packages are generated under:

```text
export/ros_ws/src/
```

You can view the generated description package in RViz. Selecting MoveIt output
also generates a MoveIt configuration package in the same workspace.

## Project structure

- `URDF_Exporter/standalone`: local server, CAD conversion, and URDF export
- `URDF_Exporter/core`: code derived from the Fusion 360 exporter and shared structure processing
- `moveit`: MoveIt configuration checks and WSL launch support
- `tools`: setup helpers for Windows, WSL2, and ROS 2
- `tests`: automated regression tests
- `examples`: Petasos assembly exchange examples
- `schemas`: schemas for the Petasos assembly exchange format

## Attribution and license

Parts of the Fusion 360 export code in this project are derived from
[syuntoku14/fusion2urdf](https://github.com/syuntoku14/fusion2urdf), created by
Toshinori Kitamura. The original code is distributed under the MIT License.

Copyright for code newly written or extended in Petasos belongs to the Petasos
contributors. See [LICENSE](LICENSE) for the full license terms.
