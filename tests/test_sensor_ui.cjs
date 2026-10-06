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

test('hover preview moves the sensor marker to the face without changing the saved pose', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const frame = new THREE.Group();
  const sensor = {id:'preview',name:'camera',parent_link_id:'root',xyz_m:[0.01,0,0],rpy_rad:[0,0,0]};
  global.THREE = THREE;
  global.treeData = {_link_id:'root',components:['base'],children:[],_preview_units_per_meter:1000,_sensors:[sensor]};
  global.meshDict = {base:frame};
  global.selectedElement = {type:'sensor',sensorId:'preview'};
  SensorEditor.selectedId = 'preview';
  SensorEditor.pickMode = true;

  SensorEditor.previewWorldPoint([20, 30, 40], [1, 0, 0]);

  assert.deepEqual(sensor.xyz_m,[0.01,0,0]);
  assert.deepEqual(SensorEditor.marker.position.toArray(),[20,30,40]);
  assert.equal(SensorEditor.marker.visible,true);

  SensorEditor.pickMode = false;
  SensorEditor.previewLocalPosition = null;
  SensorEditor.renderMarker();
  assert.deepEqual(SensorEditor.marker.position.toArray(),[10,0,0]);
});

test('picking a face aims sensor +X out of the clicked surface in preview and saved pose', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const frame = new THREE.Group();
  frame.rotation.z = Math.PI / 2;
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
  mesh.rotation.y = Math.PI / 2;
  mesh.updateMatrixWorld(true);
  const sensor = {id:'aim',name:'camera',parent_link_id:'root',xyz_m:[0,0,0],rpy_rad:[0,0,0]};
  global.THREE = THREE;
  global.treeData = {_link_id:'root',components:['base'],children:[],_preview_units_per_meter:1000,_sensors:[sensor]};
  global.meshDict = {base:frame};
  global.selectedElement = {type:'sensor',sensorId:'aim'};
  global.viewerRaycaster = {ray:{direction:new THREE.Vector3(0,0,1)}};
  global.getViewerIntersections = () => [{point:new THREE.Vector3(20,30,40),
    face:{normal:new THREE.Vector3(-1,0,0)},object:mesh}];
  global.saveState = () => {};
  global.updatePanel = () => {};
  global.scheduleWorkspaceAutosave = () => {};
  SensorEditor.selectedId = 'aim';
  SensorEditor.pickMode = true;

  SensorEditor.previewPick({});
  assert.deepEqual(SensorEditor.marker.getWorldPosition(new THREE.Vector3()).toArray(),[20,30,40]);
  const previewForward = new THREE.Vector3(1,0,0)
    .applyQuaternion(SensorEditor.marker.getWorldQuaternion(new THREE.Quaternion()));
  assert.ok(previewForward.distanceTo(new THREE.Vector3(0,0,-1)) < 1e-6, previewForward.toArray().join(','));
  assert.deepEqual(sensor.rpy_rad,[0,0,0]);

  SensorEditor.pick({});
  const savedForward = new THREE.Vector3(1,0,0)
    .applyQuaternion(SensorEditor.marker.getWorldQuaternion(new THREE.Quaternion()));
  assert.ok(savedForward.distanceTo(new THREE.Vector3(0,0,-1)) < 1e-6, savedForward.toArray().join(','));
  assert.ok(sensor.xyz_m.every((value, i) => Math.abs(value - [0.03,-0.02,0.04][i]) < 1e-10));
  assert.ok(SensorEditor.marker.getWorldPosition(new THREE.Vector3())
    .distanceTo(new THREE.Vector3(20,30,40)) < 1e-8);
  assert.equal(SensorEditor.pickMode,false);
  assert.ok(sensor.rpy_rad.some(angle => Math.abs(angle) > 1e-8));
});

