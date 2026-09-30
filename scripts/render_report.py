#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_report.py — 把转译结果渲染成人读报告

  --format md    Markdown，适合贴进对话、文档或 PR
  --format html  自包含单文件，含热力图高亮、双仪表盘与阶梯对照，可直接交付

HTML 不引用任何外部资源（无 CDN、无字体请求），可离线打开、可邮件附件发送。
明暗主题跟随系统。

用法：
  python3 render_report.py --file result.json --format md
  python3 render_report.py --file result.json --format html -o report.html
  python3 probe.py --text-file in.txt --audience us-genz | python3 render_report.py --format md

同时接受两种输入：
  * transcompile.v1  —— 完整转译结果（模型产出）
  * probe.v1         —— 预扫描结果（probe.py 产出），只渲染诊断部分
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import sys
from typing import Any, Dict, List, Optional

__version__ = "1.0.0"

CLASS_LABEL = {
    "PRESUPPOSITION": "共识预设",
    "SUBTEXT": "潜台词",
    "FACE": "面子",
    "HIERARCHY": "位阶",
    "MOTIF": "意象",
    "ELLIPSIS": "留白",
}

BAND_LABEL = {"low": "通行", "moderate": "轻阻", "high": "高阻", "severe": "闭塞"}

LEVEL_NAME = {
    "L0": "原样", "L1": "注释轨", "L2": "轻度显化",
    "L3": "叙事显化", "L4": "功能化", "L5": "机读化",
    "R1": "得体化", "R2": "关系化", "R3": "圈层化",
}


# ---------------------------------------------------------------------------
# 归一化：把 probe.v1 与 transcompile.v1 统一成同一个视图模型
# ---------------------------------------------------------------------------

