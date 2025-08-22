import os
import tempfile
import boto3
from chalice import Chalice
from google import genai
from google.genai import types
from groq import Groq
import requests

app = Chalice(app_name="helloworld")


def notify_ios_app(message: str) -> None:
    notify_url = "https://ntfy.sh/hurling3-zoom4-reliable7-shimmer8" # Unique subscription URL.
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


@app.on_s3_event("audio-to-transcribe1", events=["s3:ObjectCreated:*"], prefix="audio/")
def transcribe_audio(event):
    """
    Transcribe audio from S3 bucket
    To view the logs: 
    """

    print("🎵 S3 EVENT TRIGGERED! 🎵")
    print(f"Event: {event}")
    print(f"Bucket: {event.bucket}")
    print(f"Key: {event.key}")

    try:
        s3 = boto3.client("s3")

        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            s3.download_file(event.bucket, event.key, f.name)
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

            print(f"📝 Formatted transcription: {formatted_text[:50]}...")

            input_key_without_prefix = event.key.replace("audio/", "")
            output_key = f"transcriptions/{input_key_without_prefix}.txt"

            # Save formatted transcription back to S3.
            s3.put_object(
                Bucket=event.bucket,
                Key=output_key,
                Body=formatted_text,
                ContentType="text/plain",
            )
            print(f"💾 Saved transcription to: {output_key}")
            
            
            # Notify iOS app that the transcription is ready.
            filename = event.key.split("/")[-1]
            message = f"File: {filename}. Transcription ready. Visit in s3://{event.bucket}/{output_key}"
            notify_ios_app(message)

        print("🎉 Audio processing complete!")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise
