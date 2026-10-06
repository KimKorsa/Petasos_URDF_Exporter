const {test} = require('node:test');
const assert = require('node:assert/strict');
const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
const JointZeroFrame = require('../URDF_Exporter/core/joint_zero_frame.js');

test('joint zero alignment preserves the local rotation axis and only twists its frame', () => {
  const originalRotation = new THREE.Quaternion()
    .setFromEuler(new THREE.Euler(0.4, -0.7, 1.1, 'ZYX'));
  const originalFrame = new THREE.Matrix4().compose(
    new THREE.Vector3(12, -8, 31), originalRotation, new THREE.Vector3(1, 1, 1)
  );
  const localAxis = new THREE.Vector3(1, 0, 0);
  const originalWorldAxis = localAxis.clone().applyQuaternion(originalRotation).normalize();

  const aligned = JointZeroFrame.alignToWorld(originalFrame, localAxis.toArray(), THREE);
  const alignedPosition = new THREE.Vector3();
  const alignedRotation = new THREE.Quaternion();
  const alignedScale = new THREE.Vector3();
  aligned.frame.decompose(alignedPosition, alignedRotation, alignedScale);
  const alignedWorldAxis = new THREE.Vector3(...aligned.axis).applyQuaternion(alignedRotation).normalize();

  assert.deepEqual(alignedPosition.toArray(), [12, -8, 31]);
  assert.ok(alignedWorldAxis.distanceTo(originalWorldAxis) < 1e-5);
  assert.ok(new THREE.Vector3(...aligned.axis).distanceTo(localAxis) < 1e-5);
  assert.ok(alignedRotation.angleTo(new THREE.Quaternion()) > 1e-3);
});

test('joint zero alignment keeps alternative axes physically unchanged', () => {
  const rotation = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, Math.PI / 2));
  const frame = new THREE.Matrix4().compose(new THREE.Vector3(), rotation, new THREE.Vector3(1, 1, 1));
  const candidates = [
    {label: 'x', axis: [1, 0, 0]},
    {label: 'y', axis: [0, 1, 0]},
  ];

  const aligned = JointZeroFrame.alignToWorld(frame, [1, 0, 0], THREE, candidates);

  const alignedRotation = new THREE.Quaternion();
  const alignedScale = new THREE.Vector3();
  aligned.frame.decompose(new THREE.Vector3(), alignedRotation, alignedScale);
  const expectedWorldAxes = candidates.map(candidate =>
    new THREE.Vector3(...candidate.axis).applyQuaternion(rotation).normalize()
  );
  assert.deepEqual(aligned.axisCandidates.map(candidate => candidate.label), ['x', 'y']);
  aligned.axisCandidates.forEach((candidate, index) => {
    const actualWorldAxis = new THREE.Vector3(...candidate.axis)
      .applyQuaternion(alignedRotation).normalize();
    assert.ok(actualWorldAxis.distanceTo(expectedWorldAxes[index]) < 1e-5);
  });
});

test('joint zero alignment levels the other axes when the rotation axis is world-aligned', () => {
  const axisAlignment = new THREE.Quaternion()
    .setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0, 'XYZ'));
  const twist = new THREE.Quaternion()
    .setFromAxisAngle(new THREE.Vector3(0, 1, 0), 0.65);
  const originalRotation = twist.clone().multiply(axisAlignment);
  const frame = new THREE.Matrix4().compose(
    new THREE.Vector3(4, 5, 6), originalRotation, new THREE.Vector3(1, 1, 1)
  );

  const aligned = JointZeroFrame.alignToWorld(frame, [0, 0, 1], THREE);
  const alignedPosition = new THREE.Vector3();
  const alignedRotation = new THREE.Quaternion();
  aligned.frame.decompose(alignedPosition, alignedRotation, new THREE.Vector3());
  const alignedX = new THREE.Vector3(1, 0, 0).applyQuaternion(alignedRotation);
  const alignedY = new THREE.Vector3(0, 1, 0).applyQuaternion(alignedRotation);
  const alignedZ = new THREE.Vector3(0, 0, 1).applyQuaternion(alignedRotation);

  assert.ok(alignedPosition.distanceTo(new THREE.Vector3(4, 5, 6)) < 1e-8);
  assert.ok(alignedX.distanceTo(new THREE.Vector3(1, 0, 0)) < 1e-5);
  assert.ok(alignedY.distanceTo(new THREE.Vector3(0, 0, -1)) < 1e-5);
  assert.ok(alignedZ.distanceTo(new THREE.Vector3(0, 1, 0)) < 1e-5);
  assert.deepEqual(aligned.axis, [0, 0, 1]);
});
