import os
from datetime import datetime
import tempfile
import boto3
from chalice import Chalice
from google import genai
from google.genai import types
from groq import Groq
import requests
from pydub import AudioSegment

app = Chalice(app_name="transcriber")


def notify_ios_app(message: str) -> None:
    notify_url = (
        "https://ntfy.sh/hurling3-zoom4-reliable7-shimmer8"  # Unique subscription URL.
    )
    try:
        requests.post(notify_url, data=message)
    except Exception as notify_err:
        print(f"Failed to notify iOS app: {notify_err}")


def compress_audio(input_path: str, output_path: str) -> dict:
    """
    Compress audio file to reduce size and improve transcription reliability.

    Optimizations:
    - Convert to mono (reduces size by ~50% for stereo files)
    - Reduce bitrate to 64kbps (optimized for speech transcription)
    - Normalize audio levels
    - Export as MP3 format

    Returns dict with compression stats: original_size, compressed_size, compression_ratio
    """
    try:
        print(f"🗜️  Starting audio compression: {input_path}")

        # Get original file size
        original_size = os.path.getsize(input_path)
        original_size_mb = original_size / 1024 / 1024
        print(f"📏 Original file size: {original_size_mb:.2f} MB")

        # Load audio file
        audio = AudioSegment.from_file(input_path)

        # Get original duration
        duration_seconds = len(audio) / 1000
        duration_minutes = duration_seconds / 60
        print(f"⏱️  Audio duration: {duration_minutes:.2f} minutes ({duration_seconds:.1f} seconds)")

        # Convert to mono if stereo
        if audio.channels > 1:
            print(f"🔄 Converting from {audio.channels} channels to mono")
            audio = audio.set_channels(1)

        # Normalize audio to improve consistency
        print("📊 Normalizing audio levels")
        audio = audio.normalize()

        # Set sample rate to 16kHz (optimal for speech recognition)
        if audio.frame_rate != 16000:
            print(f"🎵 Resampling from {audio.frame_rate}Hz to 16000Hz")
            audio = audio.set_frame_rate(16000)

        # Export with low bitrate optimized for speech
        print(f"💾 Exporting compressed audio to: {output_path}")
        audio.export(
            output_path,
            format="mp3",
            bitrate="64k",
            parameters=["-ac", "1", "-ar", "16000"]
        )

        # Get compressed file size
        compressed_size = os.path.getsize(output_path)
        compressed_size_mb = compressed_size / 1024 / 1024
        compression_ratio = (1 - compressed_size / original_size) * 100

        print(f"✅ Compression complete!")
        print(f"📏 Compressed file size: {compressed_size_mb:.2f} MB")
        print(f"📉 Compression ratio: {compression_ratio:.1f}% size reduction")

        return {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": compression_ratio,
            "duration_seconds": duration_seconds,
        }

    except Exception as e:
        print(f"❌ Error compressing audio: {str(e)}")
        raise


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

        # Create temp files for original and compressed audio
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".original") as original_file, \
             tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mp3") as compressed_file:

            original_path = original_file.name
            compressed_path = compressed_file.name

        try:
            # Download original file
            s3.download_file(event.bucket, event.key, original_path)
            notify_ios_app(f"Downloaded {event.key}")
            print(f"✅ Downloaded {event.key} to {original_path}")

            # Compress the audio file
            notify_ios_app("Compressing audio file...")
            compression_stats = compress_audio(original_path, compressed_path)

            compression_msg = (
                f"Compressed audio: "
                f"{compression_stats['original_size'] / 1024 / 1024:.1f}MB → "
                f"{compression_stats['compressed_size'] / 1024 / 1024:.1f}MB "
                f"({compression_stats['compression_ratio']:.1f}% reduction)"
            )
            notify_ios_app(compression_msg)
            print(compression_msg)

            groq_client = Groq()

            # Transcribe the compressed audio file
            notify_ios_app("Starting transcription...")
            with open(compressed_path, "rb") as file:
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

        finally:
            # Clean up temporary files
            try:
                if os.path.exists(original_path):
                    os.remove(original_path)
                    print(f"🗑️  Cleaned up original temp file: {original_path}")
            except Exception as cleanup_err:
                print(f"⚠️  Failed to clean up original file: {cleanup_err}")

            try:
                if os.path.exists(compressed_path):
                    os.remove(compressed_path)
                    print(f"🗑️  Cleaned up compressed temp file: {compressed_path}")
            except Exception as cleanup_err:
                print(f"⚠️  Failed to clean up compressed file: {cleanup_err}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise
