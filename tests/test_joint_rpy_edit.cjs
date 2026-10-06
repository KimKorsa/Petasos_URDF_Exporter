const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const THREE = require('../URDF_Exporter/vendor/three/three.min.js');

const source = fs.readFileSync(path.join(__dirname, '../URDF_Exporter/core/web_ui.py'), 'utf8');
function extract(name) {
    const start = source.indexOf(`        function ${name}(`);
    assert.ok(start >= 0, `missing ${name}`);
    const end = source.indexOf('\n        }', start);
    return source.slice(start, end + '\n        }'.length);
}
function frame(xyz, rpy = [0, 0, 0]) {
    return new THREE.Matrix4().compose(
        new THREE.Vector3(...xyz),
        new THREE.Quaternion().setFromEuler(new THREE.Euler(...rpy, 'ZYX')),
        new THREE.Vector3(1, 1, 1)
    );
}
function close(actual, expected, message) {
    const error = Math.max(...actual.elements.map((v, i) => Math.abs(v - expected.elements[i])));
    assert.ok(error < 1e-6, `${message}: matrix error ${error}`);
}
function components(node) {
    return [...(node.components || []), ...(node.children || []).flatMap(child => components(child.link_group))];
}
function entries(node, parentNode = null, jointObj = null, result = []) {
    result.push({node, parentNode, jointObj});
    for (const child of node.children || []) entries(child.link_group, node, child, result);
    return result;
}
function fixture({posed = false, picked = true, type = 'revolute'} = {}) {
    const root = {name: 'world', components: ['base'], children: []};
    const arm = {name: 'arm', components: ['arm'], children: []};
    const tool = {name: 'tool', components: ['tool'], children: []};
    const tip = {name: 'tip', components: ['tip'], children: []};
    const sibling = {name: 'sibling', components: ['sibling'], children: []};
    const parentFrame = frame([20, 30, 10], [0.3, -0.2, 0.6]);
    const local = frame([45, -12, 8], [-0.1, 0.2, -0.3]);
    const incoming = parentFrame.clone().multiply(local);
    const tipLocal = frame([10, 35, 2], [0.2, 0.1, 0.4]);
    const outgoing = incoming.clone().multiply(tipLocal);
    function joint(name, node, xyz, rpy, world, value, jointType = 'revolute') {
        const info = {xyz: xyz.map(v => v / 1000), rpy: rpy.slice(), _manual_rpy: rpy.slice(),
            axis: [0, 0, 1], lower_limit: -2, upper_limit: 2, initial_position: value};
        if (picked) {
            info._preview_world_frame_matrix = world.toArray();
            info._preview_world_xyz = new THREE.Vector3().setFromMatrixPosition(world).divideScalar(1000).toArray();
            info._preview_world_quaternion = new THREE.Quaternion().setFromRotationMatrix(world).toArray();
            info._joint_snap = {component: 'arm', root_point: new THREE.Vector3().setFromMatrixPosition(world).toArray()};
        }
        return {joint_name: name, joint_type: jointType, joint_info: info, link_group: node};
    }
    root.children.push(joint('parent', arm, [20, 30, 10], [0.3, -0.2, 0.6], parentFrame, posed ? 0.7 : 0));
    const selected = joint('selected', tool, [45, -12, 8], [-0.1, 0.2, -0.3], incoming,
        posed ? (type === 'prismatic' ? 0.012 : -0.5) : 0, type);
    arm.children.push(selected);
    tool.children.push(joint('tip', tip, [10, 35, 2], [0.2, 0.1, 0.4], outgoing, posed ? 0.45 : 0));
    root.children.push(joint('sibling', sibling, [-30, 0, 0], [0, 0, 0], frame([-30, 0, 0]), 0, 'fixed'));
    root._preview_units_per_meter = 1000;
    root._preview_transforms = {
        base: new THREE.Matrix4().toArray(),
        arm: parentFrame.clone().multiply(frame([5, 2, 1])).toArray(),
        tool: incoming.clone().multiply(frame([4, -3, 2], [0.2, -0.1, 0.3])).toArray(),
        tip: outgoing.clone().multiply(frame([2, 3, 5])).toArray(),
        sibling: frame([-30, 0, 0]).toArray(),
    };
    return {root, selected, incoming, parentFrame, local, outgoing, tipLocal};
}
function harness(treeData) {
    const robotRoot = new THREE.Group();
    robotRoot.position.set(3, -4, 5);
    robotRoot.rotation.set(0.1, -0.2, 0.3);
    const meshDict = {}, collisionMeshDict = {};
    for (const component of components(treeData)) {
        for (const dict of [meshDict, collisionMeshDict]) {
            const mesh = new THREE.Object3D();
            new THREE.Matrix4().fromArray(treeData._preview_transforms[component])
                .decompose(mesh.position, mesh.quaternion, mesh.scale);
            robotRoot.add(mesh);
            dict[component] = mesh;
        }
    }
    const context = vm.createContext({
        THREE, treeData, robotRoot, meshDict, collisionMeshDict,
        previewJointControllers: [], previewPivotGroups: [], jointFrameHelpers: [],
        previewRigReady: false, previewRigDirty: false, previewControlsDirty: false,
        selectedElement: null, SensorEditor: {invalidateViewer() {}},
        window: {
            PetasosMimicPreview: require('../URDF_Exporter/core/mimic_preview.js'),
            PetasosJointZeroFrame: require('../URDF_Exporter/core/joint_zero_frame.js'),
        },
        document: {querySelectorAll: () => [], getElementById: () => null},
        collectNodeComponents: components, getFlatLinks: entries,
        isPatcherJointActive: () => true, isJointDisabled: () => false, isLinkDisabled: () => false,
        attachJointSnapMarkerToRig() {}, applyPreviewControlState() {}, applyViewerIsolationVisibility() {},
        scheduleWorkspaceAutosave() {}, updateSelectedJointFrameVisibility() {},
        saveState() {},
    });
    for (const name of [
        'buildPreviewJointRig', 'clearPreviewJointRig', 'ensureJointMotionLimits',
        'setPreviewJointValue', 'applyPreviewJointValue', 'syncAllMimicPreviewValues',
        'updateJointRpyVal', 'setPreviewJointRpy', 'jointEntryFor', 'jointEntryForNode',
        'previewFrameMatrixForNode', 'syncPickedJointLocalFrames',
        'ensureJointCadTransformSnapshot', 'cloneJointSetting',
        'ensurePreviewJointWorldFrames', 'updateStoredJointWorldFrame', 'applyJointZeroDeltaToSubtree',
        'neutralFrameForFaceAlignmentParent',
        'setPreviewJointZero', 'cloneJsonValue', 'shiftMimicOffsetsForNewZero',
        'previewControllerZeroWorldFrame', 'previewControllerNeutralZeroWorldFrame',
    ]) vm.runInContext(extract(name), context);
    if (source.includes('        function applyJointOriginRpyChange(')) {
        vm.runInContext(extract('applyJointOriginRpyChange'), context);
    }
    if (source.includes('        function syncJointOriginRpyInputs(')) {
        vm.runInContext(extract('syncJointOriginRpyInputs'), context);
    }
    for (const name of ['previewNeutralFrameForJoint', 'jointOriginParentFrame', 'getJointOriginRpy']) {
        if (source.includes(`        function ${name}(`)) vm.runInContext(extract(name), context);
    }
    context.render = () => { if (context.previewRigDirty) context.buildPreviewJointRig(); };
    context.refreshPreviewRig = () => context.buildPreviewJointRig();
    context.buildPreviewJointRig();
    return context;
}
function rootMatrix(context, mesh) {
    context.robotRoot.updateMatrixWorld(true);
    return context.robotRoot.matrixWorld.clone().invert().multiply(mesh.matrixWorld);
}
function edit(context, joint, axis, degrees, fromPreview = false) {
    if (fromPreview) {
        context.setPreviewJointRpy(context.previewJointControllers.findIndex(c => c.jointObj === joint), axis, degrees);
    } else {
        context.selectedElement = {jointObj: joint};
        context.updateJointRpyVal(joint.joint_name, axis, degrees);
    }
}
function expectedPosed(context, neutralTransform, local, data) {
    const motion = (joint) => joint.joint_type === 'fixed' ? new THREE.Matrix4() : joint.joint_type === 'prismatic'
        ? new THREE.Matrix4().makeTranslation(0, 0, joint.joint_info.initial_position * 1000)
        : new THREE.Matrix4().makeRotationZ(joint.joint_info.initial_position);
    return data.parentFrame.clone().multiply(motion(data.root.children[0]))
        .multiply(local).multiply(motion(data.selected))
        .multiply(data.incoming.clone().invert()).multiply(neutralTransform);
}

