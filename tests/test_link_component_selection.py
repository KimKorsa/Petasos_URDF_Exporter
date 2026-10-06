import unittest

from URDF_Exporter.core.web_ui import HTML_CONTENT


class LinkComponentSelectionTests(unittest.TestCase):
    def test_ungroup_cancels_pending_connection_preview(self):
        ungroup = HTML_CONTENT.split("function ungroupPatcherLink(node)", 1)[1].split(
            "function extractComponentFromPatcherLink", 1
        )[0]
        self.assertIn("cancelPatcherConnection();", ungroup)

    def test_component_property_name_is_an_isolation_action(self):
        self.assertIn("function selectViewerComponent(component, node)", HTML_CONTENT)
        self.assertIn("viewerIsolatedComponent = component", HTML_CONTENT)
        self.assertIn("selectViewerComponent(component, node)", HTML_CONTENT)

    def test_patcher_cards_repair_duplicate_position_ids(self):
        entries = HTML_CONTENT.split("function patcherEntries()", 1)[1].split(
            "function patcherConnectedState", 1
        )[0]
        self.assertIn("const usedIds = new Set()", entries)
        self.assertIn("if (usedIds.has(id))", entries)

    def test_clicking_component_controls_does_not_start_card_drag(self):
        move = HTML_CONTENT.split("function attachPatcherNodeMove(handle, node, element)", 1)[1].split(
            "function patcherNodeIdFor", 1
        )[0]
        self.assertIn(".link-parts, .link-parts-list", move)
        self.assertIn("if (event.target.closest(", move)
        self.assertIn("handle.setPointerCapture(event.pointerId)", move)


if __name__ == "__main__":
    unittest.main()
