#!/usr/bin/env python3
"""Douyin & TikTok Video Downloader via REST API.

Pure Python 3 standard library implementation.
Zero third-party dependencies.

Requires environment variables:
  - DTK_BASE_URL: Base URL of the Douyin_TikTok_Download_API service
  - DTK_API_KEY:  API Key with douyin:read / tiktok:read scopes
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ENV_BASE_URL = "DTK_BASE_URL"
ENV_API_KEY = "DTK_API_KEY"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def get_required_env() -> tuple[str, str]:
    """Retrieve and strictly validate required environment variables."""
    base_url = (os.environ.get(ENV_BASE_URL) or os.environ.get("DOUYIN_TIKTOK_API_BASE") or "").strip()
    api_key = (os.environ.get(ENV_API_KEY) or os.environ.get("DOUYIN_TIKTOK_API_KEY") or "").strip()

    missing = []
    if not base_url:
        missing.append(f"{ENV_BASE_URL} (e.g., http://192.168.1.100:8000)")
    if not api_key:
        missing.append(f"{ENV_API_KEY} (e.g., dtk_0a1b2c3d4e5f_...)")

    if missing:
        sys.stderr.write("Error: Missing required environment variables.\n")
        sys.stderr.write("This tool does NOT provide default fallback values for security and neutrality.\n")
        sys.stderr.write("Please set the following environment variables before running:\n")
        for item in missing:
            sys.stderr.write(f"  - export {item}\n")
        sys.stderr.write("\nExample:\n")
        sys.stderr.write("  export DTK_BASE_URL='http://your-server-address:8000'\n")
        sys.stderr.write("  export DTK_API_KEY='dtk_your_secret_api_key'\n")
        sys.exit(1)

    return base_url.rstrip("/"), api_key


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Sanitize string for safe filesystem filename."""
    cleaned = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length]


def extract_url(text: str) -> str:
    """Extract first HTTP/HTTPS link from arbitrary text."""
    match = re.search(r"https?://[^\s<>\"']+", text)
    if match:
        return match.group(0)
    return text.strip()


