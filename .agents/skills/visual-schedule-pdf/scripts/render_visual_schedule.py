#!/usr/bin/env python3
"""Render a fixed-style A4 landscape visual schedule from a PNG grid."""

from __future__ import annotations

import argparse
import base64
import html
import math
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


PAGE_WIDTH = 1122
PAGE_HEIGHT = 794


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a 2–6 step Chinese visual schedule as an A4 landscape PDF."
    )
    parser.add_argument("--image", required=True, type=Path, help="PNG grid image")
    parser.add_argument("--steps", required=True, nargs="+", help="Ordered step labels")
    parser.add_argument("--title", default="我的视觉流程", help="Schedule title")
    parser.add_argument("--footer", default="全部完成，真棒！", help="Footer message")
    parser.add_argument("--output", required=True, type=Path, help="Output PDF path")
    parser.add_argument(
        "--source-columns",
        type=int,
        choices=(1, 2, 3),
        help="Columns in the source grid; defaults to the fixed output layout",
    )
    parser.add_argument(
        "--keep-svg", action="store_true", help="Keep an editable SVG beside the PDF"
    )
    return parser.parse_args()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as file:
        header = file.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"素材必须是 PNG：{path}")
    return struct.unpack(">II", header[16:24])


def grid_columns(step_count: int) -> int:
    if step_count <= 2:
        return 1
    if step_count <= 4:
        return 2
    return 3


def arrow_line(
    start: tuple[float, float], end: tuple[float, float]
) -> str:
    return (
        f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" '
        f'x2="{end[0]:.1f}" y2="{end[1]:.1f}" '
        'stroke="#f09b5a" stroke-width="7" stroke-linecap="round" '
        'marker-end="url(#arrow)"/>'
    )


