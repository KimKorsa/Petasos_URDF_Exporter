"""Flask module lifecycle endpoints, kept separate from the main editor server."""
import copy
import io
import tempfile
import zipfile
from pathlib import Path
from flask import jsonify, request, send_file
from .robot_modules import create_module, validate_modules, validate_module_selection
from .module_geometry import capture_module
from .module_library import ModuleLibrary, ModuleLimitError
from .module_service import ModuleService, RevisionConflict, reposition_module


def register_module_api(app, store):
    library = ModuleLibrary(store.projects_root.parent / 'standalone_modules')
    service = ModuleService(store, library)

    def endpoint(function):
        def wrapped(*args, **kwargs):
            try:
                with store.module_lock:
                    return function(*args, **kwargs)
            except RevisionConflict as exc:
                return jsonify(error=str(exc), details=[]), 409
            except ModuleLimitError as exc:
                return jsonify(error=str(exc), details=[]), 413
            except (ValueError, KeyError, TypeError, OSError, StopIteration, zipfile.BadZipFile):
                # File-system paths and raw parser exceptions must not leak to UI.
                return jsonify(error='모듈 데이터/선택 범위를 확인하세요. 파일 누락 또는 이름 충돌일 수 있습니다.', details=[]), 400
        wrapped.__name__ = function.__name__
        return wrapped

    @app.post('/modules/validate')
    @endpoint
    def modules_validate():
        data = request.get_json()
        return jsonify(validate_module_selection(data['tree'], data['link_ids'], data['joint_ids'], data.get('editing_id')))

    @app.post('/modules/create')
    @app.post('/modules/update')
    @app.post('/modules/unassign')
    @endpoint
    def modules_edit():
        data = request.get_json()
        service.check_revision(data.get('revision'))
        tree = copy.deepcopy(data['tree'])
        if request.path.endswith(('/update', '/unassign')):
            previous = next(m for m in tree.get('_modules', []) if m['id'] == data['module_id'])
            tree['_modules'].remove(previous)
        if not request.path.endswith('/unassign'):
            tree = create_module(tree, data['link_ids'], data['joint_ids'], data['name'])
            if request.path.endswith('/update'):
                tree['_modules'][-1]['id'] = previous['id']
        errors = validate_modules(tree)
        if errors:
            return jsonify(error='모듈 범위를 확인하세요.', details=errors), 400
        return jsonify(service.commit(copy.deepcopy(store.state), tree))

    @app.get('/modules/library')
    @endpoint
    def modules_list():
        return jsonify(items=library.list_modules())

    @app.post('/modules/library/save')
    @endpoint
    def modules_save():
        data = request.get_json()
        service.check_revision(data.get('revision'))
        payload = capture_module(store.state, data['tree'], data['module_id'])
        return jsonify(library.save(payload, store.project_dir / 'meshes'))

    @app.post('/modules/library/import')
    @endpoint
    def modules_import():
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'module.zip'
            uploaded = request.files['file']
            total = 0
            with path.open('wb') as output:
                while block := uploaded.stream.read(65536):
                    total += len(block)
                    if total > library.compressed_limit:
                        raise ModuleLimitError('압축 파일 크기 제한 초과')
                    output.write(block)
            return jsonify(library.import_archive(path))

    @app.get('/modules/library/<identity>/download')
    @endpoint
    def modules_download(identity):
        with tempfile.TemporaryDirectory() as directory:
            path = library.export_archive(identity, Path(directory) / 'module.zip')
            content = io.BytesIO(path.read_bytes())
        return send_file(content, mimetype='application/zip', as_attachment=True, download_name='petasos-module.zip')

    @app.post('/modules/preview')
    @endpoint
    def modules_preview():
        data = request.get_json()
        service.check_revision(data.get('revision'))
        result, _, _ = service.preview(data)
        return jsonify(tree=result['tree'], changes=result['changes'])

    @app.post('/modules/apply')
    @endpoint
    def modules_apply():
        data = request.get_json()
        return jsonify(service.apply(data, data.get('revision')))

    @app.post('/modules/restore')
    @endpoint
    def modules_restore():
        data = request.get_json()
        return jsonify(service.restore(data['snapshot_id'], data.get('revision')))

    @app.post('/modules/placement')
    @endpoint
    def modules_placement():
        data = request.get_json()
        service.check_revision(data.get('revision'))
        state = reposition_module(store.state, data['tree'], data['module_id'], data['xyz_m'], data['rpy_rad'])
        return jsonify(service.commit(state, state['tree']))