test('panel RPY edit rotates the whole neutral subtree and preserves joint limits and slider pose', () => {
    const data = fixture({posed: true});
    const c = harness(data.root);
    const meshBefore = new THREE.Matrix4().fromArray(data.root._preview_transforms.tool);
    const unrelated = JSON.stringify(data.root._preview_transforms.arm);
    const jointBefore = JSON.stringify(data.selected.joint_info);
    const nextLocal = frame([45, -12, 8], [-0.1, 0.2, Math.PI / 2]);
    const nextWorld = data.parentFrame.clone().multiply(nextLocal);
    const delta = nextWorld.clone().multiply(data.incoming.clone().invert());
    edit(c, data.selected, 2, 90);
    close(new THREE.Matrix4().fromArray(data.root._preview_transforms.tool), delta.clone().multiply(meshBefore), 'stored mesh rotated');
    close(new THREE.Matrix4().fromArray(data.selected.joint_info._preview_world_frame_matrix), nextWorld, 'incoming frame');
    close(new THREE.Matrix4().fromArray(data.selected.link_group.children[0].joint_info._preview_world_frame_matrix), delta.clone().multiply(data.outgoing), 'child frame follows');
    close(rootMatrix(c, c.meshDict.tool), expectedPosed(c, meshBefore, nextLocal, data), 'posed mesh rotated once');
    close(rootMatrix(c, c.collisionMeshDict.tool), rootMatrix(c, c.meshDict.tool), 'collision follows visual');
    assert.equal(JSON.stringify(data.root._preview_transforms.arm), unrelated);
    const previous = JSON.parse(jointBefore);
    for (const key of ['axis', 'initial_position', 'lower_limit', 'upper_limit']) {
        assert.deepEqual(data.selected.joint_info[key], previous[key]);
    }
});

