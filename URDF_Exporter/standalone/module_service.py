"""Prepare first, commit once. Undo retains full project state, not just the tree."""
import copy
import filecmp
import re
import shutil
import uuid
import numpy as np
from .module_geometry import world_frames, place_module, to_preview, set_world_frame, transform_pick_metadata, rigid, _math
from .module_library import validate_payload, safe_path
from .robot_modules import walk_tree, create_module, validate_modules


class RevisionConflict(ValueError):
    pass


def reposition_module(state, tree, module_id, xyz_m, rpy_rad):
    state, tree = copy.deepcopy(state), copy.deepcopy(tree)
    errors = validate_modules(tree)
    if errors:
        raise ValueError(' / '.join(error['message'] for error in errors))
    module = next(m for m in tree['_modules'] if m['id'] == module_id)
    root, mount, parent = next(e for e in walk_tree(tree) if e[0]['_link_id'] == module['root_link_id'])
    components, frames = world_frames(state, tree)
    target = frames[parent['_link_id']] @ rigid(_math._matrix_from_xyz_rpy(xyz_m, rpy_rad))
    delta = target @ np.linalg.inv(frames[root['_link_id']])
    units = tree.get('_preview_units_per_meter', 1000)
    for node, joint, _ in walk_tree(root):
        for name in node['components']:
            matrix = delta @ components[name]
            state['visual_transforms'][name] = matrix.flatten().tolist()
            tree.setdefault('_preview_transforms', {})[name] = to_preview(matrix, units)
        if joint is not None:
            set_world_frame(joint['joint_info'], delta @ frames[node['_link_id']], units)
            transform_pick_metadata(joint['joint_info'], delta, units)
    info = mount.setdefault('joint_info', {})
    info.update(xyz=xyz_m, rpy=rpy_rad, _manual_rpy=rpy_rad)
    set_world_frame(info, target, units)
    transform_pick_metadata(info, delta, units)
    state['tree'] = tree
    return state


