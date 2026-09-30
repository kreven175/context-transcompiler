#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_examples.py — 生成 examples/ 下的端到端样例

为什么用脚本生成而不是手写 JSON：
  hotspot 的 span 偏移量必须与原文逐字符对齐，手写必错；
  friction / loss / curve 必须与 probe.py 的评分内核一致，手算必漂。
  这里把「语义内容」手写、「数值与偏移量」交给脚本算，再跑一遍 validate.py。

用法：
  python3 evals/build_examples.py            # 生成
  python3 evals/build_examples.py --check     # 只校验，不写文件（CI 用）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import probe as probe_mod  # noqa: E402


def span_of(text: str, fragment: str, occurrence: int = 1) -> Dict[str, int]:
    """按出现次序定位片段；找不到就报错而不是静默给错偏移量。"""
    idx, seen = -1, 0
    start = 0
    while seen < occurrence:
        idx = text.find(fragment, start)
        if idx == -1:
            raise ValueError(f"片段未在原文中找到：{fragment!r}（第 {occurrence} 次出现）")
        seen += 1
        start = idx + 1
    return {"start": idx, "end": idx + len(fragment)}


def assemble(source: str, audience: str, target: str, domain: str,
             hotspots: List[Dict[str, Any]], ladder: Dict[str, Any],
             tracks: Dict[str, str], **extra) -> Dict[str, Any]:
    """跑 probe 取数值，与手写语义内容合并成 transcompile.v1。"""
    p = probe_mod.probe(source, audience_id=audience, target_level=target)
    sc = p["scoring"]
    # R 轨不在正向曲线上：probe 已把目标值算好并回填到 scoring
    tgt = next(
        (c for c in p["trade_off"]["curve"] if c["level"] == target),
        {"level": target, "friction": sc["friction_at_target"],
         "loss": sc["loss_at_target"], "fidelity": sc["fidelity_at_target"]},
    )

    for i, h in enumerate(hotspots, 1):
        h.setdefault("id", f"h{i}")
        if "fragment" in h:
            h["span"] = span_of(source, h.pop("fragment"), h.pop("occurrence", 1))
            h["text"] = source[h["span"]["start"]:h["span"]["end"]]

    doc: Dict[str, Any] = {
        "schema": "context-transcompiler/v1",
        "meta": {
            "source_lang": extra.get("source_lang", "zh-CN"),
            "domain": domain,
            "register": extra.get("register", "semi-formal"),
            "audience": audience,
            "ladder_target": target,
            "char_count": len(source),
            "probe_executed": True,
        },
        "diagnosis": {
            "context_density": extra.get("context_density", "high"),
            "friction_score": sc["friction_score"],
            "friction_band": sc["friction_band"],
            "raw_score": sc["raw_score"],
            "subscores": sc["subscores"],
            "fidelity_at_target": tgt["fidelity"],
            "loss_at_target": tgt["loss"],
            "hotspot_density": sc["hotspot_density"],
            "hotspots": hotspots,
        },
        "ladder": ladder,
        "tracks": tracks,
        "trade_off": {
            "curve": p["trade_off"]["curve"],
            "recommended_level": p["trade_off"]["recommended_level"],
            "rationale": extra.get("rationale", p["trade_off"]["rationale"]),
        },
        "confidence": {
            "overall": extra.get("confidence", 0.85),
            "caveats": extra.get("caveats", []),
        },
    }

    if target.startswith("R"):
        doc["diagnosis"]["directness_index"] = sc["directness_index"]
        doc["diagnosis"]["abrasion_score"] = sc["abrasion_score"]
    if extra.get("power_map"):
        doc["diagnosis"]["power_map"] = extra["power_map"]
    if extra.get("premises"):
        doc["diagnosis"]["unstated_premises"] = extra["premises"]
    if extra.get("machine_readable"):
        doc["machine_readable"] = extra["machine_readable"]
    if extra.get("creator_advice"):
        doc["creator_advice"] = extra["creator_advice"]
    if extra.get("needs_confirmation"):
        doc["confidence"]["needs_confirmation"] = extra["needs_confirmation"]
    return doc


# ===========================================================================
# 样例 01 · 职场含蓄否决 → L4 功能轨
# ===========================================================================

SRC1 = ("张总在会上对小李说：你这个方案的出发点是好的，年轻人有冲劲很难得。"
        "不过里面涉及到的几个跨部门协作的细节，我们回头再找时间慢慢对齐一下，今天先不展开了。")

