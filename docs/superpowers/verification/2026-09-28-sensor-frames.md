# Link-attached sensor frames verification

Implemented on `codex/link-attached-sensor-frames` from `358ff0c`.

- Legacy trees without `_sensors` remain valid and leave their Xacro untouched.
- Sensor records persist by stable parent link ID, meter/radian pose, and unique sensor ID/name.
- A translated/rotated link converts a world point into link-local XYZ without changing RPY or joint state.
- Two sensors can share one link. Deleted/disabled parent links and invalid coordinates are rejected.
- Real Xacro expansion verifies a renamed `base_link`, empty frame link, fixed joint, meter/radian origin,
  and no visual, inertia, ros2_control, sensor data topic, or sensor plugin.
- The internal MoveIt seed URDF contains the same sensor frame topology.
- Module capture, two instantiations, replacement, and Xacro split retain disjoint sensor IDs/frame names.
- Disposable browser fixture: added Depth Camera to base link, entered X=15 mm, picked a 3D surface;
  XYZ changed to 9.0664, -20, 14.1006 mm. ESC hid the marker and selected panel. Console errors: 0.
  Changing type to Depth Camera and switching between two sensors on one link were then verified.
  Screenshot: [sensor UI](2026-09-28-sensor-ui.png).
- A second disposable browser fixture translated the root CAD part by (100, 200) mm and rotated it 90°.
  Picking its visible box gave root-local XYZ (-20, -1.9399, 13.9407) mm, not the CAD/world offset.
  Reparenting to `palm` gave XYZ (91.9399, 160, -16.0593) mm and yaw 90°, preserving the
  same displayed 3D pose. Console errors: 0.
- Review fixes: reject sensors under disabled ancestor edges, reject malformed JSON fields with
  validation errors, preserve root link IDs on reroot, block merging a sensor-owning source link
  until its sensors are moved/deleted, and prevent stale 3D picking after another selection.

Commands on Windows with the repository virtualenv and bundled Node:

- `python -m unittest discover -s tests -q` — 159 tests, passed.
- `node --test tests/test_module_selection.cjs tests/test_sensor_ui.cjs` — 10 tests, passed.
- `git diff --check` — no whitespace errors.

ROS/WSL sensor runtime was not run; this release exports frames only, not measurement-producing sensor plugins.
