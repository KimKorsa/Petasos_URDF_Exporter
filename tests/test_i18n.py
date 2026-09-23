import unittest

from URDF_Exporter.core.web_ui import HTML_CONTENT


class WebUiLanguageSwitchTests(unittest.TestCase):
    def test_header_contains_explicit_english_and_korean_controls(self):
        self.assertIn('id="language-en"', HTML_CONTENT)
        self.assertIn('>ENGLISH</button>', HTML_CONTENT)
        self.assertIn('id="language-ko"', HTML_CONTENT)
        self.assertIn('>한국어</button>', HTML_CONTENT)

    def test_language_choice_is_persisted_and_dynamic_content_is_observed(self):
        self.assertIn("petasos.ui.language", HTML_CONTENT)
        self.assertIn("localStorage.setItem(PETASOS_LANGUAGE_KEY", HTML_CONTENT)
        self.assertIn("new MutationObserver", HTML_CONTENT)
        self.assertIn("attributeFilter: PETASOS_TRANSLATED_ATTRIBUTES", HTML_CONTENT)

    def test_primary_editor_surfaces_have_english_translations(self):
        expected = (
            "URDF Structure Merge & 3D Preview Editor",
            "Import CAD assembly",
            "Origin coordinates",
            "Robot Structure Tree",
            "Selected Item Properties",
            "MoveIt setup and validation",
            "URDF generation complete",
        )
        for text in expected:
            with self.subTest(text=text):
                self.assertIn(text, HTML_CONTENT)


if __name__ == "__main__":
    unittest.main()