for (const type of ['revolute', 'prismatic', 'fixed']) {
    test(`${type}: panel and preview rotations agree after rebuild and saved-work reload`, () => {
        const a = fixture({posed: true, type}), b = fixture({posed: true, type});
        const ca = harness(a.root), cb = harness(b.root);
        for (const [axis, degrees] of [[0, 37], [1, -42], [2, 80], [2, -25.1]]) {
            edit(ca, a.selected, axis, degrees);
            edit(cb, b.selected, axis, degrees, true);
        }
        const target = frame([45, -12, 8], [37, -42, -25.1].map(v => v * Math.PI / 180));
        const originalMesh = new THREE.Matrix4().fromArray(fixture({posed: true, type}).root._preview_transforms.tool);
        close(rootMatrix(ca, ca.meshDict.tool), expectedPosed(ca, originalMesh, target, a), 'panel posed rotation');
        close(rootMatrix(cb, cb.meshDict.tool), rootMatrix(ca, ca.meshDict.tool), 'preview matches panel');
        const before = rootMatrix(ca, ca.meshDict.tip);
        ca.buildPreviewJointRig();
        cb.buildPreviewJointRig();
        close(rootMatrix(ca, ca.meshDict.tip), before, 'rebuild retains tip');
        close(rootMatrix(cb, cb.meshDict.tip), before, 'preview rebuild retains tip');
        const restored = harness(JSON.parse(JSON.stringify(a.root)));
        close(rootMatrix(restored, restored.meshDict.tip), before, 'saved work retains tip');
    });
}

test('imported joints without picked world-frame caches also rotate and retain downstream connections', () => {
    const data = fixture({picked: false, posed: true});
    const c = harness(data.root);
    const originalMesh = new THREE.Matrix4().fromArray(data.root._preview_transforms.tool);
    const nextLocal = frame([45, -12, 8], [-0.1, -0.8, -0.3]);
    edit(c, data.selected, 1, -0.8 * 180 / Math.PI);
    close(rootMatrix(c, c.meshDict.tool), expectedPosed(c, originalMesh, nextLocal, data), 'imported origin edit');
    const before = rootMatrix(c, c.meshDict.tip);
    c.buildPreviewJointRig();
    close(rootMatrix(c, c.meshDict.tip), before, 'imported tip stable');
});