EX1 = dict(
    source=SRC1, audience="de-business", target="L4", domain="workplace",
    register="semi-formal", context_density="high",
    hotspots=[
        {
            "fragment": "出发点是好的", "class": "FACE", "secondary_classes": ["SUBTEXT"],
            "severity": 4,
            "literal_reading": "领导认可了方案的初衷，是一句正面评价。",
            "intended_reading": "先给一句肯定，让接下来的否定说得出口。肯定的是动机，不是方案。",
            "misread_risk": "把它当成实质性认可，在后续沟通中引用「领导说过出发点是好的」，会显得没听懂话。",
            "why_opaque": "汉语职场中「出发点/方向/想法 + 是好的」是否定前的固定铺垫，字面无任何否定词。",
            "bridge": "译文中把这句标注为缓冲语，与真实评价分开呈现，不要混在同一句里。",
            "evidence": ["出发点是好的", "不过"],
            "confidence": 0.9,
        },
        {
            "fragment": "年轻人有冲劲很难得", "class": "HIERARCHY", "secondary_classes": ["FACE"],
            "severity": 3,
            "literal_reading": "领导赞赏年轻人的干劲。",
            "intended_reading": "把对方归入「年轻/资历浅」一类，等于说判断力还不够，因此不采纳。",
            "misread_risk": "读成鼓励，从而认为方案还有机会，继续投入。",
            "why_opaque": "以年资评价代替内容评价，是一种不伤面子的降级方式。",
            "bridge": "译文中点明这是以资历为由的软性降级，而非鼓励。",
            "evidence": ["年轻人有冲劲很难得"],
            "confidence": 0.8,
        },
        {
            "fragment": "我们回头再找时间慢慢对齐一下", "class": "SUBTEXT",
            "secondary_classes": ["FACE"], "severity": 5,
            "literal_reading": "双方将在稍后安排一次会议继续讨论细节。",
            "intended_reading": "议题到此为止，不会再安排会议。这是一次留了面子的否决。",
            "misread_risk": "对方会等待会议邀请并继续保留资源投入，错过调整方案或改走其他路径的窗口。",
            "why_opaque": "「回头」「慢慢」在汉语职场语用中是无限期搁置的固定标记，字面无否定词。",
            "bridge": "译文中直接给出结论句「此议题已结束」，把缓冲语保留为独立的一句语气说明。",
            "evidence": ["回头再找时间", "慢慢对齐", "今天先不展开了"],
            "confidence": 0.85,
        },
        {
            "fragment": "小李", "class": "HIERARCHY", "severity": 3,
            "literal_reading": "一个叫李的人，英译为 Li 或 Xiao Li。",
            "intended_reading": "「小 X」只能由上级或年长者使用，与同句中的「张总」形成位阶落差——这次否决是当着全组、自上而下发生的。",
            "misread_risk": "位阶信息在英译中完全丢失，读者无法理解为什么被否决的一方不当场追问。",
            "why_opaque": "称谓承载位阶，而英语的 Mr./Ms. + 姓无法编码这一层。",
            "bridge": "在译文或注释中一次性说明称谓的位阶含义，或改用场景描写外化（谁先开口、谁没有回应）。",
            "evidence": ["张总", "小李"],
            "confidence": 0.85,
        },
    ],
    ladder={
        "L0": SRC1,
        "L1": {
            "text": SRC1,
            "annotations": [
                {"anchor": "张总 / 小李", "note": "称谓编码位阶：X总指向管理层，小X用于年轻下属，且只能由上级使用。"},
                {"anchor": "出发点是好的", "note": "否定前的固定铺垫，肯定的是动机不是方案。"},
                {"anchor": "回头再找时间慢慢对齐", "note": "无限期搁置的标准表述，等于本议题结束。"},
                {"anchor": "今天先不展开了", "note": "会议中终止话题的信号，通常不会再展开。"},
            ],
        },
        "L4": ("【结论】方案不通过。\n"
               "【依据】给出的理由是跨部门协作细节；这是可对外说出口的理由，真实理由未言明。\n"
               "【边界】不会另行安排讨论时间；本次会议中此议题已结束。当众否决意味着决定已定，不接受当场申辩。\n"
               "【动作】不要等待会议邀请。若仍要推进，需要更换切入点或绕开当前决策人；"
               "若要确认，只能会后单独、私下、以请教而非质疑的方式问。"),
        "R1": ("张总，谢谢您点出跨部门这块。我先把协作路径和责任边界梳理清楚，"
               "等成形了再单独向您汇报，不占用会议时间。"),
    },
    tracks={
        "business": "方案被否决。「回头再对齐」是无限期搁置，不是后续安排。不要等待会议邀请。",
        "annotated": "见 L1 注释轨。",
    },
    power_map={
        "speaker": "张总（部门负责人）",
        "addressee": "小李（资历最浅的下属）",
        "relation": "上级对下级，公开场合",
        "who_holds_floor": "张总——他决定议题何时结束",
        "face_at_stake": "小李的面子。当众否决必须包装，否则伤及其在团队中的位置",
        "obligation_flow": "无人情债产生；这是职权行使而非人情往来",
    },
    premises=[
        "在中国的会议场景中，上级当众否决下属时使用缓冲语是常规礼节，不表示态度犹豫。",
        "「回头再约时间」在绝大多数情况下不会真的产生后续会议。",
        "当众提出的否决通常已经在会前定好，会议只是宣布。",
    ],
    caveats=[
        "判定依据是语用标记而非说话人个人风格；若张总一贯说话就是这样委婉，强度应下调。",
        "若会后确实收到了会议邀请，则本判定错误，应改判为 defer。",
    ],
    needs_confirmation=["会后一周内是否收到关于该议题的日程邀请"],
    machine_readable={
        "intent": "在不损伤下属面子的前提下否决方案并结束议题",
        "stance": "reject",
        "confidence": 0.85,
        "action_items": [],
        "constraints": ["未给出重新讨论的时间", "跨部门协作细节被列为公开理由"],
        "deadline": None,
        "escalation_needed": True,
        "evidence": ["出发点是好的", "回头再找时间", "慢慢对齐", "今天先不展开了"],
    },
    rationale=("商务场景直接取 L4：需要的是「能不能继续投入」这个判断，不是语感。"
               "L1 注释轨作为补充，保留原话的分寸感供用户自行体会。"),
)

