#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe.py — 语境平抑器的确定性预扫描器

职责边界（重要）：
  本脚本只负责**可数的部分**——词典命中、正则模式、零主语率、字符级 span 偏移量。
  语义判断（这句话到底是不是拒绝、这个意象在这里起什么作用）由模型完成。
  输出的 hotspots 是**候选**，不是结论。

为什么需要它：
  1. 热力图需要精确到字符的 span，人工估算必错；
  2. 同一文本重复分析时分数可复现；
  3. Web 版（ContextBridge）与 Skill 版共用同一套评分内核，结果可对齐。

用法：
  python3 probe.py --text "..." --audience de-business --target-level L4
  python3 probe.py --text-file input.txt --audience us-genz --format md
  cat input.txt | python3 probe.py --audience global-english

零第三方依赖，仅用标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

__version__ = "1.0.0"

HERE = os.path.dirname(os.path.abspath(__file__))
LEXICON_DIR = os.path.join(HERE, "lexicon")
DATA_DIR = os.path.join(HERE, "data")

# ---------------------------------------------------------------------------
# 评分常数（与 reference/03-friction-scoring.md 保持一致，改动需同步文档与 Web 版）
# ---------------------------------------------------------------------------

SUBSCORE_CAPS = {
    "presupposition": 25.0,
    "subtext": 25.0,
    "motif": 20.0,
    "hierarchy": 15.0,
    "ellipsis": 15.0,
}

LADDER_LOSS_WEIGHT = {
    "L0": 0.00,
    "L1": 0.05,
    "L2": 0.15,
    "L3": 0.35,
    "L4": 0.75,
    "L5": 0.95,
}

# 反向轨（语境收敛）。R 轨不删减实质内容，只改变包装，因此损耗为 0、
# 阻抗不下降——反向模式真正的度量是 Abrasion 得罪风险，见 reference/03 §6。
REVERSE_LEVELS = {"R1", "R2", "R3"}

# 各级别相对 L0 的剩余阻抗系数
LADDER_FRICTION_FACTOR = {
    "L0": 1.00,
    "L1": 0.80,
    "L2": 0.67,
    "L3": 0.42,
    "L4": 0.27,
    "L5": 0.10,
}

# 单维极值权重：某一维顶格时，即使其余维为 0，理解也可能完全失败。
# 纯求和会稀释这种风险（S=25 的「字面肯定实为否定」比 5 个中等意象危险得多），
# 因此 Raw 取「广度之和」与「加权单维极值」的较大者。
# 权重体现「该维顶格 ⇒ 理解破裂」的程度：预设缺失与潜台词反转最致命，
# 零主语率高在中文里很常见，不应单独把分数推高。
PEAK_WEIGHTS = {
    "presupposition": 0.75,
    "subtext": 0.75,
    "motif": 0.55,
    "hierarchy": 0.45,
    "ellipsis": 0.45,
}

FRICTION_BANDS = [
    (0, 24, "low", "通行"),
    (25, 49, "moderate", "轻阻"),
    (50, 74, "high", "高阻"),
    (75, 100, "severe", "闭塞"),
]

SHORT_TEXT_THRESHOLD = 40  # 低于此字数不报总分


# ---------------------------------------------------------------------------
# 载入
# ---------------------------------------------------------------------------

