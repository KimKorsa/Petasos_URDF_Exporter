const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const THREE = require('../URDF_Exporter/vendor/three/three.min.js');

const source = fs.readFileSync(path.join(__dirname, '../URDF_Exporter/core/web_ui.py'), 'utf8');
const start = source.indexOf('function applyPreviewJointValue(');
const end = source.indexOf('function syncAllMimicPreviewValues(', start);

test('preview updates keep mimic zero calibration disabled while drivers can calibrate', () => {
    const button = {disabled: true};
    const controller = {
        name: 'follower', type: 'revolute', jointInfo: {mimic_joint: 'driver'},
        pivot: new THREE.Object3D(), basePosition: new THREE.Vector3(),
        baseQuaternion: new THREE.Quaternion(), axis: new THREE.Vector3(0, 0, 1),
    };
    const context = vm.createContext({
        THREE, previewJointControllers: [controller], treeData: {},
        document: {querySelectorAll: selector => selector.includes('data-set-joint-zero') ? [button] : []},
    });
    vm.runInContext(source.slice(start, end), context);
    context.applyPreviewJointValue(0, 30);
    assert.equal(button.disabled, true);
    assert.ok(controller.pivot.quaternion.angleTo(new THREE.Quaternion()) > 0.5);
    controller.jointInfo = {};
    context.applyPreviewJointValue(0, 30);
    assert.equal(button.disabled, false);
    context.applyPreviewJointValue(0, 0);
    assert.equal(button.disabled, true);
});
