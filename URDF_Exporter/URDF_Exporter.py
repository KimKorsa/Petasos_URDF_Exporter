import adsk, adsk.core, adsk.fusion, traceback
import os
import re
import sys
import importlib

# Fusion 360 script mode: ensure the script's own directory is on sys.path
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from utils import utils
from core import Link, Joint, Write, Structure, web_ui

# Fusion 360의 파이썬 모듈 캐싱으로 인한 오류 방지를 위해 모듈을 강제 리로드
try:
    importlib.reload(utils)
    importlib.reload(Link)
    importlib.reload(Joint)
    importlib.reload(Write)
    importlib.reload(Structure)
    importlib.reload(web_ui)
except:
    pass

def _get_occurrence_world_matrix(occ):
    """Return an occurrence transform accumulated from the root context."""
    matrices = []
    current = occ
    while current is not None:
        transform2 = getattr(current, 'transform2', None)
        matrices.append(transform2.copy() if transform2 else current.transform.copy())
        current = current.assemblyContext

    world = adsk.core.Matrix3D.create()
    for matrix in reversed(matrices):
        world.transformBy(matrix)
    return world

def _stl_translation_scale_from_cm(unit_type):
    units = adsk.fusion.DistanceUnits
    return {
        units.MillimeterDistanceUnits: 10.0,
        units.CentimeterDistanceUnits: 1.0,
        units.MeterDistanceUnits: 0.01,
        units.InchDistanceUnits: 1.0 / 2.54,
        units.FootDistanceUnits: 1.0 / 30.48,
        units.YardDistanceUnits: 1.0 / 91.44,
        units.MicronDistanceUnits: 10000.0,
        units.HectometerDistanceUnits: 0.0001,
        units.MileDistanceUnits: 1.0 / 160934.4,
        units.MilDistanceUnits: 1000.0 / 2.54,
        units.NauticalMileDistanceUnits: 1.0 / 185200.0,
    }.get(unit_type, 1.0)

def _stl_units_per_meter(unit_type):
    units = adsk.fusion.DistanceUnits
    return {
        units.MillimeterDistanceUnits: 1000.0,
        units.CentimeterDistanceUnits: 100.0,
        units.MeterDistanceUnits: 1.0,
        units.InchDistanceUnits: 39.37007874015748,
        units.FootDistanceUnits: 3.280839895013123,
        units.YardDistanceUnits: 1.0936132983377078,
        units.MicronDistanceUnits: 1000000.0,
        units.HectometerDistanceUnits: 0.01,
        units.MileDistanceUnits: 0.0006213711922373339,
        units.MilDistanceUnits: 39370.07874015748,
        units.NauticalMileDistanceUnits: 0.0005399568034557235,
    }.get(unit_type, 100.0)

def _matrix_to_three_js_payload(matrix, translation_scale=1.0):
    # Read the cells explicitly so the payload order is unambiguous.
    values = [matrix.getCell(row, col) for row in range(4) for col in range(4)]
    values[3] *= translation_scale
    values[7] *= translation_scale
    values[11] *= translation_scale
    # Fusion matrices are row-major. Three.js Matrix4.fromArray expects column-major.
    return [
        values[0], values[4], values[8],  values[12],
        values[1], values[5], values[9],  values[13],
        values[2], values[6], values[10], values[14],
        values[3], values[7], values[11], values[15],
    ]

def _matrix_to_row_major_m_payload(matrix):
    values = [matrix.getCell(row, col) for row in range(4) for col in range(4)]
    values[3] /= 100.0
    values[7] /= 100.0
    values[11] /= 100.0
    return values