def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_lexicons(lexicon_dir: str = LEXICON_DIR) -> Dict[str, Dict[str, Any]]:
    names = ("hedges", "motifs", "face_power", "ellipsis", "presupposition", "directness")
    out: Dict[str, Dict[str, Any]] = {}
    for name in names:
        path = os.path.join(lexicon_dir, f"{name}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"缺少词典文件：{path}")
        out[name] = _load_json(path)
    return out


def load_audiences(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    path = path or os.path.join(DATA_DIR, "audiences.json")
    blob = _load_json(path)
    return {p["id"]: p for p in blob.get("profiles", [])}


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------

def _scan_terms(text: str, entries: List[Dict[str, Any]], default_class: str) -> List[Dict[str, Any]]:
    """字面匹配。重叠命中保留较长者。"""
    hits: List[Dict[str, Any]] = []
    for entry in entries:
        term = entry.get("term")
        if not term:
            continue
        # variants 覆盖同一意象的常见变形（折柳 / 折了一枝柳）。
        # 词典是字面匹配，召回必然不全——未收录的变形由模型在语义层补齐。
        surfaces = [term] + [v for v in entry.get("variants", []) if v]
        for surface in surfaces:
            start = 0
            while True:
                idx = text.find(surface, start)
                if idx == -1:
                    break
                hits.append({
                    "span": {"start": idx, "end": idx + len(surface)},
                    "text": surface,
                    "canonical": term,
                    "class": entry.get("class", default_class),
                    "strength": int(entry.get("strength", 3)),
                    "gloss": entry.get("gloss") or entry.get("intended", ""),
                    "literal": entry.get("literal", ""),
                    "intended": entry.get("intended", ""),
                    "trap": entry.get("trap", ""),
                    "zone": entry.get("zone", ""),
                    "tags": entry.get("tags", []),
                    "lang": entry.get("lang", "zh"),
                    "source": "lexicon",
                })
                start = idx + 1
    return hits


def _scan_patterns(text: str, patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for pat in patterns:
        try:
            rx = re.compile(pat["regex"])
        except re.error as exc:  # pragma: no cover - 词典写错时的保护
            print(f"[warn] 正则无效，已跳过：{pat.get('regex')} ({exc})", file=sys.stderr)
            continue
        for m in rx.finditer(text):
            hits.append({
                "span": {"start": m.start(), "end": m.end()},
                "text": m.group(0),
                "class": pat.get("class", "HIERARCHY"),
                "strength": int(pat.get("strength", 3)),
                "gloss": pat.get("gloss", ""),
                "literal": "",
                "intended": "",
                "trap": "",
                "zone": "pattern",
                "tags": [],
                "lang": "zh",
                "source": "pattern",
            })
    return hits


def _dedupe(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同一区间内保留最长、其次强度最高的命中；完全相同的 span+class 去重。"""
    hits = sorted(
        hits,
        key=lambda h: (h["span"]["start"], -(h["span"]["end"] - h["span"]["start"]), -h["strength"]),
    )
    kept: List[Dict[str, Any]] = []
    for h in hits:
        s, e = h["span"]["start"], h["span"]["end"]
        swallowed = False
        for k in kept:
            ks, ke = k["span"]["start"], k["span"]["end"]
            if ks <= s and e <= ke and k["class"] == h["class"]:
                swallowed = True
                break
        if not swallowed:
            kept.append(h)
    return kept


# ---------------------------------------------------------------------------
# 零主语率
# ---------------------------------------------------------------------------

# 「名词主语 + 谓词标记」的结构性证据。仅靠人称代词判断主语会把
# 「合同将于本周五签署」这类完全显性的句子误判为零主语，是早期版本的主要误报源。
_NP_PREDICATE = re.compile(
    r"^[^，。；！？、：\s]{2,6}(将|会|为|是|于|按|应|须|已|可|由|在|有|都|定为|系|属于|需要|包括|采用)"
)

ZERO_SUBJECT_BASELINE = 0.5  # 中文里约半数小句省略主语属正常，只有超出部分才计入阻抗

# M（文化意象）与 P（共识预设）是计数型子分，不归一会低估「短而密」的文本：
# 60 字里出现 3 个不可直译意象，远比 3000 字里出现 3 个难读。
# 因此按 500 字参考窗归一，倍率钳制在 [1.0, 2.0]——只上抬短密文本，不惩罚长文本。
DENSITY_REF_CHARS = 500
DENSITY_MIN_CHARS = 120


def density_factor(char_count: int) -> float:
    return min(2.0, max(1.0, DENSITY_REF_CHARS / max(DENSITY_MIN_CHARS, char_count)))


def estimate_ellipsis_rate(text: str, lex: Dict[str, Any]) -> Tuple[float, int, int]:
    """
    启发式估算零主语率：把文本切成小句，统计**既无人称/机构主语标记、
    又不符合「名词主语 + 谓词标记」结构**的小句比例。

    这是粗略估计，不是句法分析。中文省略主语极常见且语法合法，
    比例高不代表写得差，只代表低语境受众需要自行补全的信息点多。
    因此调用方只把超出 ZERO_SUBJECT_BASELINE 的部分计入分数。
    """
    markers = lex["ellipsis"].get("subject_markers", {})
    subject_tokens = list(markers.get("pronouns", [])) + list(markers.get("org_terms", []))
    delims = lex["ellipsis"].get("clause_delimiters", ["。", "！", "？", "；", "\n", "，"])

    pattern = "[" + re.escape("".join(d for d in delims if len(d) == 1)) + "]"
    clauses = [c.strip() for c in re.split(pattern, text) if c.strip()]

    meaningful = [c for c in clauses if len(c) >= 4]
    if not meaningful:
        return 0.0, 0, len(clauses)

    zero_subject = 0
    for c in meaningful:
        has_token = any(tok in c for tok in subject_tokens)
        has_np = bool(_NP_PREDICATE.match(c))
        if not (has_token or has_np):
            zero_subject += 1

    return zero_subject / len(meaningful), zero_subject, len(meaningful)


# ---------------------------------------------------------------------------
# 子分计算
# ---------------------------------------------------------------------------

def _key(hit: Dict[str, Any]) -> str:
    """去重键：优先用词典原形，避免同一意象的不同变形被重复计数。"""
    return hit.get("canonical") or hit["text"]


_KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")


def detect_script(text: str) -> str:
    """
    零主语启发式与主语标记词都是按中文校准的，用在日/韩/拉丁文本上会系统性失真。
    这里做一个粗略的书写系统判定，非中文时跳过零主语估算并在 caveats 说明。
    """
    n = max(1, len(text))
    if len(_KANA.findall(text)) / n > 0.05:
        return "ja"
    if len(_HANGUL.findall(text)) / n > 0.05:
        return "ko"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    if cjk / n > 0.20:
        return "zh"
    if len(_LATIN_WORD.findall(text)) > 3:
        return "latin"
    return "unknown"


def compute_directness(text: str, hits: List[Dict[str, Any]],
                       lex: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    """
    直白度 0-1：直接否定/最后通牒/硬性要求越多、缓冲与面子语越少，越高。
    只在反向模式（把低语境文本发给高语境受众）下有意义。
    """
    d_hits = _scan_terms(text, lex["directness"]["entries"], "DIRECTNESS")
    d_hits = _dedupe(d_hits)

    weighted = 0.0
    for h in {_key(x): x for x in d_hits}.values():
        entry_weight = 0.6
        for e in lex["directness"]["entries"]:
            if e["term"] == (h.get("canonical") or h["text"]):
                entry_weight = float(e.get("weight", 0.6))
                break
        weighted += entry_weight

    softeners = len({_key(h) for h in hits if h["class"] in ("SUBTEXT", "FACE")})

    raw = weighted / (1.0 + weighted)              # 饱和到 (0,1)
    damp = 1.0 / (1.0 + 0.45 * softeners)          # 缓冲语越多，直白度越低
    return max(0.0, min(1.0, raw * damp)), d_hits


def compute_abrasion(directness_index: float, audience: Dict[str, Any]) -> int:
    """得罪风险 = 直白度 × 受众对直接否定的不耐受度。"""
    tolerance = float(audience.get("confrontation", 0.6))
    return int(round(100 * directness_index * (1.0 - tolerance)))


def _cap(value: float, key: str) -> float:
    return float(round(min(float(value), SUBSCORE_CAPS[key]), 1))


def compute_subscores(text: str, hits: List[Dict[str, Any]], lex: Dict[str, Any],
                      audience: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
    detail: Dict[str, Any] = {}

    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        by_class.setdefault(h["class"], []).append(h)

    # --- S · 潜台词背离度 -------------------------------------------------
    sub_hits = by_class.get("SUBTEXT", [])
    if sub_hits:
        max_strength = max(h["strength"] for h in sub_hits)
        n_unique = len({_key(h) for h in sub_hits})
        s_raw = max_strength * 4.0 + min(5.0, (n_unique - 1) * 1.5)
    else:
        max_strength, n_unique, s_raw = 0, 0, 0.0
    detail["subtext"] = {"max_strength": max_strength, "unique_hits": n_unique}

    # --- M · 文化意象负载 -------------------------------------------------
    motif_hits = by_class.get("MOTIF", [])
    idioms = {_key(h) for h in motif_hits if h.get("zone") == "idiom"}
    non_idioms = {_key(h) for h in motif_hits if h.get("zone") != "idiom"}
    dfactor = density_factor(len(text))
    m_raw = (4.0 * len(non_idioms) + 2.0 * len(idioms)) * dfactor
    detail["motif"] = {
        "unique_motifs": sorted(non_idioms),
        "unique_idioms": sorted(idioms),
        "density_factor": round(dfactor, 2),
    }

    # --- H · 位阶与面子编码 -----------------------------------------------
    hier_hits = by_class.get("HIERARCHY", [])
    face_hits = by_class.get("FACE", [])
    h_unique = {_key(h) for h in hier_hits}
    f_unique = {_key(h) for h in face_hits}
    h_raw = sum(3.0 * (h["strength"] / 5.0) for h in
                {_key(h): h for h in hier_hits}.values())
    h_raw += sum(2.0 * (h["strength"] / 5.0) for h in
                 {_key(h): h for h in face_hits}.values())
    detail["hierarchy"] = {
        "unique_hierarchy_markers": sorted(h_unique),
        "unique_face_markers": sorted(f_unique),
    }

    # --- E · 留白与省略率 -------------------------------------------------
    script = detect_script(text)
    if script == "zh":
        rate, zero_n, clause_n = estimate_ellipsis_rate(text, lex)
    else:
        # 非中文：零主语启发式不适用，只用显性留白证据
        rate, zero_n, clause_n = 0.0, 0, 0
    ell_hits = by_class.get("ELLIPSIS", [])
    ell_unique = {_key(h) for h in ell_hits}
    silence_markers = {_key(h) for h in ell_hits if "沉默" in (h.get("gloss") or "")}

    # 只有超出基线的零主语比例才计分：显性证据（留白词、沉默描写）是主要来源
    zero_excess = max(0.0, rate - ZERO_SUBJECT_BASELINE) / max(1e-6, 1.0 - ZERO_SUBJECT_BASELINE)
    e_raw = 3.0 * len(ell_unique) + 2.0 * len(silence_markers) + 7.0 * zero_excess
    detail["ellipsis"] = {
        "script": script,
        "zero_subject_heuristic_applied": script == "zh",
        "zero_subject_rate": round(rate, 3),
        "zero_subject_baseline": ZERO_SUBJECT_BASELINE,
        "zero_subject_excess": round(zero_excess, 3),
        "zero_subject_clauses": zero_n,
        "total_clauses": clause_n,
        "silence_markers": sorted(silence_markers),
        "ellipsis_lexicon_hits": sorted(ell_unique),
    }

    # --- P · 共识预设依赖 -------------------------------------------------
    presup_hits = by_class.get("PRESUPPOSITION", [])
    institution = {_key(h) for h in presup_hits if h.get("zone") == "institution"}
    cultural = {_key(h) for h in presup_hits if h.get("zone") != "institution"}
    p_institution = 3.5 * len(institution)
    p_cultural = 3.0 * len(cultural)

    # shared_ground 只折减文化类预设，不折减制度类（见 reference/04 §4）
    shared = float(audience.get("shared_ground", 0.0))
    p_cultural_eff = p_cultural * (1.0 - 0.6 * shared)
    p_raw = (p_institution + p_cultural_eff) * dfactor
    detail["presupposition"] = {
        "density_factor": round(dfactor, 2),
        "institution_markers": sorted(institution),
        "cultural_markers": sorted(cultural),
        "shared_ground_applied": shared,
        "p_institution": round(p_institution, 1),
        "p_cultural_before_discount": round(p_cultural, 1),
        "p_cultural_after_discount": round(p_cultural_eff, 1),
    }

    subscores = {
        "presupposition": _cap(p_raw, "presupposition"),
        "subtext": _cap(s_raw, "subtext"),
        "motif": _cap(m_raw, "motif"),
        "hierarchy": _cap(h_raw, "hierarchy"),
        "ellipsis": _cap(e_raw, "ellipsis"),
    }
    return subscores, detail


def band_of(score: int) -> Tuple[str, str]:
    for lo, hi, code, label in FRICTION_BANDS:
        if lo <= score <= hi:
            return code, label
    return "severe", "闭塞"


def compute_friction(subscores: Dict[str, float], audience: Dict[str, Any]) -> Dict[str, Any]:
    """
    阻抗 = 语用层（可被「读空气」能力部分弥补）+ 事实层（任何语用能力都补不回来）。

    这是本评分内核最关键的一条区分：
      * S/M/H/E 是**语用不透明**——高语境受众习惯于在字面之外取信息，
        面对含蓄表达的成本确实更低，因此随 explicitness 调制。
      * P 是**背景缺失**——日本读者再善于读空气，也不会知道「编制」是什么。
        因此 P 不随 explicitness 折减，只在 compute_subscores 里按 shared_ground
        对「文化类」预设打折（制度类永不打折）。
    早期版本把 P 一起调制，再用一个 +0.15×P 的补丁找补，既不可解释也补不够。
    """
    explicitness = float(audience.get("explicitness", 0.85))
    modulation = 0.55 + 0.45 * explicitness

    factual = subscores["presupposition"]
    pragmatic_dims = ("subtext", "motif", "hierarchy", "ellipsis")
    pragmatic = sum(subscores[k] for k in pragmatic_dims)

    breadth = min(100.0, pragmatic * modulation + factual)

    # 加权单维极值：防止「一维顶格、其余为零」的高危文本被求和稀释。
    # 极值同样区分语用/事实两层。
    peak_dim, peak_value = "", 0.0
    for key, score in subscores.items():
        base = (score / SUBSCORE_CAPS[key]) * 100.0 * PEAK_WEIGHTS[key]
        candidate = base if key == "presupposition" else base * modulation
        if candidate > peak_value:
            peak_dim, peak_value = key, candidate

    friction_f = min(100.0, max(breadth, peak_value))
    friction = int(round(max(0.0, friction_f)))

    notes: List[str] = []
    if peak_value > breadth:
        notes.append(
            f"单维极值规则生效：{peak_dim} 维顶格，阻抗由广度 {breadth:.0f} 提升至 {peak_value:.0f}"
        )
    if factual > 0 and explicitness <= 0.30:
        notes.append(
            f"受众虽为高语境（explicitness={explicitness}），但 P 维 {factual} 分未被折减："
            "共识预设的缺失无法靠读空气弥补。"
        )

    code, label = band_of(friction)
    return {
        "raw_score": int(round(min(100.0, pragmatic + factual))),
        "breadth_sum": int(round(breadth)),
        "pragmatic_before_modulation": round(pragmatic, 1),
        "factual_unmodulated": round(factual, 1),
        "peak_dimension": peak_dim,
        "peak_value": int(round(peak_value)),
        "friction_score": friction,
        "friction_band": code,
        "friction_band_label": label,
        "modulation_factor": round(modulation, 3),
        "notes": notes,
    }


def compute_tradeoff(friction_l0: int, motif_score: float) -> List[Dict[str, Any]]:
    curve = []
    for level in ("L0", "L1", "L2", "L3", "L4", "L5"):
        loss = int(round(100 * LADDER_LOSS_WEIGHT[level] * (0.4 + 0.6 * (motif_score / 20.0))))
        loss = max(0, min(100, loss))
        fric = int(round(friction_l0 * LADDER_FRICTION_FACTOR[level]))
        curve.append({
            "level": level,
            "friction": fric,
            "loss": loss,
            "fidelity": 100 - loss,
        })
    return curve


def recommend_level(curve: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    推荐停点：最大化 (100-friction) * fidelity，即同时兼顾可读性与保真。
    这是一个默认建议，最终应由使用场景决定（商务恒取 L4/L5）。
    """
    best = max(curve, key=lambda p: (100 - p["friction"]) * p["fidelity"])
    rationale = (
        f"在 {best['level']} 上阻抗降到 {best['friction']}，保真仍有 {best['fidelity']}，"
        f"两者乘积最大。商务/Agent 场景请忽略此建议，直接取 L4/L5。"
    )
    return best["level"], rationale


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def probe(text: str, audience_id: str = "global-english", target_level: str = "L4",
          lexicon_dir: str = LEXICON_DIR, audience_file: Optional[str] = None,
          top: int = 40) -> Dict[str, Any]:
    lex = load_lexicons(lexicon_dir)
    audiences = load_audiences(audience_file)

    if audience_id not in audiences:
        available = ", ".join(sorted(audiences))
        raise SystemExit(f"未知受众 '{audience_id}'。可用：{available}")
    audience = audiences[audience_id]

    if target_level not in LADDER_LOSS_WEIGHT and target_level not in REVERSE_LEVELS:
        raise SystemExit(
            f"target-level 必须是 L0..L5 或 R1..R3，收到 '{target_level}'"
        )

    hits: List[Dict[str, Any]] = []
    hits += _scan_terms(text, lex["hedges"]["entries"], "SUBTEXT")
    hits += _scan_terms(text, lex["motifs"]["entries"], "MOTIF")
    hits += _scan_terms(text, lex["face_power"]["entries"], "FACE")
    hits += _scan_terms(text, lex["ellipsis"]["entries"], "ELLIPSIS")
    hits += _scan_terms(text, lex["presupposition"]["entries"], "PRESUPPOSITION")
    hits += _scan_patterns(text, lex["face_power"].get("patterns", []))
    hits = _dedupe(hits)
    hits.sort(key=lambda h: (-h["strength"], h["span"]["start"]))

    subscores, detail = compute_subscores(text, hits, lex, audience)
    scoring = compute_friction(subscores, audience)

    directness_index, directness_hits = compute_directness(text, hits, lex)
    abrasion = compute_abrasion(directness_index, audience)
    detail["directness"] = {
        "index": round(directness_index, 3),
        "markers": sorted({_key(h) for h in directness_hits}),
        "audience_confrontation": audience.get("confrontation"),
    }

    too_short = len(text.strip()) < SHORT_TEXT_THRESHOLD
    curve = compute_tradeoff(scoring["friction_score"], subscores["motif"])
    rec_level, rec_rationale = recommend_level(curve)

    if target_level in REVERSE_LEVELS:
        # R 轨保留全部实质内容，只更换包装
        target = {"level": target_level, "friction": scoring["friction_score"],
                  "loss": 0, "fidelity": 100}
    else:
        target = next(p for p in curve if p["level"] == target_level)

    strong = [h for h in hits if h["strength"] >= 3]
    density = round(len(strong) / max(1.0, len(text) / 1000.0), 2)

    caveats: List[str] = [
        "本结果为确定性预扫描，hotspots 为候选而非结论；语义判定由模型完成。",
    ]
    caveats.extend(scoring["notes"])
    if too_short:
        caveats.append(
            f"文本不足 {SHORT_TEXT_THRESHOLD} 字，密度类指标不稳定，总分仅供参考。"
        )
    if target_level in REVERSE_LEVELS:
        caveats.append(
            "反向模式：Friction 衡量的是「看不看得懂」，此处应以 Abrasion 得罪风险为准。"
        )
    if audience.get("explicitness", 0) >= 0.99:
        caveats.append("受众为机器/Agent：必须输出 L5 机读轨，零省略容忍。")
    if audience.get("confrontation", 1.0) <= 0.30:
        caveats.append(
            "受众 confrontation 低：L4 输出不可直接对外发送，必须附 R1/R2 回复草稿。"
        )
    if abrasion >= 40:
        caveats.append(
            f"得罪风险 {abrasion}/100（直白度 {directness_index:.2f}）："
            "若本文将直接发给该受众，应先走反向 R1/R2 收敛。"
        )
    if detect_script(text) != "zh":
        caveats.append(
            f"输入判定为非中文（{detect_script(text)}）：零主语启发式已跳过，"
            "E 维仅基于显性留白证据，可能偏低。"
        )

    return {
        "schema": "context-transcompiler/probe.v1",
        "version": __version__,
        "meta": {
            "audience": audience_id,
            "audience_label": audience.get("label", ""),
            "audience_params": {
                "explicitness": audience.get("explicitness"),
                "confrontation": audience.get("confrontation"),
                "shared_ground": audience.get("shared_ground"),
            },
            "target_level": target_level,
            "char_count": len(text),
            "too_short_for_scoring": too_short,
        },
        "scoring": {
            "subscores": subscores,
            "raw_score": scoring["raw_score"],
            "breadth_sum": scoring["breadth_sum"],
            "pragmatic_before_modulation": scoring["pragmatic_before_modulation"],
            "factual_unmodulated": scoring["factual_unmodulated"],
            "peak_dimension": scoring["peak_dimension"],
            "peak_value": scoring["peak_value"],
            "friction_score": scoring["friction_score"],
            "friction_band": scoring["friction_band"],
            "friction_band_label": scoring["friction_band_label"],
            "modulation_factor": scoring["modulation_factor"],
            "friction_at_target": target["friction"],
            "loss_at_target": target["loss"],
            "fidelity_at_target": target["fidelity"],
            "hotspot_density": density,
            "directness_index": round(directness_index, 3),
            "abrasion_score": abrasion,
        },
        "trade_off": {
            "curve": curve,
            "recommended_level": rec_level,
            "rationale": rec_rationale,
        },
        "candidate_hotspots": hits[:top],
        "hotspot_total": len(hits),
        "evidence_detail": detail,
        "caveats": caveats,
    }


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

CLASS_LABEL = {
    "PRESUPPOSITION": "共识预设",
    "SUBTEXT": "潜台词",
    "FACE": "面子",
    "HIERARCHY": "位阶",
    "MOTIF": "意象",
    "ELLIPSIS": "留白",
}


def to_markdown(result: Dict[str, Any]) -> str:
    m, s, t = result["meta"], result["scoring"], result["trade_off"]
    out: List[str] = []
    out.append(f"# 预扫描结果 · {m['audience_label']}（{m['audience']}）\n")
    out.append(
        f"**文化阻抗 {s['friction_score']}/100** "
        f"（{s['friction_band_label']}）· 原始分 {s['raw_score']} "
        f"· 调制系数 {s['modulation_factor']}\n"
    )
    out.append(
        f"**目标 {m['target_level']}**：阻抗 {s['friction_at_target']} · "
        f"保真 {s['fidelity_at_target']} · 损耗 {s['loss_at_target']}\n"
    )
    out.append(f"**断点密度** {s['hotspot_density']} 处/千字 · 候选热点共 {result['hotspot_total']} 处\n")
    if s.get("abrasion_score", 0) >= 20:
        out.append(
            f"**得罪风险 {s['abrasion_score']}/100**（直白度 {s['directness_index']}）"
            f" — 仅在本文要发给该受众时相关\n"
        )

    out.append("\n## 子分\n")
    out.append("| 维度 | 得分 | 满分 |")
    out.append("|---|---|---|")
    names = {
        "presupposition": "P 共识预设", "subtext": "S 潜台词", "motif": "M 文化意象",
        "hierarchy": "H 位阶面子", "ellipsis": "E 留白省略",
    }
    for k, label in names.items():
        out.append(f"| {label} | {s['subscores'][k]} | {int(SUBSCORE_CAPS[k])} |")

    out.append("\n## 阶梯取舍\n")
    out.append("| 级别 | 阻抗 | 损耗 | 保真 |")
    out.append("|---|---|---|---|")
    for p in t["curve"]:
        mark = " ←推荐" if p["level"] == t["recommended_level"] else ""
        out.append(f"| {p['level']}{mark} | {p['friction']} | {p['loss']} | {p['fidelity']} |")
    out.append(f"\n> {t['rationale']}\n")

    out.append("\n## 候选热点\n")
    if not result["candidate_hotspots"]:
        out.append("_未命中任何词典条目。文本可能已是低语境，或使用了词典未收录的表达——请人工复核。_")
    else:
        out.append("| 位置 | 片段 | 类别 | 强度 | 说明 |")
        out.append("|---|---|---|---|---|")
        for h in result["candidate_hotspots"]:
            gloss = (h.get("gloss") or h.get("intended") or "").replace("|", "／")
            out.append(
                f"| {h['span']['start']}–{h['span']['end']} | `{h['text']}` | "
                f"{CLASS_LABEL.get(h['class'], h['class'])} | {h['strength']} | {gloss} |"
            )

    out.append("\n## 注意事项\n")
    for c in result["caveats"]:
        out.append(f"- {c}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="语境平抑器 · 确定性预扫描器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python3 probe.py --text '这个方案回头再说吧' --audience de-business\n"
               "  python3 probe.py --text-file script.txt --audience us-genz --target-level L3 --format md\n",
    )
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--text", help="直接传入文本")
    src.add_argument("--text-file", help="从文件读取（UTF-8）")
    ap.add_argument("--audience", default="global-english", help="受众 id，见 data/audiences.json")
    ap.add_argument("--target-level", default="L4",
                    choices=list(LADDER_LOSS_WEIGHT.keys()) + sorted(REVERSE_LEVELS))
    ap.add_argument("--format", default="json", choices=["json", "md"])
    ap.add_argument("--top", type=int, default=40, help="返回的候选热点上限")
    ap.add_argument("--lexicon-dir", default=LEXICON_DIR)
    ap.add_argument("--audience-file", default=None, help="自定义受众档案文件")
    ap.add_argument("--list-audiences", action="store_true", help="列出可用受众后退出")
    ap.add_argument("-o", "--output", help="写入文件而非标准输出")
    ap.add_argument("--json", dest="force_json", action="store_true", help="等价于 --format json")
    ap.add_argument("--version", action="version", version=f"probe.py {__version__}")
    args = ap.parse_args(argv)

    if args.list_audiences:
        for pid, prof in sorted(load_audiences(args.audience_file).items()):
            print(f"{pid:16s} {prof.get('label','')}  "
                  f"explicitness={prof.get('explicitness')} "
                  f"confrontation={prof.get('confrontation')} "
                  f"shared_ground={prof.get('shared_ground')}")
        return 0

    if args.text is not None:
        text = args.text
    elif args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as fh:
            text = fh.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("需要 --text、--text-file 或标准输入之一")
        return 2

    if not text.strip():
        print("[error] 输入为空", file=sys.stderr)
        return 2

    result = probe(
        text,
        audience_id=args.audience,
        target_level=args.target_level,
        lexicon_dir=args.lexicon_dir,
        audience_file=args.audience_file,
        top=args.top,
    )

    fmt = "json" if args.force_json else args.format
    payload = json.dumps(result, ensure_ascii=False, indent=2) if fmt == "json" else to_markdown(result)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload if payload.endswith("\n") else payload + "\n")
        print(f"已写入 {args.output}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