def _remap(value, mapping):
    if isinstance(value, dict):
        return {mapping.get(k, k): _remap(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_remap(v, mapping) for v in value]
    return mapping.get(value, value) if isinstance(value, str) else value


def prepare_module_operation(state, tree, payload, *, parent_link_id, prefix, xyz_m, rpy_rad, replace_id=None):
    validate_payload(payload)
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', str(prefix)):
        raise ValueError('Prefix는 영문자로 시작하는 영문·숫자·밑줄이어야 합니다.')
    state, tree = copy.deepcopy(state), copy.deepcopy(tree)
    errors = validate_modules(tree)
    if errors:
        raise ValueError(' / '.join(e['message'] for e in errors))
    _, frames = world_frames(state, tree)
    entries = list(walk_tree(tree))
    parent = next((n for n, _, _ in entries if n['_link_id'] == parent_link_id), None)
    if parent is None:
        raise ValueError('장착할 부모 링크를 선택하세요.')
    if any(parent_link_id in m['link_ids'] for m in tree.get('_modules', [])):
        raise ValueError('중첩 모듈 장착은 지원하지 않습니다.')
    mount = None
    if replace_id:
        old = next((m for m in tree.get('_modules', []) if m['id'] == replace_id), None)
        if old is None:
            raise ValueError('교체할 모듈이 없습니다.')
        old_root, mount, parent = next(e for e in entries if e[0]['_link_id'] == old['root_link_id'])
        target = frames[old_root['_link_id']]
        old_parts = {c for n, _, _ in walk_tree(old_root) for c in n.get('components', [])}
        old_joints = {j['joint_name'] for _, j, _ in walk_tree(old_root) if j is not None}
        for key in ('inertial', 'materials', 'visual_transforms'):
            state[key] = {n: v for n, v in state.get(key, {}).items() if n not in old_parts}
        state['parts'] = [p for p in state.get('parts', []) if p['name'] not in old_parts]
        for key in ('_preview_transforms', '_cad_snap_features', '_component_material_assignments', '_component_physical'):
            tree[key] = {n: v for n, v in tree.get(key, {}).items() if n not in old_parts}
        tree['_controllers'] = [c for c in tree.get('_controllers', []) if not set(c.get('joints', [])) & old_joints]
        tree['_modules'] = [m for m in tree['_modules'] if m['id'] != replace_id]
        parent['children'].remove(mount)
    else:
        target = frames[parent_link_id] @ np.array(_math._matrix_from_xyz_rpy(xyz_m, rpy_rad)).reshape(4, 4)
    mapping = {}
    for node, joint, _ in walk_tree(payload['tree']):
        mapping[node['_link_id']] = uuid.uuid4().hex
        mapping[node['name']] = prefix + node['name']
        if joint is not None:
            mapping[joint['_joint_id']] = uuid.uuid4().hex
            mapping[joint['joint_name']] = prefix + joint['joint_name']
    for key in ('inertial', 'colors', 'physical_materials'):
        mapping.update({name: prefix + name for name in payload.get(key, {})})
    for controller in payload.get('controllers', []):
        mapping[controller['name']] = prefix + controller['name']
        if controller.get('id'):
            mapping[controller['id']] = uuid.uuid4().hex
    occupied = {n['name'] for n, _, _ in walk_tree(tree)} | set(state.get('inertial', {}))
    occupied |= {j['joint_name'] for _, j, _ in walk_tree(tree) if j is not None}
    occupied |= {c['name'] for c in tree.get('_controllers', [])}
    for source, existing in (('colors', state.get('colors', {})),
                             ('physical_materials', tree.get('_physical_materials', {}))):
        for name, value in payload.get(source, {}).items():
            target_name = mapping[name]
            if target_name in existing and (not replace_id or existing[target_name] != _remap(value, mapping)):
                raise ValueError('재질 이름이 중복됩니다. 다른 Prefix를 사용하세요.')
    if occupied & set(mapping.values()):
        raise ValueError('같은 Prefix의 이름이 이미 있습니다. 다른 Prefix를 사용하세요.')
    placed = _remap(place_module(payload, target.flatten().tolist()), mapping)
    new_root = placed['tree']
    for node, _, _ in walk_tree(new_root):
        node['_patcher_id'] = 'module_' + uuid.uuid4().hex
    if mount is None:
        mount = {'_joint_id': uuid.uuid4().hex, 'joint_name': prefix + 'mount', 'joint_type': 'fixed',
                 'joint_info': {'xyz': xyz_m, 'rpy': rpy_rad, 'axis': [0,0,1], 'lower_limit': 0,
                                'upper_limit': 0, '_joint_world_matrix': target.flatten().tolist()}}
        set_world_frame(mount['joint_info'], target, tree.get('_preview_units_per_meter', 1000))
        if mount['joint_name'] in occupied or mount['joint_name'] in mapping.values():
            raise ValueError('장착 조인트 이름이 중복됩니다.')
    mount['link_group'] = new_root
    parent.setdefault('children', []).append(mount)
    for key in ('inertial', 'materials', 'colors', 'visual_transforms'):
        state.setdefault(key, {}).update(placed.get(key, {}))
    state.setdefault('parts', []).extend(placed['parts'])
    for dest, source in (('_cad_snap_features', 'snap_features'), ('_physical_materials', 'physical_materials'),
                         ('_component_material_assignments', 'material_assignments'), ('_component_physical', 'component_physical')):
        tree.setdefault(dest, {}).update(placed.get(source, {}))
    tree.setdefault('_preview_transforms', {}).update({n: to_preview(m, tree.get('_preview_units_per_meter', 1000)) for n, m in placed['visual_transforms'].items()})
    tree.setdefault('_controllers', []).extend(placed.get('controllers', []))
    module_entries = list(walk_tree(new_root))
    module_name = prefix.rstrip('_')
    tree = create_module(tree, [n['_link_id'] for n, _, _ in module_entries],
                         [j['_joint_id'] for _, j, _ in module_entries if j is not None], module_name)
    tree['_modules'][-1]['prefix'] = prefix
    state['tree'] = tree
    # Original CAD joint dictionary is only a seed; keep it coherent for consumers too.
    state['joints'] = {j['joint_name']: {**copy.deepcopy(j.get('joint_info', {})), 'parent': p['name'],
                                      'child': n['name'], 'type': j['joint_type']}
                       for n, j, p in walk_tree(tree) if j is not None}
    return {'state': state, 'tree': tree, 'module_id': tree['_modules'][-1]['id'], 'name_map': mapping,
            'changes': {'operation': 'replace' if replace_id else 'attach', 'module': module_name,
                        'links': len(module_entries), 'message': '재익스포트 후 MoveIt 설정과 충돌 행렬을 다시 확인하세요.'}}


class ModuleService:
    def __init__(self, store, library):
        self.store, self.library, self.snapshots = store, library, {}

    def check_revision(self, expected):
        if expected != self.store.revision:
            raise RevisionConflict('다른 작업으로 프로젝트가 변경됐습니다. 새로 불러온 후 다시 시도하세요.')

    def preview(self, request):
        payload, folder = self.library.load(request['library_id'])
        result = prepare_module_operation(self.store.state, request.get('tree') or self.store.tree(), payload,
            **{k: request[k] for k in ('parent_link_id', 'prefix', 'xyz_m', 'rpy_rad')}, replace_id=request.get('replace_id'))
        return result, payload, folder

    def commit(self, state, tree, before_tree=None):
        before = copy.deepcopy(self.store.state)
        snapshot = copy.deepcopy(before)
        if before_tree is not None:
            snapshot['tree'] = copy.deepcopy(before_tree)
        token = uuid.uuid4().hex
        state['tree'] = tree
        try:
            self.store.state = state
            self.store._write_current_state()
        except Exception:
            self.store.state = before
            raise
        self.snapshots[token] = (self.store.project_dir, snapshot, self.store.module_epoch)
        if len(self.snapshots) > 30:
            del self.snapshots[next(iter(self.snapshots))]
        return {'tree': self.store.tree(), 'revision': self.store.revision, 'undo_snapshot_id': token}

    def apply(self, request, expected_revision):
        with self.store.module_lock:
            self.check_revision(expected_revision)
            result, payload, folder = self.preview(request)
            destination = self.store.project_dir / 'meshes'
            destination.mkdir(exist_ok=True)
            # Undo retains assets. Reuse byte-identical files, never overwrite old geometry.
            pending = []
            for item in payload['meshes']:
                name = result['name_map'][item['component']] + '.stl'
                target = destination / safe_path(name)
                source = folder / safe_path(item['path'])
                if target.exists():
                    if target.is_symlink() or not filecmp.cmp(source, target, shallow=False):
                        raise ValueError('이 Prefix에 다른 메시가 있습니다. 새 Prefix를 사용하세요.')
                else:
                    pending.append((source, target))
            created = []
            try:
                for source, target in pending:
                    with target.open('xb') as output:
                        created.append(target)
                        with source.open('rb') as input_file:
                            shutil.copyfileobj(input_file, output)
                response = self.commit(result['state'], result['tree'], request.get('tree'))
            except Exception:
                for target in created:
                    target.unlink(missing_ok=True)
                raise
            return {**response, 'changes': result['changes']}

    def restore(self, snapshot_id, expected_revision):
        with self.store.module_lock:
            self.check_revision(expected_revision)
            entry = self.snapshots.get(snapshot_id)
            if entry is None or entry[0] != self.store.project_dir or entry[2] != self.store.module_epoch:
                raise ValueError('이 세션에서 복원할 수 없는 작업입니다.')
            state = copy.deepcopy(entry[1])
            return self.commit(state, state['tree'])
