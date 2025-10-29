import os
from datetime import datetime
import tempfile
import boto3
from chalice import Chalice
from google import genai
from google.genai import types
from groq import Groq
import requests

app = Chalice(app_name="transcriber")


def notify_ios_app(message: str) -> None:
    notify_url = (
        "https://ntfy.sh/hurling3-zoom4-reliable7-shimmer8"  # Unique subscription URL.
    )
    try:
        requests.post(notify_url, data=message)
    except Exception as notify_err:
        print(f"Failed to notify iOS app: {notify_err}")


def generate_formatted_transcription(raw_transcript: str) -> str:
    """Format raw transcription using Gemini AI"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.5-pro"

    # First call: Initial formatting
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"""Transcribe this meeting. Exclude nothing.

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

    first_response_text = response.text

    # Second call: Check for missed content
    second_contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"""You've missed content. Exclude nothing.

                    Original raw transcription:
                    {raw_transcript}

                    Your previous formatted version:
                    {first_response_text}

                    Please identify and return ONLY any content that was missed or excluded from the formatted version. If nothing was missed, return an empty string."""
                ),
            ],
        ),
    ]

    second_response = client.models.generate_content(
        model=model,
        contents=second_contents,
        config=generate_content_config,
    )

    additional_content = second_response.text.strip()

    # Append additional content if any was found
    if additional_content:
        final_text = first_response_text + "\n\n" + additional_content
    else:
        final_text = first_response_text

    return final_text


def generate_title(text: str) -> str:
    """Generate a title for the transcription"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )
    model = "gemini-2.5"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=f"""
            Generate a title for the following transcription. 
            Reply only with the title, no other text.
            <transcription>{text}</transcription>
            """
                )
            ],
        ),
    ]

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )
    return response.text


@app.on_s3_event("audio-to-transcribe1", events=["s3:ObjectCreated:*"], prefix="audio/")
def transcribe_audio(event):
    """
    Transcribe audio from S3 bucket
    To view the logs:
    """
    s3 = boto3.client("s3")
    notify_ios_app(f"Transcribing {event.key}")
    
    # Estimate the time to transcribe the audio based on the file size.
    file_size = s3.head_object(Bucket=event.bucket, Key=event.key)["ContentLength"]
    estimated_transription_time = file_size / 1024 / 1024 / 10  # 10MB/s
    estimated_total_time = estimated_transription_time + 20  # 20 seconds for the LLM
    estimated_total_time_minutes = estimated_total_time / 60
    notify_ios_app(f"Estimated time to transcribe: {estimated_total_time_minutes} minutes")

    try:
        s3 = boto3.client("s3")

        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            s3.download_file(event.bucket, event.key, f.name)
            notify_ios_app(f"Downloaded {event.key} to {f.name}")
            print(f"✅ Downloaded {event.key} to {f.name}")

            groq_client = Groq()

            # Transcribe the audio file.
            with open(f.name, "rb") as file:
                filename = event.key.split("/")[-1]  # Get just the filename
                transcription = groq_client.audio.transcriptions.create(
                    file=(filename, file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    language="en",
                    temperature=0.0,
                    prompt="This is a audio recording. Please transcribe accurately with proper punctuation.",
                )

            message = f"File: {filename}. Transcribed audio to raw text."
            print(message)
            notify_ios_app(message)

            formatted_text = generate_formatted_transcription(transcription.text)
            title = generate_title(formatted_text)
            date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

            output_filename = f"{date_str}_{title}.txt"

            print(f"📝 Formatted transcription: {formatted_text[:50]}...")

            output_key = f"transcriptions/{output_filename}"

            # Save formatted transcription back to S3.
            s3.put_object(
                Bucket=event.bucket,
                Key=output_key,
                Body=formatted_text,
                ContentType="text/plain",
            )
            print(f"💾 Saved transcription to: {output_key}")

            message = f"File: {output_filename}. Transcription ready. Visit in s3://{event.bucket}/{output_key}"
            notify_ios_app(message)

        print("🎉 Audio processing complete!")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise
