import copy
import unittest
import tempfile
from pathlib import Path

from URDF_Exporter.standalone.robot_modules import (
    ensure_module_ids, validate_module_selection, create_module, validate_modules,
)


def sample_tree():
    finger = {"name": "finger", "components": ["finger_part"], "children": []}
    palm = {"name": "palm", "components": ["palm_part"], "children": [
        {"joint_name": "grip", "joint_type": "prismatic", "joint_info": {}, "link_group": finger}
    ]}
    return {"name": "base", "components": ["base_part"], "children": [
        {"joint_name": "mount", "joint_type": "fixed", "joint_info": {}, "link_group": palm}
    ]}


class RobotModuleTests(unittest.TestCase):
    def setUp(self):
        self.tree = ensure_module_ids(sample_tree())
        self.palm = self.tree["children"][0]["link_group"]
        self.grip = self.palm["children"][0]
        self.finger = self.grip["link_group"]
        self.links = [self.palm["_link_id"], self.finger["_link_id"]]
        self.joints = [self.grip["_joint_id"]]

    def test_manual_selection_does_not_add_descendants(self):
        before = copy.deepcopy(self.tree)
        result = validate_module_selection(self.tree, self.links[:1], [])
        self.assertFalse(result["valid"])
        self.assertIn("outgoing_boundary", [e["code"] for e in result["errors"]])
        self.assertEqual(self.tree, before)

    def test_ids_survive_rename_and_reload(self):
        self.palm["name"] = "renamed"
        self.assertEqual(ensure_module_ids(self.tree), self.tree)
        self.assertNotIn("_link_id", sample_tree())

    def test_missing_joint_is_rejected(self):
        result = validate_module_selection(self.tree, self.links, [])
        self.assertFalse(result["valid"])
        self.assertIn(self.joints[0], [i for e in result["errors"] for i in e["ids"]])

    def test_connected_selection_creates_exact_members_without_mutation(self):
        before = copy.deepcopy(self.tree)
        updated = create_module(self.tree, self.links, self.joints, "gripper")
        module = updated["_modules"][0]
        self.assertEqual(module["link_ids"], self.links)
        self.assertEqual(module["joint_ids"], self.joints)
        self.assertEqual(module["attachment_joint_id"], self.tree["children"][0]["_joint_id"])
        self.assertEqual(validate_modules(updated), [])
        self.assertEqual(self.tree, before)

    def test_root_duplicate_and_overlap_are_rejected(self):
        self.assertFalse(validate_module_selection(self.tree, [self.tree["_link_id"]], [])["valid"])
        updated = create_module(self.tree, self.links, self.joints, "gripper")
        self.assertFalse(validate_module_selection(updated, self.links, self.joints)["valid"])
        self.finger["_link_id"] = self.palm["_link_id"]
        with self.assertRaises(ValueError):
            ensure_module_ids(self.tree)

    def test_cross_boundary_controller_and_mimic_are_rejected(self):
        self.tree["_controllers"] = [{"name": "mixed", "joints": ["mount", "grip"]}]
        self.assertFalse(validate_module_selection(self.tree, self.links, self.joints)["valid"])
        self.tree.pop("_controllers")
        self.grip["joint_info"]["mimic_joint"] = "mount"
        self.assertFalse(validate_module_selection(self.tree, self.links, self.joints)["valid"])

    def test_unknown_ids_are_rejected(self):
        self.assertFalse(validate_module_selection(self.tree, ["missing"], [])["valid"])

    def test_workspace_persists_ids(self):
        from URDF_Exporter.standalone.server import ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / "projects")
            store.project_dir = store.projects_root / "robot"
            store.project_dir.mkdir()
            store.state = {"tree": sample_tree(), "parts": []}
            tree = store.tree()
            self.assertIn("_link_id", tree)
            store.save_workspace(tree)
            reopened = ProjectStore(store.projects_root)
            self.assertEqual(reopened.tree()["_link_id"], tree["_link_id"])

    def test_reimport_keeps_module_membership(self):
        from URDF_Exporter.standalone.reimporter import merge_reimported_state
        tree = create_module(self.tree, self.links, self.joints, "gripper")
        parts = [{"name": name} for name in ["base_part", "palm_part", "finger_part"]]
        state = {"tree": tree, "parts": parts}
        updated = merge_reimported_state(state, {"tree": sample_tree(), "parts": parts})
        self.assertEqual(updated["tree"]["_modules"], tree["_modules"])
        self.assertEqual(validate_modules(updated["tree"]), [])


if __name__ == "__main__":
    unittest.main()
