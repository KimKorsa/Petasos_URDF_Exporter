import unittest
import json
import shutil
import subprocess

from tests.i18n_source_audit import collect_ui_texts, collect_backend_texts

from URDF_Exporter.core.web_ui import HTML_CONTENT


class WebUiLanguageSwitchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required to execute the browser translator')
    def test_wsl_recovery_status_has_one_complete_english_message(self):
        source = HTML_CONTENT[HTML_CONTENT.index('const PETASOS_ENGLISH ='):HTML_CONTENT.index('function petasosTranslateNode')]
        payload = {
            'source': source,
            'text': 'WSLg 화면 연결 오류로 RViz 창이 투명하게 표시됩니다. WSLg 복구를 위해 모든 WSL 배포판을 종료한 뒤 RViz를 한 번 다시 실행합니다.',
        }
        script = r"""
const fs = require('node:fs'), vm = require('node:vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({value: payload.text});
vm.runInContext("let petasosLanguage = 'en';" + payload.source, context);
process.stdout.write(vm.runInContext('petasosTranslateText(value)', context));
"""
        result = subprocess.run(['node', '-e', script], input=json.dumps(payload),
                                capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertEqual(result.stdout,
                         'A WSLg display connection error makes the RViz window transparent. '
                         'Restarting all WSL distributions once to recover WSLg, then retrying RViz.')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required to execute the browser translator')
    def test_all_builtin_ui_and_api_text_is_translated(self):
        start = HTML_CONTENT.index('const PETASOS_ENGLISH =')
        end = HTML_CONTENT.index('function petasosTranslateNode')
        payload = {
            'source': HTML_CONTENT[start:end],
            'texts': collect_ui_texts() + collect_backend_texts(),
        }
        script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({});
vm.runInContext("let petasosLanguage = 'en';" + payload.source, context);
const missing = [];
for (const text of payload.texts) {
    context.value = text;
    const english = vm.runInContext('petasosTranslateText(value)', context);
    if (/[가-힣]/.test(english)) missing.push({text, english});
}
context.value = '두 면의 법선을 반대로 맞춰 마주보게 정렬';
vm.runInContext("petasosLanguage = 'ko'", context);
if (vm.runInContext('petasosTranslateText(value)', context) !== context.value) {
    throw new Error('Korean mode changed the original text');
}
process.stdout.write(JSON.stringify(missing));
"""
        result = subprocess.run(['node', '-e', script], input=json.dumps(payload),
                                capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertEqual(json.loads(result.stdout), [])

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
            "Align Parallel Faces",
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