# ===========================================================================
# 样例 02 · 武侠送别 → L3 叙事显化
# ===========================================================================

SRC2 = ("他在城门口折了一枝柳递过去，两个人都没说话。这一别，江湖路远，"
        "再见面时恐怕已经各自有了恩怨。她笑了笑，把柳枝收进袖中，转身走了。")

EX2 = dict(
    source=SRC2, audience="us-genz", target="L3", domain="literary",
    register="formal", context_density="high",
    hotspots=[
        {
            "fragment": "折了一枝柳", "class": "MOTIF", "severity": 4,
            "literal_reading": "他从树上折下一根柳树枝交给她——一个没有意义的随手动作。",
            "intended_reading": "折柳送别是延续千年的习俗，「柳」谐音「留」，赠柳即是挽留与不舍。",
            "misread_risk": "读者会以为这是无意义的环境描写，整场送别戏的情感核心因此落空。",
            "why_opaque": "含义建立在汉语谐音与一套读者默认共享的习俗上，两者都无法直译。",
            "bridge": "紧接动作补一句功能性说明——不是解释典故，而是让动作的意图可见（例如她接过时手停了一下）。",
            "evidence": ["折了一枝柳递过去", "把柳枝收进袖中"],
            "confidence": 0.9,
        },
        {
            "fragment": "江湖路远", "class": "MOTIF", "severity": 4,
            "literal_reading": "字面是「河流与湖泊的路途遥远」。",
            "intended_reading": "江湖指体制之外、靠人情与武力自行运转的社会；「路远」意味着此后各自漂泊、身不由己。",
            "misread_risk": "直译成 rivers and lakes 完全失效；读者不理解为什么重逢会变得不可控。",
            "why_opaque": "「江湖」在英语中没有等价概念，只能靠一句以上的描述传达。",
            "bridge": "首次出现时用一句话建立功能（一个没有王法、只认恩怨与人情的世界），之后照用不再解释。",
            "evidence": ["江湖路远"],
            "confidence": 0.85,
        },
        {
            "fragment": "各自有了恩怨", "class": "MOTIF", "secondary_classes": ["PRESUPPOSITION"],
            "severity": 3,
            "literal_reading": "各自结下了一些仇。",
            "intended_reading": "恩与怨是一本必须清算的账；有了恩怨意味着两人可能被各自的义务推到对立面。",
            "misread_risk": "读成「以后可能会吵架」，从而低估这句话的宿命感和后续冲突的必然性。",
            "why_opaque": "「恩怨」把恩情与仇怨绑成一个需要偿还的整体，英语拆成两个不相干的词。",
            "bridge": "外化为后果而非概念——写明她们日后可能要为各自的人替对方做选择。",
            "evidence": ["各自有了恩怨"],
            "confidence": 0.8,
        },
        {
            "fragment": "两个人都没说话", "class": "ELLIPSIS", "severity": 4,
            "literal_reading": "两人保持沉默，没有信息。",
            "intended_reading": "沉默是本段最重的一句。该说的都说不出口，所以用一个动作代替。",
            "misread_risk": "低语境读者读成「没有发生什么」，从而跳过整段的情绪高点。",
            "why_opaque": "留白要求读者自行补全；低语境阅读习惯是从字面取信息，遇到空白会直接略过。",
            "bridge": "用可见的身体细节把沉默填成有内容的停顿（她张了张口又合上；他把手收回袖子里）。",
            "evidence": ["两个人都没说话", "她笑了笑", "转身走了"],
            "confidence": 0.85,
        },
    ],
    ladder={
        "L0": SRC2,
        "L2": ("他在城门口折了一枝柳递过去——折柳是送别的意思。两个人都没说话。"
               "这一别，此后各自漂泊，再见面时，恐怕彼此都已欠下了不得不还的恩怨。"
               "她笑了笑，把柳枝收进袖中，转身走了。"),
        "L3": ("他在城门口停下，伸手折了一枝柳，递过去。\n"
               "她看着那枝柳，没有立刻接。城门口送行的人常做这个动作——柳枝留不住人，"
               "递的人和接的人都知道，可还是要递。\n"
               "两个人都没说话。她张了张口，又把话咽了回去。\n"
               "出了这道门就是江湖：没有王法，只有各自的师门、各自的债。"
               "下次见面，他们可能已经各自欠下了不得不还的人情，而那些人情未必站在同一边。\n"
               "她终于笑了笑，把柳枝收进袖中——收得很仔细，像是要留着。然后转身走了，没有回头。"),
    },
    tracks={
        "narrative": "见 L3 叙事显化轨。",
        "annotated": "折柳＝送别；江湖＝体制外社会；恩怨＝必须清算的人情账。",
    },
    premises=[
        "读者知道折柳是送别习俗，且知道「柳」谐音「留」。",
        "读者知道「江湖」是一个有自身规则、不受官府管辖的社会。",
        "读者知道在这个世界里，人情与恩怨会形成强制性的行动义务。",
        "读者默认沉默是有内容的，会主动去补全未说出口的部分。",
    ],
    creator_advice=[
        {
            "issue": "折柳的含义完全依赖读者已知的习俗，海外读者读到的是一个没有动机的随手动作",
            "where": "第 1 句",
            "suggestion": "不要加注释，改为让动作本身带出意图：写她接过时的迟疑，和他递出时明知留不住仍要递的姿态。",
            "preserves": "保住了留白——含义靠画面渗出来，而不是被旁白讲破。",
            "cost": "篇幅增加约两行，节奏比原文慢。",
            "priority": "P0",
        },
        {
            "issue": "「江湖」首次出现时没有任何功能锚点，读者无法理解这个词划定了什么样的世界",
            "where": "第 2 句",
            "suggestion": "首现时用一句话建立功能（没有王法，只有各自的师门与各自的债），之后全书照用不再解释。",
            "preserves": "保住了术语本身，不必把「江湖」替换成西方读者熟悉的概念。",
            "cost": "第一次出现时会略显解释性。",
            "priority": "P0",
        },
        {
            "issue": "沉默没有被身体动作支撑，低语境读者会把整段情绪高点当成空白跳过",
            "where": "第 1–2 句之间",
            "suggestion": "补一个未完成的动作（张口又咽回、手收进袖子），让沉默有可读的形状。",
            "preserves": "保住了「说不出口」这一层，比直接写出内心独白更接近原文的分寸。",
            "cost": "无实质代价，是本条建议中性价比最高的一处。",
            "priority": "P1",
        },
        {
            "issue": "「恩怨」被读成普通的争执，宿命感丢失",
            "where": "第 2 句末",
            "suggestion": "外化为具体后果：写明日后可能要为各自的人对上对方，而不是保留抽象名词。",
            "preserves": "保住了恩怨的强制性——这不是情绪，是义务。",
            "cost": "把一个凝练的词展开成一个从句。",
            "priority": "P1",
        },
    ],
    caveats=[
        "本段为节选，缺少前文语境；若「江湖」在前文已建立功能锚点，M 维得分应下调。",
        "L3 版本增加的身体细节属于改写而非翻译，需作者确认是否接受。",
    ],
    rationale=("脚本按乘积最大推荐 L2，此处仍取 L3：本段意象密度顶格（M=20/20），"
               "L2 的轻度显化不足以让折柳与江湖落地。L3 把阻抗从 52 降到 22，保真还剩 65；"
               "再降到 L4 保真会掉到 25，折柳与江湖被压成解释性说明，送别戏的情绪随之消失。"),
    confidence=0.82,
)

