**English** · [简体中文](README.zh-CN.md)

# Context Transcompiler · 语境平抑器

> A Claude Agent Skill that transcompiles text **in both directions** between high-context and low-context communication.
> Not literal translation — dimensional unpacking and semantic completion of what a culture leaves unsaid.

```
high-context source ──diagnose──►  context AST
                                   (subtext / motif / status / ellipsis / presupposition)
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                    forward  L0→L5                reverse  R1→R3
                 (decompress: write the         (compress: cushion
                  iceberg out in full)           the blunt version)
```

Guiding principle: **don't delete what's inside the compressed archive — put a legible label on the outside of it.**

---

## The problem

In high-context writing the information isn't on the surface. It lives in presupposed background, subtext, face-saving strategy, status relations and deliberate silence. Translate it literally into a low-context language and what you lose isn't words — it's meaning.

| Situation | What happens today | What this skill does |
|---|---|---|
| A German engineer reads "we support this in principle, though there are some technical difficulties" | Reads it as approval and keeps investing | Returns `stance: reject`, confidence 0.85, with the evidence spans |
| A web novel flops in translation | The team assumes the story is weak | Flags 9 comprehension breaks per 1,000 characters in the first three chapters, each with a concrete bridge |
| You need to turn down a Japanese client | The blunt version goes out; the relationship doesn't survive it | Abrasion 76/100, plus an R2 rewrite that keeps your actual bottom line |
| An agent files a client email into the CRM | Marks 「検討させていただきます」 as "in progress" | Emits an enumerated `stance` plus `evidence` that downstream systems can consume directly |

---

## Two numbers, not one

Reporting "cultural friction" alone pushes people to flatten everything and strip the original of whatever made it worth reading. So the skill always reports two:

```
        Friction ↓                                     Loss ↑
   L0 ─────────────────────────────────────────────────────────► L5
   verbatim                                           machine-readable
   100% fidelity                                           0 ambiguity
   outsiders can't follow it                  insiders find it lifeless
```

The decision isn't "how low can I get the friction" — it's **where to stop, for this particular job**.

A 65-character wuxia farewell scene (`examples/02-wuxia-farewell`), for a North American Gen Z audience:

| Level | | Friction | Fidelity | |
|---|---|---:|---:|---|
| L0 | Verbatim | 52 | 100 | Unreadable to the target |
| L1 | Annotated | 42 | 95 | Body text untouched; notes in an overlay |
| **L2** | **Softly explicit** | **35** | **85** | **What the script recommends** |
| L3 | Narrative explicit | 22 | 65 | Interiority externalised into action; what this example actually ships |
| L4 | Functional | 14 | 25 | Information only |
| L5 | Machine-readable | 5 | 5 | For agents and ticketing systems |

The script recommends L2 by maximising friction × fidelity, but this example ships L3: the passage is motif-dense (M is maxed out), and L2's light touch isn't enough to land the willow-branch farewell or *jianghu*. **The recommendation is a default; the use case is what decides.** Business always takes L4/L5, machines always take L5.

---

## Install

### As a Claude Skill

```bash
git clone https://github.com/kreven175/context-transcompiler.git
cp -r context-transcompiler ~/.claude/skills/
```

Then ask for it in conversation — "run this through the context transcompiler", or any trigger phrase (subtext, what did they actually mean, cultural friction, localisation for international release, 潜台词, 言外之意, 出海本地化).

### Scoring kernel only

The scripts have zero third-party dependencies. Anywhere `python3` runs, they run — drop them into any pipeline.

```bash
python3 scripts/probe.py --text "这个方案回头再说吧" --audience de-business --format md
```

---

## Quick start

```bash
# 1. Pre-scan: character-level spans, five sub-scores, the friction/fidelity curve
python3 scripts/probe.py \
  --text-file examples/01-workplace-hedged-rejection/input.txt \
  --audience de-business --target-level L4 --format md

# 2. Validate a model's structured output
python3 scripts/validate.py --file result.json

# 3. Render a deliverable report
#    (pre-scan output pipes straight in — it carries its own source_text)
python3 scripts/render_report.py --file result.json --format html -o report.html
python3 scripts/probe.py --text-file in.txt --audience us-genz | \
  python3 scripts/render_report.py --format html -o report.html

# List every audience profile
python3 scripts/probe.py --list-audiences
```

