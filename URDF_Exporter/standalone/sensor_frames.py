"""Link-owned sensor frames; metadata only, not simulator plugins."""
import copy
import math
import re
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np

from .robot_modules import walk_tree
from .module_geometry import rigid, _math


SENSOR_TYPES = {'depth_camera', 'rgb_camera', 'lidar', 'imu', 'generic'}
ROS_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')


def sensor_frame_name(name: str) -> str:
    return name if name.endswith('_frame') else name + '_frame'


def validate_sensors(tree: dict) -> list[dict]:
    errors = []
    sensors = tree.get('_sensors', [])
    if not isinstance(sensors, list):
        return [{'message': '센서 목록 형식이 잘못되었습니다.'}]
    try:
        entries = list(walk_tree(tree))
    except (KeyError, TypeError, ValueError) as exc:
        return [{'message': '로봇 링크 구조를 확인하세요.'}]
    active = {n.get('_link_id') for n, _, _ in entries if not n.get('disabled')}
    existing = {n.get('name') for n, _, _ in entries} | {
        j.get('joint_name') for _, j, _ in entries if j is not None} | {'world', 'base_footprint'}
    ids, names, frames = set(), set(), set()
    for index, sensor in enumerate(sensors):
        if not isinstance(sensor, dict):
            errors.append({'message': f'{index + 1}번 센서 형식이 잘못되었습니다.'})
            continue
        name = sensor.get('name')
        sid = sensor.get('id')
        frame = sensor_frame_name(name) if isinstance(name, str) else None
        if not isinstance(sid, str) or not sid or sid in ids:
            errors.append({'message': '센서 ID가 없거나 중복되었습니다.'})
        ids.add(sid)
        if not isinstance(name, str) or not ROS_NAME.fullmatch(name) or name in names:
            errors.append({'message': '센서 이름은 고유한 ROS 이름이어야 합니다.'})
        names.add(name)
        if frame in frames or frame in existing or (frame and frame + '_joint' in existing):
            errors.append({'message': '센서 프레임 이름이 링크 또는 조인트와 충돌합니다.'})
        frames.add(frame)
        if sensor.get('type') not in SENSOR_TYPES:
            errors.append({'message': '지원하지 않는 센서 종류입니다.'})
        if sensor.get('parent_link_id') not in active:
            errors.append({'message': f'{name or "센서"}의 부착 링크가 없거나 비활성입니다.'})
        for key in ('xyz_m', 'rpy_rad'):
            value = sensor.get(key)
            if not isinstance(value, list) or len(value) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in value
            ):
                errors.append({'message': f'{name or "센서"}의 {key} 좌표가 잘못되었습니다.'})
    return errors


def _valid_copy(tree):
    errors = validate_sensors(tree)
    if errors:
        raise ValueError(' / '.join(error['message'] for error in errors))
    return tree


def create_sensor(tree: dict, parent_link_id: str, sensor_type: str, name: str) -> dict:
    updated = copy.deepcopy(tree)
    updated.setdefault('_sensors', []).append({
        'id': uuid.uuid4().hex, 'name': name, 'type': sensor_type,
        'parent_link_id': parent_link_id, 'xyz_m': [0, 0, 0],
        'rpy_rad': [0, 0, 0], 'settings': {},
    })
    return _valid_copy(updated)


def update_sensor(tree: dict, sensor_id: str, changes: dict) -> dict:
    updated = copy.deepcopy(tree)
    sensor = next((s for s in updated.get('_sensors', []) if s.get('id') == sensor_id), None)
    if sensor is None:
        raise ValueError('센서를 찾을 수 없습니다.')
    for key in ('name', 'type', 'parent_link_id', 'xyz_m', 'rpy_rad'):
        if key in changes:
            sensor[key] = copy.deepcopy(changes[key])
    return _valid_copy(updated)


def delete_sensor(tree: dict, sensor_id: str) -> dict:
    updated = copy.deepcopy(tree)
    old = updated.get('_sensors', [])
    updated['_sensors'] = [s for s in old if s.get('id') != sensor_id]
    if len(updated['_sensors']) == len(old):
        raise ValueError('센서를 찾을 수 없습니다.')
    return _valid_copy(updated)


def sensor_world_matrix(sensor: dict, link_world_matrix: list[float]) -> list[float]:
    parent = rigid(link_world_matrix)
    local = rigid(_math._matrix_from_xyz_rpy(sensor['xyz_m'], sensor['rpy_rad']))
    return (parent @ local).flatten().tolist()


def set_sensor_world_point(sensor: dict, link_world_matrix: list[float], point_world_m: list[float]) -> dict:
    parent = rigid(link_world_matrix)
    point = np.array([*point_world_m, 1.0], dtype=float)
    if point.shape != (4,) or not np.all(np.isfinite(point)):
        raise ValueError('센서 위치가 올바르지 않습니다.')
    local = np.linalg.inv(parent) @ point
    result = copy.deepcopy(sensor)
    result['xyz_m'] = [float(v) for v in local[:3]]
    return result


def resolved_sensor_frames(tree: dict, export_name_map: dict) -> list[dict]:
    """Resolve stable owner IDs only after link names have been standardized."""
    _valid_copy(tree)
    link_names = export_name_map.get('links', {})
    resolved = []
    for sensor in tree.get('_sensors', []):
        parent = link_names.get(sensor['parent_link_id'])
        if not parent:
            raise ValueError(f"{sensor['name']} 센서의 익스포트 링크를 찾을 수 없습니다.")
        frame = sensor_frame_name(sensor['name'])
        resolved.append({
            'id': sensor['id'], 'name': sensor['name'], 'frame': frame,
            'joint_name': frame + '_joint', 'parent': parent,
            'xyz_m': list(sensor['xyz_m']), 'rpy_rad': list(sensor['rpy_rad']),
        })
    return resolved


def write_sensor_frames(xacro_path: Path, resolved: list[dict]) -> None:
    """Append massless, visual-free sensor frames atomically after validation."""
    if not resolved:
        return
    ET.register_namespace('xacro', 'http://www.ros.org/wiki/xacro')
    document = ET.parse(xacro_path)
    robot = document.getroot()
    existing_links = {element.get('name') for element in robot.iter('link')}
    existing_joints = {element.get('name') for element in robot.iter('joint')}
    frame_names = [sensor['frame'] for sensor in resolved]
    joint_names = [sensor['joint_name'] for sensor in resolved]
    if len(set(frame_names)) != len(frame_names) or len(set(joint_names)) != len(joint_names):
        raise ValueError('센서 프레임 이름이 중복되었습니다.')
    for sensor in resolved:
        if sensor['parent'] not in existing_links:
            raise ValueError(f"{sensor['name']} 센서의 부모 링크가 Xacro에 없습니다.")
        if sensor['frame'] in existing_links | existing_joints or sensor['joint_name'] in existing_links | existing_joints:
            raise ValueError(f"{sensor['name']} 센서 프레임 이름이 기존 이름과 충돌합니다.")
    for sensor in resolved:
        ET.SubElement(robot, 'link', {'name': sensor['frame']})
        joint = ET.SubElement(robot, 'joint', {'name': sensor['joint_name'], 'type': 'fixed'})
        ET.SubElement(joint, 'origin', {
            'xyz': ' '.join(format(value, '.12g') for value in sensor['xyz_m']),
            'rpy': ' '.join(format(value, '.12g') for value in sensor['rpy_rad']),
        })
        ET.SubElement(joint, 'parent', {'link': sensor['parent']})
        ET.SubElement(joint, 'child', {'link': sensor['frame']})
    document.write(xacro_path, encoding='utf-8', xml_declaration=True)
