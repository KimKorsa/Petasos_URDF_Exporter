import unittest
from URDF_Exporter.core.web_ui import HTML_CONTENT


class ControllerSelectionTests(unittest.TestCase):
    def test_viewport_excludes_controller_elements_from_pan_drag(self):
        self.assertIn('.patcher-controller-label', HTML_CONTENT)
        self.assertIn('.patcher-controller-frame', HTML_CONTENT)
        self.assertIn('.patcher-controller-border-hit', HTML_CONTENT)
        self.assertIn(
            "'.patcher-node, .patcher-joint-label, .patcher-cable, .patcher-world-fix, .patcher-footprint-settings, .patcher-controller-label, .patcher-controller-frame, .patcher-controller-border-hit'",
            HTML_CONTENT
        )

    def test_controller_label_and_border_have_proper_event_handlers(self):
        self.assertIn("borderSvg.setAttribute('class', 'patcher-controller-border-hit')", HTML_CONTENT)
        self.assertIn("selectRobotController(event, controller)", HTML_CONTENT)

    def test_controller_selection_styles_defined(self):
        self.assertIn('.patcher-controller-label.selected', HTML_CONTENT)
        self.assertIn('.patcher-controller-frame.selected', HTML_CONTENT)

    def test_controller_panel_rendering(self):
        self.assertIn("selectedElement.type === 'controller'", HTML_CONTENT)
        self.assertIn('컨트롤러 속성', HTML_CONTENT)
        self.assertIn('controllerTypeEditorHtml(controller)', HTML_CONTENT)

    def test_export_stops_on_interface_mismatch_and_focuses_joint_properties(self):
        self.assertIn('/static/modules/controller_interfaces.js', HTML_CONTENT)
        self.assertIn('controllerInterfaceIssues()', HTML_CONTENT)
        self.assertIn('interface-error', HTML_CONTENT)
        self.assertIn('applyDetectedControllerInterfaceIssue', HTML_CONTENT)
        from pathlib import Path
        server_source = (Path(__file__).parents[1] / 'URDF_Exporter' / 'standalone' / 'server.py').read_text(encoding='utf-8')
        self.assertIn('"joint_mate_alignment.js", "controller_interfaces.js"', server_source)
        self.assertLess(
            HTML_CONTENT.index('const interfaceIssues = controllerInterfaceIssues();'),
            HTML_CONTENT.index('showExportProgress(includeMoveIt);', HTML_CONTENT.index('function proceedSave()')),
        )


if __name__ == '__main__':
    unittest.main()
