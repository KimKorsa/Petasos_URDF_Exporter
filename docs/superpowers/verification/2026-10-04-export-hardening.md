# Export hardening verification

Collision simplification now checks the binary STL round-trip, topology,
orientation, bounds (2% of maximum extent), volume (5%), and body count.
Rejected results and invalid source topology retain the original mesh.
Generation decisions are stored in meshes/collision_mesh_generation.json.
Open boundaries and non-manifold edges are reported separately.

MoveIt re-export uses current generated controller/group/limit/home definitions.
Compatible controller tuning, unchanged-group planning settings, valid stored
poses, collision exclusions, sensor settings, and custom files are retained.
Previous settings are backed up in .petasos-previous; incompatible settings
are reported for review instead of replacing the new robot configuration.

Verification:

- 30 focused Python tests passed, including 9 hardening regression tests.
- 33 JavaScript tests passed; inline UI script parses successfully.
- Actual new_robot exported to an isolated validation directory.
- link_2 and link_4 rejected faulty simplified meshes; original meshes passed
  topology inspection and no longer appear in topology warnings.
- Source topology warnings remain for link_1, link_6, link_7, link_8, Camera_link.
- Result includes arm and gripper2 groups and the current selected gripper
  controller; preflight reports zero blocking errors.
- Full Python suite: 228 tests, 223 passed, 3 failures and 2 errors from the
  previously known unrelated cases:
  - test_nonadjacent_overlap_is_named_and_missing_backend_is_not_checked
  - test_controller_type_is_english_first_and_drives_default_name
  - test_current_preview_pose_can_be_redefined_as_joint_zero
  - test_empty_app_uses_a1_editor_in_standalone_mode
  - test_toolbar_groups_preserve_action_order

The running Petasos server was restarted after verification. /health returned
ok, and the served UI includes the collision fallback and MoveIt synchronization
diagnostics. Existing project data remains available through /data.
The final export directory was not overwritten by the isolated verification;
re-export from the updated application to apply these safeguards to final files.

No WSL MoveIt motion run was performed for this change.
