# 工具用法和提取方案

本工具负责定位辅助、原页渲染与精确裁图。题目边界、阅读顺序和依赖由 AI 阅读原页后判断；工具不会仅靠“下一个数字”自动决定一题在哪里结束。

## 环境

使用 Python 3.10 或更新版本。依赖为 `pypdfium2`、`Pillow`，已在 5.14.0 / 12.3.0 上验证。优先使用已有运行环境；缺少依赖时，在合适的环境从项目根目录运行 `python -m pip install -r .agents/skills/statistics-hw-extraction/requirements.txt`，遵守所在环境的安装权限。脚本不使用网络或 AI API。

本 Skill 的入口位于项目的 `.agents/skills/statistics-hw-extraction/SKILL.md`。下列命令从项目根目录运行；教材、`output/` 和 `tmp/` 均放在项目根目录。若当前工作目录不同，使用脚本、方案及输出的绝对路径。路径有空格时要加引号。

```bash
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py info "AP Statistics.pdf"
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py search "AP Statistics.pdf" --query "SECTION 4D Exercises"
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py render "AP Statistics.pdf" --pages 1125-1126 --out tmp/4d
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py lines "AP Statistics.pdf" --pages 1125-1126
python .agents/skills/statistics-hw-extraction/scripts/pdf_exercises.py extract --plan .agents/skills/statistics-hw-extraction/references/verified-section-4d.json --out output/section-4d
```

搜索默认从文件开头开始，返回前 10 个命中页；可用 `--start-page`、`--end-page` 和 `--limit` 缩小范围。预览默认倍率为 1.5；最终截图默认倍率为 8，即 576 dpi；从 PDF 原始矢量内容重新渲染。PNG 使用无损保存，不能仅修改 dpi 元数据或放大已有截图来冒充提高分辨率。需要控制文件大小时，可在方案中显式选择较低倍率。`lines` 的盒子包含文字提取层能读取的字符，可能遗漏数学字符、图片和装饰，不能直接代替视觉检查。

## 方案格式

```json
{
  "source_pdf": "../../../../AP Statistics.pdf",
  "section": "SECTION 4D Exercises",
  "requested_exercises": ["1", "3", "5"],
  "dependencies": {"5": ["3"]},
  "scale": 8,
  "groups": [
    {
      "filename": "SECTION_4D_01.png",
      "exercises": ["1"],
      "parts": [
        {"exercise": "1", "page": 1125, "box": [75.5, 177, 536.5, 357]}
      ]
    },
    {
      "filename": "SECTION_4D_03_05.png",
      "exercises": ["3", "5"],
      "parts": [
        {"exercise": "3", "page": 1125, "box": [75.5, 534, 536.5, 706]},
        {"exercise": "3", "page": 1126, "box": [75.5, 72, 536.5, 111]},
        {"exercise": "5", "page": 1126, "box": [75.5, 452, 536.5, 494]}
      ]
    }
  ]
}
```

- `source_pdf` 相对方案 JSON 所在目录解析；也可以是绝对路径。随 Skill 迁入 `.agents/skills/statistics-hw-extraction/references/` 的三个样例使用 `../../../../AP Statistics.pdf` 指向项目根目录的教材；新任务应按方案实际存放位置计算相对路径。`extract --pdf` 可明确替换教材位置。`--out` 相对当前工作目录解析。
- `page` 是从 1 开始的文件页序。`box` 是 `[左, 上, 右, 下]`，以该页左上角为原点，单位为 PDF 点（1/72 英寸）。不要使用印刷页码或图片像素。
- `parts` 的顺序就是最终拼接顺序；同一题可以有多块，多个题可以位于同一张图。同组各块宽度必须一致，避免缩放原文。
- `dependencies` 记录每题需要的其他题。被选中的依赖题必须和后续题在同一组，且先出现；工具检查已声明的依赖，AI 仍需检查是否漏记引用。
- 新方案的题目 ID 使用 `章节:题号`，例如 `4C:15`、`4D:15`，避免不同 Section 的相同题号被混淆。图表等来源使用 `figure:4.2`、`table:4.1`、`example:4.3` 或 `text:<稳定标识>`；这些来源不是额外布置的习题。旧的单 Section 方案仍可使用简单题号回放。
- 使用限定 ID 时，提供 `source_catalog`，覆盖所有所选题、参考来源及依赖。例如 `"4C:15": {"kind": "exercise", "section": "4C", "number": "15"}`、`"figure:4.2": {"kind": "figure", "number": "4.2", "print_page": "333"}`。`kind` 可为 `exercise`、`figure`、`table`、`example`、`text`；习题须记录所属 Section。`print_page` 是追溯信息，不代替 part 的 PDF 文件页序。
- 未选参考来源加入组的 `context_exercises`；该字段保留原名，也可容纳图表等来源 ID。其必要片段标记 `role: "context"`，并填写 `supports`（支撑本组哪些题或材料）与 `reason`（为何需要、裁入哪些信息）。例如 `{"exercise": "4D:3", "role": "context", "supports": ["4D:5"], "reason": "只需渡轮背景和概率表，不需要第3题的(a)(b)", "page": 1125, "box": [75.5, 534, 536.5, 667]}`。声明 `"dependencies": {"4D:5": ["4D:3"]}`；组的 `exercises` 只含 `4D:5`。
- 每个参考来源都必须位于所选题的实际依赖链上；`supports` 必须符合依赖声明。需要哪一块就截哪一块，可从同一未选题跳过无关小问、只取非连续的题干或表格。已经排除的内容所含引用不形成新的依赖。
- 跨 Section 的题目先搜索相应练习标题，再定位题号；按教材印刷页码找图表时，搜索其图号与图注并查看候选原页，不能直接将印刷页码作为 PDF 页序。跨来源截图通过同一 PDF 的任意文件页序组合；按材料依赖顺序拼接，而不是按物理页序排序。完整回放方案见 [引用与依赖边界](dependency-cases.md)。
- 若一份未选参考材料被两张独立作业图使用，可在两张图中分别附上必要内容；它不计为重复布置。参考来源也被用户选为作业时，则按已选题规则合并并保留完整题目。
- 通常靠原始裁剪区的留白实现间距。确需额外空隙时可在 part 设置 `gap_after_points`，并在该 group 显式设置 `background_rgb`，如 `[243, 243, 243]`；只补空白，不覆盖原文像素。
- 可选 `source_identity` 含 `size_bytes`、`page_count`、`sha256`。有这些字段时，工具会校验原文件，拒绝在另一份教材上直接套用坐标。
- 输出文件名只能是单个 `.png` 文件名；每道已选题恰好属于一个分组。漏题、重复题、依赖分组错误、非法区域、宽度不一致和源文件身份不符都会在写图前被拒绝。

`extract` 在输出目录保存全部 PNG 与 `manifest.json`；manifest 包含原方案、源文件身份、输出大小与接缝位置。图片渲染后仍必须打开核对，尤其是跨页、跨栏、共用图表和数学公式。输出过长时，先考虑将无依赖的组分开；用户确需拆开同一依赖组时，确保每张有必要上下文。
