# 07 · 输出契约

> 需要产出严格 JSON 时读本文件。Schema 在 `schemas/transcompile.v1.schema.json`。
> 对话场景请直接看 §4 的 Markdown 呈现规范，不要把 JSON 倒给用户。

---

## 1. 什么时候输出 JSON

| 情况 | 输出 |
|---|---|
| 用户在对话里问"他什么意思" | **Markdown**（§4） |
| 用户说"给我 JSON""要结构化""喂给系统" | **纯 JSON**，无前后缀 |
| 用户在跑管线 / 传了 `--json` | **纯 JSON** |
| 用户要报告文件 | JSON → `render_report.py` → Markdown/HTML |

纯 JSON 模式下**不要**加 ```json 围栏之外的任何文字，不要加"以下是结果"。

---

## 2. 必填与选填

**必填**：`schema`、`meta`、`diagnosis`、`tracks`、`confidence`

**条件必填**
- `meta.audience = ai-agent` 或 `ladder_target = L5` → `machine_readable` 必填
- `meta.domain ∈ {screenplay, webnovel, social}` → `creator_advice` 必填，且至少 1 条
- `ladder_target ∈ {R1,R2,R3}` → `ladder.R*` 必填
- 文本 ≥ 200 字 → `trade_off.curve` 必填（这是用户选停点的依据）

**允许省略**：`ladder` 中未请求的级别、`power_map`（无明显位阶时）、`unstated_premises`（为空时）。

---

## 3. 字段填写纪律

### `diagnosis.hotspots[]`
- `span` 的偏移量是**字符索引**（Python `str` 索引，非字节）。由 `probe.py` 给出；人工填写时若无把握则**省略 `span` 只填 `text`**——宁可缺 span，不可给错 span（Web 端会据此高亮，错位会毁掉整个报告）。
- `misread_risk` 必须写**后果**，不是"可能产生误解"。
  - ❌ "读者可能会误解这句话"
  - ✅ "对方会继续等待会议邀请并保留资源投入，错过调整窗口"
- `bridge` 必须**可执行**。
  - ❌ "建议增加背景说明"
  - ✅ "在第 2 段前加一句：'这一行里，牵线的人不收钱，但你欠他一次。'"
- `evidence` 是原文片段，**逐字引用**，不要转述。

### `diagnosis.subscores`
五项必须全给，允许为 0。数值范围见 Schema（P/S ≤25，M ≤20，H/E ≤15）。
`raw_score` 应等于五项之和（允许 ±1 的取整误差）。

### `machine_readable`
- `stance` 枚举外的值一律非法。拿不准用 `defer`。
- `confidence < 0.6` → `escalation_needed` 必须 `true`。
- `evidence` 至少一条，否则 Schema 校验失败。
- 时间：`"回头""改天""尽快"` → `due: null` + `constraints: ["未给出具体时间"]`。

### `ladder.L1`
- `text` 必须与 `L0` **逐字一致**（含标点）。校验脚本会比对。
- 每条 `note` ≤ 120 字符（Schema 强制），实际建议 ≤ 40 字。

### `confidence.caveats`
以下情况**必须**写入 caveats：
- 未执行 `probe.py`
- 补了无文本证据的主语
- 受众无专属档案，按 `global-english` 处理
- 涉及具体个人而非群体
- 使用了半衰期短的圈层黑话（R3）
- 文本 < 40 字，未计算总分

---

## 4. 对话场景的 Markdown 呈现规范

四段式，顺序固定。**不要加目录、不要加"以下是分析"开场白。**

```markdown
**诊断**｜语境浓度：高 · 文化阻抗 72/100（对 de-business，高阻）· 取 L4 保真 31/100

**未说出口的三件事**
1. 「回头再找时间慢慢对齐」= 议题到此为止，不会再开会。
2. 「出发点是好的，年轻人有冲劲」= 先给台阶，后面的否定才说得出口。
3. 称呼「小李」而不是名字 —— 这一句是当着全组说的，位阶本身就是压力。

**低语境版（L4）**
【结论】方案不通过。
【依据】给出的理由是跨部门协作细节；这是体面理由，真实理由未言明。
【边界】不会另约时间；本次会议此议题结束。
【动作】不要等会议邀请。若仍要推进，换切入点或换决策人。

**如果你要回复他（R1）**
> 张总，谢谢您点出跨部门这块。我先把协作路径梳理清楚，等成形了再向您汇报。

**取舍**：L4 把阻抗从 72 压到 21，但保真只剩 35——原话里的分寸感全没了。
只想读懂、不想丢语感的话，L1 注释版更合适，要我出一版吗？
```

要点：
- 数值**一行内给全**（阻抗 + 受众 + 保真），不要分散在各处
- 「未说出口的」是用户最想看的部分，放第二段
- 低语境版用 L4 的固定四段结构
- `confrontation ≤ 0.30` 的受众必须附 R1 回复草稿（见 `05` §L4）
- 结尾给一句取舍说明 + 一个可选的下一步，**只给一个**

---

## 5. 版本与兼容

- `schema` 字段固定 `"context-transcompiler/v1"`。
- v1 内只做**向后兼容的增量**（新增可选字段）。
- 破坏性变更走 `v2`，`v1` 保留至少一个 minor 周期。
- Web 版（ContextBridge）与 Skill 版共用本 Schema —— 这是两者能对齐的基础，改动需同步。

---

## 6. 校验

```bash
python3 scripts/validate.py --file result.json
```

零依赖，校验内容：
1. JSON Schema 结构（类型、必填、枚举、范围、additionalProperties）
2. 业务规则：
   - `raw_score` ≈ 五项子分之和
   - `fidelity_at_target + loss_at_target = 100`
   - `L1.text == L0`（两者都存在时）
   - `confidence < 0.6 → escalation_needed == true`
   - `span.end > span.start`，且 `text` 与 `L0[start:end]` 一致（L0 存在时）
   - `friction_band` 与 `friction_score` 的分带一致

退出码：`0` 通过，`1` 校验失败，`2` 参数错误。
