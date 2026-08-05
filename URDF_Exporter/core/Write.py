# -*- coding: utf-8 -*-
import os, re
from xml.etree.ElementTree import Element, SubElement
from . import Link, Joint
try:
    from utils import utils
except ImportError:
    from ..utils import utils

def write_link_urdf(
    joints_dict,
    repo,
    links_xyz_dict,
    file_name,
    inertial_dict,
    material_dict,
    package_name,
    additional_visuals=None,
    collision_meshes=None,
):
    with open(file_name, mode='a') as f:
        all_children = [joints_dict[j]['child'] for j in joints_dict]
        root_name = ""
        for j in joints_dict:
            if joints_dict[j]['parent'] not in all_children:
                root_name = joints_dict[j]['parent']
                break
        if not root_name: root_name = list(inertial_dict.keys())[0]

        if root_name not in inertial_dict:
            root_name = list(inertial_dict.keys())[0]

        def create_and_write_link(name, vis_xyz, vis_rpy, inv_matrix):
            center_of_mass = inertial_dict[name]['center_of_mass']
            if name not in material_dict:
                material_dict[name] = {'material': 'silver_default'}
            link = Link.Link(name=name, vis_xyz=vis_xyz, vis_rpy=vis_rpy, inv_matrix=inv_matrix,
                center_of_mass=center_of_mass, repo=repo,
                mass=inertial_dict[name]['mass'],
                inertia_tensor=inertial_dict[name]['inertia'],
                material = material_dict[name]['material'],
                package_name = package_name,
                collision_mesh_name=(collision_meshes or {}).get(name))
            
            if additional_visuals and name in additional_visuals:
                for visual_info in additional_visuals[name]:
                    if len(visual_info) == 2:
                        v_name, v_mat = visual_info
                        link.add_visual(v_name, v_mat)
                    else:
                        v_name, v_mat, v_xyz, v_rpy = visual_info
                        link.add_visual(v_name, v_mat, v_xyz, v_rpy)
            
            links_xyz_dict[link.name] = link.xyz
            link.make_link_xml()
            f.write(link.link_xml + '\n')

        create_and_write_link(root_name, [0,0,0], [0,0,0], None)

        for joint in joints_dict:
            name = joints_dict[joint]['child']
            if name not in inertial_dict or name in links_xyz_dict:
                continue
            create_and_write_link(
                name, 
                joints_dict[joint].get('link_vis_xyz', [0,0,0]),
                joints_dict[joint].get('link_vis_rpy', [0,0,0]),
                joints_dict[joint].get('link_world_inv_matrix', None)
            )

def write_joint_urdf(joints_dict, repo, links_xyz_dict, file_name):
    with open(file_name, mode='a') as f:
        for j in joints_dict:
            parent, child = joints_dict[j]['parent'], joints_dict[j]['child']
            if parent not in links_xyz_dict or child not in links_xyz_dict:
                continue
            xyz = joints_dict[j].get('xyz', [0, 0, 0])
            axis = joints_dict[j]['axis']
            joint = Joint.Joint(name=j, joint_type=joints_dict[j]['type'], xyz=xyz, \
                axis=axis, parent=parent, child=child, \
                upper_limit=joints_dict[j]['upper_limit'], lower_limit=joints_dict[j]['lower_limit'], \
                rpy=joints_dict[j].get('rpy', [0, 0, 0]),
                effort_limit=joints_dict[j].get('effort_limit', 100.0),
                velocity_limit=joints_dict[j].get('velocity_limit', 1.0),
                initial_position=joints_dict[j].get('initial_position', 0.0))
            joint.make_joint_xml()
            f.write(joint.joint_xml + '\n')

def write_urdf(
    joints_dict,
    links_xyz_dict,
    inertial_dict,
    material_dict,
    package_name,
    robot_name,
    save_dir,
    gazebo,
    additional_visuals=None,
    fix_to_world=True,
    root_orientation_rpy=None,
    root_origin_xyz=None,
    collision_meshes=None,
):
    if not os.path.exists(save_dir + '/urdf'): os.makedirs(save_dir + '/urdf')
    file_name = save_dir + '/urdf/' + robot_name.lower() + '.xacro'
    if root_orientation_rpy is None:
        root_orientation_rpy = [1.5707963267948966, 0, 0]
    if root_origin_xyz is None:
        root_origin_xyz = [0, 0, 0]
    root_orientation_text = " ".join(str(value) for value in root_orientation_rpy)
    root_origin_text = " ".join(str(value) for value in root_origin_xyz)
    
    with open(file_name, mode='w') as f:
        f.write('<?xml version="1.0" ?>\n')
        f.write('<robot name="{}" xmlns:xacro="http://www.ros.org/wiki/xacro">\n\n'.format(robot_name))
        
        # 비주얼라이저 호환을 위한 상대 경로 수정
        f.write('<xacro:arg name="use_gazebo" default="false" />\n')
        f.write('<xacro:include filename="materials.xacro" />\n')
        f.write('<xacro:include filename="{}.trans" />\n'.format(robot_name))
        if gazebo:
            f.write('<xacro:include filename="{}.gazebo" />\n'.format(robot_name))
        f.write('\n')
        
        if fix_to_world:
            # World 링크 추가 및 base_link(루트) 고정
            f.write('<link name="world"/>\n')
        
    write_link_urdf(
        joints_dict,
        "",
        links_xyz_dict,
        file_name,
        inertial_dict,
        material_dict,
        package_name,
        additional_visuals,
        collision_meshes,
    )
    
    if fix_to_world:
        # world와 root_name(보통 base_link)을 연결하는 조인트 수동 추가
        root_name = list(links_xyz_dict.keys())[0] if links_xyz_dict else "base_link"
        with open(file_name, mode='a') as f:
            f.write(f'''
<joint name="world_joint" type="fixed">
  <origin xyz="{root_origin_text}" rpy="{root_orientation_text}"/>
  <parent link="world"/>
  <child link="{root_name}"/>
</joint>
''')
    
    write_joint_urdf(joints_dict, "", links_xyz_dict, file_name)
    with open(file_name, mode='a') as f: f.write('</robot>\n')

