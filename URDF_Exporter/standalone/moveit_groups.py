"""Manual module boundaries -> planning groups, without changing ownership."""
import json
import copy
import math
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
import yaml

MOVABLE = {'revolute', 'continuous', 'prismatic'}
GRIPPER = {'position_controllers/GripperActionController', 'effort_controllers/GripperActionController'}


def _serial(names, joints):
    selected = {n for n in names if joints[n]['type'] in MOVABLE}
    by_child = {j['child']: n for n, j in joints.items()}
    for tip in selected:
        path, visited, current = set(), set(), tip
        while current is not None and current not in visited:
            visited.add(current)
            if joints[current]['type'] in MOVABLE:
                path.add(current)
            if selected <= path:
                if selected == path:
                    return True
                break
            current = by_child.get(joints[current]['parent'])
    return False


def resolve_planning_groups(tree, name_map, joints, controllers):
    modules = tree.get('_modules', [])
    groups, owned, used = [], set(), {'arm'}
    non_moveit = {n for c in controllers if c.get('type', 'joint_trajectory_controller/JointTrajectoryController')
                 not in GRIPPER | {'joint_trajectory_controller/JointTrajectoryController'} for n in c.get('joints', [])}

    def make(name, names, role):
        names = [n for n in names if joints[n]['type'] in MOVABLE]
        driven = [n for n in names if not joints[n].get('mimic_joint')]
        chain = role != 'gripper' and _serial(names, joints)
        return {'name': name, 'joints': names, 'driven_joints': driven, 'role': role,
                'chain_supported': chain, 'warnings': [] if chain or role == 'gripper' else
                ['직렬 체인이 아니므로 KDL을 자동 지정하지 않았습니다. 조인트 공간 계획만 사용하세요.']}

    for module in modules:
        name = re.sub('[^A-Za-z0-9_]', '_', module['name'])
        if not re.match('^[A-Za-z]', name):
            name = 'module_' + name
        if name in used:
            raise ValueError(f'{name}: MoveIt 그룹 이름이 중복됩니다.')
        used.add(name)
        ids = [i for i in module.get('joint_ids', []) if i != module.get('attachment_joint_id')]
        try:
            names = [name_map['joints'][i] for i in ids]
        except KeyError as error:
            raise ValueError(f'{name}: 내보낼 모듈 조인트가 없습니다.') from error
        if owned.intersection(names):
            raise ValueError(f'{name}: 모듈 조인트 범위가 중복됩니다.')
        owned.update(names)
        if any(n in non_moveit for n in names):
            raise ValueError(f'{name}: 이동용 컨트롤러는 MoveIt 자동 생성 대상이 아닙니다. description 익스포트를 사용하세요.')
        drivers = {n for n in names if joints[n]['type'] in MOVABLE and not joints[n].get('mimic_joint')}
        role = 'gripper' if any(c.get('type') in GRIPPER and drivers and drivers <= set(c.get('joints', [])) for c in controllers) else 'module'
        group = make(name, names, role)
        if group['joints']:
            groups.append(group)
    remaining = [n for n, j in joints.items() if n not in owned and j['type'] in MOVABLE]
    if not modules:
        remaining = [n for n in remaining if not joints[n].get('mimic_joint')]
    if remaining:
        arm = make('arm', remaining, 'arm')
        if not modules and any(j.get('mimic_joint') for j in joints.values()):
            arm['chain_supported'] = _serial([n for n, j in joints.items() if j['type'] in MOVABLE], joints)
        groups.insert(0, arm)
    return groups


def _group_signatures(root):
    return {group.get('name'): tuple(sorted((child.tag, tuple(sorted(child.attrib.items())))
                                           for child in group)) for group in root.findall('group')}


def _compatible_group_names(old_groups, new_groups):
    compatible = {name: name for name in old_groups
                  if name in new_groups and old_groups[name] == new_groups[name]}
    removed = {name: signature for name, signature in old_groups.items() if name not in new_groups}
    added = {name: signature for name, signature in new_groups.items() if name not in old_groups}
    for old_name, signature in removed.items():
        matches = [name for name, other in added.items() if signature and other == signature]
        # Only a unique, nonempty unchanged definition identifies a rename.
        if len(matches) == 1 and sum(other == signature for other in removed.values()) == 1:
            compatible[old_name] = matches[0]
    return compatible


