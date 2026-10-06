"""Collect built-in UI text, including text split by markup and templates."""
import re
import ast
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class UiTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skipped += 1
        if not self.skipped:
            self.texts.extend(value for key, value in attrs
                              if key in ('title', 'aria-label', 'placeholder', 'alt') and value)

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skipped:
            self.skipped -= 1

    def handle_data(self, data):
        if not self.skipped:
            self.texts.append(data)

def js_literals(source):
    """Read quoted strings and templates; use 1 for interpolated values."""
    strings = []
    def scan(pos, expression=False):
        depth = 1 if expression else 0
        while pos < len(source):
            if source.startswith('//', pos):
                end = source.find('\n', pos)
                pos = len(source) if end < 0 else end + 1
            elif source.startswith('/*', pos):
                end = source.find('*/', pos + 2)
                pos = len(source) if end < 0 else end + 2
            elif source[pos] == '/' and (not source[:pos].rstrip() or source[:pos].rstrip()[-1] in '(=[:,!&|?'):
                pos += 1
                in_class = False
                while pos < len(source):
                    if source[pos] == '\\':
                        pos += 2
                        continue
                    if source[pos] == '[':
                        in_class = True
                    elif source[pos] == ']':
                        in_class = False
                    elif source[pos] == '/' and not in_class:
                        pos += 1
                        break
                    pos += 1
            elif source[pos] in "'\"`":
                quote = source[pos]
                pos += 1
                parts = []
                while pos < len(source) and source[pos] != quote:
                    if source[pos] == '\\':
                        parts.append({'n': '\n', 't': '\t'}.get(source[pos+1], source[pos+1]))
                        pos += 2
                    elif quote == '`' and source.startswith('${', pos):
                        pos = scan(pos + 2, True)
                        parts.append('1')
                    else:
                        parts.append(source[pos])
                        pos += 1
                strings.append(''.join(parts))
                pos += 1
            elif expression and source[pos] == '{':
                depth += 1
                pos += 1
            elif expression and source[pos] == '}':
                depth -= 1
                pos += 1
                if depth == 0:
                    return pos
            else:
                pos += 1
        return pos
    scan(0)
    return strings

def collect_ui_texts():
    source = (ROOT / 'URDF_Exporter/core/web_ui.py').read_text(encoding='utf-8')
    html = source.split('HTML_CONTENT = """', 1)[1].split('"""', 1)[0]
    texts = []
    parser = UiTextParser()
    parser.feed(html)
    texts.extend(parser.texts)
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    for script in scripts:
        start = script.find('const PETASOS_ENGLISH =')
        end = script.find('function petasosTranslateNode')
        if start >= 0:
            script = script[:start] + script[end:]
        texts.extend(js_literals(script))
    for path in (ROOT / 'URDF_Exporter/core').glob('*.js'):
        texts.extend(js_literals(path.read_text(encoding='utf-8')))
    result = set()
    for text in texts:
        if '<' in text and '>' in text:
            parser = UiTextParser()
            parser.feed(text)
            fragments = parser.texts
        else:
            fragments = [text]
        for fragment in fragments:
            normalized = re.sub(r'\s+', ' ', fragment).strip()
            if re.search('[가-힣]', normalized) and normalized not in ('한국어', 'Language / 언어', '페타소스 A3 · URDF 구조 에디터'):
                result.add(normalized)
    return sorted(result)

def collect_backend_texts():
    texts = set()
    paths = list((ROOT / 'URDF_Exporter/standalone').rglob('*.py')) + list((ROOT / 'moveit').glob('*.py'))
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        template_parts = {id(part) for node in ast.walk(tree)
                          if isinstance(node, ast.JoinedStr) for part in node.values}
        for node in ast.walk(tree):
            value = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in template_parts:
                value = node.value
            elif isinstance(node, ast.JoinedStr):
                value = ''.join(part.value if isinstance(part, ast.Constant) else '1' for part in node.values)
            # Exported shell scripts and README files are not browser UI.
            if value and re.search('[가-힣]', value) and not value.lstrip().startswith(('echo ', 'set -', '#!/', 'Petasos ROS 2 Humble MoveIt 번들')):
                texts.add(re.sub(r'\s+', ' ', value).strip())
    return sorted(texts)

if __name__ == '__main__':
    import json
    print(json.dumps(collect_ui_texts(), ensure_ascii=False, indent=2))