test('stale panel events cannot change a different selected joint', () => {
    const data = fixture();
    const c = harness(data.root);
    c.selectedElement = {jointObj: data.root.children[0]};
    const before = JSON.stringify(data.root);
    c.updateJointRpyVal('selected', 2, 90);
    assert.equal(JSON.stringify(data.root), before);
});

test('zero calibration after an origin rotation preserves the current posed assembly', () => {
    const data = fixture({posed: true});
    const c = harness(data.root);
    edit(c, data.selected, 0, 45);
    const toolBefore = rootMatrix(c, c.meshDict.tool);
    const tipBefore = rootMatrix(c, c.meshDict.tip);
    const index = c.previewJointControllers.findIndex(controller => controller.jointObj === data.selected);
    assert.equal(c.setPreviewJointZero(index), true);
    close(rootMatrix(c, c.meshDict.tool), toolBefore, 'zero retains rotated tool');
    close(rootMatrix(c, c.meshDict.tip), tipBefore, 'zero retains downstream tip');
    assert.equal(data.selected.joint_info.initial_position, 0);
    const restored = harness(JSON.parse(JSON.stringify(data.root)));
    close(rootMatrix(restored, restored.meshDict.tip), tipBefore, 'zero plus rotation persists');
});

test('origin rotations retain mimic following before and after a rebuild', () => {
    const data = fixture({posed: true});
    Object.assign(data.selected.joint_info, {mimic_joint: 'parent', mimic_multiplier: -1, mimic_offset: 0.1});
    const c = harness(data.root);
    edit(c, data.selected, 2, 50, true);
    const expected = -data.root.children[0].joint_info.initial_position + 0.1;
    assert.ok(Math.abs(data.selected.joint_info.initial_position - expected) < 1e-9);
    const before = rootMatrix(c, c.meshDict.tip);
    c.buildPreviewJointRig();
    close(rootMatrix(c, c.meshDict.tip), before, 'mimic rotated subtree survives rebuild');
});

