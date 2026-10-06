/* Sensor origin belongs to a link, never to a mechanical joint. */
const SensorEditor = {
    selectedId: null, pickMode: false, marker: null, markers: new Map(),
    previewLocalPosition: null, previewRpyRad: null,
    ownerTree: null, ownerNodes: null, markerEpoch: 0,
    markerColors: {depth_camera: 0x55d9ff, rgb_camera: 0x55d9ff,
        lidar: 0x70ed91, imu: 0xffbd68, generic: 0xc29bff},
    markerOriginRadius: 8,
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
    invalidateViewer() { this.ownerTree = null; this.ownerNodes = null; },
    owner(sensor) {
        if (this.ownerTree !== treeData || !this.ownerNodes) {
            const nodes = new Map();
            const visit = node => {
                // Match the original depth-first lookup if an imported tree
                // temporarily contains duplicate IDs.
                if (!nodes.has(node._link_id)) nodes.set(node._link_id, node);
                for (const child of node.children || []) visit(child.link_group);
            };
            visit(treeData);
            this.ownerNodes = nodes;
            this.ownerTree = treeData;
        }
        return this.ownerNodes.get(sensor.parent_link_id) || null;
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
        this.previewLocalPosition = null; this.previewRpyRad = null;
        const sensor = this.current();
        if (!sensor) return this.clearSelection();
        selectedElement = {type: 'sensor', sensorId: id};
        updatePanel();
        this.renderMarker();
    },
    clearSelection() {
        this.selectedId = null; this.pickMode = false;
        this.previewLocalPosition = null; this.previewRpyRad = null;
        if (selectedElement?.type === 'sensor') selectedElement = null;
        updatePanel();
        this.renderMarker();
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
    startPick() {
        if (!this.current()) return;
        this.pickMode = true;
        this.previewLocalPosition = null;
        this.previewRpyRad = null;
        updatePanel();
        this.renderMarker();
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
        const numbers = (kind, values, axes) => axes.map((axis, index) => `<label class="sensor-axis-field"><span>${axis}</span><input type="number"
            step="any" value="${Number(values[index].toFixed(4))}" onchange="SensorEditor.changePose('${kind}',${index},this.value)"></label>`).join('');
        body.innerHTML = `<div class="sensor-properties"><h3>Sensor Frame</h3>
            <label>부착 링크<select onchange="SensorEditor.reparent(this.value)">${this.linkOptions(treeData).map(node =>
                `<option value="${node._link_id}" ${sensor.parent_link_id === node._link_id ? 'selected' : ''}>${escapeHtmlText(node.name)}</option>`).join('')}</select></label>
            <label>이름<input value="${escapeHtmlText(sensor.name)}" onchange="SensorEditor.change('name',this.value)"></label>
            <label>종류<select onchange="SensorEditor.change('type',this.value)">${this.types.map(([key, label]) =>
                `<option value="${key}" ${sensor.type === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
            <section class="sensor-pose-card sensor-position-card"><div class="sensor-pose-heading"><strong>센서 위치</strong><span>XYZ · mm</span></div>
                <div class="sensor-pose-row">${numbers('xyz_m', display.xyz_mm, ['X','Y','Z'])}</div></section>
            <section class="sensor-pose-card sensor-orientation-card"><div class="sensor-pose-heading"><strong>센서 방향</strong><span>RPY · °</span></div>
                <div class="sensor-pose-row">${numbers('rpy_rad', display.rpy_deg, ['R','P','Y'])}</div></section>
            <button type="button" class="sensor-pick-button ${this.pickMode ? 'is-active' : ''}" onclick="SensorEditor.startPick()">◎ 3D에서 센서 위치·방향 ${this.pickMode ? '선택 중' : '찍기'}</button>
            ${this.pickMode ? '<small class="sensor-pick-hint">면을 클릭하면 그 점에 센서 아이콘을 놓고 면과 평행하게 정렬합니다. 노란 화살표(+X)는 면 바깥쪽을 향합니다. ESC를 누르면 취소합니다.</small>' : ''}
            <button type="button" onclick="SensorEditor.remove()">센서 삭제</button>
            <small>좌표 프레임만 익스포트됩니다. 영상·스캔 데이터는 생성하지 않습니다.</small></div>`;
    },
    orientationFromWorldNormal(normalWorld, frame) {
        const localDirection = new THREE.Vector3(...normalWorld)
            .applyMatrix3(new THREE.Matrix3().setFromMatrix4(frame.matrixWorld).invert())
            .normalize();
        const rotation = new THREE.Quaternion().setFromUnitVectors(
            new THREE.Vector3(1, 0, 0), localDirection);
        const rpy = new THREE.Euler().setFromQuaternion(rotation, 'ZYX');
        return [rpy.x, rpy.y, rpy.z];
    },
    worldNormalFromHit(hit) {
        if (!hit.face?.normal || !hit.object) return null;
        const normal = hit.face.normal.clone()
            .applyMatrix3(new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld))
            .normalize();
        // Double-sided CAD faces can have either winding; face the visible side toward the picker.
        if (normal.dot(viewerRaycaster.ray.direction) > 0) normal.negate();
        return normal.toArray();
    },
    ownerFromHit(hit) {
        const component = Object.entries(meshDict).find(([, mesh]) => mesh === hit.object)?.[0];
        return component ? this.linkOptions(treeData).find(node => node.components.includes(component)) || null : null;
    },
    pickWorldPoint(pointMm, normalWorld = null, hitOwner = null) {
        const sensor = this.current(), owner = sensor && (hitOwner || this.owner(sensor));
        if (!sensor || selectedElement?.type !== 'sensor' || selectedElement.sensorId !== sensor.id) {
            this.pickMode = false; return false;
        }
        if (!normalWorld) return false;
        const frame = this.frameFor(owner, treeData, meshDict);
        if (!frame) return false;
        frame.updateWorldMatrix(true, false);
        const local = frame.worldToLocal(new THREE.Vector3(...pointMm));
        const scale = Number(treeData._preview_units_per_meter) || 1000;
        const rpyRad = this.orientationFromWorldNormal(normalWorld, frame);
        saveState();
        if (hitOwner) sensor.parent_link_id = hitOwner._link_id;
        sensor.xyz_m = local.toArray().map(value => value / scale);
        sensor.rpy_rad = rpyRad;
        this.previewLocalPosition = null;
        this.previewRpyRad = null;
        this.pickMode = false; updatePanel(); this.renderMarker(); scheduleWorkspaceAutosave();
        return true;
    },
    previewWorldPoint(pointMm, normalWorld = null) {
        const sensor = this.current(), owner = sensor && this.owner(sensor);
        if (!this.pickMode || !sensor || selectedElement?.type !== 'sensor'
            || selectedElement.sensorId !== sensor.id) return false;
        if (!normalWorld) {
            this.previewLocalPosition = null;
            this.previewRpyRad = null;
            this.renderMarker();
            return false;
        }
        const frame = this.frameFor(owner, treeData, meshDict);
        if (!frame) return false;
        frame.updateWorldMatrix(true, false);
        this.previewLocalPosition = frame.worldToLocal(new THREE.Vector3(...pointMm)).toArray();
        this.previewRpyRad = this.orientationFromWorldNormal(normalWorld, frame);
        this.renderMarker();
        return true;
    },
    previewPick(event) {
        if (!this.pickMode) return false;
        const hit = getViewerIntersections(event)[0];
        if (!hit) {
            this.previewLocalPosition = null;
            this.previewRpyRad = null;
            this.renderMarker();
            return false;
        }
        return this.previewWorldPoint(hit.point.toArray(), this.worldNormalFromHit(hit));
    },
    pick(event) {
        if (selectedElement?.type !== 'sensor' || selectedElement.sensorId !== this.selectedId) {
            this.pickMode = false; return false;
        }
        const hit = getViewerIntersections(event)[0];
        if (!hit) return;
        return this.pickWorldPoint(hit.point.toArray(), this.worldNormalFromHit(hit), this.ownerFromHit(hit));
    },
    markerColor(type) {
        return this.markerColors[type] || 0xc29bff;
    },
    makeMarkerIcon(sensor) {
        if (typeof document === 'undefined') return null;
        const canvas = document.createElement('canvas');
        canvas.width = 96; canvas.height = 96;
        const context = canvas.getContext('2d');
        if (!context) return null;
        const circleRadius = 42;
        const outlineWidth = 5;
        const accent = `#${this.markerColor(sensor.type).toString(16).padStart(6, '0')}`;
        context.beginPath();
        context.arc(48, 48, circleRadius, 0, Math.PI * 2);
        context.fillStyle = 'rgba(12, 27, 37, 0.8)';
        context.fill();
        context.lineWidth = outlineWidth;
        context.strokeStyle = accent;
        context.stroke();
        context.strokeStyle = '#e9fbff';
        context.fillStyle = '#e9fbff';
        context.lineWidth = 5;
        context.lineCap = 'round';
        context.lineJoin = 'round';
        if (sensor.type === 'rgb_camera' || sensor.type === 'depth_camera'
            || /camera|imager/i.test(sensor.name || '')) {
            context.strokeRect(24, 35, 48, 34);
            context.beginPath(); context.arc(48, 52, 10, 0, Math.PI * 2); context.stroke();
            context.beginPath();
            context.moveTo(32, 35); context.lineTo(38, 27);
            context.lineTo(58, 27); context.lineTo(64, 35); context.stroke();
        } else if (sensor.type === 'lidar') {
            context.beginPath(); context.arc(48, 48, 7, 0, Math.PI * 2); context.fill();
            context.beginPath(); context.arc(48, 48, 18, -Math.PI * 0.8, Math.PI * 0.8); context.stroke();
            context.beginPath(); context.arc(48, 48, 29, -Math.PI * 0.8, Math.PI * 0.8); context.stroke();
        } else if (sensor.type === 'imu') {
            context.beginPath();
            context.moveTo(48, 68); context.lineTo(48, 28); context.lineTo(42, 35);
            context.moveTo(48, 28); context.lineTo(54, 35);
            context.moveTo(28, 58); context.lineTo(68, 58); context.lineTo(61, 52);
            context.moveTo(68, 58); context.lineTo(61, 64); context.stroke();
        } else {
            context.beginPath(); context.arc(48, 48, 7, 0, Math.PI * 2); context.fill();
            for (const radius of [19, 30]) {
                context.beginPath(); context.arc(48, 48, radius, -Math.PI * 0.35, Math.PI * 0.35); context.stroke();
                context.beginPath(); context.arc(48, 48, radius, Math.PI * 0.65, Math.PI * 1.35); context.stroke();
            }
        }
        const texture = new THREE.CanvasTexture(canvas);
        const iconSize = this.markerOriginRadius * canvas.width
            / (circleRadius + outlineWidth / 2);
        const icon = new THREE.Mesh(
            new THREE.PlaneGeometry(iconSize, iconSize),
            new THREE.MeshBasicMaterial({
                map: texture, transparent: true, opacity: 0.88,
                depthTest: false, depthWrite: false,
                side: THREE.DoubleSide
            })
        );
        icon.rotation.y = Math.PI / 2;
        icon.position.x = 2;
        icon.renderOrder = 1002;
        return icon;
    },
    createMarker(sensor) {
        const marker = new THREE.Group();
        const axes = new THREE.AxesHelper(65);
        axes.renderOrder = 1000;
        axes.traverse(child => {
            if (child.material) child.material.depthTest = false;
        });
        marker.add(axes);
        const origin = new THREE.Mesh(new THREE.SphereGeometry(this.markerOriginRadius, 16, 12),
            new THREE.MeshBasicMaterial({color: this.markerColor(sensor.type),
                transparent: true, opacity: 0.95, depthTest: false, depthWrite: false}));
        origin.renderOrder = 1001;
        marker.add(origin);
        const arrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0),
            new THREE.Vector3(), 70, 0xffff66, 18, 10);
        marker.add(arrow);
        const icon = this.makeMarkerIcon(sensor);
        if (icon) marker.add(icon);
        marker.userData.sensorAxes = axes;
        marker.userData.sensorOrigin = origin;
        marker.userData.sensorArrow = arrow;
        marker.userData.sensorIcon = icon;
        marker.userData.sensorIconName = sensor.name;
        marker.userData.sensorIconType = sensor.type;
        marker.userData.sensorColorType = sensor.type;
        return marker;
    },
    disposeMarker(marker) {
        if (marker.parent) marker.parent.remove(marker);
        marker.traverse(child => {
            child.geometry?.dispose();
            const materials = Array.isArray(child.material) ? child.material : [child.material];
            materials.forEach(material => {
                material?.map?.dispose();
                material?.dispose();
            });
        });
    },
    orientMarkerIcon(marker) {
        const icon = marker.userData.sensorIcon;
        if (!icon) return;
        const markerWorld = marker.getWorldQuaternion(new THREE.Quaternion());
        const normal = new THREE.Vector3(1, 0, 0).applyQuaternion(markerWorld);
        const up = new THREE.Vector3(0, 1, 0);
        up.addScaledVector(normal, -up.dot(normal));
        if (up.lengthSq() < 1e-6) {
            up.set(0, 0, -1).addScaledVector(normal, normal.z);
        }
        up.normalize();
        const right = up.clone().cross(normal).normalize();
        const worldIcon = new THREE.Quaternion().setFromRotationMatrix(
            new THREE.Matrix4().makeBasis(right, up, normal));
        const localIcon = markerWorld.invert().multiply(worldIcon);
        if (icon.quaternion.angleTo(localIcon) > 1e-7) icon.quaternion.copy(localIcon);
    },
    renderMarker() {
        if (typeof THREE === 'undefined' || typeof treeData === 'undefined' || !treeData) return;
        const sensors = this.all();
        const epoch = ++this.markerEpoch;
        this.marker = null;
        const scale = Number(treeData._preview_units_per_meter) || 1000;
        sensors.forEach(sensor => {
            let marker = this.markers.get(sensor.id);
            if (!marker) {
                marker = this.createMarker(sensor);
                this.markers.set(sensor.id, marker);
            }
            marker.userData.sensorEpoch = epoch;
            const owner = this.owner(sensor);
            const frame = this.frameFor(owner, treeData, meshDict);
            if (!frame) { marker.visible = false; return; }
            if (marker.parent !== frame) frame.add(marker);
            const selected = this.markerVisible(this.selectedId, sensor.id, selectedElement?.type);
            if (marker.userData.sensorIconName !== sensor.name
                || marker.userData.sensorIconType !== sensor.type) {
                const oldIcon = marker.userData.sensorIcon;
                if (oldIcon) {
                    marker.remove(oldIcon);
                    this.disposeMarker(oldIcon);
                }
                const icon = this.makeMarkerIcon(sensor);
                if (icon) marker.add(icon);
                marker.userData.sensorIcon = icon;
                marker.userData.sensorIconName = sensor.name;
                marker.userData.sensorIconType = sensor.type;
            }
            if (marker.userData.sensorSelected !== selected) {
                marker.userData.sensorAxes.visible = selected;
                marker.userData.sensorArrow.visible = selected;
                marker.userData.sensorOrigin.scale.setScalar(selected ? 1.3 : 1);
                marker.userData.sensorSelected = selected;
            }
            if (marker.userData.sensorIcon
                && marker.userData.sensorIcon.scale.x !== marker.userData.sensorOrigin.scale.x) {
                marker.userData.sensorIcon.scale.copy(marker.userData.sensorOrigin.scale);
            }
            if (marker.userData.sensorColorType !== sensor.type) {
                marker.userData.sensorOrigin.material.color.setHex(this.markerColor(sensor.type));
                marker.userData.sensorColorType = sensor.type;
            }
            const componentSelection = typeof viewerSelectedComponents === 'undefined'
                ? null : viewerSelectedComponents;
            const dimmed = selectedElement?.type === 'sensor'
                ? !selected
                : componentSelection?.size > 0
                    ? !(owner.components || []).some(component => componentSelection.has(component))
                    : !!selectedElement?.node && selectedElement.node !== owner;
            marker.userData.sensorOrigin.material.opacity = dimmed ? 0.12 : 0.95;
            if (marker.userData.sensorIcon) {
                marker.userData.sensorIcon.material.opacity = dimmed ? 0.12 : 0.88;
            }
            const previewPosition = selected && this.pickMode && this.previewLocalPosition;
            const xyz = previewPosition || sensor.xyz_m;
            const unitScale = previewPosition ? 1 : scale;
            const x = xyz[0] * unitScale, y = xyz[1] * unitScale, z = xyz[2] * unitScale;
            if (marker.position.x !== x || marker.position.y !== y || marker.position.z !== z) {
                marker.position.set(x, y, z);
            }
            const rpy = selected && this.pickMode && this.previewRpyRad
                ? this.previewRpyRad : sensor.rpy_rad;
            if (marker.rotation.x !== rpy[0] || marker.rotation.y !== rpy[1]
                || marker.rotation.z !== rpy[2] || marker.rotation.order !== 'ZYX') {
                marker.rotation.set(rpy[0], rpy[1], rpy[2], 'ZYX');
            }
            this.orientMarkerIcon(marker);
            marker.visible = true;
            if (selected) this.marker = marker;
        });
        for (const [id, marker] of this.markers) {
            if (marker.userData.sensorEpoch === epoch) continue;
            this.disposeMarker(marker);
            this.markers.delete(id);
        }
    },
};
if (typeof module !== 'undefined') module.exports = SensorEditor;
