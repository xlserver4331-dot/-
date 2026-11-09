"""Ask the user how to size the *body* BEFORE size audit or model changes.

Changes only an explicitly selected *.local.json height profile, with backup.
No mesh, armature, CS2 game file or addon is touched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from height_policy_core import ALLOWED_MODES, positive, validate_height_choice

LABELS = {
    'match_agent': '人体主体高度匹配本机默认 CS2 探员（不匹配四肢骨长）',
    'custom_target': '指定另一目标主体高度（只允许全身等比例缩放）',
    'uniform_scale': '指定全身 XYZ 相同的缩放倍数（需要原始主体高度基准）',
    'keep_original': '保持原始主体高度不变（不缩放）',
}


def _ask_choice(question, options):
    print(question)
    for index, mode in enumerate(options, 1):
        print(f'  {index}. {LABELS[mode]}')
    while True:
        reply = input('请选择编号：').strip()
        if reply.isdigit() and 1 <= int(reply) <= len(options):
            return options[int(reply) - 1]
        print('选择无效；请重新输入。')


def _ask_positive(label, default=None):
    while True:
        suffix = f' [{default}]' if positive(default) else ''
        raw = input(f'{label}{suffix}：').strip()
        number = positive(default if not raw else raw)
        if number is not None:
            return number
        print('请输入在相同 Blender/Source2 标定单位下的正数，不要猜官方身高。')


def build_choice(profile, *, model_type=None, mode=None, reference_height=None,
                 original_body_height=None, target_height=None, uniform_scale=None,
                 interactive=False, confirmed=False):
    updated = dict(profile)
    kind = model_type or updated.get('model_type')
    if interactive:
        current = kind or '未设置'
        print(f'\n【必填选择：尺寸检测之前】当前角色分类：{current}')
        reply = input('角色类别 1=人形、2=非人形（直接回车保持当前分类）：').strip()
        if reply:
            kind = {'1': 'humanoid', '2': 'nonhumanoid'}.get(reply)
    if kind not in ALLOWED_MODES:
        raise ValueError('请先选择角色类别 humanoid 或 nonhumanoid')
    updated['model_type'] = kind
    updated['exclude_accessories_from_height'] = True

    if mode is None and interactive:
        mode = _ask_choice('选择主体高度策略（头发、帽子、角、翅膀、武器等装饰物不参与计高）：',
                           ALLOWED_MODES[kind])
    if mode not in ALLOWED_MODES[kind]:
        raise ValueError(f'请明确指定 {kind} 可用的高度策略：{ALLOWED_MODES[kind]}')

    previous = updated.get('height_choice') or {}
    choice = {'mode': mode, 'confirmed_by_user': bool(confirmed),
              'principle': 'uniform_xyz_only; preserve_original_limb_proportions'}
    if mode == 'match_agent':
        ref = reference_height if reference_height is not None else updated.get('agent_reference_body_height')
        if interactive:
            print('参考值须从当前本机默认探员主体（排除装饰物）测量，且与当前模型上轴/单位一致。')
            ref = _ask_positive('请输入测得的默认探员主体高度', ref)
        if positive(ref) is not None:
            updated['agent_reference_body_height'] = positive(ref)
    elif mode == 'custom_target':
        target = target_height if target_height is not None else previous.get('target_body_height')
        if interactive:
            target = _ask_positive('你希望主体达到的目标高度', target)
        if positive(target) is not None:
            choice['target_body_height'] = positive(target)
    else:
        original = original_body_height if original_body_height is not None else previous.get('original_body_height')
        if interactive:
            print('原始高度必须从未改动的完整原模型测量，装饰物不能计入。')
            original = _ask_positive('原始主体高度', original)
        if positive(original) is not None:
            choice['original_body_height'] = positive(original)
        if mode == 'uniform_scale':
            scale = uniform_scale if uniform_scale is not None else previous.get('uniform_scale_factor')
            if interactive:
                scale = _ask_positive('全身统一缩放倍数（例如 0.9 / 1.15）', scale)
            if positive(scale) is not None:
                choice['uniform_scale_factor'] = positive(scale)

    if interactive:
        print('\n方案回顾：', LABELS[mode])
        print('强制约束：仅全局等比例缩放；原四肢比例、关节位置、UV/权重不通过局部拉伸凑高。')
        print('装饰物只排除主体高度计算，仍参与完整视觉包围盒、权重和碰撞审计。')
        confirmed = input('确认保存这项选择？输入 YES：').strip() == 'YES'
    if not confirmed:
        raise ValueError('未获得明确用户确认，不能开始主体高度检测')
    choice['confirmed_by_user'] = True
    choice['confirmed_at_utc'] = datetime.now(timezone.utc).isoformat()
    updated['height_choice'] = choice
    error, target, mode = validate_height_choice(updated)
    if error:
        raise ValueError(error)
    return updated, {'model_type': kind, 'mode': mode, 'target_body_height': target,
                     'note': '推荐值不执行缩放；部署前需人工统一缩放并复检四肢和双视角动作。'}


def save_local_profile(path, updated):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or not path.name.endswith('.local.json'):
        raise ValueError('只允许保存到已存在的 *.local.json 副本，不覆盖 *.example.json 模板')
    backup = path.with_name(path.stem + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    shutil.copy2(path, backup)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.height-choice-', suffix='.tmp', delete=False) as out:
        tmp = Path(out.name)
        json.dump(updated, out, ensure_ascii=False, indent=2)
        out.write('\n')
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return backup


def configure_profile(path, *, interactive=False, save=False, **options):
    path = Path(path).expanduser().resolve()
    if save and not path.name.endswith('.local.json'):
        raise ValueError('请先复制配置模板为 *.local.json，不能覆盖 *.example.json')
    profile = json.loads(path.read_text(encoding='utf-8'))
    updated, summary = build_choice(profile, interactive=interactive, **options)
    if save:
        summary['backup_file'] = str(save_local_profile(path, updated))
        summary['saved_profile'] = str(path)
    return summary


def main():
    p = argparse.ArgumentParser(description='首先询问用户选择主体高度；只保存明确确认的本地配置')
    p.add_argument('--profile', required=True)
    p.add_argument('--model-type', choices=list(ALLOWED_MODES))
    p.add_argument('--mode', choices=sorted(LABELS))
    p.add_argument('--reference-height', type=float)
    p.add_argument('--original-body-height', type=float)
    p.add_argument('--target-height', type=float)
    p.add_argument('--uniform-scale', type=float)
    p.add_argument('--confirm', action='store_true', help='非交互使用时表示用户已明确选择并授权保存该配置')
    p.add_argument('--save', action='store_true', help='将选择写入 *.local.json 并保存旧配置备份')
    args = p.parse_args()
    interactive = args.mode is None
    if interactive and not sys.stdin.isatty():
        p.error('当前不是交互终端。请在终端运行交互设置，或提供 --mode ... --confirm --save')
    try:
        summary = configure_profile(args.profile, interactive=interactive, save=args.save,
            model_type=args.model_type, mode=args.mode, reference_height=args.reference_height,
            original_body_height=args.original_body_height, target_height=args.target_height,
            uniform_scale=args.uniform_scale, confirmed=args.confirm)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        p.exit(2, f'高度选择未保存：{exc}\n')


if __name__ == '__main__':
    main()
