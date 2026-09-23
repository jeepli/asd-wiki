#!/usr/bin/env python3
"""Download public Xiaohongshu note metadata and images."""

from __future__ import annotations

import argparse
from datetime import datetime
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
NOTE_PATH_RE = re.compile(r"/(?:discovery/item|explore)/([^/?#]+)")
IMAGE_URL_RE = re.compile(r"https?://sns-webpic[^\"'\s<]+")
INVALID_DIRECTORY_CHAR_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def fetch(url: str, user_agent: str, timeout: int) -> tuple[str, str]:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("未找到 curl，无法访问公开页面")
    with tempfile.TemporaryDirectory(prefix="xhs-note-") as temp_dir:
        body_path = Path(temp_dir) / "page.html"
        result = subprocess.run(
            [
                curl,
                "-L",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                str(timeout),
                "-A",
                user_agent,
                "-H",
                "Accept: text/html,application/xhtml+xml",
                "-H",
                "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
                "-o",
                str(body_path),
                "-w",
                "%{url_effective}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "curl 请求失败"
            raise RuntimeError(message)
        return result.stdout.strip(), body_path.read_text(encoding="utf-8", errors="replace")


def extract_note_id(url: str) -> str:
    match = NOTE_PATH_RE.search(urlparse(url).path)
    if not match:
        raise ValueError("未能从最终 URL 解析 note_id")
    return match.group(1)


def extract_json_string(scope: str, key: str) -> str:
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"')
    match = pattern.search(scope)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1)


def extract_json_number(scope: str, key: str) -> int | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*(\d+)', scope)
    return int(match.group(1)) if match else None


def extract_publish_date(scope: str, timezone_name: str) -> tuple[str, str]:
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception as error:
        raise ValueError(f"无效时区：{timezone_name}") from error

    for key in ("time", "lastUpdateTime"):
        timestamp_ms = extract_json_number(scope, key)
        if timestamp_ms:
            published_at = datetime.fromtimestamp(timestamp_ms / 1000, timezone)
            return published_at.strftime("%Y-%m-%d"), key

    return datetime.now(timezone).strftime("%Y-%m-%d"), "current_date"


def safe_directory_title(title: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip(" .") or fallback
    cleaned = INVALID_DIRECTORY_CHAR_RE.sub("_", cleaned).strip(" .")
    return cleaned[:120].rstrip(" .") or fallback


def choose_output_directory(root: Path, metadata: dict[str, object]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    title = safe_directory_title(str(metadata["title"]), str(metadata["note_id"]))
    directory_name = f"{metadata['publish_date']}_{title}"
    candidate = root / directory_name
    existing_metadata = candidate / "metadata.json"
    if existing_metadata.exists():
        try:
            existing_note_id = json.loads(existing_metadata.read_text(encoding="utf-8")).get("note_id")
        except (OSError, json.JSONDecodeError):
            existing_note_id = None
        if existing_note_id != metadata["note_id"]:
            candidate = root / f"{directory_name}_{metadata['note_id']}"
    elif candidate.exists() and any(candidate.iterdir()):
        candidate = root / f"{directory_name}_{metadata['note_id']}"

    metadata["directory_name"] = candidate.name
    return candidate


def unique_in_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = html_lib.unescape(value).strip()
        value = value.replace("\\u002F", "/")
        if value.startswith("http://"):
            value = "https://" + value[len("http://") :]
        if value not in seen and "!h5_1080jpg" in value:
            seen.add(value)
            result.append(value)
    return result


def extract_metadata(
    source_url: str, final_url: str, body: str, timezone_name: str
) -> dict[str, object]:
    note_id = extract_note_id(final_url)
    params = parse_qs(urlparse(final_url).query)
    token = params.get("xsec_token", [""])[0]
    source = params.get("xsec_source", ["app_share"])[0]

    if "/login" in urlparse(final_url).path:
        raise RuntimeError("公开详情页要求登录，已停止抓取")

    normalized = body.replace("\\u002F", "/")
    note_position = -1
    for marker in (
        '"data":{"noteData":{',
        '"noteData":{"atUserList"',
        '"noteData":{"title"',
    ):
        note_position = normalized.find(marker)
        if note_position >= 0:
            break
    if note_position < 0:
        note_position = normalized.find(f'"noteId":"{note_id}"')
    if note_position < 0:
        note_position = 0
    note_scope = normalized[note_position : note_position + 250_000]

    image_urls = unique_in_order(IMAGE_URL_RE.findall(normalized))
    if not image_urls:
        raise RuntimeError("页面未发现公开图片 URL，可能是登录页或风控页")

    publish_date, date_source = extract_publish_date(note_scope, timezone_name)
    return {
        "source_url": source_url,
        "final_url": final_url,
        "note_id": note_id,
        "xsec_source": source,
        "xsec_token": token,
        "title": extract_json_string(note_scope, "title"),
        "description": extract_json_string(note_scope, "desc"),
        "author": extract_json_string(note_scope, "nickName"),
        "publish_date": publish_date,
        "date_source": date_source,
        "image_count": len(image_urls),
        "image_urls": image_urls,
    }


def download(url: str, destination: Path, referer: str, user_agent: str, timeout: int) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("未找到 curl，无法下载图片")
    result = subprocess.run(
        [
            curl,
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            "-A",
            user_agent,
            "-H",
            f"Referer: {referer}",
            "-o",
            str(destination),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "图片下载失败"
        raise RuntimeError(message)


def write_readme(output_dir: Path, metadata: dict[str, object], image_names: list[str]) -> None:
    lines = [
        "# 小红书笔记提取",
        "",
        f"- 来源：{metadata['source_url']}",
        f"- 日期：{metadata['publish_date']}",
        f"- 目录：{metadata['directory_name']}",
        f"- 标题：{metadata['title'] or '未解析到'}",
        f"- 作者：{metadata['author'] or '未解析到'}",
        f"- 描述/话题：{metadata['description'] or '未解析到'}",
        f"- 图片数量：{metadata['image_count']}",
        "",
        "## 图片",
        "",
    ]
    lines.extend(f"{index}. [{name}](./{name})" for index, name in enumerate(image_names, 1))
    lines.extend(
        [
            "",
            "> 图片内文字需另行 OCR 或人工核对；本文件不把图片文字误当作页面正文。",
            "",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="小红书短链或公开笔记链接")
    parser.add_argument(
        "--output-root",
        "--output-dir",
        dest="output_root",
        default="raw/xhs",
        help="输出根目录，默认 raw/xhs",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timezone", default="Asia/Shanghai", help="目录日期使用的时区")
    parser.add_argument("--no-download", action="store_true", help="只解析元数据，不下载图片")
    args = parser.parse_args()

    final_url, body = fetch(args.url, args.user_agent, args.timeout)
    metadata = extract_metadata(args.url, final_url, body, args.timezone)
    output_dir = choose_output_directory(Path(args.output_root).expanduser().resolve(), metadata)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_names: list[str] = []
    if not args.no_download:
        for index, image_url in enumerate(metadata["image_urls"], 1):
            image_name = f"{index:02d}.jpg"
            download(image_url, output_dir / image_name, final_url, args.user_agent, args.timeout)
            image_names.append(image_name)
    metadata["output_directory"] = str(output_dir)

    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_readme(output_dir, metadata, image_names)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"extract_xhs_note.py: {error}", file=sys.stderr)
        raise SystemExit(1)
