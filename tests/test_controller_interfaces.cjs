const {test} = require('node:test');
const assert = require('node:assert/strict');
const {
    requiredCommandInterface,
    findControllerInterfaceIssues,
} = require('../URDF_Exporter/core/controller_interfaces.js');

test('effort gripper controller requires effort command interface despite lowercase type prefix', () => {
    assert.equal(
        requiredCommandInterface('effort_controllers/GripperActionController'),
        'effort'
    );
});

test('mismatched gripper is reported with its joint and controller for the UI to focus', () => {
    const issues = findControllerInterfaceIssues([
        {
            name: 'effort_gripper_controller',
            type: 'effort_controllers/GripperActionController',
            joints: ['joint_8'],
        },
    ], [
        {joint_name: 'joint_8', joint_info: {command_interface: 'position'}},
    ]);

    assert.deepEqual(issues, [{
        jointName: 'joint_8',
        controllerName: 'effort_gripper_controller',
        controllerType: 'effort_controllers/GripperActionController',
        expected: 'effort',
        actual: 'position',
    }]);
});

test('matching controller interfaces and state-only broadcasters produce no issues', () => {
    const controllers = [
        {name: 'gripper', type: 'effort_controllers/GripperActionController', joints: ['joint_8']},
        {name: 'state', type: 'joint_state_broadcaster/JointStateBroadcaster', joints: ['joint_8']},
    ];
    const joints = [{joint_name: 'joint_8', joint_info: {command_interface: 'effort'}}];
    assert.deepEqual(findControllerInterfaceIssues(controllers, joints), []);
});
