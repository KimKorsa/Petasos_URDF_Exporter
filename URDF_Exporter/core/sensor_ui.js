/* Sensor origin belongs to a link, never to a mechanical joint. */
const SensorEditor = {
    selectedId: null, pickMode: false, marker: null,
    types: [['depth_camera', 'Depth Camera'], ['rgb_camera', 'RGB Camera'],
        ['lidar', 'LiDAR'], ['imu', 'IMU'], ['generic', 'Generic']],
    toDisplay(sensor) {
        return {xyz_mm: sensor.xyz_m.map(value => value * 1000),
            rpy_deg: sensor.rpy_rad.map(value => value * 180 / Math.PI)};
    },
    withDisplayPose(sensor, xyzMm, rpyDeg) {
        const result = {...sensor, xyz_m: xyzMm.map(value => value / 1000),
            rpy_rad: rpyDeg.map(value => value * Math.PI / 180)};
        if (![...result.xyz_m, ...result.rpy_rad].every(Number.isFinite)) throw new Error('좌표는 유한한 숫자여야 합니다.');
        return result;
    },
    markerVisible(selectedId, sensorId, type) { return type === 'sensor' && !!sensorId && selectedId === sensorId; },
    localPointFromWorld(point, inverse) {
        return [0, 1, 2].map(row => inverse[row * 4] * point[0] + inverse[row * 4 + 1] * point[1]
            + inverse[row * 4 + 2] * point[2] + inverse[row * 4 + 3]);
    },
    all() { return treeData._sensors || []; },
    current() { return this.all().find(sensor => sensor.id === this.selectedId) || null; },
    owner(sensor) {
        const visit = node => {
            if (node._link_id === sensor.parent_link_id) return node;
            for (const child of node.children || []) {
                const found = visit(child.link_group);
                if (found) return found;
            }
            return null;
        };
        return visit(treeData);
    },
    linkSection(node) {
        const sensors = this.all().filter(sensor => sensor.parent_link_id === node._link_id);
        return `<details class="sensor-link-section" ${sensors.length ? 'open' : ''}>
            <summary>센서 · ${sensors.length}개</summary>
            <div class="sensor-link-list">${sensors.map(sensor => `<button type="button"
                onclick="SensorEditor.select('${sensor.id}')">${escapeHtmlText(sensor.name)} · ${escapeHtmlText(sensor.type)}</button>`).join('')}</div>
            <button type="button" onclick="SensorEditor.add('${node._link_id}')">＋ 센서 추가</button>
            </details>`;
    },
    add(linkId) {
        const used = new Set(this.all().map(sensor => sensor.name));
        let index = 1;
        while (used.has(`sensor_${index}`)) index++;
        saveState();
        const sensor = {id: crypto.randomUUID(), name: `sensor_${index}`, type: 'generic',
            parent_link_id: linkId, xyz_m: [0, 0, 0], rpy_rad: [0, 0, 0], settings: {}};
        treeData._sensors = [...this.all(), sensor];
        this.select(sensor.id);
        scheduleWorkspaceAutosave();
    },
    select(id) {
        this.selectedId = id; this.pickMode = false;
        const sensor = this.current();
        if (!sensor) return this.clearSelection();
        selectedElement = {type: 'sensor', sensorId: id};
        updatePanel();
        this.renderMarker();
    },
    clearSelection() {
        this.selectedId = null; this.pickMode = false;
        if (this.marker) this.marker.visible = false;
        if (selectedElement?.type === 'sensor') selectedElement = null;
        updatePanel();
    },
    change(key, value) {
        const sensor = this.current();
        if (!sensor) return;
        if (key === 'name' && (!/^[A-Za-z][A-Za-z0-9_]*$/.test(value)
            || this.all().some(other => other.id !== sensor.id && other.name === value))) {
            alert('센서 이름은 고유한 영문 ROS 이름이어야 합니다.'); updatePanel(); return;
        }
        saveState(); sensor[key] = value;
        updatePanel(); this.renderMarker(); scheduleWorkspaceAutosave();
    },
    changePose(kind, index, text) {
        const sensor = this.current(), value = Number(text);
        if (!sensor || !Number.isFinite(value)) { alert('유한한 숫자를 입력하세요.'); updatePanel(); return; }
        saveState();
        sensor[kind][index] = kind === 'xyz_m' ? value / 1000 : value * Math.PI / 180;
        this.renderMarker(); scheduleWorkspaceAutosave();
    },
    remove() {
        if (!this.current()) return;
        saveState(); treeData._sensors = this.all().filter(sensor => sensor.id !== this.selectedId);
        this.clearSelection(); render({skipPreview: true});
    },
    properties(body) {
        const sensor = this.current();
        if (!sensor) return this.clearSelection();
        const owner = this.owner(sensor), display = this.toDisplay(sensor);
        const numbers = (kind, values, axes) => axes.map((axis, index) => `<label>${axis}<input type="number"
            step="any" value="${Number(values[index].toFixed(4))}" onchange="SensorEditor.changePose('${kind}',${index},this.value)"></label>`).join('');
        body.innerHTML = `<div class="sensor-properties"><h3>Sensor Frame</h3>
            <small>부착 링크: ${escapeHtmlText(owner?.name || '누락')}</small>
            <label>이름<input value="${escapeHtmlText(sensor.name)}" onchange="SensorEditor.change('name',this.value)"></label>
            <label>종류<select onchange="SensorEditor.change('type',this.value)">${this.types.map(([key, label]) =>
                `<option value="${key}" ${sensor.type === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
            <strong>센서 위치 · XYZ (mm)</strong><div class="sensor-pose-row">${numbers('xyz_m', display.xyz_mm, ['X','Y','Z'])}</div>
            <strong>센서 방향 · RPY (°)</strong><div class="sensor-pose-row">${numbers('rpy_rad', display.rpy_deg, ['R','P','Y'])}</div>
            <button type="button" onclick="SensorEditor.pickMode=true">◎ 3D에서 센서 위치 찍기</button>
            <button type="button" onclick="SensorEditor.remove()">센서 삭제</button>
            <small>좌표 프레임만 익스포트됩니다. 영상·스캔 데이터는 생성하지 않습니다.</small></div>`;
    },
    pickWorldPoint(pointMm) {
        const sensor = this.current(), owner = sensor && this.owner(sensor);
        if (!sensor || !owner?._pivot) return false;
        owner._pivot.updateWorldMatrix(true, false);
        const point = new THREE.Vector3(...pointMm);
        const local = owner._pivot.worldToLocal(point);
        saveState(); sensor.xyz_m = local.toArray().map(value => value / (Number(treeData._preview_units_per_meter) || 1000));
        this.pickMode = false; updatePanel(); this.renderMarker(); scheduleWorkspaceAutosave();
        return true;
    },
    pick(event) {
        const hit = getViewerIntersections(event)[0];
        if (!hit) return;
        this.pickWorldPoint(hit.point.toArray());
    },
    renderMarker() {
        if (typeof THREE === 'undefined') return;
        const sensor = this.current();
        if (!this.markerVisible(this.selectedId, sensor?.id, selectedElement?.type)) {
            if (this.marker) this.marker.visible = false;
            return;
        }
        const owner = this.owner(sensor);
        if (!owner?._pivot) return;
        if (!this.marker) {
            this.marker = new THREE.Group();
            this.marker.add(new THREE.AxesHelper(45));
            this.marker.add(new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0),
                new THREE.Vector3(), 70, 0xffff66, 18, 10));
        }
        if (this.marker.parent !== owner._pivot) owner._pivot.add(this.marker);
        const scale = Number(treeData._preview_units_per_meter) || 1000;
        this.marker.position.set(...sensor.xyz_m.map(value => value * scale));
        this.marker.rotation.set(...sensor.rpy_rad, 'ZYX');
        this.marker.visible = true;
    },
};
if (typeof module !== 'undefined') module.exports = SensorEditor;