# ===========================================================================
# 样例 03 · 日本客户邮件 → L5 机读轨
# ===========================================================================

SRC3 = ("ご提案いただいた件、社内で検討させていただきます。"
        "ただ、スケジュール面でちょっと難しいところがございまして、"
        "今回は前向きに検討という形にさせてください。"
        "また機会がありましたら、ぜひよろしくお願いいたします。")

EX3 = dict(
    source=SRC3, audience="ai-agent", target="L5", domain="business",
    source_lang="ja", register="formal", context_density="high",
    hotspots=[
        {
            "fragment": "検討させていただきます", "class": "SUBTEXT", "severity": 5,
            "literal_reading": "我们会在公司内部研究这个提案。",
            "intended_reading": "礼貌性的拒绝。日本商务语境中这句话极少导向实际的内部讨论。",
            "misread_risk": "CRM 或 Agent 把状态标记为「进行中」，销售继续跟进，占用管线并错过真实机会。",
            "why_opaque": "谦让语形式使拒绝听起来像承诺，字面没有任何否定成分。",
            "bridge": "在结构化输出中直接置 stance=reject，并保留原文作为证据供人工复核。",
            "evidence": ["検討させていただきます"],
            "confidence": 0.85,
        },
        {
            "fragment": "ちょっと難しい", "class": "SUBTEXT", "severity": 5,
            "literal_reading": "有一点困难，但可以设法克服。",
            "intended_reading": "明确拒绝。这是日语中最标准的婉拒表达之一。",
            "misread_risk": "读成「有困难可以商量」，于是提出降价或压缩工期等让步，而对方根本无意继续。",
            "why_opaque": "程度副词「ちょっと」弱化了否定，使其在字面上看起来可协商。",
            "bridge": "这是 stance 判定的最强证据，置信度可给到 0.85 以上。",
            "evidence": ["ちょっと難しい"],
            "confidence": 0.9,
        },
        {
            "fragment": "前向きに検討", "class": "SUBTEXT", "severity": 5,
            "literal_reading": "会积极地、正面地考虑。",
            "intended_reading": "拒绝。「積極的に」的修饰反而是关闭的信号，属于固定套语。",
            "misread_risk": "被读成最积极的一句，从而整封邮件被判为正面。这是三处标记中最危险的一处。",
            "why_opaque": "修饰词的方向与实际语用意义相反。",
            "bridge": "在结构化输出中明确标注该短语为反向标记，避免下游情感分析误判为正面。",
            "evidence": ["前向きに検討という形にさせてください"],
            "confidence": 0.85,
        },
        {
            "fragment": "また機会がありましたら", "class": "FACE", "severity": 2,
            "literal_reading": "如果以后还有机会的话。",
            "intended_reading": "礼貌收尾，为双方保留体面，不构成任何后续承诺。",
            "misread_risk": "被记为「未来有合作意向」的线索，污染管线数据。",
            "why_opaque": "条件句形式使其看起来像一个开放的可能性。",
            "bridge": "标为礼节性收尾，不写入 action_items。",
            "evidence": ["また機会がありましたら"],
            "confidence": 0.8,
        },
    ],
    ladder={
        "L0": SRC3,
        "L4": ("【结论】提案被拒绝。\n"
               "【依据】对外给出的理由是排期；在日本商务语境中，排期常作为不伤和气的通用理由，"
               "未必是真实原因。\n"
               "【边界】没有给出任何时间点、条件或重启路径。整封邮件不含一个可执行的后续动作。\n"
               "【动作】不要追加让步条件。可在一个季度后以全新提案重新接触，"
               "但不要引用本次往来作为「上次谈过」的依据。"),
        "R1": ("ご検討いただき、ありがとうございます。スケジュールの件、承知いたしました。"
               "また適したタイミングがございましたら、あらためてご相談させてください。"),
    },
    tracks={
        "business": "拒绝。三处独立的婉拒标记叠加，无一处给出条件或时间。不要追加让步。",
    },
    machine_readable={
        "intent": "在不损伤关系的前提下拒绝提案并结束本轮往来",
        "stance": "reject",
        "confidence": 0.88,
        "action_items": [],
        "constraints": [
            "未给出任何时间点或重启条件",
            "排期为对外理由，真实原因未言明",
            "礼节性收尾不构成后续意向",
        ],
        "deadline": None,
        "escalation_needed": False,
        "evidence": [
            "検討させていただきます",
            "ちょっと難しい",
            "前向きに検討という形にさせてください",
        ],
    },
    premises=[
        "日本商务邮件中，谦让语的长度与拒绝的坚决程度正相关。",
        "不给出时间点等于不打算继续。",
        "对外理由与真实理由的分离（建前/本音）是默认预期，不是欺瞒。",
    ],
    caveats=[
        "三处标记相互独立且方向一致，因此置信度较高；若只有其中一处，应降为 defer。",
        "本判定针对日本商务惯例的群体先验，不针对具体发信人。若该客户以往用同样措辞后仍成交，应下调强度。",
    ],
    rationale=("受众为 Agent，强制 L5：下游系统需要的是可写入 CRM 的枚举值与证据，"
               "不是语气分析。同时给 L4 供人工复核、R1 供对外回复。"),
    confidence=0.88,
)