def _current_robot_entities(description_dir):
    if description_dir is None:
        return set(), {}
    description = Path(description_dir)
    files = sorted((description / 'urdf').glob('*.urdf'))
    if files:
        robot = ET.parse(files[0]).getroot()
    else:
        import xacro
        main = description / 'urdf' / (description.name.removesuffix('_description') + '.xacro')
        robot = ET.fromstring(xacro.process_file(str(main)).toxml())
    return ({link.get('name') for link in robot.findall('link')},
            {joint.get('name'): joint for joint in robot.findall('joint')})


def _sync_srdf(old_path, new_path, links, joints):
    old = ET.parse(old_path).getroot()
    new = ET.parse(new_path).getroot()
    if old.tag != 'robot' or new.tag != 'robot':
        raise ValueError('SRDF must contain a robot')
    old_groups, new_groups = _group_signatures(old), _group_signatures(new)
    compatible = _compatible_group_names(old_groups, new_groups)
    pairs = {frozenset((e.get('link1'), e.get('link2'))) for e in new.findall('disable_collisions')}
    review = False
    for element in old:
        element = copy.deepcopy(element)
        keep = False
        if element.tag == 'disable_collisions':
            pair = frozenset((element.get('link1'), element.get('link2')))
            keep = bool(links) and pair <= links and pair not in pairs
            review |= bool(links) and not pair <= links
            if keep:
                pairs.add(pair)
        elif element.tag == 'group_state' and element.get('name') != 'home':
            previous_group = element.get('group')
            keep = previous_group in compatible
            if keep:
                element.set('group', compatible[previous_group])
                names = {child.get('name') for child in new.find(f"group[@name='{element.get('group')}']").findall('joint')}
                for state_joint in element.findall('joint'):
                    try:
                        value = float(state_joint.get('value', ''))
                        keep &= state_joint.get('name') in names and math.isfinite(value)
                        model_joint = joints.get(state_joint.get('name'))
                        limit = model_joint.find('limit') if model_joint is not None else None
                        if limit is not None and model_joint.get('type') != 'continuous':
                            keep &= float(limit.get('lower', '-inf')) <= value <= float(limit.get('upper', 'inf'))
                    except ValueError:
                        keep = False
            review |= not keep
        elif element.tag == 'end_effector':
            previous_group, parent_group = element.get('group'), element.get('parent_group')
            keep = (previous_group in compatible and element.get('parent_link') in links
                    and (not parent_group or parent_group in compatible))
            if keep:
                element.set('group', compatible[previous_group])
                if parent_group:
                    element.set('parent_group', compatible[parent_group])
            review |= not keep
        elif element.tag == 'group' and element.get('name') not in new_groups:
            review |= element.get('name') not in compatible
        elif element.tag in {'virtual_joint', 'passive_joint'}:
            review |= not any(child.tag == element.tag and child.attrib == element.attrib for child in new)
        if keep:
            new.append(element)
    ET.indent(new)
    ET.ElementTree(new).write(new_path, encoding='utf-8', xml_declaration=True)
    return compatible, review


def _sync_yaml(filename, old, new, compatible_groups, old_groups):
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError('MoveIt YAML must contain a mapping')
    if filename == 'ros2_controllers.yaml':
        manager = new.get('controller_manager', {}).get('ros__parameters', {})
        old_manager = old.get('controller_manager', {}).get('ros__parameters', {})
        for key, value in old_manager.items():
            if not isinstance(value, dict):
                manager[key] = value  # Keep rates and diagnostics, not obsolete registrations.
        for name in new:
            if name == 'controller_manager' or name not in old:
                continue
            if old_manager.get(name, {}).get('type') != manager.get(name, {}).get('type'):
                continue
            previous = old[name].get('ros__parameters', {})
            current = new[name].get('ros__parameters', {})
            if previous.get('joints', previous.get('joint')) == current.get('joints', current.get('joint')):
                new[name]['ros__parameters'] = {**previous, **current}
    elif filename == 'moveit_controllers.yaml':
        new['trajectory_execution'] = {**new.get('trajectory_execution', {}), **old.get('trajectory_execution', {})}
    elif filename == 'joint_limits.yaml':
        for key in ('default_velocity_scaling_factor', 'default_acceleration_scaling_factor'):
            if key in old:
                new[key] = old[key]
    elif filename == 'sensors_3d.yaml':
        if not new.get('sensors'):
            return old
    elif filename in {'kinematics.yaml', 'ompl_planning.yaml'}:
        for old_name, new_name in compatible_groups.items():
            if new_name in new and old_name in old:
                new[new_name] = old[old_name]
        if filename == 'ompl_planning.yaml':
            new['planner_configs'] = {**new.get('planner_configs', {}), **old.get('planner_configs', {})}
            for name in ('planning_plugin', 'request_adapters', 'start_state_max_bounds_error'):
                if name in old:
                    new[name] = old[name]
    return new


