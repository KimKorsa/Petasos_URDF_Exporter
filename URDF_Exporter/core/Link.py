# -*- coding: utf-8 -*-
try:
    import adsk
except ImportError:
    adsk = None
import re, traceback
from xml.etree.ElementTree import Element, SubElement
try:
    from utils import utils
except ImportError:
    from ..utils import utils

class Link:
    def __init__(
        self,
        name,
        vis_xyz,
        vis_rpy,
        inv_matrix,
        center_of_mass,
        repo,
        mass,
        inertia_tensor,
        material,
        package_name,
        collision_mesh_name=None,
    ):
        self.name = name
        self.vis_xyz = vis_xyz
        self.vis_rpy = vis_rpy
        if inv_matrix:
            cx, cy, cz = center_of_mass
            m = inv_matrix
            self.center_of_mass = [
                m[0]*cx + m[1]*cy + m[2]*cz + m[3],
                m[4]*cx + m[5]*cy + m[6]*cz + m[7],
                m[8]*cx + m[9]*cy + m[10]*cz + m[11]
            ]
        else:
            self.center_of_mass = center_of_mass
        self.link_xml = None
        self.repo = repo
        self.mass = mass
        self.inertia_tensor = inertia_tensor
        self.material = material
        self.package_name = package_name
        self.collision_mesh_name = collision_mesh_name
        self.xyz = self.vis_xyz
        self.visuals = []
        
    def add_visual(self, name, material, xyz=None, rpy=None):
        self.visuals.append((name, material, xyz, rpy))

    def make_link_xml(self):
        link = Element('link')
        link.attrib = {'name':self.name}
        
        # inertial 설정
        inertial = SubElement(link, 'inertial')
        origin_i = SubElement(inertial, 'origin')
        origin_i.attrib = {'xyz':' '.join([str(_) for _ in self.center_of_mass]), 'rpy':' '.join([str(_) for _ in self.vis_rpy])}       
        mass = SubElement(inertial, 'mass')
        mass.attrib = {'value':str(self.mass)}
        inertia = SubElement(inertial, 'inertia')
        inertia.attrib = \
            {'ixx':str(self.inertia_tensor[0]), 'iyy':str(self.inertia_tensor[1]),\
            'izz':str(self.inertia_tensor[2]), 'ixy':str(self.inertia_tensor[3]),\
            'ixz':str(self.inertia_tensor[4]), 'iyz':str(self.inertia_tensor[5])}        
        
        # 메인 visual 설정
        visuals_to_add = self.visuals if self.visuals else [(self.name, self.material, self.vis_xyz, self.vis_rpy)]
        
        for visual_info in visuals_to_add:
            if len(visual_info) == 2:
                v_name, v_mat = visual_info
                v_xyz, v_rpy = self.vis_xyz, self.vis_rpy
            else:
                v_name, v_mat, v_xyz, v_rpy = visual_info
                v_xyz = v_xyz if v_xyz is not None else self.vis_xyz
                v_rpy = v_rpy if v_rpy is not None else self.vis_rpy
            visual = SubElement(link, 'visual')
            origin_v = SubElement(visual, 'origin')
            # World 좌표계로 추출된 메쉬를 조인트 로컬 좌표계로 맞추기 위해 World 변환의 역행렬을 적용합니다.
            origin_v.attrib = {'xyz':' '.join([str(_) for _ in v_xyz]), 'rpy':' '.join([str(_) for _ in v_rpy])}
            geometry_v = SubElement(visual, 'geometry')
            mesh_v = SubElement(geometry_v, 'mesh')
            mesh_v.attrib = {
                'filename': 'package://' + self.package_name + '/meshes/' + v_name + '.stl',
                'scale': '0.001 0.001 0.001'
            }
            material = SubElement(visual, 'material')
            material.attrib = {'name': v_mat}
            
            # collision 설정 (visual과 동일하게)
            if not self.collision_mesh_name:
                collision = SubElement(link, 'collision')
                origin_c = SubElement(collision, 'origin')
                origin_c.attrib = {'xyz':' '.join([str(_) for _ in v_xyz]), 'rpy':' '.join([str(_) for _ in v_rpy])}
                geometry_c = SubElement(collision, 'geometry')
                mesh_c = SubElement(geometry_c, 'mesh')
                mesh_c.attrib = {
                    'filename': 'package://' + self.package_name + '/meshes/' + v_name + '.stl',
                    'scale': '0.001 0.001 0.001'
                }

        if self.collision_mesh_name:
            collision = SubElement(link, 'collision')
            origin_c = SubElement(collision, 'origin')
            origin_c.attrib = {'xyz': '0 0 0', 'rpy': '0 0 0'}
            geometry_c = SubElement(collision, 'geometry')
            mesh_c = SubElement(geometry_c, 'mesh')
            mesh_c.attrib = {
                'filename': (
                    'package://' + self.package_name + '/meshes/'
                    + self.collision_mesh_name
                ),
                'scale': '0.001 0.001 0.001'
            }

        self.link_xml = "\n".join(utils.prettify(link).split("\n")[1:])

