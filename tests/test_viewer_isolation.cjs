const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const webUi = fs.readFileSync(
    path.join(__dirname, '../URDF_Exporter/core/web_ui.py'),
    'utf8'
);

function extractFunction(name, nextName) {
    const start = webUi.indexOf(`function ${name}`);
    const end = webUi.indexOf(`function ${nextName}`, start);
    assert.ok(start >= 0 && end > start, `find ${name} function`);
    return webUi.slice(start, end);
}

const disabled = new Set(['disabled-part']);
const meshDict = {
    focus: {visible: false, userData: {component: 'focus'}},
    background: {visible: false, userData: {component: 'background'}},
    'disabled-part': {visible: false, userData: {component: 'disabled-part'}},
};
const collisionMeshDict = {
    focus: {visible: false},
    background: {visible: false},
};
const applyVisibility = new Function(
    'meshDict', 'collisionMeshDict', 'viewerIsolatedComponent', 'viewerIsolatedNode',
    'jointOriginPickMode', 'jointPickAllowedComponents', 'visualMeshesEnabled',
    'collisionMeshesEnabled', 'getDisabledComponents',
    `${extractFunction('applyViewerIsolationVisibility', 'clearViewerIsolation')}; return applyViewerIsolationVisibility;`
)(meshDict, collisionMeshDict, 'focus', null, false, null, true, true, () => disabled);
applyVisibility();

assert.equal(meshDict.focus.visible, true, 'the focused link stays visible');
assert.equal(meshDict.background.visible, true, 'surrounding model remains visible as context');
assert.equal(meshDict['disabled-part'].visible, false, 'disabled parts remain hidden');
assert.equal(collisionMeshDict.background.visible, false, 'background collision stays hidden');

const renderer = {
    domElement: {getBoundingClientRect: () => ({left: 0, top: 0, width: 100, height: 100})},
};
const camera = {updateMatrixWorld() {}};
const scene = {updateMatrixWorld() {}};
let intersectedMeshes = [];
const viewerRaycaster = {
    setFromCamera() {},
    intersectObjects(meshes) {
        intersectedMeshes = meshes;
        return meshes;
    },
};
const getIntersections = new Function(
    'renderer', 'camera', 'scene', 'viewerPointer', 'viewerRaycaster', 'meshDict',
    'viewerIsolatedComponent', 'viewerIsolatedNode', 'jointOriginPickMode',
    'jointPickAllowedComponents',
    `${extractFunction('getViewerIntersections', 'screenDistanceToSegment')}; return getViewerIntersections;`
)(renderer, camera, scene, {}, viewerRaycaster, meshDict, 'focus', null, false, null);
getIntersections({clientX: 50, clientY: 50});
assert.deepEqual(intersectedMeshes, [meshDict.focus], 'faded context parts are not selectable');

console.log('viewer isolation tests passed');
