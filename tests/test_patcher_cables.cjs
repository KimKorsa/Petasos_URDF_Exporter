const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../URDF_Exporter/core/web_ui.py'), 'utf8');
const start = source.indexOf('function renderPatcherCables()');
const end = source.indexOf('function armPatcherConnectionByClick', start);
const rendererSource = source.slice(start, end);

for (const withIssue of [false, true]) {
    test(`cables, controller and module decorations render with interface warning ${withIssue}`, () => {
        const elements = [];
        const paths = [];
        const element = () => ({
            dataset: {}, style: {}, classes: new Set(),
            classList: {add(...names) { names.forEach(name => this.owner.classes.add(name)); }},
            setAttribute(name, value) { this[name] = value; },
        });
        const create = () => {
            const result = element();
            result.classList.owner = result;
            return result;
        };
        const svg = {appendChild(item) { paths.push(item); }};
        const canvas = {
            querySelector: () => svg,
            querySelectorAll: () => [],
            appendChild(item) { elements.push(item); },
        };
        const root = {name: 'base'};
        const joints = ['joint_1', 'joint_2'].map(joint_name => ({joint_name, joint_type: 'revolute', joint_info: {}}));
        const entries = [{node: root}, ...joints.map((jointObj, i) => ({jointObj, node: {name: `link_${i + 1}`}, parentNode: root}))];
        let controllerRendered = 0;
        let moduleRendered = 0;
        const context = {
            document: {getElementById: () => canvas, createElement: create, createElementNS: create},
            treeData: root, selectedElement: null,
            patcherEntries: () => entries,
            controllerInterfaceIssues: () => withIssue ? [{jointName: 'joint_2', expected: 'effort', actual: 'position'}] : [],
            rootJointMode: () => 'none',
            isPatcherJointActive: () => true, isJointDisabled: () => false, isLinkDisabled: () => false,
            ensurePatcherNodeId: node => node.name,
            patcherPortPoint: () => ({x: 10, y: 20}), cablePath: () => 'M 0 0 L 10 20',
            patcherControllerJointSelection: new Set(),
            renderPatcherControllerFrames: () => { controllerRendered++; },
            ModuleEditor: {decorate() { moduleRendered++; }},
            petasosTranslateText: text => text,
            patcherConnectionDrag: {pointer: {x: 30, y: 40}, parentNode: root},
            patcherNodeIdFor: node => node.name,
        };
        vm.createContext(context);
        vm.runInContext(rendererSource, context);
        assert.doesNotThrow(() => context.renderPatcherCables());
        assert.equal(elements.length, 2, 'both joints have clickable labels');
        assert.equal(paths.length, 3, 'both saved wires and the connection-drag wire render');
        assert.equal(controllerRendered, 1);
        assert.equal(moduleRendered, 1);
        assert.equal(elements[1].classes.has('interface-error'), withIssue);
    });
}
