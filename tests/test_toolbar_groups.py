import re
import unittest
from html.parser import HTMLParser
from URDF_Exporter.core.web_ui import HTML_CONTENT


class ToolbarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.groups = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('role') == 'group':
            self.current = []
            self.groups.append((attrs.get('aria-label'), self.current))
        if tag == 'button' and self.current is not None:
            self.current.append(attrs.get('onclick'))

    def handle_endtag(self, tag):
        if tag == 'div':
            self.current = None


class ToolbarGroupsTests(unittest.TestCase):
    def test_toolbar_groups_preserve_action_order(self):
        toolbar = HTML_CONTENT.split('<div class="patcher-toolbar">', 1)[1].split('<section id="patcher-material-shelf"', 1)[0]
        parser = ToolbarParser()
        parser.feed(toolbar)
        self.assertEqual([name for name, _ in parser.groups], ['보기 및 정렬', '그룹 편집', '컨트롤러', '모듈', '재질'])
        self.assertEqual([len(actions) for _, actions in parser.groups], [5, 5, 2, 2, 1])
        self.assertEqual(parser.groups[1][1], ['togglePatcherGroupingMode()', 'mergePatcherSelection()',
            'cancelPatcherGroupingMode()', "togglePatcherPendingAction('ungroup')",
            "togglePatcherPendingAction('disconnect')"])
        self.assertEqual(parser.groups[3][1], [
            'ModuleEditor.active ? submitModuleSelection() : enterModuleSelection()', 'ModuleEditor.cancel()'])

    def test_button_dimensions_remain_unchanged(self):
        rule = re.search(r'\.patcher-toolbar button \{([^}]+)', HTML_CONTENT).group(1)
        self.assertIn('padding: 5px 9px', rule)
        self.assertIn('font-size: 10px', rule)