def normalize(doc: Dict[str, Any]) -> Dict[str, Any]:
    kind = doc.get("schema", "")
    if kind.endswith("probe.v1"):
        scoring = doc.get("scoring", {})
        meta = doc.get("meta", {})
        return {
            "kind": "probe",
            "audience": meta.get("audience", ""),
            "audience_label": meta.get("audience_label", ""),
            "target": meta.get("target_level", ""),
            "domain": "",
            "friction": scoring.get("friction_score"),
            "band": scoring.get("friction_band"),
            "subscores": scoring.get("subscores", {}),
            "fidelity": scoring.get("fidelity_at_target"),
            "loss": scoring.get("loss_at_target"),
            "density": scoring.get("hotspot_density"),
            "hotspots": doc.get("candidate_hotspots", []),
            "hotspot_total": doc.get("hotspot_total", 0),
            "curve": (doc.get("trade_off") or {}).get("curve", []),
            "recommended": (doc.get("trade_off") or {}).get("recommended_level"),
            "rationale": (doc.get("trade_off") or {}).get("rationale", ""),
            "source_text": doc.get("source_text", ""),
            "ladder": {},
            "tracks": {},
            "machine_readable": None,
            "creator_advice": [],
            "premises": [],
            "power_map": {},
            "caveats": doc.get("caveats", []),
        }

    diag = doc.get("diagnosis", {})
    meta = doc.get("meta", {})
    ladder = doc.get("ladder", {}) or {}
    return {
        "kind": "transcompile",
        "audience": meta.get("audience", ""),
        "audience_label": meta.get("audience_note") or meta.get("audience", ""),
        "target": meta.get("ladder_target", ""),
        "domain": meta.get("domain", ""),
        "friction": diag.get("friction_score"),
        "band": diag.get("friction_band"),
        "subscores": diag.get("subscores", {}),
        "fidelity": diag.get("fidelity_at_target"),
        "loss": diag.get("loss_at_target"),
        "density": diag.get("hotspot_density"),
        "hotspots": diag.get("hotspots", []),
        "hotspot_total": len(diag.get("hotspots", [])),
        "curve": (doc.get("trade_off") or {}).get("curve", []),
        "recommended": (doc.get("trade_off") or {}).get("recommended_level"),
        "rationale": (doc.get("trade_off") or {}).get("rationale", ""),
        "source_text": ladder.get("L0", ""),
        "ladder": ladder,
        "tracks": doc.get("tracks", {}) or {},
        "machine_readable": doc.get("machine_readable"),
        "creator_advice": doc.get("creator_advice", []) or [],
        "premises": diag.get("unstated_premises", []) or [],
        "power_map": diag.get("power_map", {}) or {},
        "caveats": (doc.get("confidence") or {}).get("caveats", []) or [],
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def render_markdown(v: Dict[str, Any]) -> str:
    out: List[str] = []
    band = BAND_LABEL.get(v["band"] or "", v["band"] or "")
    title = "语境诊断报告" if v["kind"] == "probe" else "语境转译报告"
    out.append(f"# {title}\n")

    head = f"**文化阻抗 {v['friction']}/100**（{band}）"
    if v["audience_label"] or v["audience"]:
        head += f" · 受众 {v['audience_label'] or v['audience']}"
    if v["target"]:
        head += f" · 目标 {v['target']} {LEVEL_NAME.get(v['target'], '')}"
    if v["fidelity"] is not None:
        head += f" · 保真 {v['fidelity']}/100"
    out.append(head + "\n")

    if v["density"] is not None:
        out.append(f"断点密度 {v['density']} 处/千字 · 热点共 {v['hotspot_total']} 处\n")

    # 子分
    if v["subscores"]:
        names = [("presupposition", "P 共识预设", 25), ("subtext", "S 潜台词", 25),
                 ("motif", "M 文化意象", 20), ("hierarchy", "H 位阶面子", 15),
                 ("ellipsis", "E 留白省略", 15)]
        out.append("\n## 子分\n")
        out.append("| 维度 | 得分 | 满分 | |")
        out.append("|---|---:|---:|---|")
        for key, label, cap in names:
            score = v["subscores"].get(key, 0)
            filled = int(round((score / cap) * 10)) if cap else 0
            out.append(f"| {label} | {score} | {cap} | {'█' * filled}{'░' * (10 - filled)} |")

    # 热点
    if v["hotspots"]:
        out.append("\n## 断点\n")
        for h in v["hotspots"]:
            cls = CLASS_LABEL.get(h.get("class", ""), h.get("class", ""))
            sev = h.get("severity") or h.get("strength") or 0
            out.append(f"### `{h.get('text','')}` — {cls} · 严重度 {sev}\n")
            if h.get("literal_reading"):
                out.append(f"- **字面会读成**：{h['literal_reading']}")
            if h.get("intended_reading"):
                out.append(f"- **实际在说**：{h['intended_reading']}")
            elif h.get("gloss"):
                out.append(f"- **说明**：{h['gloss']}")
            if h.get("misread_risk"):
                out.append(f"- **读错的后果**：{h['misread_risk']}")
            if h.get("bridge"):
                out.append(f"- **桥接**：{h['bridge']}")
            if h.get("trap"):
                out.append(f"- **直译陷阱**：{h['trap']}")
            out.append("")

    # 未言明前提
    if v["premises"]:
        out.append("\n## 未言明的前提\n")
        for p in v["premises"]:
            out.append(f"- {p}")

    # 关系图
    pm = v["power_map"]
    if pm:
        out.append("\n## 关系结构\n")
        labels = {"speaker": "说话人", "addressee": "受话人", "relation": "关系",
                  "who_holds_floor": "话语权", "face_at_stake": "谁的面子在台上",
                  "obligation_flow": "人情流向"}
        for k, label in labels.items():
            if pm.get(k):
                out.append(f"- **{label}**：{pm[k]}")

    # 阶梯
    if v["curve"]:
        out.append("\n## 阶梯取舍\n")
        out.append("| 级别 | | 阻抗 | 保真 |")
        out.append("|---|---|---:|---:|")
        for p in v["curve"]:
            mark = " ←推荐" if p["level"] == v["recommended"] else ""
            out.append(
                f"| {p['level']}{mark} | {LEVEL_NAME.get(p['level'],'')} | "
                f"{p['friction']} | {p['fidelity']} |"
            )
        if v["rationale"]:
            out.append(f"\n> {v['rationale']}\n")

    # 转译
    ladder, tracks = v["ladder"], v["tracks"]
    if ladder or tracks:
        out.append("\n## 转译\n")
        if isinstance(ladder.get("L0"), str) and ladder["L0"]:
            out.append(f"### L0 原样\n\n> {ladder['L0']}\n")
        l1 = ladder.get("L1")
        if isinstance(l1, dict):
            out.append("### L1 注释轨\n")
            out.append(f"> {l1.get('text','')}\n")
            for a in l1.get("annotations", []):
                anchor = a.get("anchor") or (
                    l1.get("text", "")[a["span"]["start"]:a["span"]["end"]]
                    if a.get("span") else ""
                )
                out.append(f"- **{anchor}**：{a.get('note','')}")
            out.append("")
        for key in ("L2", "L3", "L4", "L5", "R1", "R2", "R3"):
            if isinstance(ladder.get(key), str) and ladder[key]:
                out.append(f"### {key} {LEVEL_NAME.get(key,'')}\n\n{ladder[key]}\n")
        for key, label in (("business", "商务功能轨"), ("narrative", "叙事显化轨"),
                           ("annotated", "旁注解析轨")):
            if tracks.get(key) and not ladder:
                out.append(f"### {label}\n\n{tracks[key]}\n")

    # 机读
    mr = v["machine_readable"]
    if mr:
        out.append("\n## 机读输出（L5）\n")
        out.append("```json")
        out.append(json.dumps(mr, ensure_ascii=False, indent=2))
        out.append("```")

    # 创作者建议
    if v["creator_advice"]:
        out.append("\n## 创作者建议\n")
        for i, a in enumerate(v["creator_advice"], 1):
            pri = f"[{a['priority']}] " if a.get("priority") else ""
            out.append(f"**{i}. {pri}{a.get('issue','')}**")
            if a.get("where"):
                out.append(f"- 位置：{a['where']}")
            out.append(f"- 建议：{a.get('suggestion','')}")
            if a.get("preserves"):
                out.append(f"- 保住了：{a['preserves']}")
            if a.get("cost"):
                out.append(f"- 代价：{a['cost']}")
            out.append("")

    if v["caveats"]:
        out.append("\n## 注意事项\n")
        for c in v["caveats"]:
            out.append(f"- {c}")

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CLASS_TOKEN = {
    "PRESUPPOSITION": "presup",
    "SUBTEXT": "subtext",
    "FACE": "face",
    "HIERARCHY": "hier",
    "MOTIF": "motif",
    "ELLIPSIS": "ellip",
}


def build_heatmap(text: str, hotspots: List[Dict[str, Any]]) -> str:
    """
    逐字符取「最高严重度」的类别着色，避免重叠 span 导致标签嵌套错乱。
    没有 span 的热点不参与高亮（宁可不标，也不标错）。
    """
    if not text:
        return ""
    owner: List[Optional[Dict[str, Any]]] = [None] * len(text)
    for h in hotspots:
        span = h.get("span")
        if not span:
            continue
        s, e = span.get("start"), span.get("end")
        if not isinstance(s, int) or not isinstance(e, int):
            continue
        s, e = max(0, s), min(len(text), e)
        sev = h.get("severity") or h.get("strength") or 1
        for i in range(s, e):
            cur = owner[i]
            cur_sev = (cur.get("severity") or cur.get("strength") or 1) if cur else -1
            if sev > cur_sev:
                owner[i] = h

    parts: List[str] = []
    i = 0
    while i < len(text):
        cur = owner[i]
        j = i
        while j < len(text) and owner[j] is cur:
            j += 1
        chunk = html_mod.escape(text[i:j])
        if cur is None:
            parts.append(chunk)
        else:
            token = CLASS_TOKEN.get(cur.get("class", ""), "subtext")
            sev = cur.get("severity") or cur.get("strength") or 1
            tip = cur.get("intended_reading") or cur.get("gloss") or cur.get("misread_risk") or ""
            label = CLASS_LABEL.get(cur.get("class", ""), "")
            parts.append(
                f'<mark class="hs {token} sev{sev}" tabindex="0" '
                f'data-tip="{html_mod.escape(label)}：{html_mod.escape(tip)}">{chunk}</mark>'
            )
        i = j
    return "".join(parts)


def gauge(label: str, value: Optional[int], tone: str, hint: str) -> str:
    v = 0 if value is None else max(0, min(100, value))
    shown = "—" if value is None else str(value)
    return f"""      <div class="gauge">
        <div class="gauge-head"><span>{html_mod.escape(label)}</span><b class="{tone}">{shown}</b></div>
        <div class="bar"><i class="{tone}" style="width:{v}%"></i></div>
        <p class="hint">{html_mod.escape(hint)}</p>
      </div>"""


def render_html(v: Dict[str, Any]) -> str:
    band = BAND_LABEL.get(v["band"] or "", v["band"] or "—")
    esc = html_mod.escape
    title = "语境诊断报告" if v["kind"] == "probe" else "语境转译报告"

    heat = build_heatmap(v["source_text"], v["hotspots"]) if v["source_text"] else ""

    # 子分条
    sub_rows = []
    for key, label, cap in [("presupposition", "P 共识预设", 25), ("subtext", "S 潜台词", 25),
                            ("motif", "M 文化意象", 20), ("hierarchy", "H 位阶面子", 15),
                            ("ellipsis", "E 留白省略", 15)]:
        score = v["subscores"].get(key, 0) or 0
        pct = (score / cap * 100) if cap else 0
        sub_rows.append(
            f'<div class="sub"><span>{esc(label)}</span>'
            f'<div class="bar"><i class="c-{key}" style="width:{pct:.1f}%"></i></div>'
            f'<b>{score}<small>/{cap}</small></b></div>'
        )

    # 阶梯
    curve_rows = []
    for p in v["curve"]:
        rec = " rec" if p["level"] == v["recommended"] else ""
        curve_rows.append(
            f'<tr class="{rec.strip()}"><td><code>{esc(p["level"])}</code> '
            f'{esc(LEVEL_NAME.get(p["level"],""))}{" ★" if rec else ""}</td>'
            f'<td><div class="mini"><i class="warm" style="width:{p["friction"]}%"></i></div>'
            f'<span>{p["friction"]}</span></td>'
            f'<td><div class="mini"><i class="cool" style="width:{p["fidelity"]}%"></i></div>'
            f'<span>{p["fidelity"]}</span></td></tr>'
        )

    # 热点卡
    cards = []
    for h in v["hotspots"]:
        token = CLASS_TOKEN.get(h.get("class", ""), "subtext")
        cls = CLASS_LABEL.get(h.get("class", ""), h.get("class", ""))
        sev = h.get("severity") or h.get("strength") or 0
        rows = []
        for field, label in (("literal_reading", "字面会读成"), ("intended_reading", "实际在说"),
                             ("gloss", "说明"), ("misread_risk", "读错的后果"),
                             ("trap", "直译陷阱"), ("bridge", "桥接")):
            if h.get(field):
                rows.append(f"<dt>{esc(label)}</dt><dd>{esc(h[field])}</dd>")
        cards.append(
            f'<article class="card {token}"><header><code>{esc(h.get("text",""))}</code>'
            f'<span class="tag {token}">{esc(cls)}</span>'
            f'<span class="sev">严重度 {sev}</span></header>'
            f'<dl>{"".join(rows)}</dl></article>'
        )

    # 转译段
    trans = []
    ladder = v["ladder"]
    l1 = ladder.get("L1")
    if isinstance(l1, dict):
        notes = "".join(
            f'<li><b>{esc(a.get("anchor") or "")}</b>{esc(a.get("note",""))}</li>'
            for a in l1.get("annotations", [])
        )
        trans.append(
            f'<section class="track"><h3><code>L1</code> 注释轨 '
            f'<small>正文一字未动</small></h3><blockquote>{esc(l1.get("text",""))}</blockquote>'
            f'<ul class="notes">{notes}</ul></section>'
        )
    for key in ("L2", "L3", "L4", "L5", "R1", "R2", "R3"):
        if isinstance(ladder.get(key), str) and ladder[key]:
            body = esc(ladder[key]).replace("\n", "<br>")
            trans.append(
                f'<section class="track"><h3><code>{key}</code> '
                f'{esc(LEVEL_NAME.get(key,""))}</h3><div class="body">{body}</div></section>'
            )
    if not trans:
        for key, label in (("business", "商务功能轨"), ("narrative", "叙事显化轨"),
                           ("annotated", "旁注解析轨")):
            if v["tracks"].get(key):
                body = esc(v["tracks"][key]).replace("\n", "<br>")
                trans.append(
                    f'<section class="track"><h3>{esc(label)}</h3>'
                    f'<div class="body">{body}</div></section>'
                )

    advice = "".join(
        f'<li><b>{esc(a.get("issue",""))}</b>'
        + (f'<em>{esc(a.get("where",""))}</em>' if a.get("where") else "")
        + f'<p>{esc(a.get("suggestion",""))}</p>'
        + (f'<p class="keep">保住了：{esc(a["preserves"])}</p>' if a.get("preserves") else "")
        + (f'<p class="cost">代价：{esc(a["cost"])}</p>' if a.get("cost") else "")
        + "</li>"
        for a in v["creator_advice"]
    )

    mr_block = ""
    if v["machine_readable"]:
        mr_block = (
            '<section class="panel"><h2>机读输出 L5</h2><pre><code>'
            + esc(json.dumps(v["machine_readable"], ensure_ascii=False, indent=2))
            + "</code></pre></section>"
        )

    caveats = "".join(f"<li>{esc(c)}</li>" for c in v["caveats"])
    premises = "".join(f"<li>{esc(p)}</li>" for p in v["premises"])

    legend = "".join(
        f'<span class="tag {tok}">{esc(CLASS_LABEL[k])}</span>'
        for k, tok in CLASS_TOKEN.items()
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
:root {{
  --bg:#faf9f7; --panel:#fff; --ink:#1b1a18; --muted:#6b6862; --line:#e5e1db;
  --warm:#c2410c; --cool:#0f766e; --accent:#7c3aed;
  --presup:#8b5cf6; --subtext:#dc2626; --face:#ea580c; --hier:#0891b2; --motif:#ca8a04; --ellip:#64748b;
  --radius:10px;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#16151a; --panel:#1f1e25; --ink:#eceaf2; --muted:#9d99a8; --line:#33313d;
    --warm:#fb923c; --cool:#5eead4; --accent:#a78bfa;
    --presup:#a78bfa; --subtext:#f87171; --face:#fb923c; --hier:#22d3ee; --motif:#facc15; --ellip:#94a3b8;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#16151a; --panel:#1f1e25; --ink:#eceaf2; --muted:#9d99a8; --line:#33313d;
  --warm:#fb923c; --cool:#5eead4; --accent:#a78bfa;
  --presup:#a78bfa; --subtext:#f87171; --face:#fb923c; --hier:#22d3ee; --motif:#facc15; --ellip:#94a3b8;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}}
.wrap {{ max-width:880px; margin:0 auto; padding:40px 16px 80px; }}
h1 {{ font-size:1.6rem; margin:0 0 4px; letter-spacing:-.01em; }}
h2 {{ font-size:1.05rem; margin:0 0 14px; letter-spacing:.02em; color:var(--muted); font-weight:600; }}
h3 {{ font-size:1rem; margin:0 0 10px; }}
h3 small {{ color:var(--muted); font-weight:400; margin-left:6px; }}
.lede {{ color:var(--muted); margin:0 0 28px; font-size:.92rem; }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:22px; margin-bottom:18px; }}
.gauges {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }}
@media (max-width:560px) {{ .gauges {{ grid-template-columns:1fr; }} }}
.gauge-head {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }}
.gauge-head span {{ color:var(--muted); font-size:.85rem; }}
.gauge-head b {{ font-size:1.9rem; font-variant-numeric:tabular-nums; line-height:1; }}
.warm {{ color:var(--warm); }} .cool {{ color:var(--cool); }}
.bar {{ height:7px; background:var(--line); border-radius:99px; overflow:hidden; }}
.bar i {{ display:block; height:100%; border-radius:99px; }}
.bar i.warm {{ background:var(--warm); }} .bar i.cool {{ background:var(--cool); }}
.hint {{ color:var(--muted); font-size:.8rem; margin:8px 0 0; }}
.sub {{ display:grid; grid-template-columns:118px 1fr 62px; align-items:center; gap:12px; margin-bottom:9px; font-size:.87rem; }}
.sub .bar {{ height:9px; }}
.sub b {{ text-align:right; font-variant-numeric:tabular-nums; }}
.sub small {{ color:var(--muted); font-weight:400; }}
.c-presupposition {{ background:var(--presup); }} .c-subtext {{ background:var(--subtext); }}
.c-motif {{ background:var(--motif); }} .c-hierarchy {{ background:var(--hier); }} .c-ellipsis {{ background:var(--ellip); }}
.heat {{ font-size:1.06rem; line-height:2.3; letter-spacing:.01em; }}
mark.hs {{ background:transparent; color:inherit; padding:2px 1px; border-radius:3px; cursor:help; position:relative; }}
mark.hs {{ box-shadow:inset 0 -.62em 0 color-mix(in srgb, currentColor 18%, transparent); }}
mark.presup {{ color:var(--presup); }} mark.subtext {{ color:var(--subtext); }}
mark.face {{ color:var(--face); }} mark.hier {{ color:var(--hier); }}
mark.motif {{ color:var(--motif); }} mark.ellip {{ color:var(--ellip); }}
mark.sev4, mark.sev5 {{ box-shadow:inset 0 -.62em 0 color-mix(in srgb, currentColor 30%, transparent); font-weight:600; }}
mark.hs:hover::after, mark.hs:focus::after {{
  content:attr(data-tip); position:absolute; left:0; top:calc(100% + 6px); z-index:9;
  background:var(--ink); color:var(--bg); padding:7px 10px; border-radius:7px;
  font-size:.78rem; line-height:1.5; font-weight:400; white-space:normal; width:max-content; max-width:320px;
  box-shadow:0 6px 20px rgba(0,0,0,.2);
}}
.legend {{ margin-top:16px; display:flex; flex-wrap:wrap; gap:6px; }}
.tag {{ font-size:.72rem; padding:2px 8px; border-radius:99px; border:1px solid currentColor; }}
.tag.presup {{ color:var(--presup); }} .tag.subtext {{ color:var(--subtext); }}
.tag.face {{ color:var(--face); }} .tag.hier {{ color:var(--hier); }}
.tag.motif {{ color:var(--motif); }} .tag.ellip {{ color:var(--ellip); }}
.card {{ border:1px solid var(--line); border-left:3px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:10px; background:var(--panel); }}
.card.presup {{ border-left-color:var(--presup); }} .card.subtext {{ border-left-color:var(--subtext); }}
.card.face {{ border-left-color:var(--face); }} .card.hier {{ border-left-color:var(--hier); }}
.card.motif {{ border-left-color:var(--motif); }} .card.ellip {{ border-left-color:var(--ellip); }}
.card header {{ display:flex; align-items:center; gap:9px; flex-wrap:wrap; margin-bottom:9px; }}
.card .sev {{ color:var(--muted); font-size:.75rem; margin-left:auto; }}
dl {{ margin:0; display:grid; grid-template-columns:auto 1fr; gap:4px 14px; font-size:.88rem; }}
dt {{ color:var(--muted); white-space:nowrap; }}
dd {{ margin:0; }}
code {{ background:color-mix(in srgb, var(--ink) 7%, transparent); padding:2px 6px; border-radius:5px; font-size:.88em; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
pre {{ background:color-mix(in srgb, var(--ink) 5%, transparent); padding:14px; border-radius:8px; overflow:auto; font-size:.82rem; line-height:1.6; }}
pre code {{ background:none; padding:0; }}
table {{ width:100%; border-collapse:collapse; font-size:.87rem; }}
td {{ padding:8px 6px; border-bottom:1px solid var(--line); vertical-align:middle; }}
td:first-child {{ width:40%; white-space:nowrap; }}
thead th {{ padding:0 6px 6px; text-align:left; font-size:.76rem; font-weight:500; color:var(--muted); border-bottom:1px solid var(--line); }}
tr.rec {{ background:color-mix(in srgb, var(--accent) 9%, transparent); }}
.cell {{ display:flex; align-items:center; gap:8px; }}
td span {{ font-variant-numeric:tabular-nums; min-width:26px; text-align:right; color:var(--muted); font-size:.82rem; }}
.mini {{ flex:1; min-width:52px; height:5px; background:var(--line); border-radius:99px; overflow:hidden; }}
.mini i {{ display:block; height:100%; }}
.mini i.warm {{ background:var(--warm); }} .mini i.cool {{ background:var(--cool); }}
.track {{ border-top:1px solid var(--line); padding-top:16px; margin-top:16px; }}
.track:first-child {{ border-top:none; padding-top:0; margin-top:0; }}
blockquote {{ margin:0 0 10px; padding:12px 16px; border-left:3px solid var(--line); background:color-mix(in srgb, var(--ink) 4%, transparent); border-radius:0 8px 8px 0; }}
.notes {{ margin:0; padding-left:18px; font-size:.85rem; color:var(--muted); }}
.notes b {{ color:var(--ink); margin-right:6px; }}
.body {{ font-size:.94rem; }}
ol.advice {{ padding-left:20px; }}
ol.advice li {{ margin-bottom:16px; }}
ol.advice em {{ display:block; color:var(--muted); font-size:.8rem; font-style:normal; }}
ol.advice p {{ margin:5px 0 0; font-size:.9rem; }}
.keep {{ color:var(--cool); }} .cost {{ color:var(--warm); }}
ul.plain {{ padding-left:20px; font-size:.88rem; color:var(--muted); }}
footer {{ margin-top:36px; color:var(--muted); font-size:.78rem; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{esc(title)}</h1>
  <p class="lede">受众 {esc(v['audience_label'] or v['audience'] or '—')}
    · 目标 {esc(v['target'] or '—')} {esc(LEVEL_NAME.get(v['target'],''))}
    {f"· 断点密度 {v['density']} 处/千字" if v['density'] is not None else ""}
    · 热点 {v['hotspot_total']} 处</p>

  <div class="panel gauges">
{gauge("文化阻抗 Friction", v["friction"], "warm", f"{band}：越高越容易被目标受众读错")}
{gauge("保真度 Fidelity", v["fidelity"], "cool", "降到目标级别后，原文韵味还剩多少")}
  </div>

  <div class="panel">
    <h2>子分构成</h2>
    {''.join(sub_rows)}
  </div>

  {f'''<div class="panel">
    <h2>热力图</h2>
    <div class="heat">{heat}</div>
    <div class="legend">{legend}</div>
  </div>''' if heat else ''}

  {f'''<div class="panel">
    <h2>断点 · {len(cards)} 处</h2>
    {''.join(cards)}
  </div>''' if cards else ''}

  {f'''<div class="panel">
    <h2>未言明的前提</h2>
    <ul class="plain">{premises}</ul>
  </div>''' if premises else ''}

  {f'''<div class="panel">
    <h2>阶梯取舍</h2>
    <table><thead><tr><th>级别</th><th>阻抗 Friction</th><th>保真 Fidelity</th></tr></thead>
    <tbody>{''.join(curve_rows)}</tbody></table>
    <p class="hint">{esc(v['rationale'])}</p>
  </div>''' if curve_rows else ''}

  {f'''<div class="panel">
    <h2>转译</h2>
    {''.join(trans)}
  </div>''' if trans else ''}

  {mr_block}

  {f'''<div class="panel">
    <h2>创作者建议</h2>
    <ol class="advice">{advice}</ol>
  </div>''' if advice else ''}

  {f'''<div class="panel">
    <h2>注意事项</h2>
    <ul class="plain">{caveats}</ul>
  </div>''' if caveats else ''}

  <footer>context-transcompiler · 语境平抑器 · 分数为可复现的启发式指标，用于相对比较而非绝对测定</footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="语境平抑器 · 报告渲染器")
    ap.add_argument("--file", help="结果 JSON；省略则读标准输入")
    ap.add_argument("--format", default="md", choices=["md", "html"])
    ap.add_argument("--source-text", help="原文（probe.v1 输入时用于绘制热力图）")
    ap.add_argument("-o", "--output", help="输出文件")
    ap.add_argument("--version", action="version", version=f"render_report.py {__version__}")
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

    if args.source_text:
        doc["source_text"] = args.source_text

    view = normalize(doc)
    payload = render_html(view) if args.format == "html" else render_markdown(view)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"已写入 {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
