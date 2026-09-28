"""Split the already-serialized URDF; never re-tessellate module geometry."""
import copy
import re
from pathlib import Path
from xml.etree import ElementTree as ET

XACRO = 'http://www.ros.org/wiki/xacro'
ET.register_namespace('xacro', XACRO)


def resolve_module_exports(tree, name_map):
    from .sensor_frames import sensor_frame_name
    result = []
    for module in tree.get('_modules', []):
        try:
            owned_sensors = [sensor for sensor in tree.get('_sensors', [])
                             if sensor.get('parent_link_id') in module['link_ids']]
            result.append({'name': module['name'],
                           'links': [name_map['links'][i] for i in module['link_ids']],
                           'joints': [name_map['joints'][i] for i in module['joint_ids']],
                           'sensor_frames': [sensor_frame_name(s['name']) for s in owned_sensors]})
        except KeyError as exc:
            raise ValueError('비활성/누락된 모듈 링크 또는 조인트는 내보낼 수 없습니다.') from exc
    return result


def write_module_xacros(description_dir, modules):
    if not modules:
        return {'modules': []}
    urdf = Path(description_dir) / 'urdf'
    candidates = [p for p in urdf.glob('*.xacro') if p.name != 'materials.xacro']
    if len(candidates) != 1:
        raise ValueError('메인 로봇 Xacro 파일을 확인하세요.')
    main_path = candidates[0]
    main = ET.parse(main_path)
    transmission_path = main_path.with_suffix('.trans')
    transmission = ET.parse(transmission_path)
    folder = urdf / 'modules'; folder.mkdir(exist_ok=True)
    for module in modules:
        name = module['name']
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', name):
            raise ValueError('잘못된 모듈 파일 이름입니다.')
        sensor_frames = set(module.get('sensor_frames', []))
        owned = set(module['links']) | set(module['joints']) | sensor_frames | {
            frame + '_joint' for frame in sensor_frames}
        document = ET.Element('robot')
        macro_name = 'petasos_' + name
        macro = ET.SubElement(document, f'{{{XACRO}}}macro', name=macro_name, params="prefix:=''")
        control_macro = ET.SubElement(document, f'{{{XACRO}}}macro', name=macro_name + '_control', params="prefix:=''")

        def prefixed(element):
            copied = copy.deepcopy(element)
            for descendant in copied.iter():
                for key in ('name', 'link', 'joint'):
                    value = descendant.get(key)
                    if value in owned:
                        descendant.set(key, '${prefix}' + value)
            return copied

        for element in list(main.getroot()):
            if element.tag in {'link', 'joint'} and element.get('name') in owned:
                macro.append(prefixed(element)); main.getroot().remove(element)
        for control in transmission.getroot().iter('ros2_control'):
            moved = False
            for element in list(control):
                if element.tag == 'joint' and element.get('name') in module['joints']:
                    control_macro.append(prefixed(element)); control.remove(element); moved = True
            if moved:
                ET.SubElement(control, f'{{{XACRO}}}{macro_name}_control', prefix='')
        filename = 'modules/' + name + '.xacro'
        main.getroot().insert(0, ET.Element(f'{{{XACRO}}}include', filename=filename))
        ET.SubElement(main.getroot(), f'{{{XACRO}}}{macro_name}', prefix='')
        ET.indent(document)
        ET.ElementTree(document).write(urdf / filename, encoding='utf-8', xml_declaration=True)
    for document, path in ((main, main_path), (transmission, transmission_path)):
        ET.indent(document)
        document.write(path, encoding='utf-8', xml_declaration=True)
    return {'modules': [m['name'] for m in modules]}
