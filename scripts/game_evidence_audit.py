"""Conservative game screenshot/log triage. Results are only flags for review.

Image regression does not prove/deny rig, AG2, hitbox or physics correctness.
This script never reaches into CS2 process memory or external services.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LOG_SIGNATURES = {
    "MISSING_MODEL": re.compile(r"(?:fail(?:ed)? to load|missing|not found).{0,90}(?:\.vmdl|model)", re.I),
    "MISSING_MATERIAL": re.compile(r"(?:fail(?:ed)? to load|missing|not found).{0,90}(?:\.vmat|material|texture)", re.I),
    "ANIMGRAPH_WARNING": re.compile(r"(?:error|failed|incompatib|not found).{0,100}(?:animgraph|\.vnmgraph|skeleton|\.vnmskel)", re.I),
    "RESOURCE_ERROR": re.compile(r"(?:resource|precache|addon).{0,90}(?:failed|error|missing)", re.I),
}


def audit_logs(files: list[tuple[Path, int]], max_bytes=2_000_000):
    matches = []
    for path, offset in files:
        if not path.is_file():
            continue
        with path.open("rb") as f:
            f.seek(min(max(0, offset), path.stat().st_size))
            contents = f.read(max_bytes).decode("utf-8", "replace")
        for line_no, line in enumerate(contents.splitlines(), 1):
            for category, pattern in LOG_SIGNATURES.items():
                if pattern.search(line):
                    matches.append({"category": category, "path": str(path),
                                    "new_line_index": line_no, "text": line[:240]})
                    if len(matches) >= 40:
                        return {"status": "WARN_POSSIBLE_ENGINE_ERRORS", "matches": matches, "truncated": True}
    return {"status": "WARN_POSSIBLE_ENGINE_ERRORS" if matches else "NO_MATCHES_NOT_A_PASS",
            "matches": matches, "truncated": False}


def crop_image(img, ratios):
    if not isinstance(ratios, list) or len(ratios) != 4 or any(not isinstance(x, (int, float)) for x in ratios):
        raise ValueError("crop_relative 需要 [left,top,right,bottom] 四个 0~1 数字")
    x0, y0, x1, y1 = ratios
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("crop_relative 的宽高必须大于零，范围必须在 0~1")
    return img.crop((round(x0*img.width), round(y0*img.height), round(x1*img.width), round(y1*img.height)))


def audit_visual(report: dict, baseline: dict, base_dir: Path):
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        return {"status": "PENDING_MISSING_PILLOW", "checks": []}
    checks = []
    references = baseline.get("steps", {})
    if not isinstance(references, dict):
        raise ValueError("baseline.steps 必须是对象")
    for item in report.get("test_results", []):
        if not item.get("screenshot"):
            continue
        ident = item["id"]
        conf = references.get(ident)
        if not conf:
            checks.append({"id": ident, "status": "NO_REFERENCE_PENDING_REVIEW"})
            continue
        shot = Path(item["screenshot"])
        ref = Path(conf.get("reference_image", ""))
        ref = ref if ref.is_absolute() else base_dir / ref
        if not shot.is_file() or not ref.is_file():
            checks.append({"id": ident, "status": "PENDING_MISSING_IMAGE"})
            continue
        with Image.open(shot) as raw_img, Image.open(ref) as raw_ref:
            img, expected = raw_img.convert("RGB"), raw_ref.convert("RGB")
            if img.size != expected.size:
                checks.append({"id": ident, "status": "WARN_RESOLUTION_CHANGED",
                               "observed": img.size, "reference": expected.size})
                continue
            ratios = conf.get("crop_relative", [0, 0, 1, 1])
            img = crop_image(img, ratios)
            expected = crop_image(expected, ratios)
            score = sum(ImageStat.Stat(ImageChops.difference(img, expected)).mean) / 3
            threshold = float(conf.get("max_mean_pixel_delta", 35))
            if not 0 <= threshold <= 255:
                raise ValueError("max_mean_pixel_delta 应为 0~255")
            checks.append({"id": ident, "status": "WARN_VISUAL_REGRESSION" if score > threshold else "NO_REGRESSION_DETECTED_NOT_VERIFIED",
                           "mean_pixel_delta": round(score, 3), "threshold": threshold,
                           "reference_image": str(ref)})
    return {"status": "WARN_REVIEW" if any(c["status"].startswith("WARN") for c in checks) else "PENDING_HUMAN_REVIEW",
            "checks": checks,
            "note": "像素差只能做场景固定的回归提醒；无法自动识别真实穿模、T-pose 或命中盒。"}


def main():
    ap = argparse.ArgumentParser(description="CS2 游戏测试截图回归与新日志线索检查（不代表通过）")
    ap.add_argument("--report", required=True)
    ap.add_argument("--baseline", help="可选每动作参考图配置")
    ap.add_argument("--log", action="append", default=[], help="要扫描的本地 CS2/插件日志路径（仅当前文件，历史日志谨慎）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    result = {"visual": {"status": "PENDING_NO_REFERENCE"},
              "logs": audit_logs([(Path(x), 0) for x in args.log]) if args.log else {"status": "PENDING_NO_LOGS"},
              "conclusion": "REQUIRES_HUMAN_ENGINE_REVIEW"}
    if args.baseline:
        base = Path(args.baseline).expanduser().resolve()
        result["visual"] = audit_visual(report, json.loads(base.read_text(encoding="utf-8")), base.parent)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evidence audit ->", args.out, result["conclusion"])


if __name__ == "__main__":
    main()
