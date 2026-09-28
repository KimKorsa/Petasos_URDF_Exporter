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
    frameName(name) { return name.endsWith('_frame') ? name : `${name}_frame`; },
    nameConflict(name, rootNode, exceptId = null) {
        const frame = this.frameName(name), jointName = `${frame}_joint`;
        const occupied = new Set(['world', 'base_footprint', 'world_joint', 'base_footprint_joint']);
        const visit = node => {
            occupied.add(node.name);
            (node.children || []).forEach(child => {
                occupied.add(child.joint_name);
                visit(child.link_group);
            });
        };
        visit(rootNode);
        const otherSensors = (rootNode._sensors || []).filter(sensor => sensor.id !== exceptId);
        otherSensors.forEach(sensor => {
            const other = this.frameName(sensor.name);
            occupied.add(other); occupied.add(`${other}_joint`);
        });
        return occupied.has(frame) || occupied.has(jointName)
            || otherSensors.some(sensor => sensor.name === name);
    },
    frameFor(owner, rootNode, meshes) {
        // The exported root frame is the first CAD component, not robotRoot.
        if (owner === rootNode) return meshes[owner?.components?.[0]] || null;
        return owner?._pivot || null;
    },
    linkOptions(rootNode) {
        const result = [];
        const visit = node => {
            if (!node || node.disabled || !node.components?.length) return;
            result.push(node);
            (node.children || []).forEach(child => {
                if (!child.disabled) visit(child.link_group);
            });
        };
        visit(rootNode);
        return result;
    },
    reparent(linkId) {
        const sensor = this.current(), oldOwner = sensor && this.owner(sensor);
        const newOwner = this.linkOptions(treeData).find(node => node._link_id === linkId);
        if (!sensor || !newOwner || !oldOwner) { updatePanel(); return; }
        if (oldOwner === newOwner) return;
        const oldFrame = this.frameFor(oldOwner, treeData, meshDict);
        const newFrame = this.frameFor(newOwner, treeData, meshDict);
        if (!oldFrame || !newFrame) {
            alert('3D 링크 프레임을 불러온 뒤 센서를 옮겨주세요.'); updatePanel(); return;
        }
        const scale = Number(treeData._preview_units_per_meter) || 1000;
        oldFrame.updateWorldMatrix(true, false);
        newFrame.updateWorldMatrix(true, false);
        const local = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(...sensor.rpy_rad, 'ZYX'));
        local.setPosition(...sensor.xyz_m.map(value => value * scale));
        const transformed = new THREE.Matrix4().copy(newFrame.matrixWorld).invert()
            .multiply(oldFrame.matrixWorld).multiply(local);
        const position = new THREE.Vector3(), rotation = new THREE.Quaternion(), visualScale = new THREE.Vector3();
        transformed.decompose(position, rotation, visualScale);
        const rpy = new THREE.Euler().setFromQuaternion(rotation, 'ZYX');
        const xyzM = position.toArray().map(value => value / scale);
        const rpyRad = [rpy.x, rpy.y, rpy.z];
        if (![...xyzM, ...rpyRad].every(Number.isFinite)) {
            alert('센서 좌표를 변환할 수 없습니다.'); updatePanel(); return;
        }
        saveState();
        sensor.parent_link_id = linkId;
        sensor.xyz_m = xyzM;
        sensor.rpy_rad = rpyRad;
        updatePanel(); this.renderMarker(); scheduleWorkspaceAutosave();
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
        let index = 1;
        while (this.nameConflict(`sensor_${index}`, treeData)) index++;
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
            || this.nameConflict(value, treeData, sensor.id))) {
            alert('센서 이름 또는 프레임 이름이 기존 링크·조인트·센서와 충돌합니다.'); updatePanel(); return;
        }
        saveState(); sensor[key] = value;
        updatePanel(); this.renderMarker(); scheduleWorkspaceAutosave();
    },
    changePose(kind, index, text) {
        const sensor = this.current(), value = Number(text);
        if (!sensor || !Number.isFinite(value)) { alert('유한한 숫자를 입력하세요.'); updatePanel(); return; }
        const converted = kind === 'xyz_m' ? value / 1000 : value * Math.PI / 180;
        if (!Number.isFinite(converted)) { alert('변환된 좌표가 유한하지 않습니다.'); updatePanel(); return; }
        saveState();
        sensor[kind][index] = converted;
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
        const display = this.toDisplay(sensor);
        const numbers = (kind, values, axes) => axes.map((axis, index) => `<label>${axis}<input type="number"
            step="any" value="${Number(values[index].toFixed(4))}" onchange="SensorEditor.changePose('${kind}',${index},this.value)"></label>`).join('');
        body.innerHTML = `<div class="sensor-properties"><h3>Sensor Frame</h3>
            <label>부착 링크<select onchange="SensorEditor.reparent(this.value)">${this.linkOptions(treeData).map(node =>
                `<option value="${node._link_id}" ${sensor.parent_link_id === node._link_id ? 'selected' : ''}>${escapeHtmlText(node.name)}</option>`).join('')}</select></label>
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
        if (!sensor || selectedElement?.type !== 'sensor' || selectedElement.sensorId !== sensor.id) {
            this.pickMode = false; return false;
        }
        const frame = this.frameFor(owner, treeData, meshDict);
        if (!frame) return false;
        frame.updateWorldMatrix(true, false);
        const point = new THREE.Vector3(...pointMm);
        const local = frame.worldToLocal(point);
        saveState(); sensor.xyz_m = local.toArray().map(value => value / (Number(treeData._preview_units_per_meter) || 1000));
        this.pickMode = false; updatePanel(); this.renderMarker(); scheduleWorkspaceAutosave();
        return true;
    },
    pick(event) {
        if (selectedElement?.type !== 'sensor' || selectedElement.sensorId !== this.selectedId) {
            this.pickMode = false; return false;
        }
        const hit = getViewerIntersections(event)[0];
        if (!hit) return;
        return this.pickWorldPoint(hit.point.toArray());
    },
    renderMarker() {
        if (typeof THREE === 'undefined') return;
        const sensor = this.current();
        if (!this.markerVisible(this.selectedId, sensor?.id, selectedElement?.type)) {
            if (this.marker) this.marker.visible = false;
            return;
        }
        const owner = this.owner(sensor);
        const frame = this.frameFor(owner, treeData, meshDict);
        if (!frame) { if (this.marker) this.marker.visible = false; return; }
        if (!this.marker) {
            this.marker = new THREE.Group();
            this.marker.add(new THREE.AxesHelper(45));
            this.marker.add(new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0),
                new THREE.Vector3(), 70, 0xffff66, 18, 10));
        }
        if (this.marker.parent !== frame) frame.add(this.marker);
        const scale = Number(treeData._preview_units_per_meter) || 1000;
        this.marker.position.set(...sensor.xyz_m.map(value => value * scale));
        this.marker.rotation.set(...sensor.rpy_rad, 'ZYX');
        this.marker.visible = true;
    },
};
if (typeof module !== 'undefined') module.exports = SensorEditor;
