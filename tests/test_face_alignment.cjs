const assert = require('node:assert/strict');
const fs = require('node:fs');
const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
const {
    buildFaceParallelDelta,
    buildPlanarFaceOverlayGeometry,
    deltaInNeutralParentFrame,
    getFaceParallelNormalMode,
    normalizeFacePair,
    setFaceParallelNormalMode,
    validateFacePair,
} = require('../URDF_Exporter/core/face_alignment.js');

const pivot = new THREE.Vector3(12, -4, 7);
const referenceNormal = new THREE.Vector3(0, 1, 0);
const movingNormal = new THREE.Vector3(0, 0, 1);
const result = buildFaceParallelDelta(THREE, referenceNormal.toArray(), movingNormal.toArray(), pivot.toArray());
assert.ok(result, 'valid face normals produce a rotation');

const delta = new THREE.Matrix4().fromArray(result.matrix);
const alignedNormal = movingNormal.clone().transformDirection(delta);
assert.ok(alignedNormal.distanceTo(referenceNormal.clone().negate()) < 1e-9);
assert.ok(pivot.clone().applyMatrix4(delta).distanceTo(pivot) < 1e-9, 'rotation keeps the picked point fixed');
const jointOrigin = new THREE.Vector3(-14, 5, 21);
const jointPivotDelta = new THREE.Matrix4().fromArray(buildFaceParallelDelta(
    THREE,
    referenceNormal.toArray(),
    movingNormal.toArray(),
    jointOrigin.toArray(),
    'opposed'
).matrix);
assert.ok(
    jointOrigin.clone().applyMatrix4(jointPivotDelta).distanceTo(jointOrigin) < 1e-9,
    'rotation keeps the joint origin fixed'
);
const sameDirectionResult = buildFaceParallelDelta(
    THREE,
    referenceNormal.toArray(),
    movingNormal.toArray(),
    pivot.toArray(),
    'same'
);
const sameDirectionDelta = new THREE.Matrix4().fromArray(sameDirectionResult.matrix);
const sameDirectionNormal = movingNormal.clone().transformDirection(sameDirectionDelta);
assert.ok(sameDirectionNormal.distanceTo(referenceNormal) < 1e-9);
assert.equal(getFaceParallelNormalMode({ _face_parallel_normal_mode: 'same' }), 'same');
assert.equal(getFaceParallelNormalMode({ _face_parallel_normal_mode: 'opposed' }), 'opposed');
assert.equal(getFaceParallelNormalMode({ _face_parallel_normal_mode: 'invalid' }), 'opposed');
assert.equal(getFaceParallelNormalMode({}), 'opposed');
const modeState = {};
assert.equal(setFaceParallelNormalMode(modeState, 'same'), true);
assert.equal(getFaceParallelNormalMode(JSON.parse(JSON.stringify(modeState))), 'same');
assert.equal(setFaceParallelNormalMode(modeState, 'sideways'), false);
assert.equal(validateFacePair({ linkId: 'link-a' }, { linkId: 'link-a' }).ok, false);
assert.equal(validateFacePair({ linkId: 'link-a' }, { linkId: 'link-b' }).ok, true);
assert.equal(validateFacePair(
    { linkId: 'link-a' },
    { linkId: 'root', subtreeLinkIds: ['root', 'link-a'] }
).reason, 'fixed_face_in_moving_subtree');
const link1 = { linkId: 'link-1', subtreeLinkIds: ['link-1', 'link-2', 'link-6'] };
const link6 = { linkId: 'link-6', subtreeLinkIds: ['link-6'] };
assert.deepEqual(normalizeFacePair(link1, link6), {
    ok: true, reference: link1, moving: link6, swapped: false,
});
assert.deepEqual(normalizeFacePair(link6, link1), {
    ok: true, reference: link1, moving: link6, swapped: true,
});
const sibling = { linkId: 'link-3', subtreeLinkIds: ['link-3'] };
assert.deepEqual(normalizeFacePair(link1, sibling), {
    ok: true, reference: link1, moving: sibling, swapped: false,
});

