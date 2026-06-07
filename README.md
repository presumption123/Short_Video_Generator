# Short-Form Video Generator

This project generates short-form videos with AI-generated stories and uploads them to various social media platforms (YouTube Shorts, Instagram Reels, TikTok).

## Features

- **AI-powered Story Generation:** Uses Google Gemini to create stories based on a specified style (scary, funny, romantic).
- **Text-to-Speech:** Converts the generated script to high-quality audio using `edge-tts`.
- **Video Production:** Lays the audio over provided footage with animated subtitles.
- **Social Media Uploads:** Supports uploading to YouTube Shorts, Instagram Reels, and TikTok (configurable via environment variables).
- **Reusable Pipeline:** Easily extendable to add new video styles.

## Setup

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/short-video-generator.git
    cd short-video-generator
    ```

2.  **Create a Python virtual environment and install dependencies:**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables:**

    Copy the `.env.example` file to `.env` and fill in your API keys and credentials. These are essential for the script to function.

    ```bash
    cp .env.example .env
    ```

    Open `.env` and provide values for:

    -   `GEMINI_API_KEY`: Your Google Gemini API key.
    -   `GTA_FOOTAGE_PATHS`: Comma-separated paths to your video footage files.
    -   `INSTAGRAM_USERNAME` and `INSTAGRAM_PASSWORD`: For Instagram uploads.
    -   `TIKTOK_ACCESS_TOKEN`: Your TikTok Content Posting API access token.
    -   `YOUTUBE_CLIENT_SECRET_FILE`: Path to your YouTube OAuth 2.0 client secret JSON file.

4.  **Install ImageMagick (if not already installed):**

    `moviepy` requires ImageMagick for certain operations. On macOS, you can install it via Homebrew:

    ```bash
    brew install imagemagick
    ```

    On other systems, please refer to the ImageMagick documentation for installation instructions.

## Usage

To generate and upload a video, run one of the entry point scripts:

-   **Scary Story:**

    ```bash
    python3 short_video_generator.py
    ```

-   **Funny Story:**

    ```bash
    python3 funny_video_generator.py
    ```

-   **Romantic Story:**

    ```bash
    python3 romantic_video_generator.py
    ```

You can customize various settings by editing the `.env` file, such as:

-   `UPLOAD_TO_YOUTUBE`, `UPLOAD_TO_INSTAGRAM`, `UPLOAD_TO_TIKTOK`: Enable/disable uploads to specific platforms.
-   `STORY_DURATION_SECONDS`, `WORDS_PER_SECOND`: Control story length.
-   `SUBTITLE_FONT`, `SUBTITLE_FONT_SIZE`, etc.: Customize subtitle appearance.
-   `OUTPUT_VIDEO_PATH`: Specify the output filename (supports `{style}` placeholder).

## Extending

To add a new video style:

1.  **Define a new `VideoPreset` in `video_pipeline.py`** within the `VIDEO_PRESETS` dictionary. This includes prompts, titles, tags, and hashtags specific to your new style.
2.  **Create a new entry point script** (e.g., `my_new_style_generator.py`) that calls `run_pipeline("my_new_style")`.
