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


def check_performance() -> List[str]:
    """
    长文本性能哨兵。批量模式要在几秒内扫完整本书，这条守住那个承诺。
    历史：早期 _dedupe 是 O(n^2)，15 万字要跑 31.8 秒；改成扫描线后降到 0.17 秒。
    阈值放在 5 秒，留足慢机器与 CI 的余量，但仍能在退回 O(n^2) 时立刻报警。
    """
    import time
    base = ("\u5f20\u603b\u5728\u4f1a\u4e0a\u5bf9\u5c0f\u674e\u8bf4\uff1a\u4f60\u8fd9\u4e2a\u65b9\u6848\u7684\u51fa\u53d1\u70b9\u662f\u597d\u7684\uff0c"
            "\u4e0d\u8fc7\u6211\u4eec\u56de\u5934\u518d\u6162\u6162\u5bf9\u9f50\u3002\u4ed6\u5728\u57ce\u95e8\u53e3\u6298\u4e86\u4e00\u679d\u67f3\uff0c\u6c5f\u6e56\u8def\u8fdc\u3002")
    text = base * 3000
    t0 = time.time()
    result = probe_mod.probe(text, audience_id="us-genz", target_level="L3", top=20)
    elapsed = time.time() - t0
    print(f"\n\u6027\u80fd\u54e8\u5175\uff1a{len(text):,} \u5b57 \u2192 {elapsed * 1000:,.0f}ms"
          f"\uff08\u70ed\u70b9 {result['hotspot_total']:,}\uff09")
    if elapsed > 5.0:
        return [f"15 \u4e07\u5b57\u626b\u63cf\u8017\u65f6 {elapsed:.1f}s\uff0c\u8d85\u8fc7 5s \u9608\u503c\u2014\u2014\u68c0\u67e5\u662f\u5426\u5f15\u5165\u4e86\u4e8c\u6b21\u65b9\u590d\u6742\u5ea6"]
    return []


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

    perf = check_performance()
    for w in perf:
        print(f"✗ 性能 {w}")
    failed += len(perf)

    print(f"\n{passed}/{len(cases)} 条用例通过"
          + ("，确定性与性能检查通过" if not det and not perf else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
