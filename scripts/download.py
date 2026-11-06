#!/usr/bin/env python3
"""Douyin & TikTok Video Downloader via REST API.

Pure Python 3 standard library implementation.
Zero third-party dependencies.

The ONLY credential source is config.json in the skill root (the parent of
this scripts/ directory). No environment variables, no absolute paths baked in:
the skill works wherever its directory is placed, on Windows, Linux and macOS.
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

CONFIG_FILENAME = "config.json"
# 技能根目录由脚本位置推导，与当前工作目录、用户主目录、盘符均无关
SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / CONFIG_FILENAME

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class ConfigError(Exception):
    """配置缺失或不合法，需向用户收集信息后重新生成 config.json。"""


def is_http_url(value: str) -> bool:
    """Basic shape check so a typo in base_url is reported as invalid config."""
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def warn_if_insecure_permissions(config_path: Path) -> None:
    """config.json 内含密钥；POSIX 下提醒收紧权限，Windows 依赖用户目录 ACL。"""
    if os.name != "posix":
        return
    try:
        mode = config_path.stat().st_mode
    except OSError:
        return
    if mode & 0o077:
        sys.stderr.write(
            f"Warning: {CONFIG_FILENAME} 对其他用户可读；"
            f"请在技能根目录执行 chmod 600 {CONFIG_FILENAME}\n"
        )


def load_config(config_path: Path | None = None) -> tuple[str, str]:
    """从技能根目录的 config.json 读取凭据，任何其他来源都不参与。"""
    path = config_path or CONFIG_PATH
    if not path.is_file():
        raise ConfigError(f"未找到配置文件 {CONFIG_FILENAME}")

    # utf-8-sig 兼容 Windows 记事本保存时带 BOM 的 JSON
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{CONFIG_FILENAME} 不是合法 JSON: {e}") from e
    except (OSError, UnicodeError) as e:
        raise ConfigError(f"无法读取 {CONFIG_FILENAME}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_FILENAME} 顶层必须是 JSON 对象")

    base_url = str(raw.get("base_url") or "").strip()
    api_key = str(raw.get("api_key") or "").strip()
    problems: list[str] = []
    if not base_url:
        problems.append("base_url 缺失")
    elif not is_http_url(base_url):
        problems.append("base_url 必须是 http:// 或 https:// 开头的地址")
    if not api_key:
        problems.append("api_key 缺失")
    if problems:
        raise ConfigError("配置项无效: " + "、".join(problems))

    warn_if_insecure_permissions(path)
    return base_url.rstrip("/"), api_key


def config_status() -> dict[str, Any]:
    """给 agent 自检用：只报告配置是否有效，绝不把密钥输出到对话或日志。"""
    try:
        load_config()
    except ConfigError as e:
        return {"configured": False, "config_file": CONFIG_FILENAME, "reason": str(e)}
    return {"configured": True, "config_file": CONFIG_FILENAME}


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """生成跨 Windows / Linux / macOS 都合法的文件名片段。"""
    # Windows 禁用字符、ASCII 控制字符；macOS 禁冒号，Linux 禁斜杠与 NUL
    cleaned = re.sub(r'[\\/*?:"<>|\x00-\x1f\x7f]', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Windows 不允许以点或空格结尾，也不允许 CON/PRN/AUX/NUL/COM1.. 等设备名
    cleaned = cleaned[:max_length].rstrip(". ")
    if not cleaned:
        cleaned = "untitled"
    if cleaned.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        cleaned = "_" + cleaned
    return cleaned


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
    base_url, api_key = load_config()
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
    # 非 UTF-8 locale（尤其是英文版 Windows 重定向输出时）避免中文提示触发编码异常
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Download Douyin & TikTok videos/images via REST API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Credentials come only from config.json in the skill root:\n"
            '  {"base_url": "http://host:8000", "api_key": "dtk_xxx"}\n'
            "See config.example.json. No environment variables are read.\n"
        ),
    )
    parser.add_argument("url", nargs="?", help="Video URL or share text containing URL")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Report whether config.json is valid, without printing the API key",
    )
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

    if args.check_config:
        print(json.dumps(config_status(), ensure_ascii=False))
        return
    if not args.url:
        parser.error("必须提供视频链接，或使用 --check-config 检查配置")

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
