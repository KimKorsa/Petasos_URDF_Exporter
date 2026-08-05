# -*- coding: utf-8 -*-
import re
import math

class RobotStructure:
    def __init__(self, joints_dict, inertial_dict, material_dict, visual_transforms=None):
        self.joints = joints_dict
        self.inertial = inertial_dict
        self.materials = material_dict
        self.visual_transforms = visual_transforms or {}
        self.links = list(inertial_dict.keys())
        self.tree = {}
        self.build_tree()

    def _identity_matrix(self):
        return [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, 0, 1
        ]

    def _mat_mul(self, a, b):
        return [
            sum(a[row * 4 + k] * b[k * 4 + col] for k in range(4))
            for row in range(4)
            for col in range(4)
        ]

    def _mat_inv_rigid(self, m):
        return [
            m[0], m[4], m[8], -(m[0] * m[3] + m[4] * m[7] + m[8] * m[11]),
            m[1], m[5], m[9], -(m[1] * m[3] + m[5] * m[7] + m[9] * m[11]),
            m[2], m[6], m[10], -(m[2] * m[3] + m[6] * m[7] + m[10] * m[11]),
            0, 0, 0, 1
        ]

    def _relative_matrix(self, parent_world, child_world):
        return self._mat_mul(self._mat_inv_rigid(parent_world), child_world)

    def _preview_world_matrix(self, values, units_per_meter):
        """Convert a Three.js Matrix4 payload to row-major metres."""
        if not isinstance(values, (list, tuple)) or len(values) != 16:
            return None
        try:
            matrix = [float(value) for value in values]
            scale = float(units_per_meter)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in matrix):
            return None
        if not math.isfinite(scale) or scale <= 0:
            scale = 1000.0
        return [
            matrix[0], matrix[4], matrix[8], matrix[12] / scale,
            matrix[1], matrix[5], matrix[9], matrix[13] / scale,
            matrix[2], matrix[6], matrix[10], matrix[14] / scale,
            matrix[3], matrix[7], matrix[11], matrix[15],
        ]

    def _transform_point(self, m, p):
        return [
            m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3],
            m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7],
            m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11]
        ]

    def _matrix_xyz(self, m):
        return [round(m[3], 6), round(m[7], 6), round(m[11], 6)]

    def _matrix_rpy(self, m):
        pitch = math.atan2(-m[8], math.sqrt(m[0] * m[0] + m[4] * m[4]))
        if abs(abs(pitch) - math.pi / 2.0) < 1e-9:
            roll = math.atan2(-m[6], m[5])
            yaw = 0.0
        else:
            roll = math.atan2(m[9], m[10])
            yaw = math.atan2(m[4], m[0])
        return [round(roll, 6), round(pitch, 6), round(yaw, 6)]

    def _matrix_from_xyz_rpy(self, xyz, rpy):
        roll, pitch, yaw = rpy
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)

        return [
            cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, xyz[0],
            sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, xyz[1],
            -sp, cp * sr, cp * cr, xyz[2],
            0, 0, 0, 1
        ]

    def _manual_rpy_for_urdf(self, j_info, fallback):
        manual_rpy = j_info.get('_manual_rpy')
        if manual_rpy is None:
            return fallback
        return manual_rpy

    def build_tree(self):
        """계층 구조 생성"""
        self.tree = {link: [] for link in self.links}
        for j_name, j_info in self.joints.items():
            parent = j_info['parent']
            child = j_info['child']
            if parent in self.tree:
                self.tree[parent].append({
                    'name': j_name,
                    'child': child,
                    'type': j_info['type']
                })

    def get_visual_tree(self, root_link, indent=""):
        """트리 시각화 문자열 생성"""
        lines = [indent + "🔗 " + root_link]
        if root_link in self.tree:
            for i, child_info in enumerate(self.tree[root_link]):
                is_last = (i == len(self.tree[root_link]) - 1)
                prefix = indent + ("└── " if is_last else "├── ")
                child_indent = indent + ("    " if is_last else "│   ")
                
                j_str = f"[{child_info['type']}] -> {child_info['name']}"
                lines.append(prefix + j_str)
                lines.extend(self.get_visual_tree(child_info['child'], child_indent).split('\n')[1:])
        return "\n".join(lines)

    def find_root(self):
        """루트 링크 찾기 (부모가 없는 링크)"""
        if not self.links:
            return None

        children = set()
        parents = []
        for j_info in self.joints.values():
            parent = j_info.get('parent')
            child = j_info.get('child')
            if child:
                children.add(child)
            if parent and parent in self.inertial and parent not in parents:
                parents.append(parent)

        # Prefer roots from the joint graph. The inertial dictionary may also
        # contain the Fusion design root component, which is not necessarily a
        # robot link and can hide the real kinematic tree if chosen first.
        joint_roots = [parent for parent in parents if parent not in children]
        if "base_link" in joint_roots:
            return "base_link"
        if joint_roots:
            return joint_roots[0]
        if parents:
            return parents[0]

        roots = [link for link in self.links if link not in children]
        return roots[0] if roots else self.links[0]

    def get_merge_suggestions(self):
        """Fixed(Rigid) 조인트 병합 제안"""
        suggestions = []
        for j_name, j_info in self.joints.items():
            if j_info['type'] == 'fixed':
                suggestions.append(f"Merge {j_info['child']} into {j_info['parent']} (Fixed Joint: {j_name})")
        return suggestions

    def simplify(self):
        """Fixed 조인트를 병합하여 구조 단순화"""
        fixed_joints = [j for j in self.joints if self.joints[j]['type'] == 'fixed']
        
        # 각 링크별 추가 visual 정보 저장
        self.additional_visuals = {link: [] for link in self.links}
        
        for j_name in fixed_joints:
            if j_name not in self.joints: continue
            
            j_info = self.joints[j_name]
            parent = j_info['parent']
            child = j_info['child']
            j_xyz = j_info['xyz'] # 조인트 위치 = 자식 링크의 원점
            
            # 자식 링크의 관성 정보를 부모 링크로 합산
            m1 = self.inertial[parent]['mass']
            m2 = self.inertial[child]['mass']
            if m1 + m2 > 0:
                p1 = self.inertial[parent]['center_of_mass']
                p2 = self.inertial[child]['center_of_mass']
                # p2는 child 기준이므로 parent 기준으로 변환 필요 (여기서는 j_xyz 더함)
                p2_global = p2  # p2 is already in world coordinates
                new_com = [(m1*p1[i] + m2*p2_global[i])/(m1+m2) for i in range(3)]
                
                # Inertia 합산 (단순 합산 - 실제로는 Parallel Axis Theorem 적용 필요)
                # 여기서는 ixx, iyy, izz 등 주요 성분만이라도 유지되도록 합산
                i1 = self.inertial[parent]['inertia']
                i2 = self.inertial[child]['inertia']
                new_inertia = [i1[k] + i2[k] for k in range(6)]
                
                self.inertial[parent]['mass'] = m1 + m2
                self.inertial[parent]['center_of_mass'] = new_com
                self.inertial[parent]['inertia'] = new_inertia
            
            # 자식 링크의 visual 정보를 부모에게 전달
            child_mat = self.materials[child]['material']
            self.additional_visuals[parent].append((child, child_mat))
            # 자식이 이미 가지고 있던 추가 visual들도 부모에게 전달
            for v_name, v_mat in self.additional_visuals[child]:
                self.additional_visuals[parent].append((v_name, v_mat))
            
            # 자식 링크에 연결된 다른 조인트들을 부모 링크로 재연결
            for other_j in list(self.joints.keys()):
                if other_j == j_name: continue
                if self.joints[other_j]['parent'] == child:
                    self.joints[other_j]['parent'] = parent
                    # 조인트의 xyz도 업데이트 (parent 기준으로 변경)
                    self.joints[other_j]['xyz'] = [self.joints[other_j]['xyz'][i] + j_xyz[i] for i in range(3)]
                if self.joints[other_j]['child'] == child:
                    self.joints[other_j]['child'] = parent
                    # 조인트의 xyz도 업데이트
                    self.joints[other_j]['xyz'] = [self.joints[other_j]['xyz'][i] + j_xyz[i] for i in range(3)]
            
            # 병합된 조인트와 자식 링크 삭제
            del self.joints[j_name]
            if child in self.inertial: del self.inertial[child]
            if child in self.materials: del self.materials[child]
            
        self.links = list(self.inertial.keys())
        self.build_tree()

    def build_tree_data(self):
        """Web UI로 보낼 JSON 트리 데이터를 생성합니다."""
        root = self.find_root()
        if root is None:
            return {"name": "base_link", "components": [], "children": []}
        
        def build_node(link_name):
            node = {
                "name": link_name,
                "components": [link_name],
                "children": []
            }
            for child_info in self.tree.get(link_name, []):
                j_name = child_info['name']
                j_info_full = self.joints[j_name]
                node["children"].append({
                    "joint_name": j_name,
                    "joint_type": child_info['type'],
                    "joint_info": j_info_full,
                    "link_group": build_node(child_info['child'])
                })
            return node
            
        return build_node(root)

    def apply_tree_data(self, data):
        """Web UI에서 수정한 JSON 트리 데이터를 바탕으로 물리 속성을 갱신합니다."""
        new_joints = {}
        new_inertial = {}
        new_materials = {}
        new_additional_visuals = {}
        preview_units_per_meter = data.get('_preview_units_per_meter', 1000.0)

        def traverse(node, parent_link_name=None, link_frame_world=None):
            link_name = node['name']
            components = node.get('components') or []
            if not components:
                return
            
            base_comp = components[0] # 첫 번째 컴포넌트를 메인 레퍼런스로 사용
            if link_frame_world is None:
                link_frame_world = self.visual_transforms.get(base_comp, self._identity_matrix())
            
            total_mass = 0
            com_global = [0, 0, 0]
            inertia_global = [0] * 6
            visuals = []
            
            for comp in components:
                m = self.inertial[comp]['mass']
                total_mass += m
                p = self.inertial[comp]['center_of_mass']
                com_global = [com_global[i] + m * p[i] for i in range(3)]
                
                i_t = self.inertial[comp]['inertia']
                inertia_global = [inertia_global[k] + i_t[k] for k in range(6)]
                
                mat = self.materials[comp]['material']
                
                if comp == base_comp:
                    new_materials[link_name] = {'material': mat}
                
                comp_world = self.visual_transforms.get(comp, self._identity_matrix())
                comp_local = self._relative_matrix(link_frame_world, comp_world)
                visuals.append((comp, mat, self._matrix_xyz(comp_local), self._matrix_rpy(comp_local)))

                    
            if total_mass > 0:
                com_global = [com_global[i] / total_mass for i in range(3)]
            link_frame_world_inv = self._mat_inv_rigid(link_frame_world)
            com_local = self._transform_point(link_frame_world_inv, com_global)
                
            new_inertial[link_name] = {
                'mass': total_mass,
                'center_of_mass': com_local,
                'inertia': inertia_global
            }
            new_additional_visuals[link_name] = visuals
            
            for child in node['children']:
                j_name = child['joint_name']
                j_info = child['joint_info']
                # Use the exact frame seen in the 3D viewer as the URDF source
                # of truth. This keeps nested joints on the same transform
                # chain instead of rebuilding them from a separate xyz/rpy
                # cache.
                preview_joint_world = self._preview_world_matrix(
                    j_info.get('_preview_world_frame_matrix'),
                    preview_units_per_meter,
                )
                joint_world = preview_joint_world or j_info.get('_joint_world_matrix')
                if joint_world:
                    joint_local = self._relative_matrix(link_frame_world, joint_world)
                    j_info['xyz'] = self._matrix_xyz(joint_local)
                    computed_rpy = self._matrix_rpy(joint_local)
                    if preview_joint_world is not None:
                        # Manual RPY edits remove the preview world matrix in
                        # the UI. If it still exists, the picked matrix is the
                        # authoritative final orientation.
                        j_info['rpy'] = computed_rpy
                    else:
                        j_info['rpy'] = self._manual_rpy_for_urdf(j_info, computed_rpy)
                    j_info['link_vis_xyz'] = [0, 0, 0]
                    j_info['link_vis_rpy'] = [0, 0, 0]
                    j_info['link_world_inv_matrix'] = None
                    child_link_frame_world = joint_world
                else:
                    j_info['rpy'] = self._manual_rpy_for_urdf(j_info, j_info.get('rpy', [0, 0, 0]))
                    joint_local = self._matrix_from_xyz_rpy(
                        j_info.get('xyz', [0, 0, 0]),
                        j_info['rpy']
                    )
                    child_link_frame_world = self._mat_mul(link_frame_world, joint_local)
                
                j_info['parent'] = link_name
                j_info['child'] = child['link_group']['name']
                j_info['type'] = child['joint_type']
                
                new_joints[j_name] = j_info
                traverse(child['link_group'], link_name, child_link_frame_world)
                
        traverse(data)
        
        self.joints = new_joints
        self.inertial = new_inertial
        self.materials = new_materials
        self.additional_visuals = new_additional_visuals
        self.links = list(self.inertial.keys())
        self.build_tree()

    def standardize_names(self):
        """
        루트 링크를 base_link로 변경하고,
        트리 순회 순서에 따라 조인트를 joint_1, joint_2 ... 순서로 강제 리네이밍합니다.
        """
        root = self.find_root()
        
        # 1. 루트 링크 이름 변경 -> base_link
        if root != "base_link":
            if "base_link" in self.inertial:
                pass # 이미 base_link가 따로 존재한다면 충돌 방지를 위해 패스
            else:
                self.inertial["base_link"] = self.inertial.pop(root)
                self.materials["base_link"] = self.materials.pop(root)
                if root in self.additional_visuals:
                    self.additional_visuals["base_link"] = self.additional_visuals.pop(root)
                
                # 조인트 업데이트
                for j_name, j_info in self.joints.items():
                    if j_info['parent'] == root: j_info['parent'] = "base_link"
                    if j_info['child'] == root: j_info['child'] = "base_link"
                
                self.links = list(self.inertial.keys())
                self.build_tree()
                root = "base_link"

        # 2. 조인트 순차적 이름 변경 (트리 순회)
        new_joints = {}
        joint_counter = 1
        
        def traverse_joints(current_link):
            nonlocal joint_counter
            if current_link not in self.tree: return
            
            for child_info in self.tree[current_link]:
                old_j_name = child_info['name']
                new_j_name = f"joint_{joint_counter}"
                joint_counter += 1
                
                # 조인트 복사 및 업데이트
                if old_j_name in self.joints:
                    new_joints[new_j_name] = self.joints[old_j_name]
                
                # 다음 자식으로
                traverse_joints(child_info['child'])
                
        traverse_joints(root)
        
        # 트리에 포함되지 않은 고아 조인트가 있다면(거의 없겠지만) 번호 이어서 부여
        for old_j_name in self.joints:
            if old_j_name not in new_joints.values(): # 값 비교는 안됨, 구조가 바뀌었으니
                # 위 traverse에서 안 걸린 것
                is_handled = False
                for nj in new_joints.values():
                    if nj == self.joints[old_j_name]: is_handled = True; break
                if not is_handled:
                    new_j_name = f"joint_{joint_counter}"
                    joint_counter += 1
                    new_joints[new_j_name] = self.joints[old_j_name]

        self.joints = new_joints
        self.build_tree()

def get_structure_summary(joints_dict, inertial_dict, material_dict):

    struct = RobotStructure(joints_dict, inertial_dict, material_dict)
    root = struct.find_root()
    viz = struct.get_visual_tree(root)
    suggestions = struct.get_merge_suggestions()
    
    summary = "--- Robot Structure Visualization ---\n"
    summary += viz + "\n"
    if suggestions:
        summary += "\n--- Optimization Suggestions ---\n"
        summary += "\n".join(suggestions) + "\n"
    summary += "--------------------------------------"
    return summary, struct
