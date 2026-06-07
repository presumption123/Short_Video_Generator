"""Reusable short-form video generator and uploader."""

from __future__ import annotations

import asyncio
import math
import os
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import edge_tts
import google.generativeai as genai
import requests
from moviepy.config import change_settings
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def load_env_file(env_path: Path) -> None:
    """Load simple KEY=VALUE pairs from a local .env file."""

    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_env_file(SCRIPT_DIR / ".env")

change_settings(
    {"IMAGEMAGICK_BINARY": os.getenv("IMAGEMAGICK_BINARY", "/opt/homebrew/bin/magick")}
)


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        sys.exit(f"ERROR: missing required environment variable: {name}")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def env_list(name: str, default: Sequence[str]) -> list[str]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class VideoPreset:
    name: str
    story_prompt: str
    description_prompt: str
    youtube_title: str
    youtube_tags: tuple[str, ...]
    tiktok_title: str
    instagram_hashtags: str
    instagram_caption_prefix: str


VIDEO_PRESETS: dict[str, VideoPreset] = {
    "scary": VideoPreset(
        name="scary",
        story_prompt=(
            "Write a self-contained, terrifying true-crime-style or paranormal "
            "horror story."
        ),
        description_prompt=(
            "Write a short, eerie social caption that fits a horror short."
        ),
        youtube_title="Scary Story #shorts",
        youtube_tags=(
            "shorts",
            "horror",
            "scary",
            "scarystory",
            "paranormal",
            "storytime",
        ),
        tiktok_title="Scary story #horror #scary #storytime",
        instagram_hashtags="#horror #scarystory #scary #paranormal #fyp #viral #shorts #reels",
        instagram_caption_prefix="A nightmare you can't wake up from.",
    ),
    "funny": VideoPreset(
        name="funny",
        story_prompt=(
            "Write a self-contained funny story with a sharp punchline ending. "
            "Keep it lively, relatable, and easy to follow in a short-form video."
        ),
        description_prompt=(
            "Write a short, playful social caption that fits a comedy short."
        ),
        youtube_title="Funny Story #shorts",
        youtube_tags=(
            "shorts",
            "funny",
            "comedy",
            "storytime",
            "viral",
            "reels",
        ),
        tiktok_title="Funny story #funny #comedy #storytime",
        instagram_hashtags="#funny #comedy #storytime #fyp #viral #shorts #reels",
        instagram_caption_prefix="This one goes off the rails fast.",
    ),
    "romantic": VideoPreset(
        name="romantic",
        story_prompt=(
            "Write a self-contained romantic story with a warm, heartfelt tone "
            "and a satisfying emotional ending."
        ),
        description_prompt=(
            "Write a short, sweet social caption that fits a romantic short."
        ),
        youtube_title="Romantic Story #shorts",
        youtube_tags=(
            "shorts",
            "romantic",
            "love",
            "storytime",
            "reels",
            "viral",
        ),
        tiktok_title="Romantic story #romantic #love #storytime",
        instagram_hashtags="#romantic #love #storytime #fyp #viral #shorts #reels",
        instagram_caption_prefix="A soft little love story.",
    ),
}


def get_preset(style_name: str) -> VideoPreset:
    preset = VIDEO_PRESETS.get(style_name.lower())
    if preset is None:
        available = ", ".join(sorted(VIDEO_PRESETS))
        raise SystemExit(f"ERROR: unknown video style '{style_name}'. Choose from: {available}")
    return preset


GEMINI_API_KEY = env("GEMINI_API_KEY", required=True)
GTA_FOOTAGE_PATHS = env_list(
    "GTA_FOOTAGE_PATHS",
    default=[
        "/Users/ananthmangalam/Downloads/YTDown_YouTube_GTA-5-Gameplay-No-Copyright-Mega-Ramp-Ve_Media_bEQTUMAPFZQ_001_1080p.mp4",
        "/Users/ananthmangalam/Downloads/YTDown_YouTube_Best-GTA-5-MEGA-RAMP-No-Copyright-Gamepl_Media_VS3D8bgYhf4_001_1080p.mp4",
        "/Users/ananthmangalam/Downloads/YTDown_YouTube_GTA-5-Mega-Ramp-No-Copyright-Gameplay-Ve_Media_RQ3tfdCMjN4_001_1080p.mp4",
    ],
)

TTS_VOICE = env("TTS_VOICE", "en-US-ChristopherNeural")
STORY_DURATION_SECONDS = env_int("STORY_DURATION_SECONDS", 55)
WORDS_PER_SECOND = env_float("WORDS_PER_SECOND", 2.7)
TARGET_WORD_COUNT = int(STORY_DURATION_SECONDS * WORDS_PER_SECOND)

