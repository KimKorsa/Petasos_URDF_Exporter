"""Portable module frames. Component inertias and CAD snap features stay local."""
from __future__ import annotations
import copy
import numpy as np
from URDF_Exporter.core.Structure import RobotStructure
from .robot_modules import walk_tree, validate_modules

_math = RobotStructure({}, {}, {})


def rigid(values):
    matrix = np.asarray(values, dtype=float).reshape(4, 4)
    if (not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1])
            or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(matrix[:3, :3]), 1, atol=1e-6)):
        raise ValueError('모듈 변환은 유한한 회전·이동 행렬이어야 합니다.')
    return matrix


def to_preview(matrix, units=1000):
    result = rigid(matrix).copy()
    result[:3, 3] *= units
    return result.T.flatten().tolist()


def world_frames(state, tree):
    units = tree.get('_preview_units_per_meter', 1000)
    components = {name: rigid(value) for name, value in state.get('visual_transforms', {}).items()}
    for name, value in tree.get('_preview_transforms', {}).items():
        converted = _math._preview_world_matrix(value, units)
        if converted is not None:
            components[name] = rigid(converted)
    frames = {}
    for link, joint, parent in walk_tree(tree):
        if joint is None:
            frame = components.get((link.get('components') or [''])[0], np.eye(4))
        else:
            info = joint.get('joint_info') or {}
            preview = _math._preview_world_matrix(info.get('_preview_world_frame_matrix'), units)
            value = preview or info.get('_joint_world_matrix')
            if value is not None:
                frame = rigid(value)
            else:
                local = _math._matrix_from_xyz_rpy(info.get('xyz', [0, 0, 0]),
                                                  info.get('_manual_rpy', info.get('rpy', [0, 0, 0])))
                frame = frames[parent['_link_id']] @ rigid(local)
        frames[link['_link_id']] = frame
    return components, frames


def capture_module(state, tree, module_id):
    errors = validate_modules(tree)
    if errors:
        raise ValueError(' / '.join(error['message'] for error in errors))
    module = next((m for m in tree.get('_modules', []) if m['id'] == module_id), None)
    if module is None:
        raise ValueError('모듈을 찾을 수 없습니다.')
    entries = list(walk_tree(tree))
    root = next(node for node, _, _ in entries if node['_link_id'] == module['root_link_id'])
    components, frames = world_frames(state, tree)
    inverse = np.linalg.inv(frames[module['root_link_id']])
    subtree = copy.deepcopy(root)
    # Root project settings are not module settings.
    for key in list(subtree):
        if key.startswith('_') and key not in {'_link_id'}:
            del subtree[key]
    names = {name for node, _, _ in walk_tree(subtree) for name in node.get('components', [])}
    for node, joint, _ in walk_tree(subtree):
        if joint is not None:
            info = joint.setdefault('joint_info', {})
            info['_joint_world_matrix'] = (inverse @ frames[node['_link_id']]).flatten().tolist()
            info.pop('_preview_world_frame_matrix', None)
            info.pop('link_world_inv_matrix', None)
    joint_names = {joint['joint_name'] for _, joint, _ in walk_tree(subtree) if joint is not None}
    transforms = {name: (inverse @ components[name]).flatten().tolist() for name in names}
    parts = []
    for part in state.get('parts', []):
        if part['name'] in names:
            item = copy.deepcopy(part)
            # No CAD machine paths in a portable module.
            for key in ('source_file', 'source_path', 'mesh_path', 'assembly_path'):
                item.pop(key, None)
            matrix = transforms[item['name']]
            item['position_mm'] = [matrix[i] * 1000 for i in (3, 7, 11)]
            item['rotation_rpy'] = _math._matrix_rpy(matrix)
            parts.append(item)
    return {'format': 'petasos-module', 'version': 1, 'name': module['name'],
            'root_link_id': root['_link_id'], 'tree': subtree, 'parts': parts,
            'inertial': {n: copy.deepcopy(state['inertial'][n]) for n in names},
            'materials': {n: copy.deepcopy(state['materials'][n]) for n in names},
            'colors': copy.deepcopy(state.get('colors', {})), 'visual_transforms': transforms,
            'snap_features': {n: copy.deepcopy(tree.get('_cad_snap_features', {})[n]) for n in names if n in tree.get('_cad_snap_features', {})},
            'physical_materials': copy.deepcopy(tree.get('_physical_materials', {})),
            'material_assignments': {n: v for n, v in tree.get('_component_material_assignments', {}).items() if n in names},
            'component_physical': {n: copy.deepcopy(v) for n, v in tree.get('_component_physical', {}).items() if n in names},
            'controllers': [copy.deepcopy(c) for c in tree.get('_controllers', []) if set(c.get('joints', [])) & joint_names],
            'meshes': [{'component': n, 'path': 'meshes/' + n + '.stl'} for n in sorted(names)]}


def place_module(payload, root_world):
    target = rigid(root_world)
    placed = copy.deepcopy(payload)
    placed['visual_transforms'] = {name: (target @ rigid(matrix)).flatten().tolist()
                                   for name, matrix in payload['visual_transforms'].items()}
    for node, joint, _ in walk_tree(placed['tree']):
        if joint is not None:
            info = joint['joint_info']
            info['_joint_world_matrix'] = (target @ rigid(info['_joint_world_matrix'])).flatten().tolist()
    for part in placed['parts']:
        matrix = placed['visual_transforms'][part['name']]
        part['position_mm'] = [matrix[i] * 1000 for i in (3, 7, 11)]
        part['rotation_rpy'] = _math._matrix_rpy(matrix)
    return placed
