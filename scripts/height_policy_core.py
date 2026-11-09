"""Decision-first, accessory-excluded height validation for CS2 authored models.

Only reports recommended *uniform* global scale; never changes bones or meshes.
The user must confirm a model category and a sizing choice before height audit.
"""
from __future__ import annotations

import math

ALLOWED_MODES = {
    'humanoid': ('match_agent', 'custom_target', 'uniform_scale', 'keep_original'),
    'nonhumanoid': ('custom_target', 'uniform_scale', 'keep_original'),
}


def positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 1e-8 else None


def _limits(profile, default_warn, default_fail, *, prefix=''):
    try:
        warn = float(profile.get(prefix + 'warn_relative_deviation', default_warn))
        fail = float(profile.get(prefix + 'fail_relative_deviation', default_fail))
    except (TypeError, ValueError):
        return None
    return (warn, fail) if 0 <= warn < fail < 1 else None


def validate_height_choice(profile):
    """Return (error or None, intended_target or None, mode or None).

    Do not silently select a mode: explicit end-user confirmation is mandatory.
    """
    if profile.get('exclude_accessories_from_height') is not True:
        return '必须明确 exclude_accessories_from_height=true', None, None
    kind = profile.get('model_type')
    if kind not in ALLOWED_MODES:
        return '先确认 model_type 为 humanoid 或 nonhumanoid', None, None
    choice = profile.get('height_choice')
    if not isinstance(choice, dict) or choice.get('confirmed_by_user') is not True:
        return 'NEEDS_HEIGHT_CHOICE: 检测身高前必须询问用户并保存确认的缩放策略', None, None
    mode = choice.get('mode')
    if mode not in ALLOWED_MODES[kind]:
        return f'高度策略 {mode!r} 不适用于 {kind}', None, mode
    if mode == 'match_agent':
        target = positive(profile.get('agent_reference_body_height'))
        if target is None:
            return '选择与默认探员等高，但缺少同单位、去装饰的本机参考主体高度', None, mode
    elif mode == 'custom_target':
        target = positive(choice.get('target_body_height'))
        if target is None:
            return '自定义目标模式必须填写有效的目标主体高度', None, mode
    elif mode in {'uniform_scale', 'keep_original'}:
        original = positive(choice.get('original_body_height'))
        if original is None:
            return '必须先从未修改的原始主体捕获 original_body_height（装饰物不计）', None, mode
        if mode == 'uniform_scale':
            factor = positive(choice.get('uniform_scale_factor'))
            if factor is None:
                return '整体等比例缩放倍数必须为正数，XYZ 三轴须使用相同倍数', None, mode
            target = original * factor
        else:
            target = original
    else:
        return '未知高度策略', None, mode
    if not math.isfinite(target):
        return '目标高度无效', None, mode
    return None, target, mode


def evaluate_height_policy(profile, body_height, *, rig_height=None):
    """Validate height in one calibrated unit and space, with all accessories excluded.

    Human: compare selected target to body, not limb-by-limb agent dimensions.
    Nonhuman: *also* require the primary skeleton's vertical span to match body.
    """
    height = positive(body_height)
    if height is None:
        return {'status': 'FAIL', 'reason': '主体几何高度无效：检查分类、上轴和单位'}
    error, target, mode = validate_height_choice(profile)
    if error:
        return {'status': 'PENDING' if error.startswith('NEEDS_HEIGHT_CHOICE') or '缺少' in error or '捕获' in error
                else 'FAIL', 'reason': error, 'body_height': height,
                'selection_confirmed': bool(profile.get('height_choice', {}).get('confirmed_by_user'))
                if isinstance(profile.get('height_choice'), dict) else False}

    limits = _limits(profile, .05, .15)
    if limits is None:
        return {'status': 'FAIL', 'reason': '主体高度阈值无效，要求 0 <= warn < fail < 1'}
    warn, fail = limits
    deviation = abs(height / target - 1.0)
    body_status = 'FAIL' if deviation > fail else 'WARN' if deviation > warn else 'PASS'
    result = {
        'status': body_status,
        'body_height': height,
        'target_body_height': target,
        'height_choice_mode': mode,
        'selection_confirmed': True,
        'model_type': profile['model_type'],
        'relative_deviation': deviation,
        'warning_threshold': warn,
        'failure_threshold': fail,
        'recommended_uniform_scale_for_review': target / height,
        'body_target_status': body_status,
        'interpretation': '只建议全局 XYZ 等比例缩放（几何、骨架、碰撞/挂点一起处理），禁止拉伸四肢或改变原模型相对比例。',
    }
    if profile['model_type'] == 'nonhumanoid':
        skeleton_height = positive(rig_height)
        if skeleton_height is None:
            result.update(status='PENDING', skeleton_body_status='PENDING',
                          reason='非人形缺少主骨架高度（排除装饰骨）')
            return result
        skeleton_limits = _limits(profile, .03, .08, prefix='skeleton_')
        if skeleton_limits is None:
            return {'status': 'FAIL', 'reason': '非人形主骨架阈值无效'}
        swarn, sfail = skeleton_limits
        diff = abs(skeleton_height / height - 1.0)
        skeleton_status = 'FAIL' if diff > sfail else 'WARN' if diff > swarn else 'PASS'
        result.update(primary_skeleton_height=skeleton_height,
                      skeleton_to_body_relative_deviation=diff,
                      skeleton_body_status=skeleton_status,
                      skeleton_warning_threshold=swarn,
                      skeleton_failure_threshold=sfail,
                      interpretation='非人形主骨架必须按原本主体几何定位；整体缩放不会修复骨架与网格的相对高度不一致。禁止用骨骼拉伸凑身高。')
        result['status'] = ('FAIL' if 'FAIL' in (body_status, skeleton_status)
                            else 'WARN' if 'WARN' in (body_status, skeleton_status) else 'PASS')
    return result
