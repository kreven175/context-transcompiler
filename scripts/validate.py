#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — 零依赖的输出契约校验器

两层校验：
  1. 结构层：对 schemas/transcompile.v1.schema.json 做 JSON Schema 子集校验
     （type / required / properties / additionalProperties / enum /
      minimum / maximum / maxLength / minItems / items）
  2. 业务层：Schema 表达不了但必须成立的规则，例如
     - L1.text 必须与 L0 逐字一致
     - span 指向的文本必须与 hotspot.text 一致
     - confidence < 0.6 时 escalation_needed 必须为 true
     - friction_band 与 friction_score 的分带必须一致

用法：
  python3 validate.py --file result.json
  python3 validate.py --file result.json --quiet     # 只看退出码
  cat result.json | python3 validate.py

退出码：0 通过 · 1 校验失败 · 2 参数或文件错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

__version__ = "1.0.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.normpath(
    os.path.join(HERE, "..", "schemas", "transcompile.v1.schema.json")
)

FRICTION_BANDS = [(0, 24, "low"), (25, 49, "moderate"), (50, 74, "high"), (75, 100, "severe")]

TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


# ---------------------------------------------------------------------------
# JSON Schema 子集校验
# ---------------------------------------------------------------------------

def _type_ok(value: Any, expected: Any) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    for t in types:
        py = TYPE_MAP.get(t)
        if py is None:
            continue
        # JSON 里 true/false 是 bool，但 bool 在 Python 里是 int 的子类
        if t in ("number", "integer") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate_schema(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    errors: List[str] = []

    if "type" in schema and not _type_ok(instance, schema["type"]):
        errors.append(f"{path}: 类型应为 {schema['type']}，实际为 {type(instance).__name__}")
        return errors  # 类型不对，后续检查无意义

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: 值 {instance!r} 不在允许集合 {schema['enum']} 内")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} 小于最小值 {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} 大于最大值 {schema['maximum']}")

    if isinstance(instance, str) and "maxLength" in schema and len(instance) > schema["maxLength"]:
        errors.append(f"{path}: 长度 {len(instance)} 超过上限 {schema['maxLength']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: 至少需要 {schema['minItems']} 项，实际 {len(instance)} 项")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                errors += validate_schema(item, item_schema, f"{path}[{i}]")

    if isinstance(instance, dict):
        props: Dict[str, Any] = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: 缺少必填字段 '{key}'")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{path}: 出现未定义字段 '{key}'")
        for key, value in instance.items():
            if key in props:
                errors += validate_schema(value, props[key], f"{path}.{key}")

    return errors


# ---------------------------------------------------------------------------
# 业务规则
# ---------------------------------------------------------------------------

def band_of(score: int) -> str:
    for lo, hi, code in FRICTION_BANDS:
        if lo <= score <= hi:
            return code
    return "severe"


