"""Per-joint actuator metadata; joint positions and limits remain output-side SI values."""
import math

PRESETS = {'AK45-36': 36.0, 'AK45-10': 10.0}
REFERENCES = {'motor_shaft', 'output_shaft'}


def normalize(config):
    if not config:
        return None
    if not isinstance(config, dict):
        raise ValueError('Actuator settings must be an object.')
    model = config.get('model', 'custom')
    if model not in {*PRESETS, 'custom'}:
        raise ValueError('Unknown actuator model.')
    try:
        ratio = float(config.get('gear_ratio', PRESETS.get(model, 1)))
        direction = float(config.get('direction', 1))
        offset = float(config.get('zero_offset', 0))
    except (ValueError, TypeError) as exc:
        raise ValueError('Actuator ratio, direction and zero offset must be numbers.') from exc
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError('Actuator gear ratio must be finite and greater than zero.')
    if model in PRESETS and ratio != PRESETS[model]:
        raise ValueError('Use the custom model to change the preset gear ratio.')
    if direction not in (-1, 1) or not math.isfinite(offset):
        raise ValueError('Actuator direction must be +1 or -1 and zero offset must be finite.')
    result = {'model': model, 'gear_ratio': ratio, 'direction': int(direction),
              'zero_offset': offset}
    if model == 'custom':
        result['model_name'] = str(config.get('model_name', '')).strip()
    for field in ('command_reference', 'feedback_reference'):
        value = config.get(field, 'output_shaft')
        if value not in REFERENCES:
            raise ValueError('Actuator angle reference must be motor_shaft or output_shaft.')
        result[field] = value
    return result


def feedback_to_joint(position, config):
    """Convert feedback position to joint radians; zero_offset is output-shaft radians."""
    scale = config['gear_ratio'] if config['feedback_reference'] == 'motor_shaft' else 1
    return config['direction'] * (position / scale - config['zero_offset'])


def joint_to_command(position, config):
    """Convert joint radians to the configured command position reference."""
    scale = config['gear_ratio'] if config['command_reference'] == 'motor_shaft' else 1
    return scale * (config['direction'] * position + config['zero_offset'])


def normalize_joints(joints):
    for name, joint in joints.items():
        if joint.get('type') not in ('revolute', 'continuous'):
            continue
        try:
            config = normalize(joint.get('actuator'))
        except ValueError as exc:
            raise ValueError(f'{name}: {exc}') from exc
        if config:
            joint['actuator'] = config
