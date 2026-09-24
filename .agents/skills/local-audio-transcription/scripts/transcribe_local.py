#!/usr/bin/env python3
"""Transcribe a local audio file with a cached faster-whisper model."""

import argparse
import json
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用本地 Whisper 模型转写中文音频。")
    parser.add_argument("audio", type=Path, help="待转写的音频文件")
    parser.add_argument("--output", required=True, type=Path, help="JSONL 输出路径")
    parser.add_argument("--model", default="small", help="本地缓存中的模型名，默认 small")
    parser.add_argument("--model-cache", required=True, type=Path, help="Hugging Face 模型缓存目录")
    parser.add_argument("--device", default="cpu", choices=("cpu",), help="推理设备")
    parser.add_argument("--compute-type", default="int8", help="CTranslate2 计算类型")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.audio.is_file():
        raise SystemExit(f"找不到音频文件：{args.audio}")
    if not args.model_cache.is_dir():
        raise SystemExit(f"找不到本地模型缓存：{args.model_cache}")

    os.environ["HF_HOME"] = str(args.model_cache)
    from faster_whisper import WhisperModel

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        local_files_only=True,
    )
    segments, info = model.transcribe(
        str(args.audio),
        language="zh",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,
        condition_on_previous_text=False,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        output.write(json.dumps({
            "type": "metadata",
            "language": info.language,
            "duration": round(info.duration, 2),
            "model": args.model,
        }, ensure_ascii=False) + "\n")
        for segment in segments:
            output.write(json.dumps({
                "type": "segment",
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
                "words": [
                    {
                        "start": round(word.start, 2),
                        "end": round(word.end, 2),
                        "word": word.word,
                    }
                    for word in segment.words or []
                ],
            }, ensure_ascii=False) + "\n")

    print(f"已写入 {args.output}")


if __name__ == "__main__":
    main()
