const {test} = require('node:test');
const assert = require('node:assert/strict');
const SensorEditor = require('../URDF_Exporter/core/sensor_ui.js');

test('sensor coordinate UI converts mm and degrees without mutating stored pose', () => {
  const sensor = {xyz_m: [0.1, -0.02, 0.005], rpy_rad: [0, 0, Math.PI / 2]};
  assert.deepEqual(SensorEditor.toDisplay(sensor).xyz_mm, [100, -20, 5]);
  assert.equal(SensorEditor.toDisplay(sensor).rpy_deg[2], 90);
  assert.deepEqual(SensorEditor.withDisplayPose(sensor, [10, 20, 30], [0, 0, 180]).xyz_m, [0.01, 0.02, 0.03]);
  assert.equal(sensor.xyz_m[0], 0.1);
});

test('only selected sensor owns marker and world pick uses link inverse', () => {
  assert.equal(SensorEditor.markerVisible('a', 'a', 'sensor'), true);
  assert.equal(SensorEditor.markerVisible('a', 'b', 'sensor'), false);
  assert.equal(SensorEditor.markerVisible('a', 'a', 'link'), false);
  const inverse = [0, 1, 0, -2, -1, 0, 0, 1, 0, 0, 1, -3, 0, 0, 0, 1];
  assert.deepEqual(SensorEditor.localPointFromWorld([1, 3, 3], inverse), [1, 0, 0]);
});

test('root sensor uses first CAD component frame, child uses joint pivot', () => {
  const root = {components: ['base_part'], _pivot: {id: 'world'}};
  const child = {components: ['arm_part'], _pivot: {id: 'joint'}};
  const meshes = {base_part: {id: 'cad-base'}};
  assert.equal(SensorEditor.frameFor(root, root, meshes), meshes.base_part);
  assert.equal(SensorEditor.frameFor(child, root, meshes), child._pivot);
});

test('editor rejects frame names colliding with links or other sensors', () => {
  const tree = {name:'base', children:[{joint_name:'imu_frame_joint',link_group:{name:'arm',children:[]}}],
    _sensors:[{id:'a',name:'camera',type:'generic'}]};
  assert.equal(SensorEditor.nameConflict('camera',tree,'a'), false);
  assert.equal(SensorEditor.nameConflict('camera',tree,'b'), true);
  assert.equal(SensorEditor.nameConflict('arm',tree,'b'), false);
  assert.equal(SensorEditor.nameConflict('camera_frame',tree,'b'), true);
  assert.equal(SensorEditor.nameConflict('imu',tree,'b'), true);
  assert.equal(SensorEditor.nameConflict('lidar',tree,'b'), false);
});

test('display conversion rejects degree overflow after radians conversion', () => {
  assert.throws(() => SensorEditor.withDisplayPose({xyz_m:[0,0,0],rpy_rad:[0,0,0]},
    [0,0,0],[Number.MAX_VALUE,0,0]));
});

test('sensor parent selector lists active links and excludes disabled branches', () => {
  const tree = {_link_id:'root',name:'base',components:['a'],children:[
    {link_group:{_link_id:'child',name:'arm',components:['b'],children:[]}},
    {disabled:true,link_group:{_link_id:'hidden',name:'hidden',components:['c'],children:[]}}
  ]};
  assert.deepEqual(SensorEditor.linkOptions(tree).map(node=>node._link_id),['root','child']);
});

test('reparent preserves sensor world pose across translated and rotated link frames', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const world = new THREE.Group();
  const rootFrame = new THREE.Group(); rootFrame.position.x = 100; rootFrame.rotation.z = Math.PI / 2; world.add(rootFrame);
  const childFrame = new THREE.Group(); childFrame.position.x = 200; world.add(childFrame);
  const child = {_link_id:'child',name:'arm',components:['arm_part'],children:[],_pivot:childFrame};
  const sensor = {id:'a',name:'camera',type:'generic',parent_link_id:'root',xyz_m:[.01,0,0],rpy_rad:[0,0,0]};
  global.THREE = THREE;
  global.treeData = {_link_id:'root',name:'base',components:['base_part'],children:[{link_group:child}],
    _preview_units_per_meter:1000,_sensors:[sensor]};
  global.meshDict = {base_part:rootFrame};
  global.saveState = () => {};
  global.updatePanel = () => {};
  global.scheduleWorkspaceAutosave = () => {};
  global.selectedElement = {type:'sensor',sensorId:'a'};
  SensorEditor.selectedId = 'a';
  const previousRenderMarker = SensorEditor.renderMarker;
  SensorEditor.renderMarker = () => {};
  SensorEditor.reparent('child');
  SensorEditor.renderMarker = previousRenderMarker;
  assert.equal(sensor.parent_link_id,'child');
  assert.ok(Math.abs(sensor.xyz_m[0] + .1) < 1e-10);
  assert.ok(Math.abs(sensor.xyz_m[1] - .01) < 1e-10);
  assert.ok(Math.abs(sensor.rpy_rad[2] - Math.PI / 2) < 1e-10);
});

test('stale sensor pick cannot move sensor after another item is selected', () => {
  const sensor = {id:'s',name:'imu',parent_link_id:'root',xyz_m:[0,0,0],rpy_rad:[0,0,0]};
  global.treeData = {_link_id:'root',name:'base',components:['part'],children:[],_sensors:[sensor]};
  global.selectedElement = {type:'link'};
  SensorEditor.selectedId = 's';
  SensorEditor.pickMode = true;
  assert.equal(SensorEditor.pickWorldPoint([50,0,0]),false);
  assert.equal(SensorEditor.pickMode,false);
  assert.deepEqual(sensor.xyz_m,[0,0,0]);
});
