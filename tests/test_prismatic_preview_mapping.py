import unittest

from URDF_Exporter.core.web_ui import HTML_CONTENT


class PrismaticPreviewMappingTests(unittest.TestCase):
    def test_selected_joint_prefers_object_identity_over_duplicate_name(self):
        self.assertIn("function findPreviewJointControllerIndex(joint)", HTML_CONTENT)
        resolver = HTML_CONTENT.split(
            "function findPreviewJointControllerIndex(joint)", 1
        )[1].split("function selectedJointMotionEditorHtml", 1)[0]
        exact_match = resolver.index("controller.jointObj === joint")
        name_fallback = resolver.index("controller.name === joint.joint_name")
        self.assertLess(exact_match, name_fallback)
        self.assertIn("matchingIndices.length === 1", resolver)

    def test_motion_editor_uses_resolved_prismatic_controller(self):
        editor = HTML_CONTENT.split(
            "function selectedJointMotionEditorHtml(joint)", 1
        )[1].split("function updateJointType", 1)[0]
        self.assertIn("findPreviewJointControllerIndex(joint)", editor)
        self.assertIn("const isPrismatic = controller.type === 'prismatic'", editor)
        self.assertIn("const step = isPrismatic ? 0.001 : 1", editor)
        self.assertIn("const effortUnit = isPrismatic ? 'N' : 'N·m'", editor)
        self.assertIn("const velocityUnit = isPrismatic ? 'm/s' : 'rad/s'", editor)


if __name__ == "__main__":
    unittest.main()
