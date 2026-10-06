(function (root) {
    'use strict';

    const rotationalTypes = new Set(['revolute', 'continuous']);

    function sameUnitFamily(first, second) {
        if (rotationalTypes.has(first)) return rotationalTypes.has(second);
        return first === 'prismatic' && second === 'prismatic';
    }

    function previewToUrdfValue(controller, value) {
        return rotationalTypes.has(controller.type) ? value * Math.PI / 180 : value;
    }

    function urdfToPreviewValue(controller, value) {
        return rotationalTypes.has(controller.type) ? value * 180 / Math.PI : value;
    }

    function resolveMimicPreviewValues(controllers, masterController, masterPreviewValue) {
        if (!Array.isArray(controllers) || !masterController || !Number.isFinite(Number(masterPreviewValue))) {
            return [];
        }

        const counts = new Map();
        const byName = new Map();
        controllers.forEach(controller => {
            if (controller && controller.name) {
                counts.set(controller.name, (counts.get(controller.name) || 0) + 1);
                byName.set(controller.name, controller);
            }
        });
        if (counts.get(masterController.name) !== 1) return [];

        const byMaster = new Map();
        controllers.forEach(controller => {
            const info = controller && controller.jointInfo;
            if (!controller || !info || !info.mimic_joint
                || counts.get(controller.name) !== 1
                || counts.get(info.mimic_joint) !== 1) return;
            if (!sameUnitFamily(controller.type, byName.get(info.mimic_joint)?.type)) return;
            const followers = byMaster.get(info.mimic_joint) || [];
            followers.push(controller);
            byMaster.set(info.mimic_joint, followers);
        });

        const visited = new Set([masterController.name]);
        const queue = [{ controller: masterController, urdfValue: previewToUrdfValue(masterController, Number(masterPreviewValue)) }];
        const updates = [];
        for (let cursor = 0; cursor < queue.length; cursor += 1) {
            const current = queue[cursor];
            for (const follower of byMaster.get(current.controller.name) || []) {
                if (visited.has(follower.name)) continue;
                const info = follower.jointInfo || {};
                const multiplierValue = Number(info.mimic_multiplier);
                const offsetValue = Number(info.mimic_offset);
                const multiplier = Number.isFinite(multiplierValue) ? multiplierValue : 1;
                const offset = Number.isFinite(offsetValue) ? offsetValue : 0;
                const urdfValue = current.urdfValue * multiplier + offset;
                const previewValue = urdfToPreviewValue(follower, urdfValue);
                if (!Number.isFinite(previewValue)) continue;
                visited.add(follower.name);
                updates.push({ controller: follower, value: previewValue });
                queue.push({ controller: follower, urdfValue });
            }
        }
        return updates;
    }

    const api = { resolveMimicPreviewValues };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.PetasosMimicPreview = api;
})(typeof window !== 'undefined' ? window : globalThis);
