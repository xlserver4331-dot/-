"""Heuristic text-only scan of editable .vmdl sources (NOT an AG2 validator)."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vmdl", required=True, help="Text-form ModelDoc .vmdl; compiled .vmdl_c unsupported")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    source = Path(args.vmdl)
    if source.suffix.lower() != ".vmdl":
        ap.error("只接受未编译的可读 .vmdl 文件（不支持二进制 .vmdl_c）")
    payload = source.read_bytes()
    if b"\x00" in payload:
        ap.error("含有 NUL 字节：文件可能不是文本 ModelDoc 资源")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        ap.error(f"无法作为 UTF-8 文本读取：{exc}")
    tokens = ["AnimGraph2List", "NmSkeletonList", "DefaultAnimGraph2", "worldmodel.vnmgraph", "viewmodel.vnmskel", "worldmodel.vnmskel", "wpnPivot", "root_motion"]
    present = {token: token in text for token in tokens}
    deprecated = {token: text.count(token) for token in [".vanmgrph", "anim_graph_name", "animsets/animset_"]}
    result = {
        "source": str(source),
        "status": "HINTS_ONLY",
        "checked_kind": "editable_text_vmdl",
        "present_tokens": present,
        "deprecated_tokens": deprecated,
        "required_next_steps": ["ModelDoc 重新编译", "检查输出资源依赖", "在玩家实体上验证 AG2 动画", "逐条检查 Physics / Hitbox"],
        "note": "存在字符串不等于节点结构正确；缺失字符串可能来自 include 等引用。勿据此判定成功或自动编辑文本。"
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hints -> {out}")


if __name__ == "__main__":
    main()
