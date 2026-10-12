"""Tests for the download.py script."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.download import (
    extract_url,
    get_required_env,
    sanitize_filename,
)


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

    def test_env_validation_fails_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                get_required_env()

    def test_env_validation_succeeds_when_present(self):
        with patch.dict(
            os.environ,
            {"DTK_BASE_URL": "http://1.2.3.4:8000/", "DTK_API_KEY": "dtk_test_123"},
            clear=True,
        ):
            base_url, api_key = get_required_env()
            self.assertEqual(base_url, "http://1.2.3.4:8000")
            self.assertEqual(api_key, "dtk_test_123")


if __name__ == "__main__":
    unittest.main()