test('camera icon is a compact plane parallel to the picked face', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const oldDocument = global.document;
  const context = {beginPath() {}, arc() {}, fill() {}, stroke() {}, strokeRect() {},
    moveTo() {}, lineTo() {}};
  global.THREE = THREE;
  global.document = {createElement: () => ({getContext: () => context})};
  try {
    const marker = SensorEditor.createMarker({name:'camera',type:'rgb_camera'});
    const icon = marker.userData.sensorIcon;
    const origin = marker.userData.sensorOrigin;
    assert.ok(icon.isMesh);
    assert.equal(icon.geometry.parameters.width,icon.geometry.parameters.height);
    assert.ok(Math.abs(icon.geometry.parameters.width * 89 / 96
      - origin.geometry.parameters.radius * 2) < 1e-10);
    assert.ok(icon.material.opacity < 1 && icon.material.opacity >= 0.8);
    assert.ok(new THREE.Vector3(0,0,1).applyQuaternion(icon.quaternion)
      .distanceTo(new THREE.Vector3(1,0,0)) < 1e-10);
    assert.equal(icon.position.x,2);
    SensorEditor.disposeMarker(marker);
  } finally {
    global.document = oldDocument;
  }
});

test('camera logo stays upright on horizontal and vertical faces', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const oldDocument = global.document;
  const context = {beginPath() {}, arc() {}, fill() {}, stroke() {}, strokeRect() {},
    moveTo() {}, lineTo() {}};
  const frame = new THREE.Group();
  const sensor = {id:'upright',name:'camera',type:'rgb_camera',parent_link_id:'root',
    xyz_m:[0,0,0],rpy_rad:[0,0,0]};
  global.THREE = THREE;
  global.document = {createElement: () => ({getContext: () => context})};
  global.treeData = {_link_id:'root',components:['base'],children:[],
    _preview_units_per_meter:1000,_sensors:[sensor]};
  global.meshDict = {base:frame};
  global.selectedElement = {type:'sensor',sensorId:'upright'};
  SensorEditor.invalidateViewer();
  SensorEditor.selectedId = 'upright';
  SensorEditor.pickMode = false;
  const sensorForward = new THREE.Vector3(1,0,0);
  const iconUp = () => new THREE.Vector3(0,1,0).applyQuaternion(
    SensorEditor.marker.userData.sensorIcon.getWorldQuaternion(new THREE.Quaternion()));
  const iconFront = () => new THREE.Vector3(0,0,1).applyQuaternion(
    SensorEditor.marker.userData.sensorIcon.getWorldQuaternion(new THREE.Quaternion()));

  try {
    const floorRotation = new THREE.Quaternion().setFromUnitVectors(sensorForward,
      new THREE.Vector3(0,1,0));
    const floorRpy = new THREE.Euler().setFromQuaternion(floorRotation,'ZYX');
    sensor.rpy_rad = [floorRpy.x,floorRpy.y,floorRpy.z];
    SensorEditor.renderMarker();
    assert.ok(iconFront().distanceTo(new THREE.Vector3(0,1,0)) < 1e-6);
    assert.ok(iconUp().distanceTo(new THREE.Vector3(0,0,-1)) < 1e-6);

    const wallRotation = new THREE.Quaternion().setFromUnitVectors(sensorForward,
      new THREE.Vector3(0,0,1)).multiply(
        new THREE.Quaternion().setFromAxisAngle(sensorForward,Math.PI / 2));
    const wallRpy = new THREE.Euler().setFromQuaternion(wallRotation,'ZYX');
    sensor.rpy_rad = [wallRpy.x,wallRpy.y,wallRpy.z];
    SensorEditor.renderMarker();
    assert.ok(iconFront().distanceTo(new THREE.Vector3(0,0,1)) < 1e-6);
    assert.ok(iconUp().distanceTo(new THREE.Vector3(0,1,0)) < 1e-6);
  } finally {
    global.document = oldDocument;
  }
});