`examples/` holds five end-to-end cases, each with the source text, structured output, and Markdown + HTML reports:

| Example | Scenario | Target |
|---|---|---|
| `01-workplace-hedged-rejection` | A hedged rejection in a Chinese workplace | L4 functional + L1 annotated |
| `02-wuxia-farewell` | A wuxia farewell scene going abroad | L3 narrative + creator advice |
| `03-jp-business-email` | A Japanese client's polite refusal | L5 machine-readable (`stance: reject`) |
| `04-reverse-blunt-to-jp` | A blunt Chinese message aimed at a Japanese counterparty | R2 relational (Abrasion 76 → safe) |
| `05-family-obligation` | Family obligation and social pressure | L3 narrative + presupposition bridging |

---

## Design notes

### Six semantic probes

| Code | Class | In one line |
|---|---|---|
| `PRESUPPOSITION` | Presupposed common ground | What the author assumes you already know |
| `SUBTEXT` | Subtext | Literal meaning ≠ actual meaning |
| `FACE` | Face strategy | Offering an out, leaving room, not contradicting in public |
| `HIERARCHY` | Status and obligation | Who may speak, who owes whom, the power encoded in forms of address |
| `MOTIF` | Culture-bound motifs | *jianghu*, reading the air, wok hei, *neijuan* |
| `ELLIPSIS` | Ellipsis and silence | Dropped subjects, half-sentences, silence, a bare "呵呵" |

Every hotspot must answer four questions: what an outsider reads literally, what the text actually says, **what it costs to get it wrong**, and how to bridge it.

### An audience is two orthogonal parameters, not one dial

| Parameter | Meaning |
|---|---|
| `explicitness` | Does information have to be stated outright |
| `confrontation` | Can a negative opinion be said to someone's face |

The UK sits at `explicitness 0.78 / confrontation 0.25` — contract terms are spelled out precisely, but "quite interesting" means no. Model the UK on a single axis and you get one end or the other wrong.

### Three rules in the scoring kernel

1. **Pragmatic layer vs factual layer.** S/M/H/E scale with the audience (high-context readers really are better at reading between the lines); **P does not** — a Japanese reader can be excellent at reading the air and still have no idea what 编制 (a permanent state payroll post) is. Result: the same passage containing 编制 and 宅基地 scores 42 for both a Japanese and a German audience.
2. **Weighted single-dimension peak.** When one dimension maxes out, a plain sum dilutes the risk. The "the intention behind it is good… let's align on this later" passage sums to only 32 across dimensions, but S is maxed → 73.
3. **Density normalisation.** M and P are count-based, so they're normalised against a 500-character reference window — this only lifts short, dense passages; it never penalises long ones.

Full derivation and worked examples in [`reference/03-friction-scoring.md`](reference/03-friction-scoring.md).

### Reverse mode needs a different number

Send a blunt Chinese message to a Japanese client and Friction is only 8 — they understand it perfectly well. The problem isn't comprehension. It's that they understood.

```
Abrasion = round( 100 × directness_index × (1 − audience.confrontation) )
```

| Audience | Friction | Abrasion |
|---|---|---|
| `jp-business` | 8 | **76** |
| `nl` | 13 | **4** |

**Friction is nearly identical. Abrasion differs by 19×.**

---

## Layout