test('preview RPY inputs remain immediate while the selected-joint toolbox omits manual rotation and restore', () => {
    const toolboxStart = source.indexOf('const jointOriginToolsHtml =');
    const toolboxEnd = source.indexOf('const jointProperty', toolboxStart);
    const toolbox = source.slice(toolboxStart, toolboxEnd > toolboxStart ? toolboxEnd : toolboxStart + 5500);
    assert.ok(!toolbox.includes('oninput="updateJointRpyVal('));
    assert.ok(!toolbox.includes('restoreImportedAssemblyPose(true)'));
    const start = source.indexOf("container.querySelectorAll('[data-preview-rpy]')");
    const end = source.indexOf("container.querySelectorAll(", start + 30);
    const bindings = source.slice(start, end);
    assert.match(bindings, /addEventListener\('input'/);
    assert.match(bindings, /addEventListener\('focus'/);
});

test('typing updates the live pivot immediately without rebuilding focused input DOM', () => {
    const data = fixture({posed: true});
    const c = harness(data.root);
    c.selectedElement = {jointObj: data.selected};
    const controller = c.previewJointControllers.find(item => item.jointObj === data.selected);
    const pivotBefore = controller.pivot;
    const index = c.previewJointControllers.indexOf(controller);
    const input = {dataset: {jointRpyName: 'selected', axis: '2'}, value: '-25.1'};
    const counterpart = {dataset: {previewRpy: String(index), axis: '2'}, value: '-17.2'};
    c.document.activeElement = input;
    c.document.querySelectorAll = selector => selector === '[data-joint-rpy-name], [data-preview-rpy]'
        ? [input, counterpart] : [];
    c.render = () => { throw new Error('render would replace the focused input'); };
    c.saveState = () => { throw new Error('live input must reuse the history saved on focus'); };
    let autosaves = 0;
    c.scheduleWorkspaceAutosave = () => { autosaves++; };
    const meshBefore = new THREE.Matrix4().fromArray(data.root._preview_transforms.tool);
    for (const value of ['-2', '-25', '-25.1']) {
        input.value = value;
        c.updateJointRpyVal('selected', 2, input.value, false);
    }
    const nextLocal = frame([45, -12, 8], [-0.1, 0.2, -25.1 * Math.PI / 180]);
    close(rootMatrix(c, c.meshDict.tool), expectedPosed(c, meshBefore, nextLocal, data), 'input immediately rotates the posed tool');
    assert.equal(controller.pivot, pivotBefore);
    assert.equal(c.document.activeElement, input);
    assert.equal(input.value, '-25.1');
    assert.equal(counterpart.value, '-25.1');
    assert.equal(autosaves, 3);
    const beforeInvalidInput = rootMatrix(c, c.meshDict.tool);
    c.setPreviewJointRpy(index, 2, '', false);
    close(rootMatrix(c, c.meshDict.tool), beforeInvalidInput, 'partial number does not rotate to zero');
});

test('a 0.1 degree root-joint edit stays small when the CAD base frame is rotated', () => {
    const data = fixture({posed: true});
    const baseFrame = frame([3, -4, 5], [1.1, -0.7, 0.9]);
    data.root._preview_transforms.base = baseFrame.toArray();
    const rootJoint = data.root.children[0];
    const local = baseFrame.clone().invert().multiply(data.parentFrame);
    const rotation = new THREE.Euler().setFromRotationMatrix(local, 'ZYX');
    rootJoint.joint_info.rpy = [rotation.x, rotation.y, rotation.z];
    rootJoint.joint_info._manual_rpy = rootJoint.joint_info.rpy.slice();
    const c = harness(data.root);
    const before = rootMatrix(c, c.meshDict.arm);
    const nextDegrees = rotation.z * 180 / Math.PI + 0.1;
    edit(c, rootJoint, 2, nextDegrees);
    const after = rootMatrix(c, c.meshDict.arm);
    const change = new THREE.Quaternion().setFromRotationMatrix(before).angleTo(
        new THREE.Quaternion().setFromRotationMatrix(after)
    );
    assert.ok(change < 0.101 * Math.PI / 180, `0.1 degree input caused ${change * 180 / Math.PI} degrees of rotation`);
    const wanted = baseFrame.clone().multiply(frame(
        new THREE.Vector3().setFromMatrixPosition(local).toArray(),
        [rotation.x, rotation.y, nextDegrees * Math.PI / 180]
    ));
    close(new THREE.Matrix4().fromArray(rootJoint.joint_info._preview_world_frame_matrix), wanted, 'rotation uses CAD base parent');
    c.buildPreviewJointRig();
    close(rootMatrix(c, c.meshDict.arm), after, 'root correction survives rebuild');
});

test('display and the next edit use the actual picked frame even if cached Euler values are stale', () => {
    const data = fixture({posed: true});
    data.selected.joint_info._manual_rpy = [0, 0, 0];
    data.selected.joint_info.rpy = [0, 0, 0];
    const c = harness(data.root);
    assert.equal(typeof c.getJointOriginRpy, 'function');
    const shown = c.getJointOriginRpy(data.selected);
    assert.ok(Math.abs(shown[0] + 0.1) < 1e-9);
    assert.ok(Math.abs(shown[1] - 0.2) < 1e-9);
    const before = rootMatrix(c, c.meshDict.tool);
    edit(c, data.selected, 2, shown[2] * 180 / Math.PI + 0.1);
    const after = rootMatrix(c, c.meshDict.tool);
    const change = new THREE.Quaternion().setFromRotationMatrix(before).angleTo(
        new THREE.Quaternion().setFromRotationMatrix(after)
    );
    assert.ok(change < 0.101 * Math.PI / 180);
});

test('continuing to edit past a 90 degree Euler boundary does not jump to another representation', () => {
    const data = fixture({posed: true});
    const c = harness(data.root);
    edit(c, data.selected, 1, 100);
    const before = rootMatrix(c, c.meshDict.tool);
    assert.ok(Math.abs(c.getJointOriginRpy(data.selected)[1] * 180 / Math.PI - 100) < 1e-8);
    edit(c, data.selected, 1, 100.1);
    const after = rootMatrix(c, c.meshDict.tool);
    const degrees = new THREE.Quaternion().setFromRotationMatrix(before)
        .angleTo(new THREE.Quaternion().setFromRotationMatrix(after)) * 180 / Math.PI;
    assert.ok(Math.abs(degrees - 0.1) < 1e-6);
});
