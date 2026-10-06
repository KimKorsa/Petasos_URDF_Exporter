const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
const JointMateAlignment = require('../URDF_Exporter/core/joint_mate_alignment.js');
const webUi = fs.readFileSync(
  require.resolve('../URDF_Exporter/core/web_ui.py'),
  'utf8'
);

test('moves the child connector onto the parent and opposes the face normals', () => {
  const parent = {
    point: [2, 3, 4],
    normal: [0, 0, 1],
    tangent: [1, 0, 0],
  };
  const child = {
    point: [12, -7, 14],
    normal: [0, 0, 1],
    tangent: [1, 0, 0],
  };

  const alignment = JointMateAlignment.build(THREE, parent, child, [1, 0, 0]);
  const alignedPoint = new THREE.Vector3(...child.point)
    .applyMatrix4(alignment.childDelta);
  const alignedNormal = new THREE.Vector3(...child.normal)
    .transformDirection(alignment.childDelta);

  assert.ok(alignedPoint.distanceTo(new THREE.Vector3(...parent.point)) < 1e-8);
  assert.ok(alignedNormal.distanceTo(new THREE.Vector3(0, 0, -1)) < 1e-8);
  assert.ok(new THREE.Vector3().setFromMatrixPosition(alignment.jointFrame)
    .distanceTo(new THREE.Vector3(...parent.point)) < 1e-8);
});

test('preserves a child connector that already faces the parent', () => {
  const parent = {point: [0, 0, 0], normal: [0, 0, 1], tangent: [1, 0, 0]};
  const child = {point: [0, 0, 10], normal: [0, 0, -1], tangent: [1, 0, 0]};
  const alignment = JointMateAlignment.build(THREE, parent, child, [1, 0, 0]);
  const alignedNormal = new THREE.Vector3(...child.normal)
    .transformDirection(alignment.childDelta);

  assert.ok(new THREE.Vector3(...child.point).applyMatrix4(alignment.childDelta)
    .distanceTo(new THREE.Vector3(...parent.point)) < 1e-8);
  assert.ok(alignedNormal.distanceTo(new THREE.Vector3(0, 0, -1)) < 1e-8);
});

function runJointFacePick({childNormal = [0, 0, -1], camera = null} = {}) {
  const visibleNormalBlock = webUi.slice(
    webUi.indexOf('function visibleJointFaceNormal'),
    webUi.indexOf('function updateGroundFaceSnapPreview')
  );
  const pickBlock = webUi.slice(
    webUi.indexOf('function handleJointOriginPick'),
    webUi.indexOf('function flipSelectedJointAxis')
  );
  const frameBlock = webUi.slice(
    webUi.indexOf('function jointFrameFromSurface'),
    webUi.indexOf('function jointPickScopeNode')
  );
  const deltaBlock = webUi.slice(
    webUi.indexOf('function applyJointZeroDeltaToSubtree'),
    webUi.indexOf('function previewControllerZeroWorldFrame')
  );
  const seedFrameBlock = webUi.slice(
    webUi.indexOf('function ensurePreviewJointWorldFrames'),
    webUi.indexOf('function applyJointZeroDeltaToSubtree')
  );
  const childTransform = new THREE.Matrix4().makeTranslation(0, 0, 10).toArray();
  const childNode = {components: ['child'], children: []};
  const parentNode = {components: ['parent'], children: []};
  const joint = {joint_type: 'revolute', joint_info: {}, link_group: childNode};
  const childMesh = new THREE.Object3D();
  childMesh.position.set(0, 0, 10);
  childMesh.updateMatrixWorld(true);
  const selection = {
    component: 'child',
    hit: {object: childMesh},
    snap: {
      localCenter: new THREE.Vector3(),
      localNormal: new THREE.Vector3(...childNormal),
      localTangent: new THREE.Vector3(1, 0, 0),
      minimumNormalAgreement: 1,
      snapMode: 'cad_planar_face_center',
      snapSource: 'opencascade',
    },
    candidateCount: 1,
    candidateIndex: 0,
    usedDepthSelection: false,
  };
  const context = {
    THREE,
    camera,
    window: {PetasosJointMateAlignment: JointMateAlignment},
    treeData: {_preview_units_per_meter: 1000, _preview_transforms: {child: childTransform.slice()}},
    robotRoot: new THREE.Group(),
    jointOriginPickJoint: joint,
    jointMateRollMode: 0,
    jointOriginPickStage: 'child',
    jointOriginParentSnap: {
      component: 'parent',
      rootPoint: new THREE.Vector3(),
      rootNormal: new THREE.Vector3(0, 0, 1),
      rootTangent: new THREE.Vector3(1, 0, 0),
    },
    jointEntryFor: () => ({jointObj: joint, node: childNode, parentNode}),
    getViewerIntersections: () => [],
    resolveBestSurfaceSnap: () => selection,
    previewFrameMatrixForNode: () => new THREE.Matrix4(),
    saveState: () => {},
    ensureJointMotionLimits: () => {},
    syncPickedJointLocalFrames: () => {},
    endJointOriginPickScope: () => {},
    hideJointSnapMarker: () => {},
    render: () => {},
    updateJointOriginPickUi: () => {},
    snapDisplayLabel: () => 'CAD face',
  };
  vm.runInNewContext(`${visibleNormalBlock}\n${frameBlock}\n${seedFrameBlock}\n${deltaBlock}\n${pickBlock}\nhandleJointOriginPick({});`, context);

  return {context, joint};
}

test('joint repick mates the selected child face to the parent face', () => {
  const {context, joint} = runJointFacePick();

  const result = context.treeData._preview_transforms.child;
  new THREE.Matrix4().toArray().forEach((expected, index) => {
    assert.ok(Math.abs(result[index] - expected) < 1e-8);
  });
  assert.deepEqual(Array.from(joint.joint_info._preview_world_xyz), [0, 0, 0]);
  assert.ok(joint.joint_info._joint_mates.gap_after_m < 1e-12);
});

test('a CAD circle normal pointing into the clicked child face keeps the child body outside the parent', () => {
  const camera = new THREE.PerspectiveCamera();
  camera.position.set(0, 0, 100);
  camera.updateMatrixWorld(true);
  const {context, joint} = runJointFacePick({childNormal: [0, 0, -1], camera});
  const transformedBodyPoint = new THREE.Vector3(0, 0, -1).applyMatrix4(
    new THREE.Matrix4().fromArray(context.treeData._preview_transforms.child)
  );

  assert.ok(transformedBodyPoint.z > 0.9 && transformedBodyPoint.z < 1.1);
  assert.ok(joint.joint_info._joint_mates.gap_after_m < 1e-12);
});
