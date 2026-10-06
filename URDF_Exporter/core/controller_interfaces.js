(function (root) {
    'use strict';

    function requiredCommandInterface(type, settings = {}) {
        const normalized = String(type || '').toLowerCase();
        if (normalized.includes('jointstatebroadcaster')) return null;
        if (normalized.includes('velocity') || normalized.includes('diff_drive')) return 'velocity';
        if (normalized.includes('effort')) return 'effort';
        if (normalized.includes('forwardcommand') || normalized.includes('pidcontroller')) {
            return settings.command_interface || 'position';
        }
        return 'position';
    }

    function findControllerInterfaceIssues(controllers, joints) {
        const jointsByName = new Map((joints || [])
            .filter(joint => joint && joint.joint_name)
            .map(joint => [joint.joint_name, joint]));
        const issues = [];
        (controllers || []).forEach(controller => {
            if (!controller) return;
            const expected = requiredCommandInterface(controller.type, controller.settings);
            if (!expected) return;
            const names = new Set(controller.joints || []);
            if (controller.settings?.joint) names.add(controller.settings.joint);
            names.forEach(jointName => {
                const joint = jointsByName.get(jointName);
                if (!joint) return;
                const actual = joint.joint_info?.command_interface || 'position';
                if (actual === expected) return;
                issues.push({
                    jointName,
                    controllerName: controller.name || controller.type || 'controller',
                    controllerType: controller.type || '',
                    expected,
                    actual,
                });
            });
        });
        return issues;
    }

    const api = {requiredCommandInterface, findControllerInterfaceIssues};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.PetasosControllerInterfaces = api;
})(typeof window !== 'undefined' ? window : globalThis);