def validate_rules(doc: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """返回 (errors, warnings)。"""
    errors: List[str] = []
    warnings: List[str] = []

    diag = doc.get("diagnosis", {}) or {}
    meta = doc.get("meta", {}) or {}
    ladder = doc.get("ladder", {}) or {}
    mr = doc.get("machine_readable")

    # --- 分带一致性 ------------------------------------------------------
    score = diag.get("friction_score")
    band = diag.get("friction_band")
    if isinstance(score, int) and band:
        expected = band_of(score)
        if expected != band:
            errors.append(
                f"diagnosis: friction_score={score} 应落在 '{expected}' 带，但标为 '{band}'"
            )

    # --- 子分之和 --------------------------------------------------------
    subs = diag.get("subscores") or {}
    if subs and isinstance(diag.get("raw_score"), int):
        total = sum(v for v in subs.values() if isinstance(v, (int, float)))
        if abs(total - diag["raw_score"]) > 1.5:
            warnings.append(
                f"diagnosis: raw_score={diag['raw_score']} 与子分之和 {total:.1f} 不符"
                "（若因单维极值或密度归一导致，请在 caveats 说明）"
            )

    # --- 保真 + 损耗 = 100 ----------------------------------------------
    fid, loss = diag.get("fidelity_at_target"), diag.get("loss_at_target")
    if isinstance(fid, int) and isinstance(loss, int) and fid + loss != 100:
        errors.append(f"diagnosis: fidelity_at_target({fid}) + loss_at_target({loss}) ≠ 100")

    # --- L1 正文必须与 L0 逐字一致 ---------------------------------------
    l0 = ladder.get("L0")
    l1 = ladder.get("L1")
    if isinstance(l0, str) and isinstance(l1, dict) and isinstance(l1.get("text"), str):
        if l1["text"] != l0:
            errors.append(
                "ladder.L1.text 与 L0 不一致：L1 注释轨不得改动正文任何一个字"
                f"（L0 {len(l0)} 字，L1 {len(l1['text'])} 字）"
            )

    # --- span 与 text 对齐 ------------------------------------------------
    for i, h in enumerate(diag.get("hotspots") or []):
        span, text = h.get("span"), h.get("text")
        if not span:
            continue
        s, e = span.get("start"), span.get("end")
        if isinstance(s, int) and isinstance(e, int) and e <= s:
            errors.append(f"diagnosis.hotspots[{i}]: span.end({e}) 必须大于 span.start({s})")
        if isinstance(l0, str) and isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= len(l0):
            actual = l0[s:e]
            if actual != text:
                errors.append(
                    f"diagnosis.hotspots[{i}]: span[{s}:{e}] 指向 {actual!r}，"
                    f"但 text 为 {text!r} —— 偏移量错位会导致 Web 端高亮全错"
                )

    # --- machine_readable ------------------------------------------------
    target = meta.get("ladder_target")
    audience = meta.get("audience")
    if (target == "L5" or audience == "ai-agent") and not mr:
        errors.append(
            f"meta.ladder_target={target} / audience={audience} 要求填写 machine_readable"
        )
    if isinstance(mr, dict):
        conf = mr.get("confidence")
        if isinstance(conf, (int, float)) and conf < 0.6 and mr.get("escalation_needed") is not True:
            errors.append(
                f"machine_readable: confidence={conf} < 0.6 时 escalation_needed 必须为 true"
            )
        if not mr.get("evidence"):
            errors.append("machine_readable: evidence 不得为空——无证据的 stance 判定不允许输出")

    # --- 创作者建议 ------------------------------------------------------
    if meta.get("domain") in ("screenplay", "webnovel", "social") and not doc.get("creator_advice"):
        errors.append(
            f"meta.domain={meta['domain']} 要求至少一条 creator_advice"
        )

    # --- 低对抗受众的对外风险 --------------------------------------------
    low_conf_audiences = {"jp-business", "kr-business", "mena", "uk", "latam"}
    if audience in low_conf_audiences and target in ("L4", "L5"):
        caveats = " ".join((doc.get("confidence") or {}).get("caveats") or [])
        tracks_blob = json.dumps(doc.get("ladder", {}), ensure_ascii=False)
        has_reverse = any(k in doc.get("ladder", {}) for k in ("R1", "R2"))
        if not has_reverse and "对外" not in caveats and "R1" not in tracks_blob:
            warnings.append(
                f"受众 {audience} 的 confrontation 很低，但输出了 {target} 且没有 R1/R2 回复草稿。"
                "用户可能把功能化措辞直接转发出去——见 reference/05 §L4 的强制附加项。"
            )

    # --- trade_off 曲线 ---------------------------------------------------
    curve = ((doc.get("trade_off") or {}).get("curve")) or []
    for i, p in enumerate(curve):
        if isinstance(p.get("loss"), int) and isinstance(p.get("fidelity"), int):
            if p["loss"] + p["fidelity"] != 100:
                errors.append(f"trade_off.curve[{i}] ({p.get('level')}): loss + fidelity ≠ 100")

    # --- 短文本 -----------------------------------------------------------
    cc = meta.get("char_count")
    if isinstance(cc, int) and cc < 40 and isinstance(score, int):
        caveats = " ".join((doc.get("confidence") or {}).get("caveats") or [])
        if "过短" not in caveats and "短" not in caveats:
            warnings.append("文本不足 40 字却给出了总分，应在 caveats 注明分数不稳定")

    # --- 未执行预扫描 ------------------------------------------------------
    if meta.get("probe_executed") is False:
        caveats = " ".join((doc.get("confidence") or {}).get("caveats") or [])
        if "预扫描" not in caveats:
            warnings.append("probe_executed=false，应在 caveats 注明分数为人工估计")

    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="语境平抑器 · 输出契约校验器")
    ap.add_argument("--file", help="待校验的 JSON 文件；省略则读标准输入")
    ap.add_argument("--schema", default=DEFAULT_SCHEMA)
    ap.add_argument("--quiet", action="store_true", help="不打印，只用退出码")
    ap.add_argument("--strict", action="store_true", help="把警告也视为失败")
    ap.add_argument("--version", action="version", version=f"validate.py {__version__}")
    args = ap.parse_args(argv)

    try:
        if args.file:
            with open(args.file, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        else:
            doc = json.load(sys.stdin)
    except FileNotFoundError:
        print(f"[error] 找不到文件：{args.file}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[error] JSON 解析失败：{exc}", file=sys.stderr)
        return 2

    try:
        with open(args.schema, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except Exception as exc:  # pragma: no cover
        print(f"[error] 无法载入 Schema：{exc}", file=sys.stderr)
        return 2

    errors = validate_schema(doc, schema)
    rule_errors, warnings = validate_rules(doc)
    errors += rule_errors

    if not args.quiet:
        if errors:
            print(f"✗ 校验失败，{len(errors)} 个错误：\n")
            for e in errors:
                print(f"  ERROR  {e}")
        else:
            print("✓ 结构与业务规则校验通过")
        if warnings:
            print(f"\n{len(warnings)} 个警告：")
            for w in warnings:
                print(f"  WARN   {w}")

    if errors:
        return 1
    if warnings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
