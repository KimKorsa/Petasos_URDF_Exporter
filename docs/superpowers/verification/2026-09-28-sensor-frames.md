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
  Changing type to Depth Camera was then verified as selected. Screenshot: [sensor UI](2026-09-28-sensor-ui.png).

Commands on Windows with the repository virtualenv and bundled Node:

- `python -m unittest discover -s tests -q` — 158 tests, passed.
- `node --test tests/test_module_selection.cjs tests/test_sensor_ui.cjs` — 4 tests, passed.
- `git diff --check` — no whitespace errors.

ROS/WSL sensor runtime was not run; this release exports frames only, not measurement-producing sensor plugins.