def is_local_or_private(url: str) -> bool:
    """Check if URL targets localhost or private LAN address."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if host.lower() in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def make_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    """Execute HTTP request using urllib and return (status_code, json_data)."""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if is_local_or_private(url)
        else urllib.request.build_opener()
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            status_code = resp.status
            body_bytes = resp.read()
            try:
                body_json = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                body_json = {"raw": body_bytes.decode("utf-8", errors="replace")}
            return status_code, body_json
    except urllib.error.HTTPError as e:
        status_code = e.code
        body_bytes = e.read()
        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body_json = {
                "success": False,
                "error": {"code": "HTTP_ERROR", "message": f"HTTP {status_code}: {e.reason}"},
            }
        return status_code, body_json
    except urllib.error.URLError as e:
        return 0, {
            "success": False,
            "error": {"code": "NETWORK_ERROR", "message": f"Connection failed: {e.reason}"},
        }


def parse_video_url(base_url: str, api_key: str, target_url: str, wait_seconds: int = 15) -> dict[str, Any]:
    """Call REST API /api/v1/parse to parse video URL."""
    api_endpoint = f"{base_url}/api/v1/parse?wait={wait_seconds}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "dtk-skill-downloader/1.0",
        "Accept-Language": "zh",
    }
    payload = json.dumps({"url": target_url}).encode("utf-8")

    status_code, resp_body = make_request(api_endpoint, method="POST", headers=headers, data=payload, timeout=wait_seconds + 10)

    if not resp_body.get("success", False):
        err = resp_body.get("error") or {}
        code = err.get("code", "UNKNOWN_ERROR")
        msg = err.get("message", "API request failed")
        raise RuntimeError(f"Parse API failed [{code}]: {msg}")

    data_payload = resp_body.get("data") or {}

    # If task is still queued/running (HTTP 202 or wait timeout)
    if status_code == 202 or "task_id" in data_payload and data_payload.get("state") in ("queued", "running"):
        task_id = data_payload["task_id"]
        return poll_task_result(base_url, api_key, task_id)

    return data_payload


def poll_task_result(base_url: str, api_key: str, task_id: str, max_timeout: int = 60) -> dict[str, Any]:
    """Poll /api/v1/tasks/{task_id} until task finishes."""
    task_url = f"{base_url}/api/v1/tasks/{task_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "dtk-skill-downloader/1.0",
        "Accept-Language": "zh",
    }

    start_time = time.time()
    sys.stderr.write(f"Task {task_id} is running, waiting for results...\n")

    while time.time() - start_time < max_timeout:
        time.sleep(2)
        status_code, resp_body = make_request(task_url, headers=headers, timeout=10)
        if not resp_body.get("success", False):
            err = resp_body.get("error") or {}
            raise RuntimeError(f"Task query failed [{err.get('code')}]: {err.get('message')}")

        task_data = resp_body.get("data") or {}
        state = task_data.get("state")

        if state == "done":
            return task_data.get("data") or {}
        elif state == "failed":
            err = task_data.get("error") or {}
            raise RuntimeError(f"Task execution failed [{err.get('code')}]: {err.get('message')}")

    raise TimeoutError(f"Task {task_id} timed out after {max_timeout} seconds")


def download_file(url: str, destination: Path, platform: str = "douyin", label: str = "file") -> int:
    """Download remote URL to local file safely using chunked streaming."""
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://www.douyin.com/" if platform == "douyin" else "https://www.tiktok.com/",
    }

    req = urllib.request.Request(url, headers=headers)
    part_path = destination.with_suffix(destination.suffix + ".part")

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(part_path, "wb") as f:
            total_size = resp.headers.get("Content-Length")
            total_bytes = int(total_size) if total_size and total_size.isdigit() else 0
            downloaded = 0

            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

        # Atomic rename after download finishes
        if part_path.exists():
            part_path.replace(destination)
        return downloaded
    except Exception as e:
        if part_path.exists():
            part_path.unlink()
        raise RuntimeError(f"Failed to download {label} from {url}: {e}") from e


def process_download(
    target_input: str,
    output_dir: Path,
    save_cover: bool = False,
    save_music: bool = False,
    save_meta: bool = False,
) -> dict[str, Any]:
    """Execute end-to-end parsing and downloading workflow."""
    base_url, api_key = get_required_env()
    cleaned_url = extract_url(target_input)

    sys.stderr.write(f"Parsing URL: {cleaned_url}\n")
    content = parse_video_url(base_url, api_key, cleaned_url)

    platform = content.get("platform", "douyin")
    content_id = content.get("content_id", str(int(time.time())))
    kind = content.get("kind", "video")
    title = content.get("title", "") or content.get("description", "") or "untitled"
    author_info = content.get("author") or {}
    nickname = author_info.get("nickname") or "unknown_author"

    base_name = f"{platform}_{sanitize_filename(nickname, 30)}_{sanitize_filename(title, 40)}_{content_id}"
    results: dict[str, Any] = {
        "platform": platform,
        "content_id": content_id,
        "kind": kind,
        "title": title,
        "author": nickname,
        "downloaded_files": [],
    }

    media = content.get("media") or {}

    # 1. Download Video
    if kind == "video":
        video_obj = media.get("video") or {}
        video_url = video_obj.get("url") or (video_obj.get("urls") or [None])[0]
        if not video_url:
            # Fallback to streams
            streams = media.get("streams") or []
            if streams:
                video_url = streams[0].get("url") or (streams[0].get("urls") or [None])[0]

        if video_url:
            dest_file = output_dir / f"{base_name}.mp4"
            sys.stderr.write(f"Downloading video to {dest_file.name}...\n")
            bytes_written = download_file(video_url, dest_file, platform=platform, label="video")
            results["downloaded_files"].append({
                "type": "video",
                "path": str(dest_file.resolve()),
                "size_bytes": bytes_written,
            })
        else:
            sys.stderr.write("Warning: No video stream URL found in content response.\n")

    # 2. Download Image Album
    elif kind == "image_album":
        images = media.get("images") or []
        album_dir = output_dir / base_name
        album_dir.mkdir(parents=True, exist_ok=True)
        sys.stderr.write(f"Downloading image album ({len(images)} images) to {album_dir.name}/...\n")

        for idx, img in enumerate(images, start=1):
            img_url = img.get("url") or (img.get("urls") or [None])[0]
            if img_url:
                img_dest = album_dir / f"image_{idx:02d}.jpg"
                bytes_written = download_file(img_url, img_dest, platform=platform, label=f"image {idx}")
                results["downloaded_files"].append({
                    "type": f"image_{idx:02d}",
                    "path": str(img_dest.resolve()),
                    "size_bytes": bytes_written,
                })

    # 3. Optional Cover
    if save_cover:
        covers = media.get("covers") or []
        if covers:
            cover_url = covers[0].get("url") or (covers[0].get("urls") or [None])[0]
            if cover_url:
                cover_dest = output_dir / f"{base_name}_cover.jpg"
                sys.stderr.write(f"Downloading cover to {cover_dest.name}...\n")
                bytes_written = download_file(cover_url, cover_dest, platform=platform, label="cover")
                results["downloaded_files"].append({
                    "type": "cover",
                    "path": str(cover_dest.resolve()),
                    "size_bytes": bytes_written,
                })

    # 4. Optional Music
    if save_music:
        music_obj = content.get("music") or {}
        music_url = music_obj.get("play_url")
        if music_url:
            music_dest = output_dir / f"{base_name}_audio.mp3"
            sys.stderr.write(f"Downloading audio to {music_dest.name}...\n")
            bytes_written = download_file(music_url, music_dest, platform=platform, label="audio")
            results["downloaded_files"].append({
                "type": "audio",
                "path": str(music_dest.resolve()),
                "size_bytes": bytes_written,
            })

    # 5. Optional JSON Metadata
    if save_meta:
        meta_dest = output_dir / f"{base_name}_meta.json"
        with open(meta_dest, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        results["downloaded_files"].append({
            "type": "metadata",
            "path": str(meta_dest.resolve()),
            "size_bytes": meta_dest.stat().st_size,
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Douyin & TikTok videos/images via REST API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment variables required:\n"
            "  DTK_BASE_URL   Base URL of the service (e.g. http://127.0.0.1:8000)\n"
            "  DTK_API_KEY    API Key for authentication (e.g. dtk_xxx)\n"
        ),
    )
    parser.add_argument("url", help="Video URL or share text containing URL")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="./downloads",
        help="Directory to save downloaded files (default: ./downloads)",
    )
    parser.add_argument("--save-cover", action="store_true", help="Also download video cover image")
    parser.add_argument("--save-music", action="store_true", help="Also download background audio (MP3)")
    parser.add_argument("--save-meta", action="store_true", help="Save complete JSON metadata alongside files")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")

    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    try:
        summary = process_download(
            target_input=args.url,
            output_dir=out_dir,
            save_cover=args.save_cover,
            save_music=args.save_music,
            save_meta=args.save_meta,
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("\nDownload Complete!")
            print(f"Platform: {summary['platform']}")
            print(f"Author:   {summary['author']}")
            print(f"Title:    {summary['title']}")
            print("Files:")
            for f in summary["downloaded_files"]:
                size_mb = f["size_bytes"] / (1024 * 1024)
                print(f"  - [{f['type']}] {f['path']} ({size_mb:.2f} MB)")
    except Exception as e:
        sys.stderr.write(f"\nError: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