```
SKILL.md                      The skill itself: workflow, triggers, hard constraints
reference/
  01-context-theory.md        Hall's theory, origins, context in the AI era,
                              and the no-value-judgements red line
  02-diagnostic-taxonomy.md   Markers, misreading risks and expansions for the six probes
  03-friction-scoring.md      Full algorithm and worked examples for friction / loss / abrasion
  04-audience-profiles.md     16 audience profiles and the rules for using their parameters
  05-context-ladder.md        What each level L0–L5 and R1–R3 may and may not do
  06-domain-playbooks.md      Workplace, business, screenplay, web novel,
                              subtitles, social, reverse
  07-output-contract.md       JSON and Markdown presentation rules
  08-low-context-output.md    Acceptance checklist for the output itself: is it
                              actually low-context? Six Chinese→low-context
                              structural conversions, and the bar for explanations
schemas/transcompile.v1.schema.json
scripts/
  probe.py                    Deterministic pre-scan: span offsets, sub-scores, curve
  validate.py                 Zero-dependency schema + business-rule validation
  render_report.py            JSON → Markdown / self-contained HTML heatmap report
  lexicon/                    Hedges / motifs / face+status / ellipsis /
                              presupposition / directness
  data/audiences.json         Audience profiles
examples/                     Five end-to-end cases
evals/
  cases.jsonl                 19 calibration regression cases
  run_evals.py                Scoring-kernel regression tests
  build_examples.py           Example generator (spans and numbers computed, never hand-written)
```

**A note on language.** This README and `README.zh-CN.md` are the only translated files. `SKILL.md`, everything under `reference/`, the lexicons and `CONTRIBUTING.md` are written in Chinese, deliberately: the skill's primary source language is Chinese, its lexicon entries and glosses describe Chinese usage, and the model reads those files while analysing Chinese text. Code, CLI output, the JSON schema and all field names are English. If you want to extend the skill to another source language, the lexicons and `reference/02-diagnostic-taxonomy.md` are where that work starts — see `CONTRIBUTING.md`.

---

## Engineering conventions

- **Zero third-party dependencies.** Standard library only, so the scripts run anywhere `python3` does.
- **The deterministic kernel has to scan a whole book.** ~310 ms for 300k characters, ~140 ms for 150k, with no LLM calls. `evals/run_evals.py` carries a performance sentinel that fires above 5 seconds — an early `_dedupe` was O(n²) and took 31.8 seconds on 150k characters.
- **Span offsets are computed, never hand-written.** `validate.py` compares `text` against `L0[start:end]` and fails on mismatch. The web client highlights from these offsets; one character of drift ruins the whole heatmap.
- **Examples are generated by `evals/build_examples.py`** — semantic content is written by hand, every number and offset is computed, and the result is validated. Don't hand-edit anything under `examples/`.
- **Changed a lexicon or a formula? Run `evals/run_evals.py`.** The 19 cases assert ranges and relative ordering, not exact values.

```bash
python3 evals/run_evals.py        # regression tests
python3 evals/build_examples.py   # rebuild examples
```

---

## Scope and limits

- The scores are a **reproducible heuristic**, not a psychometric instrument validated on a large sample. Their value is in **relative comparison** — before vs after a rewrite, version A vs B, this passage vs that one — not in the absolute number.
- Audience profiles are **group priors**. They don't apply to judging a specific individual; when they're used that way, lower the confidence and say so.
- The lexicons match literally, so **recall is necessarily incomplete**. 折柳 is in the lexicon; 折了一枝柳 is covered by variants; anything further from the canonical form is for the model to catch semantically. The pre-scan produces **candidates, not conclusions.**
- The dropped-subject heuristic is calibrated for Chinese. Non-Chinese input skips it automatically and says so in the caveats.
- **No value judgements.** High-context isn't backward or insincere; low-context isn't cold. What the tool reports is the cost of getting a message across to a given audience — not the quality of the text.

---

## Theoretical sources

- Edward T. Hall, *Beyond Culture* (1976) — the high/low-context distinction
- Geert Hofstede — cultural dimensions theory
- Erin Meyer, *The Culture Map* — the Communicating and Evaluating scales, which this tool's `explicitness` and `confrontation` parameters are calibrated against

The numbers in the audience profiles are **this tool's modelling parameters**, calibrated with reference to those frameworks. They are not raw data from any of them, and they are not empirical measurements.

## Licence

MIT — see [LICENSE](LICENSE).