# ===========================================================================
# 样例 04 · 反向：直球中文 → R2 关系化（发给日本客户）
# ===========================================================================

SRC4 = "这个价格我们做不了，低于成本了。要么你们加钱，要么这单就算了。下周一之前给个准话。"

EX4 = dict(
    source=SRC4, audience="jp-business", target="R2", domain="business",
    register="casual", context_density="low",
    hotspots=[
        {
            "fragment": "做不了", "class": "FACE", "severity": 4,
            "literal_reading": "我们没有能力以这个价格供货——一个中性的事实陈述。",
            "intended_reading": "在日本商务语境中，无缓冲的能力否定会被读成情绪化和不专业，且不给对方任何退路。",
            "misread_risk": "对方无法在不失面子的情况下让步，只能整体退出谈判。真正的损失不是这一单，是这段关系。",
            "why_opaque": "说话人以为自己只是在陈述成本事实，不知道措辞本身携带关系信号。",
            "bridge": "把否定归因于客观约束（原材料成本上涨），而不是「我们不做」。",
            "evidence": ["做不了", "低于成本了"],
            "confidence": 0.85,
        },
        {
            "fragment": "要么你们加钱，要么这单就算了", "class": "FACE",
            "secondary_classes": ["HIERARCHY"], "severity": 5,
            "literal_reading": "提供两个选项让对方选择——看起来是在给对方决定权。",
            "intended_reading": "二选一的最后通牒。在高语境商务文化中，逼对方当场表态等于剥夺其内部协商的余地。",
            "misread_risk": "对方为避免当场屈服而直接选择退出；即使本愿加价，也会因为失去回旋空间而放弃。",
            "why_opaque": "说话人认为这是效率，对方读到的是压迫。",
            "bridge": "改为提供一个方案与一条备选路径，并把决定权交回对方的内部流程。",
            "evidence": ["要么", "就算了"],
            "confidence": 0.9,
        },
        {
            "fragment": "下周一之前给个准话", "class": "HIERARCHY", "severity": 4,
            "literal_reading": "请在下周一前答复——一个正常的时间要求。",
            "intended_reading": "单方面设定期限，且用「准话」排除了模糊答复的可能，等于不承认对方的内部决策流程。",
            "misread_risk": "日本企业的稟議流程通常无法在几天内完成；硬性期限会直接触发拒绝。",
            "why_opaque": "说话人不知道对方的决策需要跨层级书面流转。",
            "bridge": "把期限改为「我方的时间约束」并询问对方所需时间，而不是命令。",
            "evidence": ["下周一之前", "准话"],
            "confidence": 0.8,
        },
    ],
    ladder={
        "L0": SRC4,
        "R1": ("关于这次的价格，我们内部又核了一遍。受原材料成本上涨影响，"
               "目前这个数字确实已经低于我们的成本线，很难维持交付品质。\n"
               "如果贵司这边有调整空间，我们希望能在原有条件上继续合作；"
               "如果这次的预算已经定死，我们也理解，可以等下一个批次再谈。\n"
               "因为我们的排产要提前锁定，方便的话，能否在下周内告知一个大致方向？"),
        "R2": ("〇〇様\n\nいつも大変お世話になっております。\n\n"
               "今回のお見積もりの件、社内でもう一度精査いたしました。"
               "原材料価格の高騰により、現在ご提示いただいている水準では、"
               "品質を維持したままのご提供が難しい状況となっております。\n\n"
               "もし御社側でご調整の余地がございましたら、"
               "引き続き今の条件でお取引を続けさせていただければ幸いです。"
               "今期のご予算が既に確定している場合も承知しておりますので、"
               "次回のロットであらためてご相談させていただくことも可能です。\n\n"
               "生産計画の都合上、来週中を目安に方向性だけでもお聞かせいただけますと助かります。"
               "ご多忙のところ恐れ入りますが、何卒よろしくお願い申し上げます。"),
    },
    tracks={
        "business": "原文语义：低于成本无法接受，要求加价或终止，期限下周一。语义在 R 轨中完整保留。",
    },
    creator_advice=[
        {
            "issue": "「做不了」把否定归于己方意愿，对方无法在不失面子的前提下让步",
            "where": "第 1 句",
            "suggestion": "归因于客观约束（原材料成本上涨）而非主观拒绝。",
            "preserves": "保住了「这个价格不可接受」的实质，没有软化底线。",
            "cost": "多一个从句。",
            "priority": "P0",
        },
        {
            "issue": "二选一最后通牒剥夺了对方的内部协商空间，高概率直接触发退出",
            "where": "第 2 句",
            "suggestion": "改为一个主方案加一条备选路径（下一批次再谈），把决定权交回对方流程。",
            "preserves": "保住了「不加价就没有这一单」的事实，只是不再逼对方当场表态。",
            "cost": "放弃了当场拿到答复的可能。",
            "priority": "P0",
        },
        {
            "issue": "硬性期限不承认对方的稟議流程，几天内无法完成审批",
            "where": "第 3 句",
            "suggestion": "把期限表述为我方的排产约束，并问对方需要多久，而不是命令。",
            "preserves": "保住了时间压力，只是换成了可被接受的形式。",
            "cost": "期限从确定日期变成一个区间。",
            "priority": "P1",
        },
    ],
    premises=[
        "日本企业的采购决策通常需要跨层级的书面流转，无法在几天内完成。",
        "直接的二选一在该语境中被视为施压，而非提供选择。",
        "把否定归因于客观条件，是让对方得以体面让步的标准做法。",
    ],
    caveats=[
        "R2 版本使用了日语敬语，称谓与具体职级需由用户补全后再发送——不要猜测对方职级。",
        "R2 保留了原文的全部实质内容与底线，未代用户做出任何新的承诺或让步。",
        "本例中 Friction 很低（对方完全看得懂），真正的风险由 Abrasion 承载——这正是反向模式必须换一个度量的原因。",
    ],
    needs_confirmation=["收件人的姓名与职级", "是否真的接受「下一批次再谈」这一备选路径"],
    rationale=("反向模式取 R2：Abrasion 76 属于关系风险区间，仅加缓冲（R1）不足以抵消"
               "最后通牒与硬性期限带来的压迫感，需要完整的关系语法。"),
    confidence=0.8,
)