def preserve_assistant_config(existing_dir, generated_dir, bundle_dir, description_dir=None):
    existing, generated, bundle = map(Path, (existing_dir, generated_dir, bundle_dir))
    if not existing.is_dir():
        return None
    if existing.resolve() == generated.resolve():
        raise ValueError('기존 설정과 후보 설정 경로를 분리해야 합니다.')
    candidate = bundle / '.petasos-generated' / generated.name
    candidate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(generated, candidate, dirs_exist_ok=True)
    previous = bundle / '.petasos-previous' / generated.name
    previous.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(existing, previous, dirs_exist_ok=True)
    old_files = {p.relative_to(existing).as_posix(): p for p in existing.rglob('*') if p.is_file()}
    new_files = {p.relative_to(generated).as_posix(): p for p in generated.rglob('*') if p.is_file()}
    changed = sorted(k for k in old_files.keys() | new_files.keys()
                     if k not in old_files or k not in new_files or old_files[k].read_bytes() != new_files[k].read_bytes())
    review, preserved = [], []
    compatible_groups, old_groups = {}, set()
    links, joints = _current_robot_entities(description_dir)
    for name in sorted(new_files):
        if name.endswith('.srdf') and name in old_files:
            try:
                old_groups.update(_group_signatures(ET.parse(old_files[name]).getroot()))
                compatible_groups, needs_review = _sync_srdf(old_files[name], new_files[name], links, joints)
                if needs_review:
                    review.append(name)
            except (ET.ParseError, ValueError, OSError):
                review.append(name)  # Keep the valid generated configuration; old bytes are backed up.
    merged_yaml = {'ros2_controllers.yaml', 'moveit_controllers.yaml', 'kinematics.yaml',
                   'ompl_planning.yaml', 'joint_limits.yaml', 'sensors_3d.yaml'}
    for name, old_file in old_files.items():
        if name not in new_files:
            # Standard generated files removed by the new model must not reappear.
            if old_file.suffix == '.srdf':
                review.append(name)
                continue
            destination = generated / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_file, destination)
            preserved.append(name)
        elif Path(name).name in merged_yaml:
            try:
                old_data = yaml.safe_load(old_file.read_text(encoding='utf-8')) or {}
                new_data = yaml.safe_load(new_files[name].read_text(encoding='utf-8')) or {}
                if Path(name).name in {'kinematics.yaml', 'ompl_planning.yaml'} and isinstance(old_data, dict) and isinstance(new_data, dict):
                    if any(group in old_data and old_data[group] != new_data.get(group)
                           for group in old_groups - compatible_groups.keys()):
                        review.append(name)
                content = _sync_yaml(Path(name).name, old_data, new_data,
                                     compatible_groups, old_groups)
                new_files[name].write_text(yaml.safe_dump(content, sort_keys=False, allow_unicode=True), encoding='utf-8')
            except (yaml.YAMLError, ValueError, TypeError, AttributeError):
                review.append(name)
    report = {'status': 'synchronized', 'changed_files': changed,
              'renamed_groups': {old: new for old, new in compatible_groups.items() if old != new},
              'candidate_relative_path': candidate.relative_to(bundle).as_posix(),
              'previous_relative_path': previous.relative_to(bundle).as_posix(),
              'preserved_files': preserved, 'review_files': sorted(set(review)),
              'message': ('자동 반영하지 못한 이전 사용자 설정이 있습니다. 백업 내용을 확인하세요.' if review else
                          '현재 컨트롤러·모듈 설정을 반영하고 유효한 사용자 설정을 유지했습니다. 이전 설정은 백업했습니다.')}
    (bundle / 'moveit_settings_diff.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
