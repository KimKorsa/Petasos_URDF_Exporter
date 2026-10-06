"""Compare independently captured normalized exporter data to serialized URDF."""
import copy
from xml.etree import ElementTree as ET
import numpy as np
import trimesh
from .urdf_analysis import MOVABLE, origin, vector, joint_axis, zero_positions, world_transforms


def normalized_reference(joints, links):
    result = {'joints': copy.deepcopy(joints), 'links': copy.deepcopy(links)}
    for name, info in result['links'].items():
        joint = next((j for j in joints.values() if j['child'] == name), {})
        inverse = joint.get('link_world_inv_matrix')
        if inverse:
            point = np.r_[info['center_of_mass'], 1]
            info['center_of_mass'] = (np.array(inverse).reshape(4, 4) @ point)[:3].tolist()
        info['rpy'] = joint.get('link_vis_rpy', [0, 0, 0])
    return result


def compare_export(expected, robot, atol=1e-8, rtol=1e-6):
    differences = []
    actual_joints = {j.get('name'): j for j in robot.findall('joint')}
    actual_links = {l.get('name'): l for l in robot.findall('link')}

    def check(target, field, want, got):
        try:
            equal = np.shape(want) == np.shape(got) and np.allclose(want, got, atol=atol, rtol=rtol)
        except (TypeError, ValueError):
            equal = want == got
        if not equal:
            def plain(value):
                return value.tolist() if isinstance(value, np.ndarray) else value
            differences.append({'target': target, 'field': field, 'expected': plain(want), 'observed': plain(got),
                                'message': f'{target}: {field} 설정과 익스포트 값이 다릅니다.'})

    reference_robot = ET.Element('robot')
    for link in robot.findall('link'):
        ET.SubElement(reference_robot, 'link', name=link.get('name'))
    # Synthetic mounts/sensor joints are copied; edited robot joints are reconstructed from the normalized reference.
    for name, joint in actual_joints.items():
        if name not in expected['joints']:
            reference_robot.append(copy.deepcopy(joint))
            if joint.get('type') in MOVABLE:
                check(name, 'unexpected_joint', None, joint.get('type'))
    for name, info in expected['joints'].items():
        joint = actual_joints.get(name)
        if joint is None:
            check(name, 'joint_missing', 'present', None)
            continue
        kind = info['type']
        check(name, 'type', kind, joint.get('type'))
        for side in ('parent', 'child'):
            element = joint.find(side)
            check(name, side, info[side], element.get('link') if element is not None else None)
        want_transform = trimesh.transformations.euler_matrix(*info.get('rpy', [0, 0, 0]))
        want_transform[:3, 3] = info.get('xyz', [0, 0, 0])
        check(name, 'xyz', want_transform[:3, 3], origin(joint)[:3, 3])
        check(name, 'rotation', want_transform[:3, :3], origin(joint)[:3, :3])
        reference = ET.SubElement(reference_robot, 'joint', name=name, type=kind)
        ET.SubElement(reference, 'parent', link=info['parent'])
        ET.SubElement(reference, 'child', link=info['child'])
        ET.SubElement(reference, 'origin', xyz=' '.join(map(str, info.get('xyz', [0, 0, 0]))),
                      rpy=' '.join(map(str, info.get('rpy', [0, 0, 0]))))
        if kind in MOVABLE:
            axis = np.asarray(info.get('axis', [1, 0, 0]), dtype=float)
            check(name, 'axis', axis / np.linalg.norm(axis), joint_axis(joint))
            ET.SubElement(reference, 'axis', xyz=' '.join(map(str, axis)))
            limit = joint.find('limit')
            expected_limits = {'effort': info.get('effort_limit', 100), 'velocity': info.get('velocity_limit', 1)}
            if kind != 'continuous':
                expected_limits.update(lower=info['lower_limit'], upper=info['upper_limit'])
            ET.SubElement(reference, 'limit', **{k: str(v) for k, v in expected_limits.items()})
            for key, value in expected_limits.items():
                check(name, key, value, float(limit.get(key, 'nan')) if limit is not None else None)
        mimic = joint.find('mimic')
        check(name, 'mimic_joint', info.get('mimic_joint') or None, mimic.get('joint') if mimic is not None else None)
        if info.get('mimic_joint'):
            attrs = dict(joint=info['mimic_joint'], multiplier=str(info.get('mimic_multiplier', 1)), offset=str(info.get('mimic_offset', 0)))
            ET.SubElement(reference, 'mimic', **attrs)
            for key in ('multiplier', 'offset'):
                check(name, 'mimic_' + key, float(attrs[key]), float(mimic.get(key, '1' if key == 'multiplier' else '0')) if mimic is not None else None)
    for name, info in expected['links'].items():
        link = actual_links.get(name)
        inertial = link.find('inertial') if link is not None else None
        if inertial is None:
            check(name, 'inertial_missing', 'present', None)
            continue
        mass = inertial.find('mass')
        check(name, 'mass', info['mass'], float(mass.get('value', 'nan')) if mass is not None else None)
        check(name, 'center_of_mass', info['center_of_mass'], origin(inertial)[:3, 3])
        rotation = trimesh.transformations.euler_matrix(*info.get('rpy', [0, 0, 0]))[:3, :3]
        check(name, 'inertial_rotation', rotation, origin(inertial)[:3, :3])
        tensor = inertial.find('inertia')
        check(name, 'inertia', info['inertia'], [float(tensor.get(k, 'nan')) for k in ('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz')] if tensor is not None else None)
    positions = {}
    try:
        positions = zero_positions(robot)
        actual_poses = world_transforms(robot, positions)
        reference_poses = world_transforms(reference_robot, zero_positions(reference_robot))
        for name in expected['links']:
            check(name, 'zero_world_transform', reference_poses.get(name), actual_poses.get(name))
    except (ValueError, KeyError, AttributeError) as error:
        differences.append({'target': robot.get('name', 'robot'), 'field': 'zero_pose', 'message': str(error)})
    return {'status': 'error' if differences else 'ok', 'differences': differences,
            'tolerance': {'atol': atol, 'rtol': rtol}, 'zero_positions': positions,
            'runtime': {'status': 'unverified'}}


def check_observed_positions(robot, observed, atol=1e-6):
    positions = zero_positions(robot)
    missing = sorted(set(positions) - observed.keys())
    differences = []
    for name, value in positions.items():
        if name in observed and (not np.isfinite(observed[name]) or abs(observed[name] - value) > atol):
            differences.append({'target': name, 'expected': value, 'observed': observed[name],
                                'message': f'{name}: 초기 영점 또는 mimic 연동 값이 다릅니다.'})
    return {'status': 'error' if differences else ('unverified' if missing else 'ok'),
            'missing': missing, 'differences': differences, 'expected': positions, 'observed': observed}
