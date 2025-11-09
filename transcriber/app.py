import os
import re
import time
from datetime import datetime

import boto3
import requests
from chalice import Chalice
from google import genai
from google.genai import types
from notion_client import Client

app = Chalice(app_name="transcriber")


def notify_ios_app(message: str) -> None:
    notify_url = (
        "https://ntfy.sh/hurling3-zoom4-reliable7-shimmer8"  # Unique subscription URL.
    )
    try:
        requests.post(notify_url, data=message)
    except Exception as notify_err:
        print(f"Failed to notify iOS app: {notify_err}")


def add_transcript_to_notion(doc_name: str, transcript_text: str) -> None:
    """Add transcript to Notion database as a new page"""
    try:
        notion_api_key = os.environ.get("NOTION_API_KEY")
        if not notion_api_key:
            print("⚠️ NOTION_API_KEY not set, skipping Notion upload")
            return

        notion = Client(auth=notion_api_key)
        database_id = "25b2a405bb848084baf7c3403c6955c7"

        paragraphs = transcript_text.split("\n\n")
        children_blocks = []

        for paragraph in paragraphs:
            if paragraph.strip():
                children_blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": paragraph.strip()}}
                            ]
                        },
                    }
                )

        notion.pages.create(
            parent={"database_id": database_id},
            properties={"Doc name": {"title": [{"text": {"content": doc_name}}]}},
            children=children_blocks,
        )

        print(f"✅ Added transcript to Notion: {doc_name}")

    except Exception as notion_err:
        print(f"⚠️ Failed to add to Notion (continuing anyway): {notion_err}")


def generate_formatted_transcription(raw_transcript: str) -> str:
    """Format raw transcription using Gemini AI"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.5-pro"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"""You are an expert transcription editor. Clean up this audio transcription with:

                    1. Perfect grammar and punctuation
                    2. Proper paragraph breaks for topic changes  
                    3. Correct capitalization and spelling
                    4. Remove filler words (um, uh, like) but keep all meaningful content
                    5. Format as clear, readable markdown with headings where appropriate
                    
                    Keep the original meaning and tone entirely.
                    
                    Raw transcription:
                    {raw_transcript}"""
                ),
            ],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_budget=-1,
        ),
        tools=[types.Tool(googleSearch=types.GoogleSearch())],
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )

    return response.text


def generate_title(text: str, filename: str) -> str:
    """Generate a title for the transcription"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )
    model = "gemini-2.5-flash"

    customer_name = filename.replace("-", " ").replace("_", " ").split(".")[0]

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"""Generate a title for the following transcription.
Include the customer/client name from the filename if identifiable.

Filename: {customer_name}

Reply only with the title, no other text.

<transcription>{text}</transcription>"""
                )
            ],
        ),
    ]

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )
    return response.text


def generate_summary(text: str, filename: str) -> str:
    """Generate a summary with key points and supporting quotes"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )
    model = "gemini-2.5-flash"

    customer_name = filename.replace("-", " ").replace("_", " ").split(".")[0]

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"""Create a comprehensive summary of this transcription with:

**Customer/Client:** {customer_name}

1. Key Points - List all main topics and decisions
2. Supporting Quotes - Include relevant direct quotes that support each point

Format as clear markdown with:
- **Customer:** {customer_name}
- ## Key Points (bullet list)
- ## Supporting Quotes (grouped by topic)

<transcription>{text}</transcription>"""
                )
            ],
        ),
    ]

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )
    return response.text


def start_transcription_job(s3_bucket: str, s3_key: str, job_name: str) -> str:
    """Start AWS Transcribe job and return job name"""
    transcribe = boto3.client("transcribe")

    media_uri = f"s3://{s3_bucket}/{s3_key}"

    file_extension = s3_key.split(".")[-1].lower() if "." in s3_key else "mp3"
    valid_formats = ["amr", "flac", "wav", "ogg", "mp3", "mp4", "webm", "m4a"]
    media_format = file_extension if file_extension in valid_formats else "mp3"

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        MediaFormat=media_format,
        LanguageCode="en-GB",
        Settings={
            "ShowSpeakerLabels": True,
            "MaxSpeakerLabels": 10,
        },
    )

    return job_name


def wait_for_transcription(job_name: str, max_attempts: int = 60) -> str:
    """Wait for transcription job to complete and return transcript text"""
    transcribe = boto3.client("transcribe")

    for attempt in range(max_attempts):
        response = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = response["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            transcript_uri = response["TranscriptionJob"]["Transcript"][
                "TranscriptFileUri"
            ]
            return requests.get(transcript_uri).json()["results"]["transcripts"][0][
                "transcript"
            ]

        if status == "FAILED":
            reason = response["TranscriptionJob"].get("FailureReason", "Unknown")
            raise Exception(f"Transcription failed: {reason}")

        time.sleep(10)

    raise Exception(f"Transcription timed out after {max_attempts * 10} seconds")


@app.on_s3_event("audio-to-transcribe1", events=["s3:ObjectCreated:*"], prefix="audio/")
def transcribe_audio(event):
    """Transcribe audio from S3 using AWS Transcribe"""
    s3 = boto3.client("s3")

    try:
        filename = event.key.split("/")[-1]
        notify_ios_app(f"🎙️ Starting transcription: {filename}")

        file_size_bytes = s3.head_object(Bucket=event.bucket, Key=event.key)[
            "ContentLength"
        ]
        file_size_mb = file_size_bytes / (1024 * 1024)
        print(f"📊 File size: {file_size_mb:.2f} MB")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_filename = re.sub(r"[^0-9a-zA-Z._-]", "-", filename)[:50]
        job_name = f"transcribe-{timestamp}-{safe_filename}"

        print(f"🎙️ Starting AWS Transcribe job: {job_name}")
        start_transcription_job(event.bucket, event.key, job_name)
        notify_ios_app("🎙️ Transcribing audio (AWS Transcribe)...")

        print("⏳ Waiting for transcription to complete...")
        raw_transcript = wait_for_transcription(job_name)
        print(f"✅ Transcription complete: {len(raw_transcript)} characters")

        notify_ios_app("🤖 Formatting transcript with AI...")
        formatted_text = generate_formatted_transcription(raw_transcript)

        notify_ios_app("📝 Generating summary with key points...")
        summary = generate_summary(text=formatted_text, filename=filename)

        notify_ios_app("✍️ Generating title...")
        title = generate_title(formatted_text, filename=filename)

        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"{date_str}_{filename}.txt"
        output_key = f"transcriptions/{output_filename}"

        full_content = f"{summary}\n\n---\n\n# Full Transcript\n\n{formatted_text}"

        s3.put_object(
            Bucket=event.bucket,
            Key=output_key,
            Body=full_content,
            ContentType="text/plain",
        )
        print(f"💾 Saved to S3: {output_key}")

        add_transcript_to_notion(doc_name=title, transcript_text=full_content)

        notify_ios_app(f"✅ Complete: '{title}'")
        print(f"🎉 Transcription complete: {output_filename}")

    except Exception as e:
        error_msg = f"❌ Transcription failed: {str(e)}"
        print(error_msg)
        notify_ios_app(error_msg)
        raise
