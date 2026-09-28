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
