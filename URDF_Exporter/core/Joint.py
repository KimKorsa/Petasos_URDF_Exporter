# -*- coding: utf-8 -*-
"""Joint extraction and URDF serialization support."""

try:
    import adsk
except ImportError:
    adsk = None
import re, traceback, math
from xml.etree.ElementTree import Element, SubElement
try:
    from utils import utils
except ImportError:
    from ..utils import utils


def real_number_text(value):
    """Serialize a numeric XML value with an explicit floating-point type."""
    text = format(float(value), '.15g')
    lower_text = text.lower()
    if 'e' in lower_text:
        mantissa, exponent = lower_text.split('e', 1)
        if '.' not in mantissa:
            mantissa += '.0'
        return mantissa + 'e' + exponent
    if '.' not in text:
        text += '.0'
    return text


class Joint:
    def __init__(
        self,
        name,
        xyz,
        axis,
        parent,
        child,
        joint_type,
        upper_limit,
        lower_limit,
        rpy=None,
        effort_limit=100.0,
        velocity_limit=1.0,
        initial_position=0.0,
    ):
        """
        Attributes
        ----------
        name: str
            name of the joint
        type: str
            type of the joint(ex: rev)
        xyz: [x, y, z]
            coordinate of the joint
        axis: [x, y, z]
            coordinate of axis of the joint
        parent: str
            parent link
        child: str
            child link
        joint_xml: str
            generated xml describing about the joint
        tran_xml: str
            generated xml describing about the transmission
        """
        self.name = name
        self.type = joint_type
        self.xyz = xyz
        self.rpy = rpy or [0, 0, 0]
        self.parent = parent
        self.child = child
        self.joint_xml = None
        self.tran_xml = None
        self.axis = axis  # for 'revolute' and 'continuous'
        self.upper_limit = upper_limit  # for 'revolute' and 'prismatic'
        self.lower_limit = lower_limit  # for 'revolute' and 'prismatic'
        self.effort_limit = effort_limit
        self.velocity_limit = velocity_limit
        self.initial_position = initial_position

    def make_joint_xml(self):
        """
        Generate the joint_xml and hold it by self.joint_xml
        """
        joint = Element('joint')
        joint.attrib = {'name':self.name, 'type':self.type}

        origin = SubElement(joint, 'origin')
        origin.attrib = {
            'xyz':' '.join([str(_) for _ in self.xyz]),
            'rpy':' '.join([str(_) for _ in self.rpy])
        }
        parent = SubElement(joint, 'parent')
        parent.attrib = {'link':self.parent}
        child = SubElement(joint, 'child')
        child.attrib = {'link':self.child}
        if self.type == 'revolute' or self.type == 'continuous' or self.type == 'prismatic':
            axis = SubElement(joint, 'axis')
            axis.attrib = {'xyz':' '.join([str(_) for _ in self.axis])}
        if self.type in ('revolute', 'continuous', 'prismatic'):
            limit = SubElement(joint, 'limit')
            limit.attrib = {}
            if self.type in ('revolute', 'prismatic'):
                limit.attrib.update({
                    'upper': real_number_text(self.upper_limit),
                    'lower': real_number_text(self.lower_limit),
                })
            limit.attrib.update({
                'effort': real_number_text(self.effort_limit),
                'velocity': real_number_text(self.velocity_limit),
            })

        self.joint_xml = "\n".join(utils.prettify(joint).split("\n")[1:])

    def make_transmission_xml(self):
        """
        Generate a ROS 2 control joint interface fragment.

        The enclosing ``ros2_control`` system and hardware plugin are written
        by ``Write.write_transmissions_xacro``. The method name remains for
        compatibility with older callers.
        """
        joint = Element('joint')
        joint.attrib = {'name': self.name}
        command = SubElement(joint, 'command_interface')
        command.attrib = {'name': 'position'}
        if self.type in ('revolute', 'prismatic'):
            minimum = SubElement(command, 'param')
            minimum.attrib = {'name': 'min'}
            minimum.text = real_number_text(self.lower_limit)
            maximum = SubElement(command, 'param')
            maximum.attrib = {'name': 'max'}
            maximum.text = real_number_text(self.upper_limit)
        state_position = SubElement(joint, 'state_interface')
        state_position.attrib = {'name': 'position'}
        initial_value = float(self.initial_position)
        if self.type in ('revolute', 'prismatic') and not (
            self.lower_limit <= initial_value <= self.upper_limit
        ):
            initial_value = (self.lower_limit + self.upper_limit) / 2.0
        initial = SubElement(state_position, 'param')
        initial.attrib = {'name': 'initial_value'}
        initial.text = real_number_text(initial_value)
        state_velocity = SubElement(joint, 'state_interface')
        state_velocity.attrib = {'name': 'velocity'}
        self.tran_xml = "\n".join(utils.prettify(joint).split("\n")[1:])


