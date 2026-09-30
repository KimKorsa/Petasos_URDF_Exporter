# URDF physical and control preflight — design

Date: 2026-09-30

## Purpose and agreed outcome

Petasos should not silently export a robot whose CAD-derived mass properties are implausible, whose mimic gripper is independently commanded, or whose collision geometry has not been checked. The user requested this order: (1) trace and fix the gripper center-of-mass error, (2) verify mimic control in the actual ROS environment, and (3) show a physical/collision diagnostic table before final export. Severe physical errors block export; plausible intentional contacts are warnings requiring review. Preserve existing editor layout and unrelated work.

The current `new_robot` sample is a regression fixture, not a special-case correction. Its `link_7` visual mesh occupies about Z = -0.027 to +0.045 m in link-local coordinates, while its URDF inertial origin is Z = -0.543 m; `link_8` is similar. The exporter must trace source CAD physical coordinates through component, link, and mesh transforms and correct the conversion at its source. No hardcoded gripper offsets or mesh-specific rules.

## Approach and boundaries

Three approaches were considered: warning-only validation (insufficient because known-bad URDF still ships), automatic mesh/COM adjustment (could conceal a wrong coordinate transform), and a traced source fix plus staged preflight. Select the third. Each phase has its own regression tests and can be reviewed independently before the next begins.

### 1. Link mass properties

Trace one component through imported CAD mass/COM/inertia, its current assembly transform, `RobotStructure` aggregation, baked visual mesh, and emitted URDF. Canonical internal values are kilograms, meters, radians, and kg·m². The link-local inertial frame and link-local baked mesh must use the same reference transform. Correct whichever upstream conversion violates that invariant. Check positive finite mass, finite COM, symmetric positive-definite inertia with physically plausible scale, and whether the COM lies within a conservative tolerance of the link's full-detail visual mesh bounds. A COM outside bounds is a blocking error unless the link is explicitly documented as a mass-only/remote-payload model, which this increment does not add. A non-watertight STL with fallback mass remains flagged as low-confidence rather than silently represented as CAD-grade physical data. Changes to CAD physical data should not alter geometry or the selected robot pose.

### 2. Mimic control

Use the existing ROS 2 Humble / Gazebo Classic export target and `mock_components/GenericSystem` demo target. A mimic follower remains a URDF mimic joint and provides observable state, but it is not an independently commanded member of a trajectory/gripper controller. Export any Humble-specific `ros2_control` mimic metadata the selected backend needs; keep the Gazebo and mock paths consistent with their documented behavior. The driving joint's command and state interfaces must satisfy its selected controller. The follower's motion obeys `q_follower = multiplier * q_driver + offset`, including negative multipliers and nonzero offsets, while respecting its limits. Reject contradictory controller membership or incompatible limits with an actionable diagnostic rather than silently rewriting user groups. Verify generated XML/YAML statically and run a headless command/state smoke test in Ubuntu 22.04 + ROS 2 Humble when available. If runtime access is unavailable, report that the runtime check is unverified, never passed by assumption. Keep MoveIt planning groups and controller lists consistent with the resulting independently driven degrees of freedom.

### 3. Export preflight and UI

Generate candidate artifacts in a staging directory under the selected export root, then run checks against exactly those candidate visual/collision meshes, URDF, SRDF, and controller files. A blocking diagnostic prevents promotion to the final output and preserves the previous successful export. On success, promote the staged bundle and remove only this operation's staging files. Do not delete the existing `ros_ws` or description package before preflight succeeds.

The structured report contains stable diagnostic code, severity (`error`, `warning`, `info`, `not_checked`), affected link/joint pair, observed value, expected range or reason, and recommended action. The existing export screen shows a compact physical/collision table before finalization. Error rows disable final export; warning rows are visible and require explicit acknowledgment; unchecked rows cannot be presented as collision-free. No global toolbar layout or button-size changes are in scope. Store the same report in the output `analysis/` directory for reproducibility and future support.

Physical checks cover missing/nonfinite/nonpositive mass, COM-versus-mesh bounds, inertia validity, and low-confidence fallback provenance. Collision checks evaluate the selected zero/start pose for every non-excluded link pair, name each contact pair, and distinguish valid adjacency exemptions from unreviewed contact. Use a deterministic broadphase on collision-mesh bounds and an exact narrowphase when an available backend supports it. If exact checking cannot run on the user's environment, emit `not_checked` with the missing backend and let the user proceed only after explicit acknowledgment; never infer “clear” from AABB non-overlap alone except for those individual pairs. Preview the collision-mesh simplification ratio and indicate when a simplified collision mesh differs materially from the full-detail visual mesh. Avoid blanket SRDF collision exclusions for all gripper links.

## Error handling and compatibility

Existing project files and sensor/module metadata remain readable. Imported CAD metadata with unclear units is rejected or marked low-confidence at the boundary; no guessed unit correction occurs during export. The preflight report must identify whether failure arose from CAD physical data, aggregation, geometry, ROS control configuration, or missing collision-check capability. Headless and API exports return the report as structured data and a clear failure status. A successful export's paths and ROS package layout remain unchanged. Existing generated output and unrelated dirty working-tree edits are not reset or overwritten during development.

## Acceptance and verification

1. The current `new_robot` gripper's `link_7`/`link_8` COMs become consistent with their link-local meshes and mass/inertia remain finite and physically valid. A synthetic rotated-and-translated multi-part link proves the source transform fix without sample-specific constants.
2. Generated URDF still contains the gripper mimic relationship, while its follower is not independently commanded. Static package validation passes; in the Humble runtime, commanding only the driving joint changes both reported joint positions according to multiplier/offset. Runtime evidence or a clear unverified status is recorded.
3. A deliberately out-of-bounds COM blocks export without removing a prior valid export. A deliberate nonadjacent collision produces a named warning; an intentional adjacent fixed attachment is not misreported. An unavailable exact collision backend yields `not_checked`, not a false pass. The report appears in the editor and in `analysis/` after success.
4. Focused unit/integration tests and existing exporter tests run, followed by representative Xacro expansion and ROS package validation. Test failures attributable to pre-existing unrelated work are separated from regressions introduced by this change.

## Out of scope

Automatically repairing arbitrary CAD metadata, changing robot geometry to resolve real interpenetration, adding sensor simulation plugins, redesigning the robot-tree toolbar, and auto-generating a complete MoveIt self-collision matrix across all possible poses are separate tasks. The collision preflight checks the configured start pose and clearly states that scope.
