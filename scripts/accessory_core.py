"""Independent accessory config validation; no bpy required."""
from __future__ import annotations
import math
import re

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,63}$")
ALLOWED_MODES = {"rigid", "secondary_baked", "runtime_secondary_candidate"}


def validated_config(config):
    if not isinstance(config, dict) or not isinstance(config.get("accessories"),list):
        raise ValueError("accessories 配置必须有 accessories 数组")
    if not config["accessories"] and not config.get("no_accessories_confirmed",False):
        raise ValueError("没有装饰物时，必须确认 no_accessories_confirmed=true")
    seen_ids, seen_bones, seen_objects = set(), set(), set()
    for a in config["accessories"]:
        if not isinstance(a,dict):
            raise ValueError("accessory 必须为对象")
        ident, mode, anchor = a.get("id"),a.get("mode"),a.get("anchor_bone")
        if not isinstance(ident,str) or not NAME.fullmatch(ident) or ident in seen_ids:
            raise ValueError("装饰物 ID 重复或非法")
        seen_ids.add(ident)
        if mode not in ALLOWED_MODES:
            raise ValueError(f"{ident}: 非法 mode")
        if not isinstance(anchor,str) or not NAME.fullmatch(anchor):
            raise ValueError(f"{ident}: 非法 anchor_bone")
        meshes,bones = a.get("mesh_objects"),a.get("bones")
        if not isinstance(meshes,list) or not meshes or any(not isinstance(v,str) or not v for v in meshes):
            raise ValueError(f"{ident}: mesh_objects 不能为空")
        if any(v in seen_objects for v in meshes):
            raise ValueError("装饰物不能重复声明相同网格")
        seen_objects.update(meshes)
        if not isinstance(bones,list) or not bones:
            raise ValueError(f"{ident}: 必须为装饰物建立独立骨骼")
        if mode == "rigid" and len(bones)!=1:
            raise ValueError(f"{ident}: rigid 配件只需要 1 个辅助骨骼")
        if mode != "rigid" and len(bones)<2:
            raise ValueError(f"{ident}: 柔性配件建议至少 2 节骨骼")
        for b in bones:
            name = b.get("name") if isinstance(b,dict) else None
            if not isinstance(name,str) or not NAME.fullmatch(name) or name in seen_bones or name == anchor:
                raise ValueError("辅助骨骼名非法或跨装饰物重复")
            seen_bones.add(name)
            for key in ("head","tail"):
                p = b.get(key)
                if not isinstance(p,list) or len(p)!=3 or any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in p):
                    raise ValueError(f"{name}: {key} 必须为骨架局部坐标三元组")
            if math.dist(b["head"],b["tail"]) < 1e-5:
                raise ValueError(f"{name}: 辅助骨骼长度为 0")
        if a.get("weight_mode","manual") not in {"manual","rigid_auto","chain_linear_auto"}:
            raise ValueError("仅支持手绘权重或显式刚体自动绑定，不猜测柔性权重")
        if a.get("weight_mode") == "rigid_auto" and (mode != "rigid" or not a.get("allow_replace_weights",False)):
            raise ValueError("刚体自动权重仅限明确授权的刚性配件")
        if a.get("weight_mode") == "chain_linear_auto" and (mode == "rigid" or len(bones)<2 or
              not (a.get("allow_replace_weights",False) and a.get("approved_chain_skinning",False))):
            raise ValueError("柔性装饰物自动线性蒙皮需要至少两节骨骼，及两项明确授权开关")
    return config
