# Statistics Homework Extraction

一个用于从本地 PDF 教材提取作业截图的 Codex Skill。提供 Section 和题号，由 AI 定位并检查题目，配套工具负责裁剪和拼接原书画面。

## 功能

- 按 Section 和题号查找练习，保留原版文字、公式、表格及配图。
- 拼接跨页题目，将有依赖关系的已选题合并。
- 引用未选题或远处章节时，只补入必要材料，排除无关设问。
- 默认输出 576 dpi 无损 PNG，并保存提取方案和来源记录。

## 使用

1. （可选，部分 AI 自带 Python 环境）准备 Python 3.10+，在项目根目录安装依赖：

   ```bash
   python -m pip install -r .agents/skills/statistics-hw-extraction/requirements.txt
   ```

2. 将教材放在项目根目录，默认文件名为 `AP Statistics.pdf`；也可以在请求中指定其他 PDF 路径。

3. 在 Codex 中打开本项目并调用：

   ```text
   $statistics-hw-extraction 提取 SECTION 4D 的第 1、3、5 题。
   ```

   > 上述文本仅为示例，在其他 AI 产品中，Skills 的调用方法可能不一样。

截图默认保存到 `output/<任务名>/`，也可指定保存位置。AI 需检查题目边界、引用关系及最终图片；工具本身不自动理解题意。

## 文件位置

- [Skill 入口](.agents/skills/statistics-hw-extraction/SKILL.md)
- [工具用法与提取方案格式](.agents/skills/statistics-hw-extraction/references/workflow.md)
- [依赖处理规则与验证样例](.agents/skills/statistics-hw-extraction/references/dependency-cases.md)

教材 PDF 下载：https://drive.google.com/file/d/13fUclj6HsW5gyRtMw3q6xgpD7i7Xg7D5/view?usp=sharing

教材、生成的截图和临时文件均由 `.gitignore` 排除。仓库中的样例裁剪坐标仅适用于已验证的教材版本；使用其他版本时需重新定位。
