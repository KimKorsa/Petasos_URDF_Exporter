"""Persistent identities and explicit, non-mutating module boundary validation."""
from __future__ import annotations

import copy
import re
import uuid


def walk_tree(tree: dict):
    stack, seen = [(tree, None, None)], set()
    while stack:
        node, edge, parent = stack.pop()
        if not isinstance(node, dict) or id(node) in seen:
            raise ValueError('순환/중복 연결 또는 잘못된 링크입니다.')
        seen.add(id(node))
        yield node, edge, parent
        for joint in reversed(node.get('children', [])):
            stack.append((joint.get('link_group'), joint, node))


def ensure_module_ids(tree: dict) -> dict:
    result = copy.deepcopy(tree)
    seen = set()
    for link, joint, _ in walk_tree(result):
        for obj, key in ((link, "_link_id"), (joint, "_joint_id")):
            if obj is None:
                continue
            if not obj.get(key):
                obj[key] = uuid.uuid4().hex
            identity = obj[key]
            if not isinstance(identity, str) or identity in seen:
                raise ValueError("링크/조인트 ID가 잘못됐거나 중복되었습니다.")
            seen.add(identity)
    return result


def validate_module_selection(tree, link_ids, joint_ids, editing_id=None):
    errors = []

    def error(code, ids, message):
        errors.append({"code": code, "ids": sorted(ids), "message": message})

    try:
        entries = list(walk_tree(tree))
        ids = [n.get('_link_id') for n, _, _ in entries] + [j.get('_joint_id') for _, j, _ in entries if j is not None]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('누락/중복 ID')
    except (ValueError, TypeError):
        return {'valid': False, 'errors': [{'code':'invalid_graph','ids':[], 'message':'트리 ID 또는 연결이 올바르지 않습니다.'}], 'root_link_id':None,'attachment_joint_id':None}
    links = {node.get("_link_id"): node for node, _, _ in entries}
    joints = {joint.get("_joint_id"): (node, joint, parent)
              for node, joint, parent in entries if joint is not None}
    selected_links, selected_joints = set(link_ids), set(joint_ids)
    if not selected_links:
        error("empty", [], "모듈에 포함할 링크를 선택하세요.")
    unknown = (selected_links - links.keys()) | (selected_joints - joints.keys())
    if unknown:
        error("unknown_id", unknown, "존재하지 않는 항목이 선택되었습니다.")
    if tree.get("_link_id") in selected_links:
        error("robot_root", [tree["_link_id"]], "로봇 본체 루트는 끝단 모듈로 지정할 수 없습니다.")
    for identity in selected_links & links.keys():
        if links[identity].get('disabled'):
            error('disabled', [identity], '비활성 링크는 모듈에 포함할 수 없습니다.')
        if links[identity].get("name") in {"world", "base_footprint"}:
            error("reserved_root", [identity], "월드/바닥 프레임은 모듈로 지정할 수 없습니다.")
    incoming, outgoing, internal = [], [], set()
    for jid, (node, joint, parent) in joints.items():
        if jid in selected_joints and joint.get('disabled'):
            error('disabled', [jid], '비활성 조인트는 모듈에 포함할 수 없습니다.')
        child_in = node.get("_link_id") in selected_links
        parent_in = parent.get("_link_id") in selected_links
        if child_in and parent_in:
            internal.add(jid)
        elif child_in:
            incoming.append(jid)
        elif parent_in:
            outgoing.append(jid)
    if len(incoming) != 1:
        error("attachment_count", incoming, "본체와 연결되는 장착 조인트가 정확히 하나여야 합니다.")
    if outgoing:
        error("outgoing_boundary", outgoing, "선택 범위 밖으로 연결된 자식이 있습니다. 범위를 직접 수정하세요.")
    missing = internal - selected_joints
    if missing:
        error("missing_joint", missing, "선택 링크 사이의 조인트가 빠졌습니다.")
    extra = selected_joints - internal
    if extra:
        error("external_joint", extra, "장착/외부 조인트는 모듈 내부 조인트 선택에서 제외하세요.")
    if selected_links and len(internal) != len(selected_links) - 1:
        error("disconnected", selected_links, "선택한 링크들이 하나로 연결되어 있지 않습니다.")
    for module in tree.get("_modules", []):
        if module.get("id") == editing_id:
            continue
        overlap = selected_links & set(module.get("link_ids", []))
        if overlap:
            error("overlap", overlap, f"다른 모듈({module.get('name', '')})에 포함된 링크입니다.")
    internal_names = {joints[jid][1].get("joint_name") for jid in internal}
    for controller in tree.get("_controllers", []):
        names = set(controller.get("joints", []))
        if names & internal_names and names - internal_names:
            error("controller_boundary", internal, f"컨트롤러 {controller.get('name', '')}가 모듈 경계를 넘습니다.")
    for jid, (_, joint, _) in joints.items():
        target = (joint.get("joint_info") or {}).get("mimic_joint")
        if target and ((jid in internal) != (target in internal_names)):
            error("mimic_boundary", [jid], f"{joint.get('joint_name')}: mimic 참조가 모듈 경계를 넘습니다.")
    return {
        "valid": not errors, "errors": errors,
        "root_link_id": joints[incoming[0]][0].get("_link_id") if len(incoming) == 1 else None,
        "attachment_joint_id": incoming[0] if len(incoming) == 1 else None,
    }


def create_module(tree, link_ids, joint_ids, name):
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", str(name)):
        raise ValueError("모듈 이름은 영문자로 시작하고 영문·숫자·밑줄만 사용하세요.")
    result = validate_module_selection(tree, link_ids, joint_ids)
    if not result["valid"]:
        raise ValueError(" / ".join(item["message"] for item in result["errors"]))
    updated = copy.deepcopy(tree)
    modules = updated.setdefault("_modules", [])
    if any(module.get("name") == name for module in modules):
        raise ValueError("이미 사용 중인 모듈 이름입니다.")
    modules.append({
        "version": 1, "id": uuid.uuid4().hex, "name": name, "color": "#38bdf8",
        "link_ids": list(dict.fromkeys(link_ids)), "joint_ids": list(dict.fromkeys(joint_ids)),
        "root_link_id": result["root_link_id"], "attachment_joint_id": result["attachment_joint_id"],
        "prefix": name + "_",
    })
    return updated


def validate_modules(tree):
    errors = []
    seen = set()
    for module in tree.get("_modules", []):
        if module.get('version') != 1 or not module.get('id') or module['id'] in seen:
            errors.append({'code':'invalid_module','ids':[], 'message':'중복 모듈 ID 또는 지원하지 않는 모듈 버전입니다.'})
        seen.add(module.get('id'))
        result = validate_module_selection(tree, module.get("link_ids", []),
                                           module.get("joint_ids", []), module.get("id"))
        errors.extend(result["errors"])
        if module.get("root_link_id") != result["root_link_id"] or module.get("attachment_joint_id") != result["attachment_joint_id"]:
            errors.append({"code": "changed_attachment", "ids": [], "message": "모듈 장착 연결이 변경되었습니다."})
    return errors
