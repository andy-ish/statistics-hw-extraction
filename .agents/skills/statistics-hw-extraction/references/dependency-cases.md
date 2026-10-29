# 引用与依赖边界

## 决策规则

先阅读目标题，列出作答时实际缺失的信息，再定位引用来源。目标题中的出处链接、背景介绍或已经重述的数据，不自动构成需要额外截图的依赖。目标题明确指向供作答使用的图表时，定位并保留相应图表及必要图注。

未选题只作为材料来源：裁入必要的背景、定义、数据、表格、图和单位；不顺带布置它的其他小问。若目标题明确要使用某个小问的内容，保留该小问原文作为必要材料，不自行求解或取用书后答案。交付时说明哪些片段属于参考材料，哪些题是本次作业。

跨 Section 的引用使用章节限定 ID，并记录实际 PDF 文件页序。引用可以指向同书任何位置的习题、例题、图表或正文，不能局限于目标题相邻页。找不到时先检查完整引用、Section、题号/图号与印刷页码差异；仍缺失或有多个无法区分的候选时，说明缺哪项并询问，不交付一张明知缺材料的成品。

只对被保留片段需要的信息继续追踪引用，直到参考材料足以支持目标题。遇到循环或歧义，应检查引用是否只是出处、或是否选错同号题；无法消除时询问。不要无限递归，也不要把整条关联章节全部截图。

## 已验证 1：仅布置 SECTION 4D 第 5 题

回放方案：[verified-unselected-context.json](verified-unselected-context.json)。

- 作业题仅为 `4D:5`，在 PDF 第 1126 页。
- 原文 `Refer to Exercise 3` 指向 `4D:3`，需要渡轮背景、随机变量定义和概率分布表。
- 从 PDF 第 1125 页裁入第 3 题的题干和表格，截止于 667 点；排除其 (a) 以及在下一页的 (b)。
- 接上完整第 5 题，保留原题号；交付时说明上方是来自第 3 题的参考材料。
- 只输出第 5 题这一张作业图，文件名 `SECTION_4D_05_with_context.png`，默认 576 dpi。没有生成一张完整的第 3 题作业图。

## 已验证 2：远处的图示引用

回放方案：[verified-remote-figure.json](verified-remote-figure.json)。

- 实际教材的 `4C:15` 在 PDF 第 1068 页，题干明确引用教材印刷第 333 页的 Figure 4.2 作为掷骰子的样本空间图。
- 搜索 `Figure 4.2` 的第一个命中在 PDF 第 1005 页，是正文提及；实际图及图注在第 1006 页。需查看原图确认，不能只截第一个文字命中。
- 从第 1006 页只取图和图注，不带入下方“Probability model, Sample space”的定义或其他正文。随后拼接第 1068 页完整第 15 题，不带入第 14 题。
- 两个来源相隔 62 个 PDF 文件页序。输出按“参考图 → 作业题”的材料顺序排列，保持同一渲染倍率和原文字号；来源白底与习题灰底保留原样，用空白分隔。
- 文件名 `SECTION_4C_15_with_figure_4_2.png`，576 dpi。这验证了远距离来源定位及原图组合；跨 Section 习题的同号区分和链式依赖另外由方案检查测试覆盖。

## 避免过度补图的反例

PDF 第 1219 页第 29 题提及 `Section 4D, Exercise 9`，但当前题干已经给出所需概率 `0.097` 和抽样情境。此处不需要额外复制 4D 第 9 题的概率表或其他小问，仅凭引用文字不能认定要补截图。

## 回放命令

从项目根目录执行，或将脚本、方案和输出路径改为绝对路径。相对教材路径按方案文件所在目录解析。

```bash
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py extract --plan .agents/skills/statistics-hw-extraction/references/verified-unselected-context.json --out output/dependency-cases/unselected-context
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py extract --plan .agents/skills/statistics-hw-extraction/references/verified-remote-figure.json --out output/dependency-cases/remote-figure
```

工具能检查题号是否有章节身份、参考来源是否位于依赖链上、拼接顺序是否正确，以及是否漏题或越界。它不能从裁剪坐标判断截入了多少语义上无关的内容；仍需查看全部输出并对照原页判断。
