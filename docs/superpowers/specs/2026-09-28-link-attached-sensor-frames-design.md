# Link-attached sensor frames — design

Date: 2026-09-28

## Purpose and scope

Petasos currently represents CAD geometry and joints but has no sensor identity or measurement origin. A joint origin connects links; it must not be reused as a lens, LiDAR, or IMU origin. This first increment lets a user assign multiple sensors to a link, place and orient each sensor independently in the 3D viewer, save that work, and export named coordinate frames. It does **not** simulate depth images, scans, or IMU measurements, start a driver, bridge ROS topics, or claim sensor data is available merely because a frame exists.

The earlier toolbar grouping edit is unrelated and must be preserved. Do not add another top-level toolbar button. Existing button sizes and ordering remain unchanged.

## Options considered

1. Reuse joints as sensor positions: minimal code, but changes the mechanical meaning of a joint and cannot represent several sensors independently. Rejected.
2. Store sensors as arbitrary world coordinates: easy to pick initially, but frames become wrong when a link moves. Rejected.
3. **Store sensor pose relative to an owning link**: joints remain mechanical, pose follows the link, multiple sensors share a link, and per-type settings can extend the schema later. Selected.

## Data model and units

Add top-level `tree._sensors` (absent means empty) as a list. Each entry has a stable UUID `id`, ROS-safe unique `name`, `type` (`depth_camera`, `rgb_camera`, `lidar`, `imu`, or `generic`), `parent_link_id`, `xyz_m` (three finite numbers), and `rpy_rad` (three finite numbers). The editor labels pose as XYZ in millimeters and RPY in degrees, converting only at the UI boundary. Canonical stored/export units are meters and radians. A type-neutral `settings` object is reserved for later versions; v1 will not expose or export measurement configuration. Unknown legacy metadata may be retained, but must not be interpreted as a working plugin.

Sensor identities refer to stable `_link_id`, never the mutable link name. A sensor name maps to an exported frame name `<name>_frame` unless the entered name already ends `_frame`; collisions with links, joints, other sensor frames, `world`, and `base_footprint` are errors. Sensor names must remain stable across link renaming. Deleted or disabled parent links make the sensor invalid; validation blocks save/export and offers reassignment or deletion, never silently reattaches it.

## Editor interaction

The link properties pane gains a compact collapsible **Sensors** section and `+ 센서` action. Each row shows type, name, and parent link, and opens sensor properties. No new toolbar button. Add/edit/delete are undoable and autosaved through the existing workspace path. Choosing a sensor activates an XYZ triad plus forward marker at the actual sensor origin in the 3D viewer; deselection and Escape hide it. The existing 3D snap/selection mechanism can set a point on the model; the resulting world point is converted to owning-link local coordinates before storage. The sensor orientation is adjusted independently with RPY numeric fields. Picking a point must not alter the link frame, joint origin, or CAD/world origin. A numeric-only path works if no snap target is available. The display remains readable with many sensors by showing markers only for the selected sensor.

The initial type selector supplies `Depth Camera`, `RGB Camera`, `LiDAR`, `IMU`, and `Generic`. This is semantic metadata only in v1; each uses the same pose editing. No pretend image/scan output or nonfunctional simulation switches appear.

## Persistence, modules, and export

`ProjectStore.save_workspace` and named project saves persist `_sensors` with the tree. Importing older projects defaults to an empty list. Validation runs before mutations and export. Link renaming is resolved by the final `RobotStructure.export_name_map['links']` map so each sensor's `parent_link_id` becomes the correct final URDF link name, including `base_link` renaming.

The exporter emits one massless, visual-free `<link name="..._frame"/>` and one fixed `<joint>` from the final parent link to that frame, with `<origin xyz="..." rpy="..."/>`. This represents TF geometry through robot_state_publisher and works without Gazebo plugins. Exported frames are excluded from inertial aggregation, STL grouping, collision geometry, ros2_control, controller lists, and MoveIt planning groups. Any generated files must be included in packaged installs. The expanded Xacro/URDF must contain exactly one frame/joint per sensor and preserve the ordinary robot if there are no sensors.

When a link is part of a reusable module, sensors owned by that link must travel with the module library payload and be remapped to newly generated link IDs and unique frame names for each attached instance. Replacement removes only sensors owned by the replaced module; undo restores them. Module Xacro output includes or invokes its sensor frames in the same prefixed namespace as module links. If this cannot be guaranteed, attachment fails explicitly instead of silently dropping sensor frames.

## Validation and verification

Validate unique IDs/names/frames, supported type, parent existence and active state, finite six-degree pose, and name collision before saving or exporting. Reject malformed input with actionable errors. Tests cover migration of sensor-free projects, multiple sensors on one link, link rename, deletion/disable, point-to-link-local conversion under rotated parents, save/reload/undo, module capture/attach/replace, package install, and actual Xacro expansion. A browser test verifies selection-only markers, point picking, RPY edits, and unchanged joint pose. Existing complete test suites must remain green. Live ROS/Gazebo output is explicitly out of scope; if runtime access is unavailable, report that rather than claiming it was exercised.

## Follow-on work, outside this increment

Per-type fields, optical-frame conventions, camera calibration, Gazebo Classic sensor plugins, Gazebo Sim SDF sensors, ROS topic bridges, physical-device drivers, and sensor visualizations can layer on this common ownership and pose model. Their implementation requires an explicit simulation/hardware target and version, not an automatic inference from CAD geometry.