def write_materials_xacro(color_dict, robot_name, save_dir):
    if not os.path.exists(save_dir + '/urdf'): os.makedirs(save_dir + '/urdf')
    file_name = save_dir + '/urdf/materials.xacro'
    with open(file_name, mode='w') as f:
        f.write('<?xml version="1.0" ?>\n')
        f.write('<robot name="{}" xmlns:xacro="http://www.ros.org/wiki/xacro" >\n'.format(robot_name))
        for color in color_dict:
            f.write('<material name="{}">\n  <color rgba="{}"/>\n</material>\n'.format(color, color_dict[color]))
        f.write('</robot>\n')

def write_transmissions_xacro(joints_dict, robot_name, save_dir):
    file_name = save_dir + '/urdf/{}.trans'.format(robot_name)
    with open(file_name, mode='w') as f:
        f.write('<?xml version="1.0" ?>\n')
        f.write('<robot name="{}" xmlns:xacro="http://www.ros.org/wiki/xacro" >\n'.format(robot_name))
        movable_joints = [
            (name, info)
            for name, info in joints_dict.items()
            if info['type'] != 'fixed'
        ]
        if movable_joints:
            control = Element('ros2_control')
            control.attrib = {
                'name': '{}_system'.format(robot_name),
                'type': 'system',
            }
            hardware = SubElement(control, 'hardware')
            gazebo_hardware = SubElement(
                hardware,
                'xacro_if',
                {'value': '$(arg use_gazebo)'},
            )
            gazebo_plugin = SubElement(gazebo_hardware, 'plugin')
            gazebo_plugin.text = 'gazebo_ros2_control/GazeboSystem'
            mock_hardware = SubElement(
                hardware,
                'xacro_unless',
                {'value': '$(arg use_gazebo)'},
            )
            mock_plugin = SubElement(mock_hardware, 'plugin')
            mock_plugin.text = 'mock_components/GenericSystem'

            for name, info in movable_joints:
                joint = SubElement(control, 'joint')
                joint.attrib = {'name': name}
                command = SubElement(joint, 'command_interface')
                command.attrib = {'name': 'position'}
                if info['type'] in ('revolute', 'prismatic'):
                    minimum = SubElement(command, 'param')
                    minimum.attrib = {'name': 'min'}
                    minimum.text = Joint.real_number_text(info['lower_limit'])
                    maximum = SubElement(command, 'param')
                    maximum.attrib = {'name': 'max'}
                    maximum.text = Joint.real_number_text(info['upper_limit'])
                state_position = SubElement(joint, 'state_interface')
                state_position.attrib = {'name': 'position'}
                initial_value = float(info.get('initial_position', 0.0))
                if info['type'] in ('revolute', 'prismatic'):
                    lower = float(info['lower_limit'])
                    upper = float(info['upper_limit'])
                    if not lower <= initial_value <= upper:
                        initial_value = (lower + upper) / 2.0
                initial = SubElement(state_position, 'param')
                initial.attrib = {'name': 'initial_value'}
                initial.text = Joint.real_number_text(initial_value)
                state_velocity = SubElement(joint, 'state_interface')
                state_velocity.attrib = {'name': 'velocity'}

            control_xml = "\n".join(utils.prettify(control).split("\n")[1:])
            control_xml = control_xml.replace("xacro_if", "xacro:if")
            control_xml = control_xml.replace("xacro_unless", "xacro:unless")
            f.write(control_xml + '\n')
        f.write('</robot>\n')

def write_gazebo_xacro(joints_dict, links_xyz_dict, inertial_dict, package_name, robot_name, save_dir):
    file_name = save_dir + '/urdf/' + robot_name + '.gazebo'
    with open(file_name, mode='w') as f:
        f.write('<?xml version="1.0" ?>\n')
        f.write('<robot name="{}" xmlns:xacro="http://www.ros.org/wiki/xacro" >\n'.format(robot_name))
        f.write(
            '<xacro:if value="$(arg use_gazebo)">\n'
            '  <gazebo>\n'
            '    <plugin name="gazebo_ros2_control" filename="libgazebo_ros2_control.so">\n'
            '      <parameters>$(find {})/config/gazebo_controllers.yaml</parameters>\n'
            '    </plugin>\n'
            '  </gazebo>\n'
            '</xacro:if>\n'.format(package_name)
        )
        f.write('</robot>\n')

def write_display_launch(package_name, robot_name, save_dir):
    # ROS 1용 레거시 (필요시 구현)
    pass