# ===========================================================================
# 样例 05 · 家庭人情施压 → L3 叙事显化
# ===========================================================================

SRC5 = ("二姨托人带话，说表姐的婚事定在腊月，让我务必回去一趟。我说手头项目正紧，"
        "怕是抽不开身。她在电话那头顿了顿，只回了一句：你爸当年也是这么说的。"
        "我妈在旁边补了一句，随你，反正外人都看着呢。")

EX5 = dict(
    source=SRC5, audience="us-genz", target="L3", domain="literary",
    register="casual", context_density="high",
    hotspots=[
        {
            "fragment": "二姨", "class": "PRESUPPOSITION", "severity": 4,
            "literal_reading": "一位姨妈，英译为 aunt。",
            "intended_reading": "母亲的姐妹中排行第二者。排行与父系／母系归属在称谓里同时编码，"
                                "决定了她有多大分量来施加这个要求。",
            "misread_risk": "译成 aunt 后读者不理解为什么一位旁系亲属的口信具有强制力。",
            "why_opaque": "英语亲属系统不区分父母系与排行，信息在翻译中必然丢失。",
            "bridge": "首次出现时用一句话点明她在家族中的位置，而不是逐字解释称谓系统。",
            "evidence": ["二姨", "表姐"],
            "confidence": 0.85,
        },
        {
            "fragment": "托人带话", "class": "HIERARCHY", "secondary_classes": ["FACE"],
            "severity": 4,
            "literal_reading": "请别人转达了一条消息——一个中性的沟通方式。",
            "intended_reading": "不直接开口而经第三方传达。这既加重了分量（惊动了别人），"
                                "也给双方留了退路：正式拒绝的对象不是她本人。",
            "misread_risk": "读者以为只是随口带的话，从而低估后面冲突的烈度。",
            "why_opaque": "传话这一动作本身携带关系信号，字面只是一次消息传递。",
            "bridge": "外化为可见的代价——写出那个传话的人是谁、为此绕了多远。",
            "evidence": ["托人带话"],
            "confidence": 0.8,
        },
        {
            "fragment": "顿了顿", "class": "ELLIPSIS", "severity": 3,
            "literal_reading": "她停顿了一下。",
            "intended_reading": "停顿是这通电话的转折点：她放弃了继续劝，换成了施压。",
            "misread_risk": "读成语气自然，错过态度切换的那一刻。",
            "why_opaque": "留白要求读者自行补全，低语境阅读习惯会直接略过空白。",
            "bridge": "在停顿处给一个可见的细节（背景音、呼吸），让沉默有长度。",
            "evidence": ["在电话那头顿了顿"],
            "confidence": 0.8,
        },
        {
            "fragment": "你爸当年也是这么说的", "class": "SUBTEXT",
            "secondary_classes": ["HIERARCHY"], "severity": 5,
            "literal_reading": "陈述一件关于父亲的往事。",
            "intended_reading": "以父辈的失信先例施压。它不指责你现在做错了什么，"
                                "而是断言你正在变成一个家族里已有定论的角色——这比直接责备更难反驳。",
            "misread_risk": "读成怀旧或闲聊，从而完全错过本段的情绪高点与人物动机。",
            "why_opaque": "指责被包装成陈述句，且依赖读者知道父亲那件事的结局，"
                          "而文中并未交代。",
            "bridge": "补一句最短的前情，让读者知道父亲当年也说过类似的话、后来没有回去。",
            "evidence": ["你爸当年也是这么说的"],
            "confidence": 0.85,
        },
        {
            "fragment": "随你", "class": "SUBTEXT", "severity": 4,
            "literal_reading": "由你决定——听起来像是尊重你的选择。",
            "intended_reading": "不满，且已放弃沟通。字面把决定权交出去，实际是把责任交出去。",
            "misread_risk": "读成母亲松口了，于是读者预期冲突到此结束——而实际上它刚升级。",
            "why_opaque": "授权形式承载拒绝含义，字面无任何否定成分。",
            "bridge": "译文中保留这句的简短，但在紧随其后的动作里写出她并没有真的放手。",
            "evidence": ["随你", "反正外人都看着呢"],
            "confidence": 0.85,
        },
        {
            "fragment": "反正外人都看着呢", "class": "FACE", "severity": 5,
            "literal_reading": "别人也在看着——一句关于旁观者的陈述。",
            "intended_reading": "把争议从「你要不要回去」偷换成「家族会不会丢脸」。"
                                "在这套逻辑里，把内部分歧暴露给外人是独立于分歧本身的、更严重的过错。",
            "misread_risk": "西方读者会问「别人怎么想关你什么事」，从而认为人物在无理取闹，"
                            "整段的压迫感失效。",
            "why_opaque": "它诉诸的是一个读者不共享的前提：个人行为的评价单位是家庭而非个人。",
            "bridge": "不要解释面子概念，改为外化后果——写出如果不回去，谁会在什么场合被问起。",
            "evidence": ["反正外人都看着呢"],
            "confidence": 0.9,
        },
    ],
    ladder={
        "L0": SRC5,
        "L2": ("我母亲的二姐托人捎来口信，说我表姐的婚礼定在农历腊月，要我务必回去一趟。"
               "我说手头项目正紧，恐怕抽不开身。她在电话那头停了一下，只回了一句："
               "你爸当年也是这么说的。我妈在旁边补了一句：随你——反正外人都看着呢。"),
        "L3": ("消息是托人捎来的，不是她自己打的电话：母亲的二姐，家里排行第二，"
               "说话向来有分量。表姐的婚礼定在腊月，年前，那是一年里最不能缺席的时段。\n"
               "我说项目正紧，抽不开身。\n"
               "电话那头停了一下。背景里有电视的声音。然后她说：你爸当年也是这么说的。\n"
               "她没有说父亲后来回去没有。她不需要说——那件事家里人人都知道结局，"
               "而她刚刚把我放进了同一个位置。\n"
               "我妈在旁边补了一句：随你。\n"
               "然后是那半句真正的话：反正外人都看着呢。在这个家里，"
               "缺席不是我一个人的事——它会在往后每一场婚宴上，由别人替我们解释。"),
    },
    tracks={
        "narrative": "见 L3 叙事显化轨。",
        "annotated": "二姨＝母系排行第二；腊月＝年前；外人看着＝家族声誉优先于个人选择。",
    },
    power_map={
        "speaker": "二姨（母系长辈）与母亲",
        "addressee": "叙述者（晚辈）",
        "relation": "长辈对晚辈，且经第三方传话加重分量",
        "who_holds_floor": "二姨——她决定何时从劝说切换为施压",
        "face_at_stake": "整个家庭在熟人网络中的体面，而非某个人的情绪",
        "obligation_flow": "晚辈对家族的出席义务；托人传话又追加了一笔对传话人的人情",
    },
    premises=[
        "亲属称谓编码排行与父母系归属，二者共同决定说话人的分量。",
        "腊月（年前）是返乡义务最强的时段，婚礼排在此时并非偶然。",
        "婚姻是家族事务，旁系亲属的出席是义务而非选择。",
        "把家庭内部分歧暴露给外人，是独立于分歧本身的、更严重的过错。",
    ],
    creator_advice=[
        {
            "issue": "「你爸当年也是这么说的」依赖一段文中从未交代的前情，"
                     "海外读者读到的只是一句没有攻击性的陈述",
            "where": "第 3 句",
            "suggestion": "补一句最短的前情——父亲当年说过同样的话、后来没有回去。不要解释它的含义。",
            "preserves": "保住了这句话的杀伤力来自「不说破」，而不是来自控诉。",
            "cost": "增加一行，节奏略缓。",
            "priority": "P0",
        },
        {
            "issue": "「外人都看着呢」诉诸一个读者不共享的前提，容易被读成人物在无理取闹",
            "where": "末句",
            "suggestion": "外化为具体后果：写出往后哪一场合、由谁替这家人解释缺席。",
            "preserves": "保住了压力的来源是群体评价，而不是母亲个人的情绪。",
            "cost": "把一个凝练的短句展开成一个从句。",
            "priority": "P0",
        },
        {
            "issue": "「托人带话」的分量在译文中会蒸发，读者以为只是一条随口的消息",
            "where": "第 1 句",
            "suggestion": "写出传话这件事本身的代价——谁跑了这一趟。",
            "preserves": "保住了「惊动了别人」这一层，它是后面所有压力的起点。",
            "cost": "无。",
            "priority": "P1",
        },
    ],
    caveats=[
        "L3 版本补入的父亲前情属于改写而非翻译，需作者确认是否与全书设定一致。",
        "本段为节选；若前文已交代父亲那件事，第一条建议的优先级应下调。",
    ],
    rationale=("取 L3：阻抗从 67 降到 28，保真仍有 86。这段的障碍集中在共识预设（P=22.3）而非修辞，"
               "补前提比改写措辞更有效，因此 L2 的轻度显化不够、L4 的功能化又会把人情压力抽干。"),
    confidence=0.85,
)

