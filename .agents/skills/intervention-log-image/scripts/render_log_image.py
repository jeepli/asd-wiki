#!/usr/bin/env python3
"""Render a repository intervention log table as a local PNG image."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from html import escape
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
HEADERS = ["活动/情境", "观察到的表现", "提示/支持"]
FONT_FAMILY = "'PingFang SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
IMAGE_WIDTH = 1800
LEFT = 64
TABLE_WIDTH = IMAGE_WIDTH - 2 * LEFT
COLUMN_WIDTHS = [270, 840, TABLE_WIDTH - 270 - 840]
BODY_FONT = 23
LINE_HEIGHT = 36
PAD_X = 22
PAD_Y = 18


@dataclass(frozen=True)
class Log:
    title: str
    description: str
    kind: str
    date_key: str
    rows: list[list[str]]


def split_row(line: str) -> list[str]:
    value = line.strip()
    if not (value.startswith("|") and value.endswith("|")):
        raise ValueError(f"表格行缺少两端竖线：{line}")

    cells: list[str] = []
    current: list[str] = []
    content = value[1:-1]
    index = 0
    while index < len(content):
        char = content[index]
        if char == "\\" and index + 1 < len(content) and content[index + 1] == "|":
            current.append("|")
            index += 2
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
        else:
            current.append(char)
            index += 1
    cells.append("".join(current).strip())
    return cells


def read_log(path: Path) -> Log:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError("日志缺少一级标题")

    title = lines[0][2:].strip()
    match = re.fullmatch(r"(家庭|机构)干预日志：(\d{4})-(\d{2})-(\d{2})", title)
    if not match:
        raise ValueError("标题应为“家庭/机构干预日志：YYYY-MM-DD”")
    kind = match.group(1)
    date_key = "".join(match.groups()[1:])
    if path.stem != date_key:
        raise ValueError("文件名日期与日志标题日期不一致")

    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("|") and split_row(line) == HEADERS),
        None,
    )
    if header_index is None or header_index + 1 >= len(lines):
        raise ValueError("未找到三列表格表头")
    separator = split_row(lines[header_index + 1])
    if len(separator) != 3 or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        raise ValueError("表格表头缺少 Markdown 分隔行")

    descriptions = [line.strip() for line in lines[1:header_index] if line.strip()]
    if len(descriptions) != 1:
        raise ValueError("表格前应有一行日志说明")

    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.strip():
            break
        cells = split_row(line)
        if len(cells) != 3:
            raise ValueError(f"表格行应有三列：{line}")
        rows.append(cells)
    if not rows:
        raise ValueError("日志表格没有记录行")

    return Log(title, descriptions[0], kind, date_key, rows)


def character_width(char: str, font_size: int) -> float:
    if char.isspace():
        return font_size * 0.34
    east = unicodedata.east_asian_width(char)
    return font_size if east in ("W", "F") or char == "—" else font_size * 0.56


def wrap_text(value: str, max_width: int, font_size: int) -> list[str]:
    lines: list[str] = []
    current = ""
    current_width = 0.0
    closing_punctuation = "，。！？；：、）》〉】」』”’"
    for char in value:
        width = character_width(char, font_size)
        # Keep closing punctuation with the preceding text when a line is full.
        if current and current_width + width > max_width and char not in closing_punctuation:
            lines.append(current.rstrip())
            current = char if not char.isspace() else ""
            current_width = width if current else 0.0
        else:
            current += char
            current_width += width
    if current:
        lines.append(current.rstrip())
    return lines or [""]


def svg_text(x: int, y: int, value: str, size: int, color: str, weight: int = 400) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT_FAMILY}" '
        f'font-size="{size}" font-weight="{weight}" fill="{color}" '
        f'xml:space="preserve">{escape(value)}</text>'
    )


def make_svg(log: Log) -> str:
    description_lines = wrap_text(log.description, TABLE_WIDTH, 20)
    table_y = 198 + (len(description_lines) - 1) * 30
    header_height = 68
    x_positions = [LEFT, LEFT + COLUMN_WIDTHS[0], LEFT + COLUMN_WIDTHS[0] + COLUMN_WIDTHS[1]]

    wrapped_rows = [
        [wrap_text(cell, COLUMN_WIDTHS[index] - 2 * PAD_X - 10, BODY_FONT) for index, cell in enumerate(row)]
        for row in log.rows
    ]
    row_heights = [
        max(80, max(len(cell_lines) for cell_lines in row) * LINE_HEIGHT + 2 * PAD_Y)
        for row in wrapped_rows
    ]
    table_height = header_height + sum(row_heights)
    footer_y = table_y + table_height + 48
    image_height = footer_y + 42

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{IMAGE_WIDTH}" height="{image_height}" '
        f'viewBox="0 0 {IMAGE_WIDTH} {image_height}">',
        '<rect width="100%" height="100%" fill="#F1F6FB"/>',
        '<rect x="64" y="43" width="8" height="64" rx="4" fill="#3E91B2"/>',
        svg_text(96, 98, log.title, 52, "#183A52", 700),
    ]
    for index, line in enumerate(description_lines):
        parts.append(svg_text(64, 151 + index * 30, line, 20, "#8095A6"))
    parts.extend(
        [
            f'<defs><clipPath id="tableClip"><rect x="{LEFT}" y="{table_y}" '
            f'width="{TABLE_WIDTH}" height="{table_height}" rx="14"/></clipPath></defs>',
            f'<rect x="{LEFT}" y="{table_y}" width="{TABLE_WIDTH}" '
            f'height="{table_height}" rx="14" fill="#FFFFFF"/>',
            '<g clip-path="url(#tableClip)">',
            f'<rect x="{LEFT}" y="{table_y}" width="{TABLE_WIDTH}" '
            f'height="{header_height}" fill="#174E6A"/>',
        ]
    )
    for index, header in enumerate(HEADERS):
        parts.append(svg_text(x_positions[index] + PAD_X, table_y + 44, header, 24, "#FFFFFF", 700))

    y = table_y + header_height
    for row_index, (cell_lines, row_height) in enumerate(zip(wrapped_rows, row_heights)):
        fill = "#F7FAFD" if row_index % 2 else "#FFFFFF"
        parts.append(f'<rect x="{LEFT}" y="{y}" width="{TABLE_WIDTH}" height="{row_height}" fill="{fill}"/>')
        for column_index, lines in enumerate(cell_lines):
            x = x_positions[column_index] + PAD_X
            baseline = y + PAD_Y + BODY_FONT
            for line_index, line in enumerate(lines):
                parts.append(
                    svg_text(x, baseline + line_index * LINE_HEIGHT, line, BODY_FONT, "#42596C", 700 if column_index == 0 else 400)
                )
        y += row_height

    grid_y = table_y + header_height
    parts.append(f'<path d="M {LEFT} {grid_y} H {LEFT + TABLE_WIDTH}" stroke="#D4E1EB" stroke-width="1.5"/>')
    for row_height in row_heights:
        grid_y += row_height
        parts.append(f'<path d="M {LEFT} {grid_y} H {LEFT + TABLE_WIDTH}" stroke="#D4E1EB" stroke-width="1.5"/>')
    for x in x_positions[1:]:
        parts.append(f'<path d="M {x} {table_y} V {table_y + table_height}" stroke="#D4E1EB" stroke-width="1.5"/>')
    parts.extend(
        [
            '</g>',
            f'<rect x="{LEFT}" y="{table_y}" width="{TABLE_WIDTH}" height="{table_height}" '
            'rx="14" fill="none" stroke="#D4E1EB" stroke-width="1.5"/>',
            svg_text(LEFT, footer_y, f"{log.kind}观察记录 · {len(log.rows)} 项活动与情境", 18, "#8CA1B2"),
            '</svg>',
        ]
    )
    return "\n".join(parts)


def render(svg: str, output: Path) -> None:
    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise RuntimeError("找不到 rsvg-convert；请安装 librsvg 后重试")
    if not output.parent.is_dir():
        raise ValueError(f"输出目录不存在：{output.parent}")
    with tempfile.TemporaryDirectory(prefix=".intervention-log-image-", dir=output.parent) as temp_dir:
        temp_path = Path(temp_dir)
        svg_path = temp_path / "log.svg"
        png_path = temp_path / "log.png"
        svg_path.write_text(svg, encoding="utf-8")
        subprocess.run([converter, "--format=png", f"--output={png_path}", str(svg_path)], check=True)
        png_path.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="将家庭或机构干预日志 Markdown 表格生成 PNG 长图")
    parser.add_argument("source", type=Path, help="tracking/log/family 或 institution 下的 YYYYMMDD.md")
    parser.add_argument("--output", "-o", type=Path, help="输出 PNG 路径；默认在仓库根目录")
    args = parser.parse_args()

    try:
        source = args.source.resolve()
        log = read_log(source)
        output = (args.output or REPO_ROOT / f"{log.date_key}_{log.kind}干预日志.png").resolve()
        if output.suffix.lower() != ".png":
            raise ValueError("输出文件需要使用 .png 扩展名")
        render(make_svg(log), output)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"生成失败：{error}", file=sys.stderr)
        return 1

    print(f"已生成：{output}（{len(log.rows)} 条记录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
