---
name: local-audio-transcription
description: 将仓库中的 m4a 等中文家庭音频在本机转写为带时间戳的文本，并辅助区分爸爸、妈妈与可乐等说话人；适用于用户要求语音转文字、整理对话或标注聊天角色。
---

# 本地音频转写

使用此技能处理仓库中的家庭音频。目标是交付一份可读的 Markdown 转写，并明确哪些角色标注已由原话或语境确认、哪些位置需要保留“[听不清]”或“[角色待确认]”。

## 本地模型

本项目已使用 `faster-whisper` 的 `small` 中文模型。默认复用以下本机缓存：

- 依赖：`/private/tmp/asd-wiki-asr`
- 模型：`/private/tmp/asd-wiki-hf`

可用 `ASD_WIKI_ASR_LIB` 和 `ASD_WIKI_ASR_MODEL_CACHE` 覆盖这两个位置。先检查两个目录存在，再运行脚本；脚本只从本地缓存加载模型。缓存缺失时，先说明原因并取得用户同意，再下载依赖或模型。音频不应上传到第三方识别服务。

## 流程

1. 定位用户指定的音频，使用 `afinfo` 确认时长和声道。
2. 运行转写脚本，生成包含时间戳、词级时间戳的 JSONL 中间结果：

   ```bash
   PYTHONPATH="${ASD_WIKI_ASR_LIB:-/private/tmp/asd-wiki-asr}" \
   python3 .agents/skills/local-audio-transcription/scripts/transcribe_local.py \
   <音频路径> \
   --output /private/tmp/<音频名>.asr.jsonl \
   --model-cache "${ASD_WIKI_ASR_MODEL_CACHE:-/private/tmp/asd-wiki-hf}"
   ```

3. 运行声线估计脚本，产生每个分段的 `speaker_candidate`。它在本次家庭录音中可帮助识别低声线的爸爸、较高声线的可乐和中间范围的妈妈，但结果只是候选：

   ```bash
   PYTHONPATH="${ASD_WIKI_ASR_LIB:-/private/tmp/asd-wiki-asr}" \
   python3 .agents/skills/local-audio-transcription/scripts/estimate_pitch.py \
   <音频路径> /private/tmp/<音频名>.asr.jsonl \
   --output /private/tmp/<音频名>.pitch.jsonl
   ```

4. 以角色称呼、上下文和 `speaker_candidate` 交叉核对，整理为 `音频名-语音转写.md`。相邻的报数、连续走棋和重复提示可以合并为带时间范围的段落；不得补写未识别出的事实或原话。
5. 交付前阅读生成的 Markdown，检查角色是否前后一致，时间范围是否覆盖录音首尾，以及每处不确定内容是否已明确标注。

## 转写格式

```markdown
# <音频名> 语音转写

> 音频时长：……。转写日期：……。
>
> 角色依据原话中的称呼、语境和声线区分。重叠或不清楚的位置以“[听不清]”或“[角色待确认]”标记。

## 00:00–00:00：场景

**妈妈**：……

**可乐**：……
```

用户只要求转写时，不把内容写入干预日志或可乐画像；只有用户明确要求记录、分析或更新时，才使用相应技能。
