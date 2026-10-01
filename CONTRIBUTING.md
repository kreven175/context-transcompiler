# 参与贡献

## 改动前先读这两条

1. **不做优劣评判。** 高语境不等于落后或虚伪，低语境不等于冷漠。任何把某种沟通方式描述为"更正确"的措辞都不会被合入。见 `reference/01-context-theory.md` §4。
2. **分数的意义在相对比较。** 不要为了让某个绝对值"看起来合理"而调参，要看 `evals/run_evals.py` 里的相对关系有没有被破坏。

## 改词典

词典在 `scripts/lexicon/`，六个文件各管一类探针。

- 新增条目必须填 `strength` 与功能性 `gloss`——说明它**在句中起什么作用**，不是百科解释。
- `hedges.json` 的条目要同时给 `literal` 与 `intended`，这两个字段会直接进报告。
- `motifs.json` 的 `trap` 要写**具体的误读**（"被读成真的睡在柴火上"），不要写"可能产生误解"。
- 常见变形放 `variants`，不要新建条目——否则会被重复计数。
- 新条目与已有条目**部分重叠**也会重复计数（`_dedupe` 只消解包含关系，不消解部分重叠）。
  收作 `variants` 或改写成不重叠的形式。
- **高强度词条要考虑假阳性。** 强度 4–5 的条目如果存在常见的字面用法，
  配一条 `unless` 守卫：

  ```json
  {"term": "回头再说", "strength": 5, "...": "...",
   "unless": [{"near": ["五分钟", "一会儿", "马上", "等下"],
               "window": 24, "action": "downgrade"}]}
  ```

  `action` 取 `downgrade`（降到强度 1 并标记 `guarded`）或 `drop`（整条丢弃）。
  加守卫后务必同时加两条用例：一条验证守卫触发，一条验证**没有线索时不误伤**。
- 词条的假阳性率如果高到无法用守卫收敛，就删掉它。「四」曾因谐音忌讳入库，
  结果任何时间、楼层、数量都会命中，已移除。
- 圈层黑话（`zone: subculture`）半衰期以月计，提 PR 时请说明该词目前是否仍在活跃使用。

改完跑：

```bash
python3 evals/run_evals.py
```

## 改评分公式

公式在 `scripts/probe.py`，常数集中在文件顶部。**改了公式必须同步改 `reference/03-friction-scoring.md`**——文档与代码不一致比没有文档更糟。

三条核心规则不要轻易推翻，它们各自解决一个具体的误报：

| 规则 | 解决的问题 |
|---|---|
| 语用层 / 事实层拆分 | 日本受众的 P 维被 explicitness 折减，导致"编制"这类背景缺失被严重低估 |
| 加权单维极值 | 纯求和会把"字面肯定实为否定"稀释成 32 分 |
| 密度归一 | 60 字里 3 个意象与 3000 字里 3 个意象被同等对待 |

## 改样例

**不要手工编辑 `examples/` 下的文件。** 它们由 `evals/build_examples.py` 生成：语义内容在脚本里手写，span 偏移量与所有数值由 `probe.py` 算出，再过一遍 `validate.py`。

```bash
python3 evals/build_examples.py
```

手写 span 必错，而错位的 span 会让 Web 端的热力图整张废掉。

## 新增受众档案

在 `scripts/data/audiences.json` 增加条目，三个参数（`explicitness` / `confrontation` / `shared_ground`）必须全给，并在 `notes` 说明校准依据。同步更新 `reference/04-audience-profiles.md` 的表格。

提醒：这些是**群体先验**，不是对具体个人的断言。`notes` 里不要写成对某国人的性格描述。

## 提交前

```bash
python3 evals/run_evals.py          # 12 条校准用例
python3 evals/build_examples.py     # 重建并校验样例
```

CI 会在 Python 3.9 / 3.11 / 3.12 上跑同样的检查。脚本**只能用标准库**，不要引入第三方依赖。
