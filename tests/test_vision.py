"""Tests for utils.vision — image encoding."""
import base64

import pytest

from utils.vision import SUPPORTED_FORMATS, encode_image

# 1x1 transparent PNG (smallest possible valid PNG)
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
    b"\xcf\xc0\x00\x00\x00\x03\x00\x01\xa6\xb8\x84_\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestEncodeImage:
    def test_encodes_png(self, tmp_path):
        path = tmp_path / "shot.png"
        path.write_bytes(TINY_PNG)
        data, media_type = encode_image(str(path))
        assert media_type == "image/png"
        assert base64.b64decode(data) == TINY_PNG

    def test_extension_is_case_insensitive(self, tmp_path):
        path = tmp_path / "shot.PNG"
        path.write_bytes(TINY_PNG)
        _, media_type = encode_image(str(path))
        assert media_type == "image/png"

    @pytest.mark.parametrize(
        "ext,expected",
        [
            (".png", "image/png"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".gif", "image/gif"),
            (".webp", "image/webp"),
        ],
    )
    def test_all_supported_formats_map_correctly(self, tmp_path, ext, expected):
        path = tmp_path / f"img{ext}"
        path.write_bytes(b"dummy")
        _, media_type = encode_image(str(path))
        assert media_type == expected

    def test_rejects_unsupported_format(self, tmp_path):
        path = tmp_path / "doc.pdf"
        path.write_bytes(b"%PDF")
        with pytest.raises(ValueError, match="Unsupported format"):
            encode_image(str(path))

    def test_supported_formats_constant_unchanged(self):
        # Guard: if someone adds a format, they should also update this test
        assert set(SUPPORTED_FORMATS) == {".png", ".jpg", ".jpeg", ".gif", ".webp"}
