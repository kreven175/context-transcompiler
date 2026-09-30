# 职场含蓄否决 → L4 功能轨

| 文件 | 内容 |
|---|---|
| `input.txt` | 原文 |
| `output.json` | 完整 transcompile.v1 输出，通过 `scripts/validate.py` 校验 |
| `report.md` | Markdown 报告 |
| `report.html` | 自包含 HTML 报告（含热力图，可离线打开） |

复现：

```bash
python3 scripts/probe.py --text-file examples/01-workplace-hedged-rejection/input.txt \
  --audience de-business --target-level L4 --format md
python3 scripts/validate.py --file examples/01-workplace-hedged-rejection/output.json
```

> 数值由 `scripts/probe.py` 的评分内核算出，语义内容为模型产出。
> 本目录由 `evals/build_examples.py` 生成，请勿手工编辑。