def make_inertial_dict(root, msg):
    # Include root component and all occurrences
    items = [root] + list(root.allOccurrences)
    inertial_dict = {}
    for item in items:
        occs_dict = {}
        prop = item.getPhysicalProperties(adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy)
        occs_dict['name'] = utils.valid_name(item.name)
        mass = prop.mass
        occs_dict['mass'] = mass
        center_of_mass = [_/100.0 for _ in prop.centerOfMass.asArray()]
        occs_dict['center_of_mass'] = center_of_mass
        (_, xx, yy, zz, xy, yz, xz) = prop.getXYZMomentsOfInertia()
        moment_inertia_world = [_ / 10000.0 for _ in [xx, yy, zz, xy, yz, xz] ]
        occs_dict['inertia'] = utils.origin2center_of_mass(moment_inertia_world, center_of_mass, mass)
        inertial_dict[utils.valid_name(item.name)] = occs_dict
    return inertial_dict, msg

def make_material_dict(root, msg):
    def convert_german(str_in):
        for c, r in [('ä','ae'),('ö','oe'),('ü','ue'),('Ä','Ae'),('Ö','Oe'),('Ü','Ue'),('ß','ss')]:
            str_in = str_in.replace(c, r)
        return str_in
    
    # Include root component and all occurrences
    items = [root] + list(root.allOccurrences)
    material_dict = {}
    color_dict = {'silver_default': "0.700 0.700 0.700 1.000"}
    
    for item in items:
        app_dict = {'material': "silver_default"}
        def traverseColor(obj):
            appear = None
            if hasattr(obj, 'appearance') and obj.appearance:
                for prop in obj.appearance.appearanceProperties:
                    if type(prop) == adsk.core.ColorProperty: return (obj.appearance.name, prop)
            
            # Check for bRepBodies (Components and Occurrences have these)
            if hasattr(obj, 'bRepBodies') and obj.bRepBodies:
                for body in obj.bRepBodies:
                    if body.appearance:
                        for prop in body.appearance.appearanceProperties:
                            if type(prop) == adsk.core.ColorProperty: return (body.appearance.name, prop)
            
            # For Occurrences, also check their component
            if hasattr(obj, 'component') and obj.component and obj.component.material:
                comp = obj.component
                if comp.material and comp.material.appearance:
                    for prop in comp.material.appearance.appearanceProperties:
                        if type(prop) == adsk.core.ColorProperty: return (comp.material.appearance.name, prop)
            
            # For Occurrences, traverse children
            if hasattr(obj, 'childOccurrences') and obj.childOccurrences:
                for child in obj.childOccurrences:
                    appear = traverseColor(child)
                    if appear is not None:
                        return appear
            return appear
        
        result = traverseColor(item)
        if result is not None:
            try:
                prop_name, prop = result
                if prop:
                    color_name = convert_german(prop_name).replace("Farbe - ","").replace("Color - ","")
                    color_name = ("".join(re.findall(r"[A-Za-z0-9 ]*", color_name)))
                    color_name = re.sub(r'\s+',' ',color_name).strip()
                    color_name = re.sub('[ :()]', '_', color_name).replace("__","_").lower()
                    if not color_name: color_name = "silver_default"
                    app_dict['material'] = color_name
                    color_dict[color_name] = f"{prop.value.red/255} {prop.value.green/255} {prop.value.blue/255} {prop.value.opacity/255}"
            except Exception:
                pass
        
        if not app_dict.get('material'):
            app_dict['material'] = "silver_default"
            
        material_dict[utils.valid_name(item.name)] = app_dict
    return material_dict, color_dict, msg
