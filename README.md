# 语境平抑器 · Context Transcompiler

> 一个 Claude Agent Skill：在高语境与低语境之间**双向**转译文本。
> 不做字面翻译，做文化维度的降维展开与语义补全。

```
高语境源文  ──诊断──►  语境 AST（潜台词 / 意象 / 位阶 / 留白 / 预设）
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
          正向 L0→L5 展开              反向 R1→R3 收敛
        （解压缩：把冰山写出来）      （压缩：给直球加缓冲）
```

核心原则：**不删除压缩包里的内容，只在包裹外面贴一张清晰的标签。**

---

## 它解决什么

高语境文本的信息不在字面上，而在预设背景、潜台词、面子策略、位阶关系与留白里。直译成低语境语言，丢掉的不是词，是意思。

| 场景 | 现在会发生什么 | 这个技能做什么 |
|---|---|---|
| 德国工程师收到"原则上支持，但有些技术难点" | 读成"通过了"，继续投入 | 判定 `stance: reject`，置信度 0.85，附证据 |
| 网文出海遇冷 | 以为是故事不好 | 指出前三章每千字 9 处断点，逐条给桥接方案 |
| 你要拒绝日本客户 | 直球发出去，关系没了 | Abrasion 76/100，给出保留底线的 R2 版本 |
| Agent 要把邮件写进 CRM | 把"検討させていただきます"标成"进行中" | 输出枚举化的 `stance` + `evidence`，可直接消费 |

---

## 两个数，不是一个

只报"文化阻抗"会诱导用户一路降维、把原作韵味删空。所以永远同时报两个：

```
        Friction ↓                                  Loss ↑
   L0 ──────────────────────────────────────────────────────► L5
   原样                                                    机读化
   100% 保真                                            0 歧义
   圈外人看不懂                                      圈内人索然无味
```

用户要做的决策不是"降到最低"，而是**在自己的场景里选一个停点**。

一段 65 字的武侠送别（`examples/02-wuxia-farewell`），对北美 Z 世代受众：

| 级别 | | 阻抗 | 保真 | |
|---|---|---:|---:|---|
| L0 | 原样 | 52 | 100 | 看不懂 |
| L1 | 注释轨 | 42 | 95 | 正文一字不动，只加浮层注释 |
| **L2** | **轻度显化** | **35** | **85** | **脚本推荐的停点** |
| L3 | 叙事显化 | 22 | 65 | 心理外化为动作；本例实际采用 |
| L4 | 功能化 | 14 | 25 | 只剩信息 |
| L5 | 机读化 | 5 | 5 | 给机器读 |

脚本按"阻抗与保真乘积最大"推荐 L2，本例仍选了 L3——因为意象密集（M 顶格），L2 的轻度显化不足以让折柳与江湖落地。**推荐值是默认建议，场景才是决定因素**：商务恒取 L4/L5，机器恒取 L5。

---

## 安装

### 作为 Claude Skill

```bash
git clone https://github.com/<your-account>/context-transcompiler.git
cp -r context-transcompiler ~/.claude/skills/
```

之后在对话里说"用语境平抑器分析这段话"，或任何触发词（潜台词、言外之意、文化阻抗、出海本地化、他到底什么意思……）即可唤起。

### 只用评分内核

脚本零第三方依赖，`python3` 即可运行，可独立嵌入任何管线。

```bash
python3 scripts/probe.py --text "这个方案回头再说吧" --audience de-business --format md
```

---

## 快速开始

```bash
# 1. 预扫描：字符级 span + 五维子分 + 阻抗/保真曲线
python3 scripts/probe.py \
  --text-file examples/01-workplace-hedged-rejection/input.txt \
  --audience de-business --target-level L4 --format md

# 2. 校验模型产出的结构化结果
python3 scripts/validate.py --file result.json

# 3. 渲染成可交付的报告（预扫描结果可直接管道进来，自带 source_text）
python3 scripts/render_report.py --file result.json --format html -o report.html
python3 scripts/probe.py --text-file in.txt --audience us-genz | \
  python3 scripts/render_report.py --format html -o report.html

# 列出全部受众档案
python3 scripts/probe.py --list-audiences
```

`examples/` 下有四个完整样例，每个含原文、结构化输出、Markdown 与 HTML 报告：

| 样例 | 场景 | 目标 |
|---|---|---|
| `01-workplace-hedged-rejection` | 职场含蓄否决 | L4 功能轨 + L1 注释轨 |
| `02-wuxia-farewell` | 武侠送别出海 | L3 叙事显化 + 创作者建议 |
| `03-jp-business-email` | 日本客户婉拒邮件 | L5 机读轨（`stance: reject`） |
| `04-reverse-blunt-to-jp` | 直球中文发给日方 | R2 关系化（Abrasion 76→安全） |

---

## 设计要点

### 六类语义探针

| 代码 | 类别 | 一句话 |
|---|---|---|
| `PRESUPPOSITION` | 共识预设 | 作者默认你已经知道的事 |
| `SUBTEXT` | 潜台词 | 字面义 ≠ 实际义 |
| `FACE` | 面子策略 | 给台阶、留余地、不驳面子 |
| `HIERARCHY` | 位阶与人情 | 谁能说话、谁欠谁、称谓里的权力 |
| `MOTIF` | 文化意象与典故 | 江湖、读空气、锅气、内卷 |
| `ELLIPSIS` | 留白与省略 | 零主语、半截话、沉默、"呵呵" |