SUBTITLE_CHUNK_WORDS = env_int("SUBTITLE_CHUNK_WORDS", 5)
SUBTITLE_FONT_SIZE = env_int("SUBTITLE_FONT_SIZE", 70)
SUBTITLE_FONT = env(
    "SUBTITLE_FONT",
    "/System/Library/Fonts/SFNSMono.ttf",
)
SUBTITLE_COLOR = env("SUBTITLE_COLOR", "white")
SUBTITLE_STROKE_COLOR = env("SUBTITLE_STROKE_COLOR", "black")
SUBTITLE_STROKE_WIDTH = env_int("SUBTITLE_STROKE_WIDTH", 3)
SUBTITLE_Y_POSITION = env_float("SUBTITLE_Y_POSITION", 0.75)

DEFAULT_STYLE = env("VIDEO_STYLE", "scary")
DEFAULT_OUTPUT_TEMPLATE = env("OUTPUT_VIDEO_PATH", "")
UPLOAD_TO_YOUTUBE = env_bool("UPLOAD_TO_YOUTUBE", True)
UPLOAD_TO_INSTAGRAM = env_bool("UPLOAD_TO_INSTAGRAM", False)
UPLOAD_TO_TIKTOK = env_bool("UPLOAD_TO_TIKTOK", False)
KEEP_OUTPUT_VIDEO = env_bool("KEEP_OUTPUT_VIDEO", False)

YOUTUBE_CLIENT_SECRET_FILE = env(
    "YOUTUBE_CLIENT_SECRET_FILE",
    str(SCRIPT_DIR / "client_secret.json"),
)
YOUTUBE_TOKEN_FILE = env("YOUTUBE_TOKEN_FILE", str(SCRIPT_DIR / "youtube_token.pickle"))
YOUTUBE_CATEGORY_ID = env("YOUTUBE_CATEGORY_ID", "24")

INSTAGRAM_USERNAME = env("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = env("INSTAGRAM_PASSWORD")
TIKTOK_ACCESS_TOKEN = env("TIKTOK_ACCESS_TOKEN")


def configure_genai() -> None:
    genai.configure(api_key=GEMINI_API_KEY)


def generate_script(preset: VideoPreset) -> str:
    print(f"[1/4] Generating {preset.name} story with Gemini...")
    configure_genai()
    model = genai.GenerativeModel("gemini-3.5-flash")

    prompt = f"""You are writing a {preset.name} short-form video script.

{preset.story_prompt}

Requirements:
- Approximately {TARGET_WORD_COUNT} words (fits in about {STORY_DURATION_SECONDS} seconds when spoken aloud).
- Written entirely in second person ("you") for maximum immersion.
- No chapter titles or scene headings.
- Build momentum quickly and end with a memorable final line.
- Output ONLY the story script, nothing else."""

    response = model.generate_content(prompt)
    script = response.text.strip()
    print(f"    Script generated ({len(script.split())} words).")
    return script


def generate_description(script: str, preset: VideoPreset) -> str:
    """Generate a short social caption for the finished video."""

    configure_genai()
    model = genai.GenerativeModel("gemini-3.5-flash")

    prompt = f"""Based on this {preset.name} story script, write a short social media description.
{preset.description_prompt}

Requirements:
- 1-2 sentences max
- Do not spoil the ending
- Output ONLY the description, nothing else

Script:
{script}"""

    response = model.generate_content(prompt)
    return response.text.strip()


def text_to_speech(script: str, audio_path: str) -> None:
    print("[2/4] Converting script to speech...")

    async def _run() -> None:
        communicate = edge_tts.Communicate(script, TTS_VOICE)
        await communicate.save(audio_path)

    asyncio.run(_run())
    print(f"    Audio saved -> {audio_path}")


def chunk_script(script: str, chunk_size: int) -> list[str]:
    words = script.split()
    return [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]


def build_video(script: str, audio_path: str, output_path: str) -> None:
    print("[3/4] Building video...")

    audio_clip = AudioFileClip(audio_path)
    total_dur = audio_clip.duration
    print(f"    Audio duration: {total_dur:.1f}s")

    raw_clips = [VideoFileClip(p) for p in GTA_FOOTAGE_PATHS]
    footage = concatenate_videoclips(raw_clips, method="compose")

    if footage.duration < total_dur:
        loops_needed = math.ceil(total_dur / footage.duration)
        footage = concatenate_videoclips([footage] * loops_needed, method="compose")

    footage = footage.subclip(0, total_dur)
    width, _height = footage.size

    chunks = chunk_script(script, SUBTITLE_CHUNK_WORDS)
    dur_per = total_dur / max(len(chunks), 1)
    subtitle_clips = []

    for i, chunk in enumerate(chunks):
        start = i * dur_per
        wrapped = textwrap.fill(chunk, width=20)
        txt = (
            TextClip(
                wrapped,
                fontsize=SUBTITLE_FONT_SIZE,
                font=SUBTITLE_FONT,
                color=SUBTITLE_COLOR,
                stroke_color=SUBTITLE_STROKE_COLOR,
                stroke_width=SUBTITLE_STROKE_WIDTH,
                method="caption",
                size=(int(width * 0.9), None),
                align="center",
            )
            .set_start(start)
            .set_duration(dur_per)
            .set_position(("center", SUBTITLE_Y_POSITION), relative=True)
        )
        subtitle_clips.append(txt)

    final = (
        CompositeVideoClip([footage] + subtitle_clips)
        .set_audio(audio_clip)
        .set_duration(total_dur)
    )

    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        threads=4,
        preset="fast",
        logger="bar",
    )
    print(f"    Video saved -> {output_path}")