def make_joints_dict(root, msg):
    """
    joints_dict holds parent, axis and xyz informatino of the joints


    Parameters
    ----------
    root: adsk.fusion.Design.cast(product)
        Root component
    msg: str
        Tell the status

    Returns
    ----------
    joints_dict:
        {name: {type, axis, upper_limit, lower_limit, parent, child, xyz}}
    msg: str
        Tell the status
    """

    joint_type_list = [
    'fixed', 'revolute', 'prismatic', 'Cylindrical',
    'PinSlot', 'Planar', 'Ball']  # these are the names in urdf

    joints_dict = {}

    def _occ_transform(occ):
        if occ is None:
            return adsk.core.Matrix3D.create()
        # root component doesn't have transform
        if not hasattr(occ, 'transform'):
            return adsk.core.Matrix3D.create()
        transform2 = getattr(occ, 'transform2', None)
        if transform2:
            return transform2.copy()
        return occ.transform.copy()

    def _get_occurrence_world_transform(occ):
        matrices = []
        current = occ
        while current is not None:
            # occurrences have assemblyContext. root component doesn't.
            # but usually this loop receives an Occurrence or None.
            matrices.append(_occ_transform(current))
            if hasattr(current, 'assemblyContext'):
                current = current.assemblyContext
            else:
                current = None

        world = adsk.core.Matrix3D.create()
        for matrix in reversed(matrices):
            world.transformBy(matrix)
        return world

    def _joint_geometry_transform(joint, suffix):
        transform = getattr(joint, f'geometry{suffix}Transform', None)
        if transform:
            return transform.copy()

        origin_obj = getattr(joint, f'geometryOrOrigin{suffix}', None)
        if origin_obj:
            origin_transform = getattr(origin_obj, 'transform', None)
            if origin_transform:
                return origin_transform.copy()

            mat = adsk.core.Matrix3D.create()
            geometry = getattr(origin_obj, 'geometry', None)
            origin = getattr(geometry, 'origin', None) if geometry else getattr(origin_obj, 'origin', None)
            if origin:
                mat.translation = adsk.core.Vector3D.create(origin.x, origin.y, origin.z)
            return mat
        return adsk.core.Matrix3D.create()

    def _matrix_rpy(matrix):
        r00 = matrix.getCell(0, 0)
        r10 = matrix.getCell(1, 0)
        r20 = matrix.getCell(2, 0)
        r21 = matrix.getCell(2, 1)
        r22 = matrix.getCell(2, 2)
        r11 = matrix.getCell(1, 1)
        r12 = matrix.getCell(1, 2)

        pitch = math.atan2(-r20, math.sqrt(r00 * r00 + r10 * r10))
        if abs(abs(pitch) - math.pi / 2.0) < 1e-9:
            roll = math.atan2(-r12, r11)
            yaw = 0.0
        else:
            roll = math.atan2(r21, r22)
            yaw = math.atan2(r10, r00)
        return [round(roll, 6), round(pitch, 6), round(yaw, 6)]

    def _matrix_payload_m(matrix):
        values = [matrix.getCell(row, col) for row in range(4) for col in range(4)]
        values[3] /= 100.0
        values[7] /= 100.0
        values[11] /= 100.0
        return values

    def _normalize(values):
        length = math.sqrt(sum(value * value for value in values))
        if length <= 1e-12:
            return [0.0, 0.0, 0.0]
        return [round(value / length, 6) for value in values]

    def _rotate_vector(matrix, vector):
        return [
            matrix.getCell(0, 0) * vector[0] + matrix.getCell(0, 1) * vector[1] + matrix.getCell(0, 2) * vector[2],
            matrix.getCell(1, 0) * vector[0] + matrix.getCell(1, 1) * vector[1] + matrix.getCell(1, 2) * vector[2],
            matrix.getCell(2, 0) * vector[0] + matrix.getCell(2, 1) * vector[1] + matrix.getCell(2, 2) * vector[2],
        ]

    def _snap_axis(axis):
        axis = _normalize(axis)
        if abs(axis[0]) > 0.9:
            return [1 if axis[0] > 0 else -1, 0, 0]
        if abs(axis[1]) > 0.9:
            return [0, 1 if axis[1] > 0 else -1, 0]
        if abs(axis[2]) > 0.9:
            return [0, 0, 1 if axis[2] > 0 else -1]
        return axis

    def _add_axis_candidate(candidates, label, axis):
        snapped = _snap_axis(axis)
        if not any(item['axis'] == snapped for item in candidates):
            candidates.append({'label': label, 'axis': snapped})

    def _axis_candidates_in_joint_frame(joint_world_inv, raw_axis, one_occ, two_occ):
        candidates = []
        # Fusion can report motion vectors in different contexts depending on
        # joint geometry. Keep all interpretations so the UI can expose them.
        _add_axis_candidate(candidates, 'fusion_world', _rotate_vector(joint_world_inv, raw_axis))

        if one_occ:
            one_world = _get_occurrence_world_transform(one_occ)
            one_world_axis = _rotate_vector(one_world, raw_axis)
            _add_axis_candidate(candidates, 'occurrence_one_local', _rotate_vector(joint_world_inv, one_world_axis))

        if two_occ:
            two_world = _get_occurrence_world_transform(two_occ)
            two_world_axis = _rotate_vector(two_world, raw_axis)
            _add_axis_candidate(candidates, 'occurrence_two_local', _rotate_vector(joint_world_inv, two_world_axis))

        return candidates or [{'label': 'default_z', 'axis': [0, 0, 1]}]

    def _translation_distance(a, b):
        ta = a.translation
        tb = b.translation
        dx = ta.x - tb.x
        dy = ta.y - tb.y
        dz = ta.z - tb.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _joint_world_candidates(joint, suffix):
        occ = getattr(joint, f'occurrence{suffix}', None)
        geometry_transform = _joint_geometry_transform(joint, suffix)
        candidates = []

        if occ:
            occ_world = _get_occurrence_world_transform(occ)
            occ_relative = occ_world.copy()
            occ_relative.transformBy(geometry_transform)
            candidates.append(occ_relative)

        # Some Fusion joint geometry transforms are already expressed in the
        # assembly/root context. Keep this candidate to avoid applying the
        # occurrence transform twice.
        candidates.append(geometry_transform.copy())
        return candidates

    def _joint_world_transform(joint):
        one_candidates = _joint_world_candidates(joint, 'One')
        two_candidates = _joint_world_candidates(joint, 'Two')
        best = None

        for one_world in one_candidates:
            for two_world in two_candidates:
                distance = _translation_distance(one_world, two_world)
                if best is None or distance < best[0]:
                    best = (distance, two_world)

        if best:
            return best[1].copy()

        occ_world = _get_occurrence_world_transform(joint.occurrenceTwo)
        joint_world = occ_world.copy()
        joint_world.transformBy(_joint_geometry_transform(joint, 'Two'))
        return joint_world

    def _relative_joint_origin(parent_link_occ, child_occ, joint):
        """
        Calculate the joint's origin (xyz, rpy) relative to the parent link's origin.
        parent_link_occ: the top-level occurrence representing the parent link.
        """
        # 1. Get the world transform of the parent link's origin
        parent_link_world = _get_occurrence_world_transform(parent_link_occ)
        parent_link_world_inverse = parent_link_world.copy()
        parent_link_world_inverse.invert()

        # 2. Get the world transform of the joint itself. Fusion can expose
        # joint geometry in either occurrence-local or assembly/root context,
        # so pick the interpretation where side One and Two meet.
        joint_world = _joint_world_transform(joint)

        # 3. Calculate joint transform relative to parent link
        parent_relative = parent_link_world_inverse.copy()
        parent_relative.transformBy(joint_world)

        translation = parent_relative.translation
        xyz = [
            round(translation.x / 100.0, 6),
            round(translation.y / 100.0, 6),
            round(translation.z / 100.0, 6),
        ]
        
        joint_world_translation = joint_world.translation
        preview_world_xyz = [
            round(joint_world_translation.x / 100.0, 6),
            round(joint_world_translation.y / 100.0, 6),
            round(joint_world_translation.z / 100.0, 6),
        ]
        
        return xyz, _matrix_rpy(parent_relative), parent_link_world_inverse, _get_occurrence_world_transform(child_occ), preview_world_xyz
    
    for i, joint in enumerate(root.joints):
        if joint.isLightBulbOn :
            joint_dict = {}
            joint_type = joint_type_list[joint.jointMotion.jointType]
            joint_dict['type'] = joint_type
    
            # switch by the type of the joint
            joint_dict['axis'] = [0, 0, 0]
            joint_dict['rpy'] = [0, 0, 0]
            joint_dict['upper_limit'] = 0.0
            joint_dict['lower_limit'] = 0.0
    
            # support  "Revolute", "Rigid" and "Slider"
            if joint_type == 'revolute':
                max_enabled = joint.jointMotion.rotationLimits.isMaximumValueEnabled
                min_enabled = joint.jointMotion.rotationLimits.isMinimumValueEnabled
                if max_enabled and min_enabled:
                    joint_dict['upper_limit'] = round(joint.jointMotion.rotationLimits.maximumValue, 6)
                    joint_dict['lower_limit'] = round(joint.jointMotion.rotationLimits.minimumValue, 6)
                elif max_enabled and not min_enabled:
                    msg = joint.name + ' is not set its lower limit. Please set it and try again.'
                    break
                elif not max_enabled and min_enabled:
                    msg = joint.name + ' is not set its upper limit. Please set it and try again.'
                    break
                else:  # if there is no angle limit
                    joint_dict['type'] = 'continuous'

            elif joint_type == 'prismatic':
                max_enabled = joint.jointMotion.slideLimits.isMaximumValueEnabled
                min_enabled = joint.jointMotion.slideLimits.isMinimumValueEnabled
                if max_enabled and min_enabled:
                    joint_dict['upper_limit'] = round(joint.jointMotion.slideLimits.maximumValue/100, 6)
                    joint_dict['lower_limit'] = round(joint.jointMotion.slideLimits.minimumValue/100, 6)
                elif max_enabled and not min_enabled:
                    msg = joint.name + ' is not set its lower limit. Please set it and try again.'
                    break
                elif not max_enabled and min_enabled:
                    msg = joint.name + ' is not set its upper limit. Please set it and try again.'
                    break
            elif joint_type == 'fixed':
                pass
            
    
            def get_parent(occ): 
            # function to find the root component of the joint. This is necessary for the correct component name in the urdf file
                if occ is None:
                    return root
                if hasattr(occ, 'assemblyContext') and occ.assemblyContext != None:
                    occ = get_parent(occ.assemblyContext)
                return occ
    
            if joint.occurrenceOne != None and joint.occurrenceOne.isLightBulbOn:
                top_parent_occ = get_parent(joint.occurrenceTwo)
                joint_dict['parent'] = utils.valid_name(top_parent_occ.name)
                top_child_occ = get_parent(joint.occurrenceOne)
                joint_dict['child'] = utils.valid_name(top_child_occ.name)
            else:
                continue 
            
            def getJointOriginWorldCoordinates(joint :adsk.fusion.Joint):
            # Function to transform the joint origin coordinates which are in the component context into world coordinates
                def getMatrixFromRoot(root_occ) -> adsk.core.Matrix3D:
                    mat = adsk.core.Matrix3D.create()
                    if root_occ is None:
                        return mat # root
                    
                    occ = adsk.fusion.Occurrence.cast(root_occ)
                    if not occ:
                        return mat # root

                    def getParentOccs(occ_item):
                        occs_list = []
                        if occ_item != None:    
                            occs_list.append(occ_item)
                        if hasattr(occ_item, 'assemblyContext') and occ_item.assemblyContext != None:
                            occs_list = occs_list + getParentOccs(occ_item.assemblyContext)
                        return occs_list
                    
                    occs = getParentOccs(root_occ)
                    mat3ds = [o.transform for o in occs if o!= None]
                    for mat3d in mat3ds:
                        mat.transformBy(mat3d)
                    return mat
    
                mat = getMatrixFromRoot(joint.occurrenceTwo)
                if hasattr(joint.geometryOrOriginTwo, 'geometry') and hasattr(joint.geometryOrOriginTwo.geometry, 'origin'):
                    ori2 = joint.geometryOrOriginTwo.geometry.origin.copy()
                else:
                    ori2 = joint.geometryOrOriginTwo.origin.copy()
                ori2.transformBy(mat)
                return ori2
    
            try:
                xyz, rpy, parent_world_inverse, child_world, preview_world_xyz = _relative_joint_origin(
                    top_parent_occ,
                    joint.occurrenceOne,
                    joint
                )
                joint_dict['xyz'] = xyz
                joint_dict['rpy'] = rpy
                joint_dict['_preview_world_xyz'] = preview_world_xyz

                joint_world = _joint_world_transform(joint)
                joint_dict['_joint_world_matrix'] = _matrix_payload_m(joint_world)
                joint_world_inv = joint_world.copy()
                joint_world_inv.invert()
                
                inv_trans = joint_world_inv.translation
                joint_dict['link_vis_xyz'] = [
                    round(inv_trans.x / 100.0, 6),
                    round(inv_trans.y / 100.0, 6),
                    round(inv_trans.z / 100.0, 6),
                ]
                joint_dict['link_vis_rpy'] = _matrix_rpy(joint_world_inv)
                
                m = [joint_world_inv.getCell(r, c) for r in range(4) for c in range(4)]
                m[3] /= 100.0
                m[7] /= 100.0
                m[11] /= 100.0
                joint_dict['link_world_inv_matrix'] = m

                if joint_dict['type'] in ('revolute', 'continuous'):
                    axis_vec = joint.jointMotion.rotationAxisVector
                    raw_axis = [axis_vec.x, axis_vec.y, axis_vec.z]
                    candidates = _axis_candidates_in_joint_frame(
                        joint_world_inv,
                        raw_axis,
                        joint.occurrenceOne,
                        joint.occurrenceTwo
                    )
                    joint_dict['_axis_candidates'] = candidates
                    joint_dict['_axis_source'] = candidates[0]['label']
                    joint_dict['axis'] = candidates[0]['axis']
                elif joint_dict['type'] == 'prismatic':
                    axis_vec = joint.jointMotion.slideDirectionVector
                    raw_axis = [axis_vec.x, axis_vec.y, axis_vec.z]
                    candidates = _axis_candidates_in_joint_frame(
                        joint_world_inv,
                        raw_axis,
                        joint.occurrenceOne,
                        joint.occurrenceTwo
                    )
                    joint_dict['_axis_candidates'] = candidates
                    joint_dict['_axis_source'] = candidates[0]['label']
                    joint_dict['axis'] = candidates[0]['axis']

            except:
                print('Failed:\n{}'.format(traceback.format_exc()))
                try:
                    xyz_of_joint = getJointOriginWorldCoordinates(joint)
                    joint_dict['xyz'] = [round(xyz_of_joint.x / 100.0, 6), round(xyz_of_joint.y / 100.0, 6), round(xyz_of_joint.z / 100.0, 6)]
                    joint_dict['_preview_world_xyz'] = joint_dict['xyz']
                    joint_dict['rpy'] = [0, 0, 0]
                    joint_dict['link_vis_xyz'] = [-v for v in joint_dict['xyz']]
                    joint_dict['link_vis_rpy'] = [0, 0, 0]
                    joint_dict['link_world_inv_matrix'] = [
                        1, 0, 0, joint_dict['link_vis_xyz'][0],
                        0, 1, 0, joint_dict['link_vis_xyz'][1],
                        0, 0, 1, joint_dict['link_vis_xyz'][2],
                        0, 0, 0, 1
                    ]
                    if joint_dict['type'] in ('revolute', 'continuous'):
                        axis_vec = joint.jointMotion.rotationAxisVector
                        joint_dict['axis'] = _normalize([axis_vec.x, axis_vec.y, axis_vec.z])
                    elif joint_dict['type'] == 'prismatic':
                        axis_vec = joint.jointMotion.slideDirectionVector
                        joint_dict['axis'] = _normalize([axis_vec.x, axis_vec.y, axis_vec.z])
                except:
                    msg = joint.name + " doesn't have joint origin. Please set it and run again."
                    break
    
            joint_name = f"joint_{i+1}"
            joints_dict[joint_name] = joint_dict
    return joints_dict, msg