const patchGeometry = new THREE.BufferGeometry();
patchGeometry.setAttribute('position', new THREE.Float32BufferAttribute([
    0, 0, 0, 1, 0, 0, 0, 1, 0,
    4, 0, 0, 5, 0, 0, 4, 1, 0,
], 3));
const faceOverlay = buildPlanarFaceOverlayGeometry(THREE, patchGeometry, [1]);
assert.equal(faceOverlay.getAttribute('position').count, 3);
faceOverlay.computeBoundingBox();
assert.deepEqual(faceOverlay.boundingBox.min.toArray(), [4, 0, 0]);
assert.deepEqual(faceOverlay.boundingBox.max.toArray(), [5, 1, 0]);
assert.equal(buildFaceParallelDelta(THREE, [0, 0, 0], [1, 0, 0], [0, 0, 0]), null);

const rootDelta = new THREE.Matrix4().makeRotationZ(Math.PI / 4);
rootDelta.setPosition(3, -2, 1);
const parentNeutral = new THREE.Matrix4().makeRotationY(0.2);
parentNeutral.setPosition(-5, 6, 2);
const parentCurrent = new THREE.Matrix4().makeRotationX(-0.3);
parentCurrent.setPosition(8, 3, -4);
const parentMotion = parentCurrent.clone().multiply(parentNeutral.clone().invert());
const neutralDelta = deltaInNeutralParentFrame(THREE, rootDelta, parentCurrent, parentNeutral);
const actual = parentMotion.clone().multiply(neutralDelta);
const expected = rootDelta.clone().multiply(parentMotion);
assert.ok(actual.elements.every((value, index) => Math.abs(value - expected.elements[index]) < 1e-9));

const webUi = fs.readFileSync(require.resolve('../URDF_Exporter/core/web_ui.py'), 'utf8');
assert.ok(webUi.includes('/static/modules/face_alignment.js'));
assert.ok(webUi.includes("'face_alignment.js'"));
assert.ok(webUi.includes('handleFaceParallelPick(event)'));
assert.ok(webUi.includes('cancelFaceParallelPick();'));
const jointRepickBlock = webUi.slice(
    webUi.indexOf('function toggleJointOriginPick'),
    webUi.indexOf('function handleJointOriginPick')
);
assert.doesNotMatch(jointRepickBlock, /\bbackup\b|\bjointInfo\b/);
const facePickBlock = webUi.slice(
    webUi.indexOf('function handleFaceParallelPick'),
    webUi.indexOf('function scheduleGroundFaceSnapPreview')
);
assert.ok(facePickBlock.includes('resolvePlanarFaceSelection(getViewerIntersections(event))'));
assert.ok(!facePickBlock.includes('resolveBestSurfaceSnap'));
const faceHoverBlock = webUi.slice(
    webUi.indexOf('function updateGroundFaceSnapPreview'),
    webUi.indexOf('function updateFaceParallelPickUi')
);
assert.ok(faceHoverBlock.includes('resolvePlanarFaceSelection(intersections)'));
assert.ok(facePickBlock.includes('showFaceParallelOverlay(picked, \'first\')'));
assert.ok(faceHoverBlock.includes('showFaceParallelOverlay(selection, \'hover\')'));
assert.ok(webUi.includes('id="face-parallel-opposed"'));
assert.ok(webUi.includes('id="face-parallel-same"'));
assert.match(webUi, /class="face-parallel-directions"[^>]*hidden/);
assert.ok(webUi.includes("let faceParallelNormalMode = 'opposed'"));
assert.ok(webUi.includes('jointOriginWorldPointForFaceAlignment(second.owner)'));
assert.ok(webUi.includes('faceParallelOptions.hidden = !faceParallelOptionsOpen'));
assert.ok(webUi.includes('조인트 위치는 유지했습니다'));

console.log('face alignment tests passed');
