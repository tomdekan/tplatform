# Simple Transcribe

AI-powered audio transcription service using AWS Lambda, Groq Whisper, and Gemini AI formatting.

## Overview

Upload audio files to S3 → Get clean, formatted transcriptions automatically.

**Pipeline:**
1. Upload audio to S3 `audio/` folder
2. Lambda triggers on upload
3. Groq transcribes with Whisper
4. Gemini formats and cleans text  
5. Saves to S3 `transcriptions/` folder
6. iOS app gets push notification

## Development

### Prerequisites

* Python 3.13+ with uv
* AWS CLI configured
* API keys: `GROQ_API_KEY`,  `GEMINI_API_KEY`

### Setup

```bash
cd transcriber/
uv sync
```

### Environment Variables

Add to `.chalice/config.json` :

```json
{
  "environment_variables": {
    "GROQ_API_KEY": "your_groq_key",
    "GEMINI_API_KEY": "your_gemini_key"
  }
}
```

### Local Testing

```bash
uv run chalice local
```

## Deployment

```bash
cd transcriber/
uv run chalice deploy
```

**Creates:**
* Lambda function for S3 events
* S3 bucket notifications for `audio/` prefix
* IAM roles and policies

## Usage

### S3 Upload Structure

```
s3://audio-to-transcribe1/
├── audio/              # Upload audio files here
│   ├── meeting.m4a
│   └── interview.wav
└── transcriptions/     # Formatted output appears here
    ├── meeting.m4a.txt
    └── interview.wav.txt
```

### Supported Formats

* `.m4a`,  `.mp3`,  `.wav` (filtered at S3 level)
* Other formats: `.flac`,  `.aac`,  `.ogg` (add more handlers if needed)

### Monitoring

```bash
# View logs
uv run chalice logs --name transcribe_audio --follow

# Check deployed resources  
uv run chalice logs
```

## Features

* ✅ **Auto-triggered** processing on S3 upload
* ✅ **SOTA accuracy** with Whisper-large-v3
* ✅ **Smart formatting** removes filler words, adds structure
* ✅ **Push notifications** to iOS via ntfy.sh
* ✅ **Markdown output** with proper headings and paragraphs

## Architecture

```
iOS App → S3 Upload → Lambda → Groq → Gemini → S3 Output → iOS Notification
```

**Cost:** ~$0.01 per minute of audio transcribed.
