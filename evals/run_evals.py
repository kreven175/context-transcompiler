#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_evals.py — 评分内核的回归测试

这不是模型质量评测，是**确定性内核的回归测试**：
词典、正则与评分公式改动后，跑这个脚本确认校准没有漂移。

每条用例断言的是**相对关系与区间**，不是精确值——
分数的意义在比较，硬编码精确值会让每次调参都变成大规模改测试。

用法：
  python3 evals/run_evals.py
  python3 evals/run_evals.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import probe as probe_mod  # noqa: E402

CASES_PATH = os.path.join(ROOT, "evals", "cases.jsonl")


def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    return probe_mod.probe(
        case["text"],
        audience_id=case["audience"],
        target_level=case.get("target", "L4"),
    )


def check(case: Dict[str, Any], result: Dict[str, Any],
          all_results: Dict[str, Dict[str, Any]]) -> List[str]:
    e = case.get("expect", {})
    sc = result["scoring"]
    detail = result["evidence_detail"]
    fails: List[str] = []

    fr = sc["friction_score"]
    if "friction_min" in e and fr < e["friction_min"]:
        fails.append(f"friction {fr} < 下限 {e['friction_min']}")
    if "friction_max" in e and fr > e["friction_max"]:
        fails.append(f"friction {fr} > 上限 {e['friction_max']}")
    if "band" in e and sc["friction_band"] != e["band"]:
        fails.append(f"band 应为 {e['band']}，实际 {sc['friction_band']}")
    if "peak_dimension" in e and sc["peak_dimension"] != e["peak_dimension"]:
        fails.append(f"peak 维应为 {e['peak_dimension']}，实际 {sc['peak_dimension']}")

    for dim, lo in (e.get("subscore_min") or {}).items():
        if sc["subscores"].get(dim, 0) < lo:
            fails.append(f"子分 {dim}={sc['subscores'].get(dim)} < 下限 {lo}")
    for dim, hi in (e.get("subscore_max") or {}).items():
        if sc["subscores"].get(dim, 0) > hi:
            fails.append(f"子分 {dim}={sc['subscores'].get(dim)} > 上限 {hi}")

    classes = {h["class"] for h in result["candidate_hotspots"]}
    for cls in e.get("hotspot_classes_include", []):
        if cls not in classes:
            fails.append(f"缺少 {cls} 类热点（实际类别：{sorted(classes) or '无'}）")

    texts = " ".join(h["text"] for h in result["candidate_hotspots"])
    for frag in e.get("hotspot_text_includes", []):
        if frag not in texts:
            fails.append(f"未命中片段 {frag!r}")

    if "script" in e and detail["ellipsis"].get("script") != e["script"]:
        fails.append(f"脚本判定应为 {e['script']}，实际 {detail['ellipsis'].get('script')}")
    if e.get("zero_subject_skipped") and detail["ellipsis"].get("zero_subject_heuristic_applied"):
        fails.append("非中文文本仍应用了零主语启发式")

    ab = sc.get("abrasion_score", 0)
    if "abrasion_min" in e and ab < e["abrasion_min"]:
        fails.append(f"abrasion {ab} < 下限 {e['abrasion_min']}")
    if "abrasion_max" in e and ab > e["abrasion_max"]:
        fails.append(f"abrasion {ab} > 上限 {e['abrasion_max']}")
    if "directness_min" in e and sc.get("directness_index", 0) < e["directness_min"]:
        fails.append(f"directness {sc.get('directness_index')} < 下限 {e['directness_min']}")

    if e.get("too_short") and not result["meta"].get("too_short_for_scoring"):
        fails.append("未标记为过短文本")

    # 跨用例关系
    other_id = e.get("lower_than")
    if other_id and other_id in all_results:
        other = all_results[other_id]["scoring"]["friction_score"]
        if fr >= other:
            fails.append(f"friction {fr} 应低于 {other_id} 的 {other}")
    other_id = e.get("lower_abrasion_than")
    if other_id and other_id in all_results:
        other = all_results[other_id]["scoring"].get("abrasion_score", 0)
        if ab >= other:
            fails.append(f"abrasion {ab} 应低于 {other_id} 的 {other}")
    close = e.get("close_to")
    if close and close["case"] in all_results:
        other = all_results[close["case"]]["scoring"]["friction_score"]
        if abs(fr - other) > close["tolerance"]:
            fails.append(
                f"friction {fr} 与 {close['case']} 的 {other} 相差 {abs(fr-other)}，"
                f"超出容差 {close['tolerance']}"
            )
    return fails


def check_determinism(cases: List[Dict[str, Any]]) -> List[str]:
    """同一输入必须给出完全相同的结果——可复现性是本内核存在的理由之一。"""
    fails = []
    for case in cases[:4]:
        a = json.dumps(run_case(case), ensure_ascii=False, sort_keys=True)
        b = json.dumps(run_case(case), ensure_ascii=False, sort_keys=True)
        if a != b:
            fails.append(f"{case['id']}：两次运行结果不一致")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    with open(CASES_PATH, "r", encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]

    results: Dict[str, Dict[str, Any]] = {}
    for case in cases:
        results[case["id"]] = run_case(case)

    passed = failed = 0
    for case in cases:
        r = results[case["id"]]
        fails = check(case, r, results)
        sc = r["scoring"]
        mark = "✓" if not fails else "✗"
        line = (f"{mark} {case['id']:24s} friction={sc['friction_score']:3d} "
                f"{sc['friction_band']:8s} peak={sc['peak_dimension']:14s}")
        if sc.get("abrasion_score"):
            line += f" abrasion={sc['abrasion_score']:3d}"
        print(line)
        if args.verbose:
            print(f"    {case['note']}")
            print(f"    subscores={ {k: v for k, v in sc['subscores'].items() if v} }")
        for f in fails:
            print(f"    ! {f}")
        passed += not fails
        failed += bool(fails)

    det = check_determinism(cases)
    for d in det:
        print(f"✗ 确定性 {d}")
    failed += len(det)

    print(f"\n{passed}/{len(cases)} 条用例通过" + ("，确定性检查通过" if not det else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