def upload_youtube(video_path: str, description: str, preset: VideoPreset) -> str:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import pickle

    if not Path(YOUTUBE_CLIENT_SECRET_FILE).exists():
        raise FileNotFoundError(f"YouTube client secret not found: {YOUTUBE_CLIENT_SECRET_FILE}")

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None

    if Path(YOUTUBE_TOKEN_FILE).exists():
        with open(YOUTUBE_TOKEN_FILE, "rb") as tok:
            creds = pickle.load(tok)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRET_FILE, scopes)
            creds = flow.run_local_server(port=0)
        with open(YOUTUBE_TOKEN_FILE, "wb") as tok:
            pickle.dump(creds, tok)

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": preset.youtube_title,
            "description": description,
            "tags": list(preset.youtube_tags),
            "categoryId": YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"    YouTube upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"    YouTube -> https://youtube.com/shorts/{video_id}")
    return video_id


def upload_instagram(video_path: str, script: str, preset: VideoPreset) -> None:
    from instagrapi import Client

    caption = (
        preset.instagram_caption_prefix
        + "\n\n"
        + script[:200].rstrip()
        + "...\n\n"
        + preset.instagram_hashtags
    )

    cl = Client()
    cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    media = cl.clip_upload(video_path, caption)
    print(f"    Instagram -> https://www.instagram.com/p/{media.code}/")


def upload_tiktok(video_path: str, preset: VideoPreset) -> None:
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    video_size = os.path.getsize(video_path)
    init_payload = {
        "post_info": {
            "title": preset.tiktok_title,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    init_resp = requests.post(init_url, json=init_payload, headers=headers)
    init_resp.raise_for_status()
    init_data = init_resp.json()
    publish_id = init_data["data"]["publish_id"]
    upload_url = init_data["data"]["upload_url"]

    with open(video_path, "rb") as vf:
        video_bytes = vf.read()

    upload_headers = {
        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        "Content-Type": "video/mp4",
    }
    upload_resp = requests.put(upload_url, data=video_bytes, headers=upload_headers)
    upload_resp.raise_for_status()

    status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    for _ in range(20):
        time.sleep(5)
        status_resp = requests.post(
            status_url,
            json={"publish_id": publish_id},
            headers=headers,
        )
        status_data = status_resp.json()
        state = status_data.get("data", {}).get("status", "")
        print(f"    TikTok publish status: {state}")
        if state == "PUBLISH_COMPLETE":
            print("    TikTok -> upload complete!")
            return
        if state in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"TikTok upload failed: {status_data}")

    print("    TikTok -> still processing; check your TikTok app.")


def resolve_output_path(preset: VideoPreset) -> str:
    if DEFAULT_OUTPUT_TEMPLATE:
        return DEFAULT_OUTPUT_TEMPLATE.format(style=preset.name)
    return f"{preset.name}_story_output.mp4"


def validate_footage_paths() -> None:
    for path in GTA_FOOTAGE_PATHS:
        if not Path(path).exists():
            sys.exit(f"ERROR: GTA footage not found: {path}")


def run_pipeline(style_name: str | None = None) -> None:
    preset = get_preset(style_name or DEFAULT_STYLE)
    validate_footage_paths()

    output_path = resolve_output_path(preset)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        audio_path = tmp.name

    final_video_path = Path(output_path)

    try:
        script = generate_script(preset)
        print("\n--- SCRIPT PREVIEW ------------------------------------------------")
        print(script[:400] + ("..." if len(script) > 400 else ""))
        print("-----------------------------------------------------------------\n")

        description = generate_description(script, preset)
        text_to_speech(script, audio_path)
        build_video(script, audio_path, output_path)

        print("[4/4] Uploading to platforms...")

        if UPLOAD_TO_YOUTUBE:
            print("  -> YouTube Shorts")
            try:
                upload_youtube(output_path, description, preset)
            except Exception as exc:
                print(f"    YouTube upload failed: {exc}")

        if UPLOAD_TO_INSTAGRAM:
            print("  -> Instagram Reels")
            try:
                upload_instagram(output_path, script, preset)
            except Exception as exc:
                print(f"    Instagram upload failed: {exc}")

        if UPLOAD_TO_TIKTOK:
            print("  -> TikTok")
            try:
                upload_tiktok(output_path, preset)
            except Exception as exc:
                print(f"    TikTok upload failed: {exc}")

        print("\nPipeline complete.")
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)
            print("    Cleaned up temp audio.")
        if not KEEP_OUTPUT_VIDEO and final_video_path.exists():
            final_video_path.unlink()
            print("    Cleaned up output video.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate and upload short-form videos.")
    parser.add_argument(
        "style",
        nargs="?",
        help=f"Video style to generate. Available: {', '.join(sorted(VIDEO_PRESETS))}",
    )
    args = parser.parse_args()
    run_pipeline(args.style)


if __name__ == "__main__":
    main()
