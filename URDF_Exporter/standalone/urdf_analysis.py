"""Strict, read-only URDF expansion and zero-pose kinematics (SI units)."""
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
import trimesh

MOVABLE = {'revolute', 'continuous', 'prismatic'}


def load_robot(path: Path) -> ET.Element:
    path = Path(path)
    if path.suffix == '.xacro':
        import xacro
        return ET.fromstring(xacro.process_file(str(path)).toxml())
    return ET.parse(path).getroot()


def vector(text, default='0 0 0'):
    result = np.asarray([float(v) for v in (text or default).split()])
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError('유한한 XYZ/RPY 값 3개가 필요합니다.')
    return result


def origin(element):
    item = element.find('origin')
    matrix = trimesh.transformations.euler_matrix(*vector(item.get('rpy') if item is not None else None))
    matrix[:3, 3] = vector(item.get('xyz') if item is not None else None)
    return matrix


def joint_axis(joint):
    item = joint.find('axis')
    axis = vector(item.get('xyz') if item is not None else None, '1 0 0')
    length = np.linalg.norm(axis)
    if length < 1e-12:
        raise ValueError(f"{joint.get('name')}: 조인트 축이 0입니다.")
    return axis / length


def zero_positions(robot):
    joints = {j.get('name'): j for j in robot.findall('joint') if j.get('type') in MOVABLE}
    result, visiting = {}, set()

    def resolve(name):
        if name in visiting:
            raise ValueError(f'{name}: mimic 순환 참조입니다.')
        if name in result:
            return result[name]
        if name not in joints:
            raise ValueError(f'{name}: mimic 구동 조인트가 없습니다.')
        visiting.add(name)
        joint = joints[name]
        mimic = joint.find('mimic')
        value = 0.0 if mimic is None else (
            resolve(mimic.get('joint')) * float(mimic.get('multiplier', '1')) + float(mimic.get('offset', '0')))
        if not np.isfinite(value):
            raise ValueError(f'{name}: 영점 값이 유한하지 않습니다.')
        if joint.get('type') != 'continuous':
            limit = joint.find('limit')
            if limit is None or not float(limit.get('lower', 'nan')) - 1e-10 <= value <= float(limit.get('upper', 'nan')) + 1e-10:
                raise ValueError(f'{name}: 영점 {value}가 조인트 제한 밖입니다. 제한 또는 영점을 수정하세요.')
        result[name] = value
        visiting.remove(name)
        return value

    for name in joints:
        resolve(name)
    return result


def world_transforms(robot, positions):
    links = {link.get('name') for link in robot.findall('link')}
    pending = list(robot.findall('joint'))
    children = [j.find('child').get('link') for j in pending]
    if len(children) != len(set(children)):
        raise ValueError('중복 부모 연결입니다.')
    roots = links - set(children)
    if len(roots) != 1:
        raise ValueError('로봇 루트가 하나여야 합니다.')
    poses = {next(iter(roots)): np.eye(4)}
    while pending:
        later = []
        for joint in pending:
            parent, child = joint.find('parent').get('link'), joint.find('child').get('link')
            if parent not in poses:
                later.append(joint)
                continue
            if child not in links:
                raise ValueError(f'{child}: 없는 링크입니다.')
            transform = origin(joint)
            kind = joint.get('type')
            if kind in MOVABLE:
                axis = joint_axis(joint)
                value = positions[joint.get('name')]
                motion = np.eye(4)
                if kind == 'prismatic':
                    motion[:3, 3] = axis * value
                else:
                    motion = trimesh.transformations.rotation_matrix(value, axis)
                transform = transform @ motion
            elif kind != 'fixed':
                raise ValueError(f"{joint.get('name')}: {kind} 순기구학 검사는 지원하지 않습니다.")
            poses[child] = poses[parent] @ transform
        if len(later) == len(pending):
            raise ValueError('로봇 연결이 순환 또는 단절되었습니다.')
        pending = later
    return poses
