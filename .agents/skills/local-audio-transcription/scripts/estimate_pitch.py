#!/usr/bin/env python3
"""Estimate a pitch-based speaker candidate for timestamped ASR segments."""

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为本地转写片段估计声线与说话人候选。")
    parser.add_argument("audio", type=Path, help="与转写结果对应的音频文件")
    parser.add_argument("segments", type=Path, help="transcribe_local.py 生成的 JSONL 文件")
    parser.add_argument("--output", required=True, type=Path, help="带声线信息的 JSONL 输出路径")
    return parser.parse_args()


def estimate_pitch(audio, start: float, end: float):
    import numpy as np

    sample_rate = 16000
    part = audio[int(start * sample_rate):int(min(end, start + 3) * sample_rate)]
    if len(part) < 800:
        return None

    part = part - np.mean(part)
    frame_size = 8192
    hop = 2048
    frames = [part[offset:offset + frame_size] for offset in range(0, max(1, len(part) - frame_size), hop)]
    frame = max(frames, key=lambda item: np.mean(item * item))
    if len(frame) < frame_size:
        return None

    frame = frame * np.hanning(len(frame))
    spectrum = np.fft.rfft(frame, n=16384)
    correlation = np.fft.irfft(spectrum * np.conj(spectrum))[:len(frame)]
    low_lag, high_lag = 40, 267  # 60–400 Hz at 16 kHz.
    lag = low_lag + np.argmax(correlation[low_lag:high_lag])
    frequency = sample_rate / lag
    return round(frequency, 1) if 65 <= frequency <= 380 else None


def speaker_candidate(pitch_hz):
    if pitch_hz is None:
        return "待确认"
    if pitch_hz < 160:
        return "爸爸（候选）"
    if pitch_hz > 260:
        return "可乐（候选）"
    return "妈妈（候选）"


def main() -> None:
    args = parse_args()
    if not args.audio.is_file():
        raise SystemExit(f"找不到音频文件：{args.audio}")
    if not args.segments.is_file():
        raise SystemExit(f"找不到转写文件：{args.segments}")

    import av
    import numpy as np

    container = av.open(str(args.audio))
    resampler = av.audio.resampler.AudioResampler(format="flt", layout="mono", rate=16000)
    samples = []
    for frame in container.decode(audio=0):
        converted = resampler.resample(frame)
        for output in converted if isinstance(converted, list) else [converted]:
            samples.append(output.to_ndarray().reshape(-1))
    audio = np.concatenate(samples)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.segments.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as output:
        for line in source:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Earlier runs did not include a type field; start/end remain the stable contract.
            if "start" not in record or "end" not in record:
                continue
            pitch_hz = estimate_pitch(audio, record["start"], record["end"])
            record["pitch_hz"] = pitch_hz
            record["speaker_candidate"] = speaker_candidate(pitch_hz)
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"已写入 {args.output}")


if __name__ == "__main__":
    main()
