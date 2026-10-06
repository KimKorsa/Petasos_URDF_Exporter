const assert = require('node:assert/strict');
const { resolveMimicPreviewValues } = require('../URDF_Exporter/core/mimic_preview.js');

function controller(name, type, mimic_joint = '', mimic_multiplier = 1, mimic_offset = 0) {
    return { name, type, jointInfo: { mimic_joint, mimic_multiplier, mimic_offset } };
}

{
    const master = controller('master', 'revolute');
    const follower = controller('follower', 'continuous', 'master', -2, 0.25);
    const updates = resolveMimicPreviewValues([master, follower], master, 90);
    assert.equal(updates.length, 1);
    assert.equal(updates[0].controller, follower);
    assert.ok(Math.abs(updates[0].value - (-180 + 0.25 * 180 / Math.PI)) < 1e-9);
}

{
    const master = controller('slide', 'prismatic');
    const follower = controller('follower_slide', 'prismatic', 'slide', -0.5, 0.02);
    const updates = resolveMimicPreviewValues([master, follower], master, 0.04);
    assert.ok(Math.abs(updates[0].value) < 1e-12);
}

{
    const master = controller('master', 'revolute');
    const first = controller('first', 'revolute', 'master', 2, 10 * Math.PI / 180);
    const second = controller('second', 'revolute', 'first', -0.5, 5 * Math.PI / 180);
    const updates = resolveMimicPreviewValues([master, first, second], master, 30);
    assert.deepEqual(updates.map(item => item.controller.name), ['first', 'second']);
    assert.ok(Math.abs(updates[0].value - 70) < 1e-9);
    assert.ok(Math.abs(updates[1].value - -30) < 1e-9);
}

{
    const master = controller('master', 'revolute');
    const follower = controller('follower', 'prismatic', 'master');
    assert.deepEqual(resolveMimicPreviewValues([master, follower], master, 30), []);
}

{
    const first = controller('first', 'revolute', 'second');
    const second = controller('second', 'revolute', 'first');
    assert.deepEqual(resolveMimicPreviewValues([first, second], first, 10).map(item => item.controller.name), ['second']);
}

{
    const master = controller('master', 'revolute');
    const follower = controller('follower', 'revolute', 'master');
    const duplicate = controller('master', 'revolute');
    assert.deepEqual(resolveMimicPreviewValues([master, follower, duplicate], master, 10), []);
}

console.log('mimic preview tests passed');
