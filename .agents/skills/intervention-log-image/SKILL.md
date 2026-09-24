---
name: intervention-log-image
description: 将本仓库 tracking/log/family/ 或 tracking/log/institution/ 的三列表格干预日志生成中文 PNG 长图；用于日志导出图片、分享图或重新生成图片。
---

# 干预日志图片

运行本技能的[渲染脚本](scripts/render_log_image.py)，直接读取已写好的日志：

```bash
python3 .agents/skills/intervention-log-image/scripts/render_log_image.py tracking/log/family/20260923.md
```

脚本默认在仓库根目录生成 `YYYYMMDD_家庭干预日志.png` 或 `YYYYMMDD_机构干预日志.png`；需要其他位置时传入 `--output 路径.png`。它保留日志的标题、说明和三列表格原文，并根据内容自动调整长图高度。运行环境需要 `python3` 和 `rsvg-convert`（librsvg）。图片在本地生成。

生成后查看图片，核对中文显示、行数、长段落和表格边界，再向用户提供图片链接。需要修订日志文字时，先按对应的家庭或机构日志技能处理源文件，再重新生成图片。