每个热点必须写清四件事：字面会读成什么、实际在说什么、**读错的后果**、怎么桥接。

### 受众是两个正交参数，不是一个刻度

| 参数 | 含义 |
|---|---|
| `explicitness` | 信息要不要写明白 |
| `confrontation` | 负面意见能不能直说 |

英国 `explicitness 0.78 / confrontation 0.25`——合同条款写得清清楚楚，但 "quite interesting" 的意思是不行。用单一维度建模英国，任何一头都会错。

### 评分内核的三条规则

1. **语用层 vs 事实层**。S/M/H/E 随受众调制（高语境受众确实更会读空气）；**P 不调制**——日本读者再善于读空气，也不会知道"编制"是什么。效果：同一段含"编制""宅基地"的文本，对日本和德国受众都是 42 分。
2. **加权单维极值**。一维顶格时，纯求和会稀释风险。PDF 里那段"出发点是好的……回头再对齐"广度和只有 32，但 S 顶格 → 73 分。
3. **密度归一**。M 与 P 是计数型子分，按 500 字参考窗归一，只上抬短密文本。

完整推导与算例见 [`reference/03-friction-scoring.md`](reference/03-friction-scoring.md)。

### 反向模式用另一个数

直球中文发给日本客户，Friction 只有 8——对方完全看得懂。问题不是看不懂，是看懂了会不高兴。

```
Abrasion = round( 100 × directness_index × (1 − audience.confrontation) )
```

| 受众 | Friction | Abrasion |
|---|---|---|
| `jp-business` | 8 | **76** |
| `nl` | 13 | **4** |

**Friction 几乎一样，Abrasion 差 19 倍。**

---

## 目录

```
SKILL.md                      技能主体：工作流、触发条件、硬性约束
reference/
  01-context-theory.md        霍尔理论、成因、AI 时代的语境重塑、不做优劣评判的红线
  02-diagnostic-taxonomy.md   六类探针的识别标记、误读风险与展开式
  03-friction-scoring.md      阻抗/损耗/得罪风险的完整算法与算例
  04-audience-profiles.md     16 个受众档案与参数使用规则
  05-context-ladder.md        L0–L5 与 R1–R3 各级的「允许/禁止」清单
  06-domain-playbooks.md      职场/商务/剧本/网文/字幕/社媒/反向 七个领域剧本
  07-output-contract.md       JSON 与 Markdown 两种呈现规范
schemas/transcompile.v1.schema.json
scripts/
  probe.py                    确定性预扫描：span 偏移量 + 五维子分 + 曲线
  validate.py                 零依赖 Schema + 业务规则校验
  render_report.py            JSON → Markdown / 自包含 HTML 热力图报告
  lexicon/                    缓冲语 / 意象 / 面子位阶 / 留白 / 预设 / 直白度
  data/audiences.json         受众档案
examples/                     四个端到端样例
evals/
  cases.jsonl                 12 条校准回归用例
  run_evals.py                评分内核回归测试
  build_examples.py           样例生成器（span 与数值由脚本算，不手写）
```

---

## 工程约定

- **脚本零第三方依赖**，只用标准库，任何有 `python3` 的地方都能跑。
- **确定性内核要能扫完整本书。** 30 万字约 310ms、15 万字约 140ms（无 LLM 调用）。`evals/run_evals.py` 里有性能哨兵，超过 5 秒即报警——早期 `_dedupe` 是 O(n²)，15 万字要跑 31.8 秒。
- **span 偏移量由脚本算，不手写**。`validate.py` 会比对 `text` 与 `L0[start:end]`，错位直接报错——Web 端据此高亮，偏一个字整张图就废了。
- **样例由 `evals/build_examples.py` 生成**，语义内容手写、数值与偏移量脚本算，再过一遍校验。不要手工编辑 `examples/` 下的文件。
- **改了词典或公式就跑 `evals/run_evals.py`**。12 条用例断言的是区间与相对关系，不是精确值。

```bash
python3 evals/run_evals.py        # 回归测试
python3 evals/build_examples.py   # 重建样例
```

---

## 边界与限制

- 评分是**可复现的启发式**，不是经过大样本验证的心理测量量表。价值在**相对比较**（改写前后、A 版 B 版、这一段那一段），不在绝对值。
- 受众档案是**群体先验**，不适用于判断具体某个人。涉及个体时置信度下调并注明。
- 词典是字面匹配，**召回必然不全**——"折柳"收录了，"折了一枝柳"靠 variants 覆盖，再变形就得靠模型在语义层补齐。预扫描给的是**候选**，不是结论。
- 零主语启发式按中文校准，非中文输入自动跳过并在 caveats 注明。
- **不做优劣评判。** 高语境不等于落后或虚伪，低语境不等于冷漠。工具报告的是"对目标受众的传达成本"，不是"文本质量"。

---

## 致谢与理论来源

- Edward T. Hall, *Beyond Culture* (1976) — 高低语境概念
- Geert Hofstede — 文化维度理论
- Erin Meyer, *The Culture Map* — Communicating / Evaluating 标尺，本工具 `explicitness` 与 `confrontation` 两参数的校准基础

受众档案中的数值是**本工具的建模参数**，参考上述框架校准而来，非任何框架的原始数据，亦非经验测量值。

## 许可

MIT，见 [LICENSE](LICENSE)。
