# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-30

首个完整版本。

### 技能主体
- `SKILL.md`：七步工作流（锁参数 → 预扫描 → 诊断 → 评分 → 编译 → 创作者建议 → 渲染）与七条硬性约束
- 七份 `reference/` 知识库，按需加载

### 转译模型
- 正向语境阶梯 `L0`–`L5`：原样 / 注释轨 / 轻度显化 / 叙事显化 / 功能化 / 机读化
- 反向语境收敛 `R1`–`R3`：得体化 / 关系化 / 圈层化
- 六类语义探针：`PRESUPPOSITION` `SUBTEXT` `FACE` `HIERARCHY` `MOTIF` `ELLIPSIS`
- `machine_readable.stance` 六值枚举，为下游 Agent 与工单系统提供可消费输出

### 评分内核
- 五维子分 P/S/M/H/E 与文化阻抗 Friction
- **语用层与事实层拆分**：P 维不随受众 explicitness 调制
- **加权单维极值规则**：防止一维顶格的高危文本被求和稀释
- **密度归一**：M 与 P 按 500 字参考窗归一
- 韵味损耗 Loss / 保真度 Fidelity 与阶梯取舍曲线
- 反向模式专用的 **Abrasion 得罪风险**

### 脚本（零第三方依赖）
- `probe.py`：字符级 span 偏移量、五维子分、阻抗曲线、直白度与得罪风险、书写系统检测
- `validate.py`：JSON Schema 子集校验 + 九条业务规则
- `render_report.py`：Markdown 与自包含 HTML 报告（热力图、双仪表盘、阶梯对照，明暗主题）

### 数据
- 16 个受众档案，`explicitness` / `confrontation` / `shared_ground` 三参数建模
- 六套词典：缓冲语（含日/韩/英/阿）、文化意象（传统/成语/东亚/圈层）、面子位阶（含姓氏白名单正则）、留白、共识预设、直白度

### 工程
- 13 条校准回归用例 + 确定性检查 + 长文本性能哨兵
- 输入归一化：清理零宽字符与 BOM（粘贴自网页/PDF 的文本常夹带，会静默切断词典匹配）；
  `probe.py` 返回归一化后的 `source_text` 作为 span 基准
- 五个端到端样例，span 与数值由脚本生成
- GitHub Actions CI
