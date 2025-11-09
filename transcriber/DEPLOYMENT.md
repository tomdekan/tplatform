# Deployment Guide

## Step 1: Deploy Without FFmpeg Layer

Deploy the app first (FFmpeg layer will be added separately):

```bash
cd /Users/t/PycharmProjects/tplatform/transcriber
uv run chalice deploy
```

## Step 2: Add FFmpeg Layer

See [FFMPEG_LAYER_SETUP.md](FFMPEG_LAYER_SETUP.md) for detailed instructions on adding the FFmpeg layer.

## Verify Deployment

Check logs:
```bash
uv run chalice logs --name transcribe_audio --follow
```

Upload a test file to S3:
```bash
aws s3 cp test-audio.m4a s3://audio-to-transcribe1/audio/
```

## Configuration

### Lambda Settings (Pre-configured in `.chalice/config.json`)

- **Timeout**: 10 minutes (600 seconds)
- **Memory**: 3GB (3008 MB)
- **FFmpeg Layer**: Auto-attached on deployment
- **Environment Variables**: API keys for Groq, Gemini, Notion

### File Size Limits

- Files < 20MB: Direct transcription
- Files 20-25MB: Automatic compression
- Files > 25MB after compression: Automatic chunking (10-minute segments)

## Different AWS Region?

If you're not using `us-east-1`, update the FFmpeg layer ARN in `.chalice/config.json`:

```json
"layers": ["arn:aws:lambda:YOUR-REGION:145266761615:layer:ffmpeg:4"]
```

Common regions:
- `us-west-2`: `arn:aws:lambda:us-west-2:145266761615:layer:ffmpeg:4`
- `eu-west-1`: `arn:aws:lambda:eu-west-1:145266761615:layer:ffmpeg:4`

## Troubleshooting

### "No such file or directory: ffmpeg"

The FFmpeg layer isn't attached. Check your `.chalice/config.json` has the `layers` configuration.

### "File too large" errors

The automatic compression should handle this. Check logs for compression output.

### Timeouts on very large files

Files are automatically chunked. Each chunk processes independently. If still timing out:
1. Check CloudWatch logs for specific error
2. Consider reducing chunk size in `audio_processor.py` (line 10)

### Memory errors

Increase `lambda_memory_size` in `.chalice/config.json` to 5120 (max 10240).

## Monitoring

View detailed logs:
```bash
# Live tail
uv run chalice logs --name transcribe_audio --follow

# Recent logs
uv run chalice logs --name transcribe_audio
```

CloudWatch metrics to monitor:
- Duration (should be < 600s)
- Memory usage (should be < 3GB)
- Errors (should be 0)

