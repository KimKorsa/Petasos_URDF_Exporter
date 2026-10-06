const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {toggleModuleSelection, selectModuleRect, selectControllerJointRect} = require('../URDF_Exporter/core/module_selection.js');
test('ctrl toggles one ID without mutating selection', () => {
    const original = {linkIds:['a'],jointIds:[]};
    assert.deepEqual(toggleModuleSelection(original, 'link', 'a'), {linkIds:[],jointIds:[]});
    assert.deepEqual(original.linkIds, ['a']);
});
test('rectangle selects centers only, not crossing wires; ctrl adds', () => {
    const entries = [{kind:'link',id:'a',x:5,y:5},{kind:'joint',id:'wire',x:20,y:20}];
    assert.deepEqual(selectModuleRect({linkIds:['b'],jointIds:[]},entries,{x1:0,y1:0,x2:10,y2:10},true), {linkIds:['b','a'],jointIds:[]});
});
test('controller rectangle selects movable joint labels and supports additive selection', () => {
    assert.equal(typeof selectControllerJointRect, 'function');
    const entries = [
        {kind:'joint',id:'joint_a',x:8,y:8,movable:true},
        {kind:'joint',id:'joint_b',x:28,y:8,movable:true},
        {kind:'joint',id:'joint_fixed',x:8,y:28,movable:false},
        {kind:'link',id:'link_a',x:8,y:8,movable:true},
    ];
    const rect = {x1:0,y1:0,x2:16,y2:16};
    assert.deepEqual(selectControllerJointRect([], entries, rect, false), ['joint_a']);
    assert.deepEqual(selectControllerJointRect(['joint_b'], entries, rect, true), ['joint_b','joint_a']);
});
test('controller mode starts a joint marquee from blank canvas drags', () => {
    const webUi = fs.readFileSync(path.join(__dirname, '../URDF_Exporter/core/web_ui.py'), 'utf8');
    assert.match(webUi, /function beginControllerJointMarquee\(event, viewport\)/);
    assert.match(webUi, /patcherControllerSelectionMode && beginControllerJointMarquee\(event, viewport\)/);
});
