"""Read-only zero-state/contact inspection against a running MoveIt instance."""
import argparse
import json
import math
import time
from pathlib import Path
from xml.etree import ElementTree as ET


def summarize_validity(response, positions, srdf):
    contacts = [{'links': [c.contact_body_1, c.contact_body_2], 'depth': c.depth,
                 'position': [c.position.x, c.position.y, c.position.z],
                 'normal': [c.normal.x, c.normal.y, c.normal.z]} for c in response.contacts]
    return {'status': 'collision' if contacts else ('clear' if response.valid else 'invalid'),
            'valid': bool(response.valid), 'contacts': contacts, 'pose': positions,
            'excluded_pairs': [] if srdf is None else [dict(i.attrib) for i in srdf.findall('disable_collisions')],
            'acm_note': '서비스는 실행 중인 PlanningScene의 ACM을 사용합니다. SRDF 목록은 제공 파일의 참고값입니다.'}


def check_state_validity(robot, srdf, positions, timeout=10.0):
    try:
        import rclpy
        from moveit_msgs.srv import GetStateValidity
        from sensor_msgs.msg import JointState
    except ImportError as error:
        return {'status': 'unverified', 'message': f'ROS 런타임 미검증: {error}', 'pose': positions}
    own_context = not rclpy.ok()
    node = None
    try:
        if own_context:
            rclpy.init()
        node = rclpy.create_node('petasos_export_integrity_check')
        observed = {}
        def collect(message):
            observed.update(zip(message.name, message.position))
        node.create_subscription(JointState, '/joint_states', collect, 10)
        client = node.create_client(GetStateValidity, '/check_state_validity')
        if not client.wait_for_service(timeout_sec=timeout):
            return {'status': 'unverified', 'message': 'MoveIt state validity 서비스 준비 시간 초과', 'pose': positions}
        request = GetStateValidity.Request()
        request.robot_state.joint_state.name = list(positions)
        request.robot_state.joint_state.position = list(positions.values())
        request.robot_state.is_diff = False
        request.group_name = ''  # Check the whole robot, not only the arm.
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
        if not future.done() or future.result() is None:
            return {'status': 'unverified', 'message': 'MoveIt 충돌 검사 응답 시간 초과', 'pose': positions}
        report = summarize_validity(future.result(), positions, srdf)
        deadline = time.monotonic() + timeout
        while set(positions) - observed.keys() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
        missing = sorted(set(positions) - observed.keys())
        differences = [{'target': name, 'expected': value, 'observed': observed[name]}
                       for name, value in positions.items() if name in observed
                       and (not math.isfinite(observed[name]) or abs(observed[name] - value) > 1e-6)]
        report['joint_state'] = {'status': 'error' if differences else ('unverified' if missing else 'ok'),
                                 'missing': missing, 'differences': differences, 'observed': observed}
        return report
    except Exception as error:
        return {'status': 'unverified', 'message': f'실동작 검사 실패: {error}', 'pose': positions}
    finally:
        if node is not None:
            node.destroy_node()
        if own_context and rclpy.ok():
            rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description='초기 영점 및 실제 충돌 링크 쌍 검사 (제어 명령 없음)')
    parser.add_argument('--description', required=True, type=Path)
    parser.add_argument('--srdf', type=Path)
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error('timeout은 0초 초과, 60초 이하여야 합니다.')
    reference = json.loads((args.description / 'analysis' / 'export_consistency.json').read_text(encoding='utf-8'))
    if reference['status'] != 'ok':
        print('정적 일치 검사를 통과한 모델만 실동작 검사할 수 있습니다.')
        return 2
    srdf = ET.parse(args.srdf).getroot() if args.srdf else None
    report = check_state_validity(None, srdf, reference['zero_positions'], args.timeout)
    output = args.description / 'analysis' / 'export_runtime.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'clear' and report.get('joint_state', {}).get('status') == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
