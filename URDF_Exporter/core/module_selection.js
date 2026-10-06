(function (root) {
    function toggleModuleSelection(selection, kind, id) {
        const result = {linkIds: [...selection.linkIds], jointIds: [...selection.jointIds]};
        const key = kind === 'link' ? 'linkIds' : 'jointIds';
        result[key] = result[key].includes(id) ? result[key].filter(value => value !== id) : [...result[key], id];
        return result;
    }
    function selectModuleRect(selection, entries, rect, additive) {
        const result = additive ? {linkIds: [...selection.linkIds], jointIds: [...selection.jointIds]} : {linkIds: [], jointIds: []};
        const selected = {linkIds: new Set(result.linkIds), jointIds: new Set(result.jointIds)};
        const minX = Math.min(rect.x1, rect.x2), maxX = Math.max(rect.x1, rect.x2);
        const minY = Math.min(rect.y1, rect.y2), maxY = Math.max(rect.y1, rect.y2);
        entries.forEach(entry => {
            if (entry.x >= minX && entry.x <= maxX && entry.y >= minY && entry.y <= maxY) {
                const key = entry.kind === 'link' ? 'linkIds' : 'jointIds';
                if (!selected[key].has(entry.id)) {
                    result[key].push(entry.id);
                    selected[key].add(entry.id);
                }
            }
        });
        return result;
    }
    function selectControllerJointRect(currentJointIds, entries, rect, additive) {
        const movableJoints = (entries || []).filter(entry => (
            entry.kind === 'joint' && entry.movable === true
        ));
        return selectModuleRect(
            {linkIds: [], jointIds: Array.isArray(currentJointIds) ? currentJointIds : []},
            movableJoints,
            rect,
            additive
        ).jointIds;
    }
    const api = {toggleModuleSelection, selectModuleRect, selectControllerJointRect};
    if (typeof module !== 'undefined') module.exports = api;
    else root.ModuleSelection = api;
})(globalThis);