test('face pick attaches the sensor to the clicked link', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const rootFrame = new THREE.Group();
  const childFrame = new THREE.Group();
  childFrame.position.x = 100;
  const faceMesh = new THREE.Mesh(new THREE.BoxGeometry(1,1,1),new THREE.MeshBasicMaterial());
  childFrame.add(faceMesh);
  childFrame.updateMatrixWorld(true);
  const child = {_link_id:'child',components:['armPart'],children:[],_pivot:childFrame};
  const sensor = {id:'attached',name:'camera',type:'rgb_camera',parent_link_id:'root',
    xyz_m:[0,0,0],rpy_rad:[0,0,0]};
  global.THREE = THREE;
  global.treeData = {_link_id:'root',components:['rootPart'],children:[{link_group:child}],
    _preview_units_per_meter:1000,_sensors:[sensor]};
  global.meshDict = {rootPart:rootFrame,armPart:faceMesh};
  global.selectedElement = {type:'sensor',sensorId:'attached'};
  global.viewerRaycaster = {ray:{direction:new THREE.Vector3(0,0,-1)}};
  global.getViewerIntersections = () => [{point:new THREE.Vector3(110,20,0),
    face:{normal:new THREE.Vector3(0,0,1)},object:faceMesh}];
  global.saveState = () => {};
  global.updatePanel = () => {};
  global.scheduleWorkspaceAutosave = () => {};
  SensorEditor.invalidateViewer();
  SensorEditor.selectedId = 'attached';
  SensorEditor.pickMode = true;

  SensorEditor.pick({});
  assert.equal(sensor.parent_link_id,'child');
  assert.equal(SensorEditor.marker.parent,childFrame);
  assert.ok(SensorEditor.marker.getWorldPosition(new THREE.Vector3())
    .distanceTo(new THREE.Vector3(110,20,0)) < 1e-8);
  childFrame.position.x = 150;
  assert.ok(SensorEditor.marker.getWorldPosition(new THREE.Vector3())
    .distanceTo(new THREE.Vector3(160,20,0)) < 1e-8);
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

test('sensor markers retain poses, follow rebuilt links, and release deleted sensors', () => {
  const THREE = require('../URDF_Exporter/vendor/three/three.min.js');
  const firstFrame = new THREE.Group();
  const child = {_link_id:'arm',components:['arm_part'],children:[],_pivot:firstFrame};
  const sensor = {id:'optimized',name:'camera',type:'rgb_camera',parent_link_id:'arm',
    xyz_m:[.01,.02,0],rpy_rad:[0,0,.3]};
  global.THREE = THREE;
  global.treeData = {_link_id:'base',components:['base_part'],children:[{link_group:child}],
    _preview_units_per_meter:1000,_sensors:[sensor]};
  global.meshDict = {base_part:new THREE.Group()};
  global.selectedElement = {type:'link'};
  SensorEditor.invalidateViewer();
  SensorEditor.renderMarker();
  const marker = SensorEditor.markers.get(sensor.id);
  assert.equal(marker.visible,true);
  assert.equal(marker.parent,firstFrame);
  assert.deepEqual(marker.position.toArray(),[10,20,0]);
  let rotationWrites = 0;
  const setRotation = marker.rotation.set;
  marker.rotation.set = function(...args) { rotationWrites++; return setRotation.apply(this,args); };
  for (let i=0;i<20;i++) SensorEditor.renderMarker();
  assert.equal(rotationWrites,0,'unchanged frames do not recompute sensor orientation');
  firstFrame.position.x = 50;
  assert.deepEqual(marker.getWorldPosition(new THREE.Vector3()).toArray(),[60,20,0]);

  const rebuiltFrame = new THREE.Group();
  treeData.children = [{link_group:{...child,_pivot:rebuiltFrame}}];
  SensorEditor.invalidateViewer();
  sensor.xyz_m[0] = .025;
  sensor.rpy_rad[2] = .6;
  sensor.type = 'imu';
  sensor.name = 'imu_updated';
  SensorEditor.renderMarker();
  assert.equal(marker.parent,rebuiltFrame);
  assert.deepEqual(marker.position.toArray(),[25,20,0]);
  assert.equal(marker.rotation.z,.6);
  assert.equal(marker.userData.sensorOrigin.material.color.getHex(),SensorEditor.markerColor('imu'));
  assert.equal(marker.userData.sensorIconName,'imu_updated');
  treeData._sensors = [];
  SensorEditor.renderMarker();
  assert.equal(SensorEditor.markers.size,0);
  assert.equal(marker.parent,null);
});