EXAMPLES = [
    ("01-workplace-hedged-rejection", "职场含蓄否决 → L4 功能轨", EX1),
    ("02-wuxia-farewell", "武侠送别 → L3 叙事显化", EX2),
    ("03-jp-business-email", "日本客户邮件 → L5 机读轨", EX3),
    ("04-reverse-blunt-to-jp", "反向：直球中文 → R2 关系化", EX4),
    ("05-family-obligation", "家庭人情施压 → L3 叙事显化", EX5),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    failures = 0
    for slug, title, spec in EXAMPLES:
        spec = dict(spec)
        source = spec.pop("source")
        doc = assemble(source=source, **spec)

        out_dir = os.path.join(ROOT, "examples", slug)
        tmp = os.path.join(ROOT, ".example.tmp.json")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)

        res = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "validate.py"), "--file", tmp],
            capture_output=True, text=True,
        )
        status = "✓" if res.returncode == 0 else "✗"
        print(f"{status} {slug:32s} friction={doc['diagnosis']['friction_score']:3d} "
              f"({doc['diagnosis']['friction_band']}) target={doc['meta']['ladder_target']}")
        if res.returncode != 0:
            failures += 1
            print(res.stdout)
        elif res.stdout.strip() and "警告" in res.stdout:
            print("   " + res.stdout.strip().replace("\n", "\n   "))

        if args.check:
            os.remove(tmp)
            continue

        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "input.txt"), "w", encoding="utf-8") as fh:
            fh.write(source + "\n")
        with open(os.path.join(out_dir, "output.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

        for fmt, name in (("md", "report.md"), ("html", "report.html")):
            res = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "render_report.py"),
                 "--file", os.path.join(out_dir, "output.json"), "--format", fmt,
                 "-o", os.path.join(out_dir, name)],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                failures += 1
                print(f"   渲染 {fmt} 失败：{res.stderr}")

        with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# {title}\n\n"
                     f"| 文件 | 内容 |\n|---|---|\n"
                     f"| `input.txt` | 原文 |\n"
                     f"| `output.json` | 完整 transcompile.v1 输出，通过 `scripts/validate.py` 校验 |\n"
                     f"| `report.md` | Markdown 报告 |\n"
                     f"| `report.html` | 自包含 HTML 报告（含热力图，可离线打开） |\n\n"
                     f"复现：\n\n```bash\n"
                     f"python3 scripts/probe.py --text-file examples/{slug}/input.txt \\\n"
                     f"  --audience {doc['meta']['audience']} "
                     f"--target-level {doc['meta']['ladder_target']} --format md\n"
                     f"python3 scripts/validate.py --file examples/{slug}/output.json\n```\n\n"
                     f"> 数值由 `scripts/probe.py` 的评分内核算出，语义内容为模型产出。\n"
                     f"> 本目录由 `evals/build_examples.py` 生成，请勿手工编辑。\n")
        os.remove(tmp)

    print(f"\n{len(EXAMPLES) - failures}/{len(EXAMPLES)} 个样例通过")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
