# Simple Transcribe

AI-powered audio transcription using AWS Transcribe.

**Features:** No rate limits, handles files up to 2GB/4 hours, AI-formatted output, Notion integration, iOS notifications.

## Pipeline

```
S3 Upload → AWS Transcribe → Gemini AI (format + title) → S3 + Notion + iOS
```

## Deploy

```bash
cd transcriber/
uv sync
uv run chalice deploy
```

Required env vars in `.chalice/config.json`: `GEMINI_API_KEY`, `NOTION_API_KEY`

## Usage

Upload audio to `s3://audio-to-transcribe1/audio/` → transcription appears in:

- S3 `transcriptions/` folder
- Notion database (with AI-generated title)  
- iOS notification via ntfy.sh

**Cost:** ~$0.024/minute (AWS Transcribe pricing)
