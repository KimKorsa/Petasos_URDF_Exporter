const {test} = require('node:test');
const assert = require('node:assert/strict');
const {toggleModuleSelection, selectModuleRect} = require('../URDF_Exporter/core/module_selection.js');
test('ctrl toggles one ID without mutating selection', () => {
    const original = {linkIds:['a'],jointIds:[]};
    assert.deepEqual(toggleModuleSelection(original, 'link', 'a'), {linkIds:[],jointIds:[]});
    assert.deepEqual(original.linkIds, ['a']);
});
test('rectangle selects centers only, not crossing wires; ctrl adds', () => {
    const entries = [{kind:'link',id:'a',x:5,y:5},{kind:'joint',id:'wire',x:20,y:20}];
    assert.deepEqual(selectModuleRect({linkIds:['b'],jointIds:[]},entries,{x1:0,y1:0,x2:10,y2:10},true), {linkIds:['b','a'],jointIds:[]});
});
