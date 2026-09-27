(function (root) {
    function toggleModuleSelection(selection, kind, id) {
        const result = {linkIds: [...selection.linkIds], jointIds: [...selection.jointIds]};
        const key = kind === 'link' ? 'linkIds' : 'jointIds';
        result[key] = result[key].includes(id) ? result[key].filter(value => value !== id) : [...result[key], id];
        return result;
    }
    function selectModuleRect(selection, entries, rect, additive) {
        const result = additive ? {linkIds: [...selection.linkIds], jointIds: [...selection.jointIds]} : {linkIds: [], jointIds: []};
        entries.forEach(entry => {
            if (entry.x >= Math.min(rect.x1, rect.x2) && entry.x <= Math.max(rect.x1, rect.x2)
                && entry.y >= Math.min(rect.y1, rect.y2) && entry.y <= Math.max(rect.y1, rect.y2)) {
                const key = entry.kind === 'link' ? 'linkIds' : 'jointIds';
                if (!result[key].includes(entry.id)) result[key].push(entry.id);
            }
        });
        return result;
    }
    const api = {toggleModuleSelection, selectModuleRect};
    if (typeof module !== 'undefined') module.exports = api;
    else root.ModuleSelection = api;
})(globalThis);