def run(context):
    ui = None
    success_msg = 'Successfully created ROS 2 URDF package'
    msg = success_msg

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        
        if not design:
            ui.messageBox('No active Fusion design')
            return

        root = design.rootComponent
        # 로봇 이름 설정 및 패키지 명명
        robot_name = re.sub(r'\W+', '_', root.name.split()[0].lower())
        package_name = robot_name + '_description'
        
        # 1. 폴더 선택 다이얼로그
        base_path = utils.file_dialog(ui)
        if not base_path:
            return
        
        # 2. 패키지 경로 확정 및 폴더 생성
        save_dir = os.path.join(base_path, package_name).replace('\\', '/')
        os.makedirs(save_dir, exist_ok=True)
        
        # ROS 2 표준 디렉토리 구조 생성
        sub_folders = ['urdf', 'meshes', 'launch', 'resource', package_name]
        for folder in sub_folders:
            os.makedirs(os.path.join(save_dir, folder), exist_ok=True)

        # 3. 데이터 추출 (Joints, Inertial, Materials)
        joints_dict, msg = Joint.make_joints_dict(root, msg)
        if msg != success_msg: 
            ui.messageBox(msg); return

        inertial_dict, msg = Link.make_inertial_dict(root, msg)
        material_dict, color_dict, msg = Link.make_material_dict(root, msg)

        # 🚀 3.5. 메쉬(STL) 선행 추출 (Web UI 3D 프리뷰용)
        exportMgr = design.exportManager
        mesh_dir = os.path.join(save_dir, 'meshes')

        stl_errors = []
        preview_transforms = {}
        visual_transforms = {}
        preview_units_per_meter = 100.0

        # Export Root Component if it has bodies
        if root.bRepBodies.count > 0:
            expName = utils.valid_name(root.name)
            expPath = os.path.join(mesh_dir, f'{expName}.stl')
            try:
                stlOpts = exportMgr.createSTLExportOptions(root, expPath)
                stlOpts.sendToPrintUtility = False
                exportMgr.execute(stlOpts)
                preview_transforms[expName] = _matrix_to_three_js_payload(
                    adsk.core.Matrix3D.create(), # Root is at identity
                    1.0
                )
                visual_transforms[expName] = _matrix_to_row_major_m_payload(adsk.core.Matrix3D.create())
            except Exception as e:
                stl_errors.append(f'Root Component ({root.name}): {e}')

        for occ in root.allOccurrences:
            if not occ.isLightBulbOn:
                continue

            # The web preview and generated link dictionaries both key meshes by
            # utils.valid_name(occ.name), so nested occurrences need their own STL too.
            expName = utils.valid_name(occ.name)
            expPath = os.path.join(mesh_dir, f'{expName}.stl')
            try:
                stlOpts = exportMgr.createSTLExportOptions(occ, expPath)
                stlOpts.sendToPrintUtility = False
                exportMgr.execute(stlOpts)
                preview_units_per_meter = _stl_units_per_meter(
                    getattr(stlOpts, 'unitType', adsk.fusion.DistanceUnits.CentimeterDistanceUnits)
                )
                translation_scale = _stl_translation_scale_from_cm(
                    getattr(stlOpts, 'unitType', adsk.fusion.DistanceUnits.CentimeterDistanceUnits)
                )
                preview_transforms[expName] = _matrix_to_three_js_payload(
                    _get_occurrence_world_matrix(occ),
                    translation_scale
                )
                visual_transforms[expName] = _matrix_to_row_major_m_payload(_get_occurrence_world_matrix(occ))
            except Exception as e:
                stl_errors.append(f'{occ.name}: {e}')

        # --- Web UI를 통한 구조 시각화 및 드래그 앤 드롭 편집 ---
        struct = Structure.RobotStructure(joints_dict, inertial_dict, material_dict, visual_transforms)
        tree_data = struct.build_tree_data()
        tree_data['_preview_transforms'] = preview_transforms
        tree_data['_preview_units_per_meter'] = preview_units_per_meter
        
        # Fusion 360 알림
        ui.messageBox(
            "브라우저에서 로봇 구조(Kinematic Tree) 편집기가 열립니다.\n\n"
            "링크를 드래그 앤 드롭하여 병합(그룹화)하거나 이름/조인트 타입을 수정할 수 있습니다.\n"
            "웹페이지에서 '적용 및 URDF 생성' 버튼을 누르면 다음 단계로 진행됩니다.",
            "로봇 구조 편집 대기 중"
        )
        
        # 로컬 서버 띄우기 및 대기
        modified_data = web_ui.show_ui_and_wait(tree_data, save_dir)
        
        # UI에서 반환된 페이로드 추출
        if isinstance(modified_data, dict) and 'tree' in modified_data:
            modified_tree_data = modified_data['tree']
            fix_to_world = modified_data.get('fix_to_world', True)
        else:
            modified_tree_data = modified_data
            fix_to_world = True
        
        # 수정된 데이터 적용
        struct.apply_tree_data(modified_tree_data)
        
        # 🚀 추가: 이름 표준화 (base_link 지정 및 조인트 순차적 넘버링)
        struct.standardize_names()
        
        joints_dict = struct.joints
        inertial_dict = struct.inertial
        material_dict = struct.materials
        additional_visuals = struct.additional_visuals

        links_xyz_dict = {} 
        
        # 4. URDF / Xacro 작성 (ROS 2 전용)
        Write.write_urdf(joints_dict, links_xyz_dict, inertial_dict, material_dict, package_name, robot_name, save_dir, True, additional_visuals, fix_to_world)
        Write.write_materials_xacro(color_dict, robot_name, save_dir)
        Write.write_transmissions_xacro(joints_dict, robot_name, save_dir)
        Write.write_gazebo_xacro(joints_dict, links_xyz_dict, inertial_dict, package_name, robot_name, save_dir)
        
        # 5. ROS 2 빌드 및 설정 파일 생성
        # __init__.py
        with open(os.path.join(save_dir, package_name, '__init__.py'), 'w') as f: pass
        # resource marker
        with open(os.path.join(save_dir, 'resource', package_name), 'w') as f: pass
        # setup.cfg
        with open(os.path.join(save_dir, 'setup.cfg'), 'w') as f:
            f.write(f"[develop]\nscript_dir=$base/lib/{package_name}\n[install]\ninstall_scripts=$base/lib/{package_name}\n")

        # setup.py
        with open(os.path.join(save_dir, 'setup.py'), 'w', encoding='utf-8') as f:
            f.write(f"""from setuptools import setup
import os
from glob import glob

package_name = '{package_name}'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.rviz')),
        (os.path.join('share', package_name, 'urdf'), glob('urdf/*')),
        (os.path.join('share', package_name, 'meshes'), glob('meshes/*.stl')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Petasos',
    maintainer_email='contact@petasos.dev',
    description='ROS 2 package for {robot_name}',
    license='Apache-2.0',
    entry_points={{'console_scripts': [],}},
)
""")

        # package.xml
        with open(os.path.join(save_dir, 'package.xml'), 'w', encoding='utf-8') as f:
            f.write(f"""<?xml version="1.0"?>
<package format="3">
  <name>{package_name}</name>
  <version>0.0.0</version>
  <description>ROS 2 URDF package for {robot_name}</description>
  <maintainer email="contact@petasos.dev">Petasos</maintainer>
  <license>Apache-2.0</license>
  <exec_depend>robot_state_publisher</exec_depend>
  <exec_depend>joint_state_publisher_gui</exec_depend>
  <exec_depend>xacro</exec_depend>
  <exec_depend>rviz2</exec_depend>
  <export><build_type>ament_python</build_type></export>
</package>
""")

        # 6. RViz 설정 파일 자동 생성 (.rviz)
        rviz_path = os.path.join(save_dir, 'launch', 'display.rviz')
        with open(rviz_path, 'w') as f:
            f.write(f"""
Panels:
  - Class: rviz_common/Displays
    Help Height: 78
    Name: Displays
    Property Tree Widget:
      Expanded:
        - /Global Options1
        - /RobotModel1
        - /TF1
      Splitter Ratio: 0.5
    Tree Height: 559
  - Class: rviz_common/Views
    Expanded:
      - /Current View1
    Name: Views
    Splitter Ratio: 0.5
Toolbars:
  toolButtonStyle: 2
Visualization Manager:
  Class: ""
  Displays:
    - Alpha: 0.5
      Cell Size: 0.2
      Class: rviz_default_plugins/Grid
      Color: 160; 160; 164
      Enabled: true
      Line Style:
        Line Width: 0.03
        Value: Lines
      Name: Grid
      Normal Cell Count: 0
      Offset:
        X: 0
        Y: 0
        Z: 0
      Plane: XY
      Plane Cell Count: 40
      Reference Frame: <Fixed Frame>
      Value: true
    - Alpha: 1
      Class: rviz_default_plugins/RobotModel
      Collision Enabled: false
      Description Source: Topic
      Description Topic:
        Value: /robot_description
      Enabled: true
      Name: RobotModel
      Visual Enabled: true
      Update Interval: 0
      Links:
        All Links Enabled: true
        Expand Joint Details: false
        Expand Link Details: false
        Expand Tree: false
        Link Tree Style: Links in Alphabetic Order
      Value: true
    - Class: rviz_default_plugins/TF
      Enabled: true
      Frame Timeout: 15
      Frames:
        All Enabled: true
      Marker Scale: 0.3
      Name: TF
      Show Arrows: true
      Show Axes: true
      Show Names: false
      Tree:
        world:
          {{}}
      Update Interval: 0
      Value: true
  Global Options:
    Background Color: 48; 48; 48
    Fixed Frame: world
    Frame Rate: 30
    Publish Transform Tree: true
  Name: root
  Tools:
    - Class: rviz_default_plugins/Interact
      Hide Inactive Objects: true
    - Class: rviz_default_plugins/MoveCamera
    - Class: rviz_default_plugins/Select
    - Class: rviz_default_plugins/FocusCamera
    - Class: rviz_default_plugins/Measure
      Line color: 128; 128; 0
    - Class: rviz_default_plugins/SetInitialPose
      Topic:
        Value: /initialpose
    - Class: rviz_default_plugins/SetGoal
      Topic:
        Value: /goal_pose
    - Class: rviz_default_plugins/PublishPoint
      Single click: true
      Topic:
        Value: /clicked_point
  Transformation:
    Current:
      Class: rviz_default_plugins/TF
  Value: true
  Views:
    Current:
      Class: rviz_default_plugins/Orbit
      Distance: 3
      Enable Stereo Rendering:
        Stereo Eye Separation: 0.06
        Stereo Focal Distance: 1
        Swap Stereo Eyes: false
        Value: false
      Focal Point:
        X: 0
        Y: 0
        Z: 0.4
      Focal Shape Fixed Size: true
      Focal Shape Size: 0.05
      Invert Z Axis: false
      Name: Current View
      Near Clip Distance: 0.01
      Pitch: 0.6
      Target Frame: <Fixed Frame>
      Value: Orbit (rviz)
      Yaw: 0.8
    Saved: ~
""")

        # 7. display.launch.py
        launch_path = os.path.join(save_dir, 'launch', 'display.launch.py')
        with open(launch_path, 'w', encoding='utf-8') as f:
            f.write(f"""import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.substitutions import Command
from launch_ros.actions import Node

def generate_launch_description():
    package_dir = get_package_share_directory('{package_name}')
    xacro_file = os.path.join(package_dir, 'urdf', '{robot_name}.xacro')
    rviz_config = os.path.join(package_dir, 'launch', 'display.rviz')

    return LaunchDescription([
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{{'robot_description': Command(['xacro', ' ', xacro_file])}}]
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui'
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config]
        )
    ])
""")

        # 7.5. VS Code 'Urdf-visualizer' 확장프로그램 자동 설정 파일 생성
        vscode_dir = os.path.join(save_dir, '.vscode')
        os.makedirs(vscode_dir, exist_ok=True)
        with open(os.path.join(vscode_dir, 'settings.json'), 'w', encoding='utf-8') as f:
            f.write(f'''{{
    "urdf-visualizer.packages": {{
        "{package_name}": "."
    }}
}}''')

        if stl_errors:
            ui.messageBox('STL 익스포트 실패한 컴포넌트:\n' + '\n'.join(stl_errors))

        ui.messageBox(success_msg)
        
    except:
        if ui:
            ui.messageBox('Failed:\\n{}'.format(traceback.format_exc()))
