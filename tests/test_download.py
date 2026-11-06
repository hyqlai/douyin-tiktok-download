"""Tests for the download.py script."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.download as download
from scripts.download import (
    CONFIG_PATH,
    SKILL_DIR,
    ConfigError,
    config_status,
    extract_url,
    is_http_url,
    load_config,
    sanitize_filename,
)


def write_config(directory: Path, content: str) -> Path:
    cfg = directory / "config.json"
    cfg.write_text(content, encoding="utf-8")
    return cfg


class TestDownloadScript(unittest.TestCase):
    def test_extract_url(self):
        # 1. Plain URL
        self.assertEqual(extract_url("https://v.douyin.com/iRoabc/"), "https://v.douyin.com/iRoabc/")
        # 2. Wrapped in app share text
        share_text = "7.12 03/12 d@m.xy 复制打开抖音，看看【小明的作品】 https://v.douyin.com/iRoabc/ 精彩不断"
        self.assertEqual(extract_url(share_text), "https://v.douyin.com/iRoabc/")
        # 3. TikTok link
        tt_text = "Check out this video https://vt.tiktok.com/ZS12345/ on TikTok"
        self.assertEqual(extract_url(tt_text), "https://vt.tiktok.com/ZS12345/")

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("a/b\\c:d*e?f\"g<h>i|j"), "a_b_c_d_e_f_g_h_i_j")
        self.assertEqual(sanitize_filename("   hello   world   "), "hello world")
        self.assertEqual(sanitize_filename(""), "untitled")

    def test_sanitize_filename_windows_compat(self):
        self.assertEqual(sanitize_filename("name."), "name")
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("aux.txt"), "_aux.txt")
        self.assertEqual(sanitize_filename("COM1"), "_COM1")
        self.assertEqual(sanitize_filename("a\x00b\x1fc"), "a_b_c")
        self.assertEqual(sanitize_filename("abcd." + "x" * 100, 5), "abcd")

    def test_config_path_is_relative_to_skill_dir(self):
        self.assertEqual(CONFIG_PATH, SKILL_DIR / "config.json")
        self.assertEqual(SKILL_DIR, Path(download.__file__).resolve().parent.parent)

    def test_load_config_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = write_config(Path(tmp), json.dumps({
                "base_url": "http://1.2.3.4:8000/",
                "api_key": "dtk_test_key",
            }))
            self.assertEqual(load_config(cfg), ("http://1.2.3.4:8000", "dtk_test_key"))

    def test_load_config_handles_windows_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = write_config(Path(tmp), '\ufeff{"base_url": "http://1.2.3.4:8000", "api_key": "k"}')
            self.assertEqual(load_config(cfg), ("http://1.2.3.4:8000", "k"))

    def test_load_config_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(Path(tmp) / "absent.json")

    def test_load_config_rejects_invalid_json_and_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            for content in ("not json", "[]", "{}", '{"base_url": "ftp://host", "api_key": "k"}'):
                with self.subTest(content=content):
                    cfg = write_config(Path(tmp), content)
                    with self.assertRaises(ConfigError):
                        load_config(cfg)

    def test_is_http_url(self):
        self.assertTrue(is_http_url("http://192.168.1.1:8000"))
        self.assertTrue(is_http_url("https://api.example.com"))
        self.assertFalse(is_http_url("192.168.1.1:8000"))
        self.assertFalse(is_http_url("ftp://host"))

    def test_config_status_never_leaks_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = write_config(Path(tmp), json.dumps({
                "base_url": "http://1.2.3.4:8000",
                "api_key": "dtk_super_secret",
            }))
            with patch.object(download, "CONFIG_PATH", cfg):
                status = config_status()
            self.assertTrue(status["configured"])
            self.assertNotIn("dtk_super_secret", json.dumps(status))

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(download, "CONFIG_PATH", Path(tmp) / "absent.json"):
                status = config_status()
            self.assertFalse(status["configured"])
            self.assertIn("reason", status)

    def test_environment_variables_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {"DTK_BASE_URL": "http://env:8000", "DTK_API_KEY": "dtk_env", "DTK_CONFIG": "/some/path"},
                clear=True,
            ):
                with self.assertRaises(ConfigError):
                    load_config(Path(tmp) / "absent.json")


if __name__ == "__main__":
    unittest.main()
