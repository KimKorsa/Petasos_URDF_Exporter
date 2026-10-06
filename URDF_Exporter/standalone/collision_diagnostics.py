"""Mesh integrity, zero-pose broadphase and optional exact collision results."""
from pathlib import Path
from itertools import combinations
import numpy as np
import trimesh
from .urdf_analysis import origin, vector, zero_positions, world_transforms
from .export_preflight import TrimeshFCLBackend


def _positive_dimension(value):
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError('Geometry dimensions must be positive and finite.')
    return result


def geometry(element, package, mesh_cache=None):
    if mesh_cache is None:
        mesh_cache = {}
    shape = element.find('geometry')
    if shape is None:
        raise ValueError('충돌 형상이 없습니다.')
    item = shape.find('mesh')
    if item is not None:
        filename = item.get('filename', '')
        if filename.startswith('package://'):
            package_name, relative = filename[10:].split('/', 1)
            if package_name != package.name:
                raise ValueError(f'외부 mesh 패키지는 확인되지 않았습니다: {package_name}')
            path = package / relative
        elif filename.startswith('file://'):
            path = Path(filename[7:])
        else:
            path = package / filename
        path = path.resolve()
        scale = vector(item.get('scale'), '1 1 1')
        key = (path, tuple(scale))
        if key not in mesh_cache:
            if path not in mesh_cache:
                mesh_cache[path] = trimesh.load_mesh(path, force='mesh', process=False)
            mesh = mesh_cache[path]
            if not np.array_equal(scale, [1, 1, 1]):
                mesh = mesh.copy()
                mesh.apply_scale(scale)
            mesh_cache[key] = mesh
        mesh = mesh_cache[key]
    elif shape.find('box') is not None:
        size = vector(shape.find('box').get('size'))
        if np.any(size <= 0):
            raise ValueError('Geometry dimensions must be positive and finite.')
        mesh = trimesh.creation.box(extents=size)
    elif shape.find('sphere') is not None:
        mesh = trimesh.creation.icosphere(radius=_positive_dimension(shape.find('sphere').get('radius')))
    elif shape.find('cylinder') is not None:
        item = shape.find('cylinder')
        mesh = trimesh.creation.cylinder(radius=_positive_dimension(item.get('radius')), height=_positive_dimension(item.get('length')))
    else:
        raise ValueError('지원하지 않는 충돌 형상입니다.')
    if not len(mesh.vertices) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise ValueError('충돌 mesh가 비어 있거나 유한하지 않습니다.')
    return mesh, origin(element)


def diagnose_collision_meshes(robot, package_dir, srdf=None, backend=None, *, mesh_cache=None):
    package = Path(package_dir)
    if mesh_cache is None:
        mesh_cache = {}
    positions = zero_positions(robot)
    poses = world_transforms(robot, positions)
    excluded = {} if srdf is None else {
        frozenset((item.get('link1'), item.get('link2'))): item.get('reason', 'User')
        for item in srdf.findall('disable_collisions')}
    adjacent = {frozenset((j.find('parent').get('link'), j.find('child').get('link')))
                for j in robot.findall('joint')}
    if backend is None:
        try:
            backend = TrimeshFCLBackend()
        except (ImportError, ValueError):
            backend = None
    records, shapes, pairs = [], {}, []
    for link in robot.findall('link'):
        name = link.get('name')
        for index, collision in enumerate(link.findall('collision')):
            record = {'link': name, 'index': index}
            try:
                mesh, local = geometry(collision, package, mesh_cache)
                world = poses[name] @ local
                vertices = trimesh.transform_points(mesh.vertices, world)
                bounds = np.array([vertices.min(axis=0), vertices.max(axis=0)])
                # STL has duplicate vertices until welded; inspect a copy, not the exported mesh.
                welded = mesh.copy()
                welded.merge_vertices()
                _, edge_counts = np.unique(welded.edges_sorted, axis=0, return_counts=True)
                record.update(status='ok', face_count=len(mesh.faces), watertight=bool(welded.is_watertight),
                              winding_consistent=bool(welded.is_winding_consistent),
                              boundary_edges=int(np.count_nonzero(edge_counts == 1)),
                              nonmanifold_edges=int(np.count_nonzero(edge_counts > 2)),
                              local_bounds=mesh.bounds.tolist(), world_bounds=bounds.tolist())
                shapes.setdefault(name, []).append((mesh, world, bounds))
            except (OSError, TypeError, ValueError, KeyError) as error:
                record.update(status='error', message=f'{name}: 충돌 형상 검사 실패: {error}')
            records.append(record)
    for first, second in combinations(sorted(shapes), 2):
        for mesh_a, world_a, bounds_a in shapes[first]:
            for mesh_b, world_b, bounds_b in shapes[second]:
                if np.any(bounds_a[1] < bounds_b[0]) or np.any(bounds_b[1] < bounds_a[0]):
                    continue
                pair = {'links': [first, second], 'status': 'suspected_overlap', 'exact_status': 'unverified',
                        'adjacent': frozenset((first, second)) in adjacent,
                        'excluded_reason': excluded.get(frozenset((first, second))),
                        'message': '영점에서 경계가 겹칩니다. 실제 충돌 확정은 아닙니다.'}
                if backend is not None:
                    try:
                        contact = backend.contacts(mesh_a, mesh_b, world_a, world_b)
                        pair.update(status='collision' if contact else 'clear', exact_status='verified',
                                    message=('영점에서 두 충돌 메시가 닿거나 겹칩니다.' if contact
                                             else '영점에서 두 충돌 메시가 닿지 않습니다.'))
                    except Exception as error:
                        pair['message'] = f'정밀 충돌 검사 미검증: {error}'
                pairs.append(pair)
    return {'status': 'error' if any(r['status'] == 'error' for r in records) else 'ok',
            'pose': positions, 'meshes': records, 'pairs': pairs, 'runtime': {'status': 'unverified'},
            'exact_backend': type(backend).__name__ if backend is not None else None}
