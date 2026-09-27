"""Bounded, staged portable-module archives. Never extractall untrusted ZIPs."""
from __future__ import annotations
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from .robot_modules import ensure_module_ids, walk_tree
from .module_geometry import rigid


class ModuleLimitError(ValueError):
    pass


def safe_path(value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise ValueError('잘못된 모듈 파일 경로입니다.')
    path = PurePosixPath(value)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if (path.is_absolute() or not path.parts or any(
            p in {'.', '..'} or p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved
            or any(ord(c) < 32 for c in p) for p in value.split('/'))):
        raise ValueError('모듈 경로 이탈 또는 예약 파일명입니다.')
    if path.suffix.lower() not in {'.json', '.stl', '.obj', '.mtl', '.png', '.jpg', '.jpeg'}:
        raise ValueError('지원하지 않는 모듈 파일 형식입니다.')
    return path.as_posix()


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get('format') != 'petasos-module' or payload.get('version') != 1:
        raise ValueError('지원하지 않는 모듈 형식/버전입니다.')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', str(payload.get('name', ''))):
        raise ValueError('잘못된 모듈 이름입니다.')
    tree = payload['tree']
    if ensure_module_ids(tree) != tree or payload['root_link_id'] != tree['_link_id']:
        raise ValueError('모듈 ID가 올바르지 않습니다.')
    names = {n for link, _, _ in walk_tree(tree) for n in link.get('components', [])}
    if not names or any(set(payload[key]) != names for key in ('inertial', 'materials', 'visual_transforms')):
        raise ValueError('모듈 부품/물성 정보가 누락됐습니다.')
    for matrix in payload['visual_transforms'].values():
        rigid(matrix)
    paths = [safe_path(item['path']) for item in payload['meshes']]
    if len(set(p.casefold() for p in paths)) != len(paths):
        raise ValueError('중복 메시 경로입니다.')
    if {item['component'] for item in payload['meshes']} != names:
        raise ValueError('부품 메시가 누락됐습니다.')


class ModuleLibrary:
    def __init__(self, root, compressed_limit=200 * 1024**2, expanded_limit=1024**3, file_limit=10000):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.compressed_limit, self.expanded_limit, self.file_limit = compressed_limit, expanded_limit, file_limit

    def _directory(self, identity):
        if not re.fullmatch('[a-f0-9]{32}', str(identity)):
            raise ValueError('잘못된 라이브러리 ID입니다.')
        return self.root / identity

    def load(self, module_id):
        folder = self._directory(module_id)
        payload = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        validate_payload(payload)
        return payload, folder

    def _summary(self, identity, payload):
        entries = list(walk_tree(payload['tree']))
        return {'id': identity, 'name': payload['name'], 'version': 1,
                'link_count': len(entries), 'joint_count': len(entries) - 1}

    def list_modules(self):
        result = []
        for folder in sorted(self.root.iterdir()):
            if re.fullmatch('[a-f0-9]{32}', folder.name) and folder.is_dir():
                try:
                    payload, _ = self.load(folder.name)
                    result.append(self._summary(folder.name, payload))
                except (ValueError, KeyError, OSError):
                    continue
        return result

    def _register(self, stage, payload):
        identity = uuid.uuid4().hex
        os.replace(stage, self._directory(identity))
        return self._summary(identity, payload)

    def save(self, payload, mesh_root):
        validate_payload(payload)
        with tempfile.TemporaryDirectory(dir=self.root, prefix='.staging-') as temporary:
            stage = Path(temporary) / 'module'
            stage.mkdir()
            (stage / 'manifest.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            total = (stage / 'manifest.json').stat().st_size
            if len(payload['meshes']) + 1 > self.file_limit:
                raise ModuleLimitError('모듈 파일 수 제한 초과')
            for item in payload['meshes']:
                relative = safe_path(item['path'])
                # Captured CAD meshes live directly in the project's mesh directory.
                source_name = safe_path(item['component'] + '.stl')
                if '/' in source_name:
                    raise ValueError('잘못된 부품 파일명입니다.')
                source = Path(mesh_root) / source_name
                if source.is_symlink():
                    raise ValueError('심볼릭 링크 메시를 저장할 수 없습니다.')
                total += source.stat().st_size
                if total > self.expanded_limit:
                    raise ModuleLimitError('모듈 크기 제한 초과')
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            return self._register(stage, payload)

    def import_archive(self, archive):
        if Path(archive).stat().st_size > self.compressed_limit:
            raise ModuleLimitError('압축 파일 크기 제한 초과')
        with tempfile.TemporaryDirectory(dir=self.root, prefix='.staging-') as temporary, zipfile.ZipFile(archive) as zipped:
            stage = Path(temporary) / 'module'
            stage.mkdir()
            entries = zipped.infolist()
            if len(entries) > self.file_limit or sum(i.file_size for i in entries) > self.expanded_limit:
                raise ModuleLimitError('모듈 압축 해제 제한 초과')
            names, total = set(), 0
            for entry in entries:
                name = safe_path(entry.filename)
                if name.casefold() in names or stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                    raise ValueError('중복 경로 또는 심볼릭 링크입니다.')
                names.add(name.casefold())
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry) as source, destination.open('xb') as output:
                    while block := source.read(65536):
                        total += len(block)
                        if total > self.expanded_limit:
                            raise ModuleLimitError('모듈 실제 압축 해제 크기 초과')
                        output.write(block)
            payload = json.loads((stage / 'manifest.json').read_text(encoding='utf-8'))
            validate_payload(payload)
            for item in payload['meshes']:
                if not (stage / safe_path(item['path'])).is_file():
                    raise ValueError('모듈 메시 파일이 없습니다.')
            # OBJ/MTL references cannot reach a URL, absolute path, or outside archive.
            for path in stage.rglob('*'):
                if path.suffix.lower() in {'.obj', '.mtl'}:
                    for line in path.read_text(encoding='utf-8').splitlines():
                        words = line.strip().split()
                        if words and (words[0] == 'mtllib' or words[0].startswith('map_')):
                            for reference in words[1:]:
                                relative = safe_path(reference)
                                if not (path.parent / relative).is_file():
                                    raise ValueError('외부 OBJ/MTL 참조는 지원하지 않습니다.')
            return self._register(stage, payload)

    def export_archive(self, module_id, destination):
        _, folder = self.load(module_id)
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(folder.rglob('*')):
                if path.is_file():
                    zipped.write(path, path.relative_to(folder).as_posix())
        return Path(destination)
