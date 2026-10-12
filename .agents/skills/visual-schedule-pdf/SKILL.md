---
name: visual-schedule-pdf
description: 将用户给出的 2–6 个生活或活动步骤制作成固定儿童绘本风格、A4 横版卡片布局的中文视觉流程图 PDF；适用于起床、出门、睡前、洗漱等顺序提示，不用于机构观察日志导图。
---

# 视觉流程图 PDF

把用户给出的步骤制作成一页 A4 横版 PDF。步骤文字可定制；插画风格、卡片、编号、箭头和排版规则保持一致。

## 收集

确认步骤及顺序。用户已用 `->`、列表或自然语言给出明确步骤时直接制作；步骤含义会影响画面且存在歧义时再提问。一次支持 2–6 步；更多步骤请用户决定如何拆分，避免单步图示过小。

文件名使用 `<日期或主题>_视觉流程图`；修改现有流程图时沿用原文件名。用户未指定标题时，根据内容使用“我的早晨流程”“我的睡前流程”或“我的视觉流程”。

## 生成插画

使用内置图片生成工具制作一张无文字的等分网格素材图。列数固定为：2 步用 1 列，3–4 步用 2 列，5–6 步用 3 列；行数为容纳全部步骤所需的 1–2 行。画面按从左到右、从上到下的顺序对应用户步骤；不足整行的格子使用干净的浅色空白背景。

按以下模板填写实际步骤，不增添用户未要求的环节：

```text
Use case: scientific-educational
Asset type: printable visual schedule illustrations for a preschool child
Primary request: Create one equal-panel grid showing the same cheerful preschool-aged Chinese child completing these actions in exact row-major order: <逐项写出步骤及可观察动作>.
Style/medium: clean warm children's picture-book illustration, simple shapes, gentle expressions, clear actions, low visual clutter, age-appropriate and respectful
Composition/framing: exactly <列数> columns by <行数> rows; one clear action per populated panel; same child throughout; centered subjects; generous internal margins; subtle white separators
Color palette: warm soft blue, pale yellow, coral accents, off-white backgrounds, strong enough contrast for printing
Text: none
Constraints: exact action order; no letters, words, numbers, logos, signage, clocks, watermark, or extra steps; keep important subjects away from panel edges; unused final cells are plain pale backgrounds
```

检查每格人物、动作和顺序。画面不对应步骤时，针对错误格局部重生成或编辑；确认后把最终 PNG 复制到仓库。不要依靠生成模型绘制中文文字。

## 渲染

使用[渲染脚本](scripts/render_visual_schedule.py)，步骤顺序必须与素材网格一致：

```bash
python3 .agents/skills/visual-schedule-pdf/scripts/render_visual_schedule.py \
  --image <素材.png> \
  --title "我的视觉流程" \
  --steps "步骤一" "步骤二" "步骤三" \
  --output <流程图.pdf> \
  --keep-svg
```

脚本固定输出：A4 横版、白色圆角卡片、橙色编号和箭头、深蓝中文标题、浅蓝背景及页尾完成提示。上排从左到右，下排从右到左，箭头构成连续蛇形路径。`--keep-svg` 保留可继续修改的同名 SVG。

默认认为素材网格列数与固定排版规则一致。复用既有素材且网格列数不同时，传入 `--source-columns 1|2|3`，只改变素材裁切方式，不改变输出排版。

## 核对与交付

用 `pdftoppm` 将 PDF 渲染为 PNG，再查看成图。逐项核对：

- 步骤文字、编号和图片一一对应；
- 箭头连续指向下一步；
- 中文完整，图片和卡片没有越界或截断；
- PDF 为一页 A4 横版。

发现问题时修订素材或 SVG 后重新生成。最终提供 PDF 链接，并说明插画由内置图片生成工具制作。