def build_svg(
    image_path: Path,
    steps: list[str],
    title: str,
    footer: str,
    source_columns: int | None,
) -> str:
    count = len(steps)
    columns = grid_columns(count)
    rows = math.ceil(count / columns)
    source_columns = source_columns or columns
    source_rows = math.ceil(count / source_columns)
    image_width, image_height = png_dimensions(image_path)
    source_cell_width = image_width / source_columns
    source_cell_height = image_height / source_rows
    image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")

    margin_x = 42
    column_gap = 58 if columns > 1 else 0
    row_gap = 66 if rows > 1 else 0
    cards_top = 112
    cards_bottom = 687
    card_width = (PAGE_WIDTH - 2 * margin_x - column_gap * (columns - 1)) / columns
    card_height = (cards_bottom - cards_top - row_gap * (rows - 1)) / rows
    picture_size = min(174, card_height - 78, card_width - 92)

    cards: list[str] = []
    labels: list[str] = []
    numbers: list[str] = []
    clips: list[str] = []
    images: list[str] = []
    centers: list[tuple[float, float]] = []
    positions: list[tuple[int, int]] = []

    for index, step in enumerate(steps):
        row = index // columns
        display_position = index % columns
        source_row = index // source_columns
        source_column = index % source_columns
        display_column = (
            display_position if row % 2 == 0 else columns - 1 - display_position
        )
        card_x = margin_x + display_column * (card_width + column_gap)
        card_y = cards_top + row * (card_height + row_gap)
        picture_x = card_x + (card_width - picture_size) / 2
        picture_y = card_y + 16
        center_x = card_x + card_width / 2
        center_y = card_y + card_height / 2
        centers.append((center_x, center_y))
        positions.append((row, display_column))

        clip_id = f"picture-{index + 1}"
        clips.append(
            f'<clipPath id="{clip_id}"><rect x="{picture_x:.1f}" y="{picture_y:.1f}" '
            f'width="{picture_size:.1f}" height="{picture_size:.1f}" rx="16"/></clipPath>'
        )

        source_inset = 0.12
        crop_x = (source_column + source_inset) * source_cell_width
        crop_y = (source_row + source_inset) * source_cell_height
        crop_width = source_cell_width * (1 - 2 * source_inset)
        crop_height = source_cell_height * (1 - 2 * source_inset)
        scale = max(picture_size / crop_width, picture_size / crop_height)
        scaled_crop_width = crop_width * scale
        scaled_crop_height = crop_height * scale
        image_x = (
            picture_x
            - crop_x * scale
            - (scaled_crop_width - picture_size) / 2
        )
        image_y = (
            picture_y
            - crop_y * scale
            - (scaled_crop_height - picture_size) / 2
        )
        images.append(
            f'<g clip-path="url(#{clip_id})">'
            f'<use href="#source-image" transform="matrix({scale:.8f} 0 0 {scale:.8f} '
            f'{image_x:.1f} {image_y:.1f})"/>'
            "</g>"
        )
        cards.append(
            f'<rect x="{card_x:.1f}" y="{card_y:.1f}" width="{card_width:.1f}" '
            f'height="{card_height:.1f}" rx="20" fill="#fff" stroke="#d8e7ee" '
            'stroke-width="2" filter="url(#shadow)"/>'
        )
        numbers.append(
            f'<circle cx="{card_x + 23:.1f}" cy="{card_y + 27:.1f}" r="25" fill="#f09b5a"/>'
            f'<text x="{card_x + 23:.1f}" y="{card_y + 36:.1f}" text-anchor="middle" '
            'font-size="24" font-weight="700" fill="#fff">'
            f"{index + 1}</text>"
        )
        label_size = 33 if len(step) <= 6 else 29
        labels.append(
            f'<text x="{center_x:.1f}" y="{card_y + card_height - 24:.1f}" '
            'text-anchor="middle" fill="#173f55" '
            f'font-size="{label_size}" font-weight="700">{html.escape(step)}</text>'
        )

    arrows: list[str] = []
    for index in range(count - 1):
        row, column = positions[index]
        next_row, next_column = positions[index + 1]
        center_x, center_y = centers[index]
        next_center_x, next_center_y = centers[index + 1]
        if row == next_row:
            direction = 1 if next_column > column else -1
            start_x = center_x + direction * (card_width / 2 + 10)
            end_x = next_center_x - direction * (card_width / 2 + 18)
            arrows.append(arrow_line((start_x, center_y), (end_x, next_center_y)))
        else:
            start_y = center_y + card_height / 2 + 10
            end_y = next_center_y - card_height / 2 - 18
            arrows.append(arrow_line((center_x, start_y), (next_center_x, end_y)))

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 {PAGE_WIDTH} {PAGE_HEIGHT}">
  <defs>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#244a64" flood-opacity="0.14"/>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="9" refY="6" orient="auto" markerUnits="userSpaceOnUse">
      <path d="M1 1l9 5-9 5" fill="none" stroke="#f09b5a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
    <image id="source-image" width="{image_width}" height="{image_height}" href="data:image/png;base64,{image_data}"/>
    {''.join(clips)}
  </defs>
  <rect width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}" fill="#f3f8fb"/>
  <circle cx="60" cy="56" r="21" fill="#456da0"/>
  <path d="M50 56l7 7 14-17" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <g font-family="PingFang SC, Noto Sans CJK SC, sans-serif">
    <text x="95" y="68" font-size="39" font-weight="700" fill="#173f55">{html.escape(title)}</text>
    <text x="680" y="65" text-anchor="middle" font-size="20" fill="#6a8796">跟着箭头，一步一步完成</text>
    {''.join(cards)}
    {''.join(images)}
    {''.join(numbers)}
    {''.join(labels)}
    {''.join(arrows)}
    <rect x="354" y="718" width="414" height="50" rx="25" fill="#e2eef8"/>
    <text x="561" y="751" text-anchor="middle" font-size="21" font-weight="600" fill="#45657d">{html.escape(footer)}</text>
  </g>
</svg>
'''


def main() -> None:
    args = parse_args()
    if not 2 <= len(args.steps) <= 6:
        raise SystemExit("步骤数量必须为 2–6 个。")
    if not args.image.is_file():
        raise SystemExit(f"找不到素材图片：{args.image}")
    if args.output.suffix.lower() != ".pdf":
        raise SystemExit("输出文件必须使用 .pdf 扩展名。")
    if shutil.which("rsvg-convert") is None:
        raise SystemExit("缺少 rsvg-convert，请先安装 librsvg。")

    svg = build_svg(
        args.image,
        args.steps,
        args.title,
        args.footer,
        args.source_columns,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.keep_svg:
        svg_path = args.output.with_suffix(".svg")
        svg_path.write_text(svg, encoding="utf-8")
        source_path = svg_path
    else:
        temp = tempfile.NamedTemporaryFile(suffix=".svg", delete=False)
        temp.close()
        source_path = Path(temp.name)
        source_path.write_text(svg, encoding="utf-8")

    try:
        subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(args.output), str(source_path)],
            check=True,
        )
    finally:
        if not args.keep_svg:
            source_path.unlink(missing_ok=True)

    print(f"已生成：{args.output}（{len(args.steps)} 个步骤）")


if __name__ == "__main__":
    main()
