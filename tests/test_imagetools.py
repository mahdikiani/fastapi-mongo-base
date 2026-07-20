"""Tests for image utility helpers."""

from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from src.fastapi_mongo_base.utils import imagetools

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rgb_image(
    size: tuple[int, int] = (100, 100),
    color: tuple[int, int, int] = (255, 0, 0),
) -> Image.Image:
    return Image.new("RGB", size, color)


def _rgba_image(
    size: tuple[int, int] = (100, 100),
    color: tuple[int, int, int] = (255, 0, 0),
) -> Image.Image:
    img = Image.new("RGBA", size, color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0] // 2, size[1] // 2], fill=(*color, 128))
    return img


def _image_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ===================================================================
# rgb_to_hex
# ===================================================================


class TestRgbToHex:
    """Tests for rgb_to_hex."""

    def test_black(self) -> None:
        """Test black color conversion."""
        assert imagetools.rgb_to_hex((0, 0, 0)) == "#000000"

    def test_white(self) -> None:
        """Test white color conversion."""
        assert imagetools.rgb_to_hex((255, 255, 255)) == "#ffffff"

    def test_red(self) -> None:
        """Test red color conversion."""
        assert imagetools.rgb_to_hex((255, 0, 0)) == "#ff0000"

    def test_green(self) -> None:
        """Test green color conversion."""
        assert imagetools.rgb_to_hex((0, 255, 0)) == "#00ff00"

    def test_blue(self) -> None:
        """Test blue color conversion."""
        assert imagetools.rgb_to_hex((0, 0, 255)) == "#0000ff"

    def test_clamp_above_255(self) -> None:
        """Test clamping values above 255."""
        assert imagetools.rgb_to_hex((300, 150, 0)) == "#ff9600"

    def test_clamp_below_0(self) -> None:
        """Test clamping values below 0."""
        assert imagetools.rgb_to_hex((-50, 128, 255)) == "#0080ff"

    def test_mid_gray(self) -> None:
        """Test mid-gray color conversion."""
        assert imagetools.rgb_to_hex((128, 128, 128)) == "#808080"


# ===================================================================
# rgb_to_xyz
# ===================================================================


class TestRgbToXyz:
    """Tests for rgb_to_xyz."""

    def test_black(self) -> None:
        """Test black conversion."""
        assert imagetools.rgb_to_xyz((0, 0, 0)) == (0, 0, 0)

    def test_white(self) -> None:
        """Test white conversion."""
        x, y, z = imagetools.rgb_to_xyz((255, 255, 255))
        assert x == pytest.approx(0.95047, rel=1e-4)
        assert y == pytest.approx(1.0, rel=1e-4)
        assert z == pytest.approx(1.08883, rel=1e-4)

    def test_red(self) -> None:
        """Test red conversion."""
        x, y, z = imagetools.rgb_to_xyz((255, 0, 0))
        assert x == pytest.approx(0.4124564, rel=1e-3)
        assert y == pytest.approx(0.2126729, rel=1e-3)
        assert z == pytest.approx(0.0193339, rel=1e-3)

    def test_below_srgb_threshold(self) -> None:
        """RGB value below 0.04045 (after /255) uses linear branch."""
        x, y, z = imagetools.rgb_to_xyz((10, 10, 10))
        assert x / 0.95047 == pytest.approx(y, abs=1e-6)
        assert y == pytest.approx(z / 1.08883, abs=1e-6)

    def test_above_srgb_threshold(self) -> None:
        """RGB value above 0.04045 (after /255) uses gamma branch."""
        x, y, z = imagetools.rgb_to_xyz((200, 200, 200))
        assert x / 0.95047 == pytest.approx(y, abs=1e-6)
        assert y == pytest.approx(z / 1.08883, abs=1e-6)


# ===================================================================
# xyz_to_lab
# ===================================================================


class TestXyzToLab:
    """Tests for xyz_to_lab."""

    def test_white_reference(self) -> None:
        """Test white reference conversion."""
        lightness, a, b = imagetools.xyz_to_lab((0.95047, 1.0, 1.08883))
        assert pytest.approx(100.0, abs=0.5) == lightness
        assert a == pytest.approx(0.0, abs=0.5)
        assert b == pytest.approx(0.0, abs=0.5)

    def test_black(self) -> None:
        """Test black conversion."""
        lightness, a, b = imagetools.xyz_to_lab((0, 0, 0))
        assert pytest.approx(0.0, abs=0.1) == lightness
        assert a == pytest.approx(0.0, abs=0.1)
        assert b == pytest.approx(0.0, abs=0.1)

    def test_gray(self) -> None:
        """Proper gray: x/xn == y/yn == z/zn so a* == b* == 0."""
        xn, yn, zn = 0.95047, 1.0, 1.08883
        k = 0.5
        x, y, z = k * xn, k * yn, k * zn
        _lightness, a, b = imagetools.xyz_to_lab((x, y, z))
        assert a == pytest.approx(0.0, abs=0.5)
        assert b == pytest.approx(0.0, abs=0.5)

    def test_f_t_above_threshold(self) -> None:
        """f(t) = t^(1/3) branch  (t > 0.008856)."""
        lightness, _a, _b = imagetools.xyz_to_lab((1.0, 1.0, 1.0))
        assert lightness > 0

    def test_f_t_below_threshold(self) -> None:
        """f(t) = 7.787*t + 16/116 branch."""
        xyz = (0.001, 0.001, 0.001)
        lightness, _a, _b = imagetools.xyz_to_lab(xyz)
        assert pytest.approx(0.0, abs=1.0) == lightness


# -------------------------------------------------------------------
# rgb_to_lab  (integration test)
# -------------------------------------------------------------------


class TestRgbToLab:
    """Tests for rgb_to_lab."""

    def test_white(self) -> None:
        """Test white conversion."""
        lightness, a, b = imagetools.rgb_to_lab((255, 255, 255))
        assert lightness > 95
        assert a == pytest.approx(0.0, abs=2.0)
        assert b == pytest.approx(0.0, abs=2.0)

    def test_black(self) -> None:
        """Test black conversion."""
        lightness, _a, _b = imagetools.rgb_to_lab((0, 0, 0))
        assert pytest.approx(0.0, abs=1.0) == lightness

    def test_red(self) -> None:
        """Test red conversion."""
        _lightness, a, _b = imagetools.rgb_to_lab((255, 0, 0))
        assert a > 0  # red is positive a*


# ===================================================================
# add_watermark_to_image
# ===================================================================


class TestAddWatermarkToImage:
    """Tests for add_watermark_to_image."""

    def test_raises_type_error(self, tmp_path: pytest.TempPathFactory) -> None:
        """
        Known bug: paste() call has an extra positional argument.

        (watermark passed as 4th positional arg) which raises TypeError.
        """
        bg = _rgb_image((200, 200), (0, 0, 255))
        wm = _rgb_image((50, 50), (255, 255, 0))
        bg_path = tmp_path / "bg.png"
        wm_path = tmp_path / "wm.png"
        bg.save(bg_path)
        wm.save(wm_path)
        with pytest.raises(TypeError):
            imagetools.add_watermark_to_image(str(bg_path), str(wm_path))

    def test_raises_type_error_with_resize(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test that resize parameter triggers TypeError."""
        bg = _rgb_image((200, 200), (0, 0, 255))
        wm = _rgb_image((50, 50), (255, 255, 0))
        bg_path = tmp_path / "bg.png"
        wm_path = tmp_path / "wm.png"
        bg.save(bg_path)
        wm.save(wm_path)
        with pytest.raises(TypeError):
            imagetools.add_watermark_to_image(
                str(bg_path), str(wm_path), resize=(100, 100)
            )

    def test_raises_type_error_with_position(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test that position parameter triggers TypeError."""
        bg = _rgb_image((200, 200), (0, 0, 255))
        wm = _rgb_image((50, 50), (255, 255, 0))
        bg_path = tmp_path / "bg.png"
        wm_path = tmp_path / "wm.png"
        bg.save(bg_path)
        wm.save(wm_path)
        with pytest.raises(TypeError):
            imagetools.add_watermark_to_image(
                str(bg_path), str(wm_path), position=(10, 10)
            )


# ===================================================================
# get_aspect_ratio_str
# ===================================================================


class TestGetAspectRatioStr:
    """Tests for get_aspect_ratio_str."""

    def test_16_9(self) -> None:
        """Test 16:9 aspect ratio."""
        assert imagetools.get_aspect_ratio_str(1920, 1080) == "16:9"

    def test_4_3(self) -> None:
        """Test 4:3 aspect ratio."""
        assert imagetools.get_aspect_ratio_str(4, 3) == "4:3"

    def test_1_1(self) -> None:
        """Test 1:1 aspect ratio."""
        assert imagetools.get_aspect_ratio_str(100, 100) == "1:1"

    def test_portrait(self) -> None:
        """Test portrait orientation."""
        assert imagetools.get_aspect_ratio_str(1080, 1920) == "9:16"

    def test_ultrawide(self) -> None:
        """Test ultrawide aspect ratio."""
        assert imagetools.get_aspect_ratio_str(3440, 1440) == "43:18"


# ===================================================================
# resize_image
# ===================================================================


class TestResizeImage:
    """Tests for resize_image."""

    def test_by_width(self) -> None:
        """Test resize by width only."""
        img = _rgb_image((200, 100))
        result = imagetools.resize_image(img, new_width=100)
        assert result.size == (100, 50)

    def test_by_height(self) -> None:
        """Test resize by height only."""
        img = _rgb_image((200, 100))
        result = imagetools.resize_image(img, new_width=None, new_height=50)
        assert result.size == (100, 50)

    def test_by_both(self) -> None:
        """Test resize by both width and height."""
        img = _rgb_image((200, 100))
        result = imagetools.resize_image(img, new_width=100, new_height=50)
        assert result.size == (100, 50)

    def test_none_returns_original(self) -> None:
        """Test that None dimensions return original image."""
        img = _rgb_image((200, 100))
        result = imagetools.resize_image(img, new_width=None, new_height=None)
        assert result is img
        assert result.size == (200, 100)

    def test_default_width(self) -> None:
        """Test default width is used."""
        img = _rgb_image((200, 100))
        result = imagetools.resize_image(img)
        assert result.size == (384, 192)

    def test_from_bytesio(self) -> None:
        """Test resize from BytesIO input."""
        img = _rgb_image((200, 100))
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        result = imagetools.resize_image(buf, new_width=100)
        assert result.size == (100, 50)

    def test_width_from_height(self) -> None:
        """Test width derived from height."""
        img = _rgb_image((100, 200))
        result = imagetools.resize_image(img, new_width=None, new_height=50)
        assert result.size == (25, 50)


# ===================================================================
# split_image
# ===================================================================


class TestSplitImage:
    """Tests for split_image."""

    def test_2x2(self) -> None:
        """Test 2x2 grid split."""
        img = _rgb_image((200, 200))
        parts = imagetools.split_image(img, (2, 2))
        assert len(parts) == 4
        assert all(p.size == (100, 100) for p in parts)

    def test_3x2(self) -> None:
        """Test 3x2 grid split."""
        img = _rgb_image((300, 200))
        parts = imagetools.split_image(img, (3, 2))
        assert len(parts) == 6
        assert parts[0].size == (100, 100)

    def test_1x1_returns_whole(self) -> None:
        """Test 1x1 returns whole image."""
        img = _rgb_image((200, 150))
        parts = imagetools.split_image(img, (1, 1))
        assert len(parts) == 1
        assert parts[0].size == (200, 150)

    def test_non_even_division(self) -> None:
        """Test non-even division still works."""
        img = _rgb_image((101, 101))
        parts = imagetools.split_image(img, (2, 2))
        assert len(parts) == 4

    def test_order_top_to_bottom_left_to_right(self) -> None:
        """Test parts are ordered top-to-bottom, left-to-right."""
        img = Image.new("RGB", (100, 100))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 49, 49], fill=(255, 0, 0))  # top-left
        draw.rectangle([50, 0, 99, 49], fill=(0, 255, 0))  # top-right
        draw.rectangle([0, 50, 49, 99], fill=(0, 0, 255))  # bottom-left
        draw.rectangle([50, 50, 99, 99], fill=(255, 255, 0))  # bottom-right
        parts = imagetools.split_image(img, (2, 2))
        assert len(parts) == 4
        assert parts[0].getpixel((0, 0)) == (255, 0, 0)
        assert parts[1].getpixel((0, 0)) == (0, 255, 0)
        assert parts[2].getpixel((0, 0)) == (0, 0, 255)
        assert parts[3].getpixel((0, 0)) == (255, 255, 0)


# ===================================================================
# is_aspect_ratio_valid
# ===================================================================


class TestIsAspectRatioValid:
    """Tests for is_aspect_ratio_valid."""

    def test_exact_match(self) -> None:
        """Test exact aspect ratio match."""
        img = _rgb_image((100, 100))
        assert imagetools.is_aspect_ratio_valid(img, target_ratio=1.0) is True

    def test_within_tolerance(self) -> None:
        """Test within tolerance."""
        img = _rgb_image((105, 100))
        assert (
            imagetools.is_aspect_ratio_valid(
                img, target_ratio=1.0, tolerance=0.1
            )
            is True
        )

    def test_outside_tolerance(self) -> None:
        """Test outside tolerance."""
        img = _rgb_image((200, 100))
        assert (
            imagetools.is_aspect_ratio_valid(
                img, target_ratio=1.0, tolerance=0.05
            )
            is False
        )

    def test_default_target_and_tolerance(self) -> None:
        """Test default target and tolerance."""
        img = _rgb_image((100, 100))
        assert imagetools.is_aspect_ratio_valid(img) is True

    def test_landscape_fails_for_square_target(self) -> None:
        """Test landscape fails for square target."""
        img = _rgb_image((200, 100))
        assert imagetools.is_aspect_ratio_valid(img, target_ratio=1.0) is False

    def test_exactly_on_upper_boundary(self) -> None:
        """Test exactly on upper tolerance boundary."""
        img = _rgb_image((105, 100))
        assert (
            imagetools.is_aspect_ratio_valid(
                img, target_ratio=1.0, tolerance=0.05
            )
            is True
        )

    def test_exactly_on_lower_boundary(self) -> None:
        """Test exactly on lower tolerance boundary."""
        img = _rgb_image((95, 100))
        assert (
            imagetools.is_aspect_ratio_valid(
                img, target_ratio=1.0, tolerance=0.05
            )
            is True
        )


# ===================================================================
# has_white_border
# ===================================================================


class TestHasWhiteBorder:
    """Tests for has_white_border."""

    def test_true_with_white_border(self) -> None:
        """Test detection of white border."""
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([2, 2, 97, 97], fill=(0, 0, 0))
        assert imagetools.has_white_border(img) is True

    def test_false_all_black(self) -> None:
        """Test all-black image returns False."""
        img = Image.new("RGB", (100, 100), (0, 0, 0))
        assert imagetools.has_white_border(img) is False

    def test_custom_ratio_true(self) -> None:
        """Test custom ratio returns True."""
        img = Image.new("RGB", (10, 10), (255, 255, 255))
        img.putpixel((0, 0), (0, 0, 0))
        assert imagetools.has_white_border(img, ratio=0.9) is True

    def test_custom_ratio_false(self) -> None:
        """Test custom ratio returns False."""
        img = Image.new("RGB", (10, 10), (255, 255, 255))
        img.putpixel((0, 0), (0, 0, 0))
        assert imagetools.has_white_border(img, ratio=0.99) is False

    def test_almost_white_edge_counts(self) -> None:
        """Test almost-white edge counts as white."""
        img = Image.new("RGB", (100, 100), (241, 241, 241))
        draw = ImageDraw.Draw(img)
        draw.rectangle([2, 2, 97, 97], fill=(0, 0, 0))
        assert imagetools.has_white_border(img) is True


# ===================================================================
# square_pad_white_pixels
# ===================================================================


class TestSquarePadWhitePixels:
    """Tests for square_pad_white_pixels."""

    def test_landscape(self) -> None:
        """Test padding landscape image."""
        img = _rgb_image((200, 100), (255, 0, 0))
        result = imagetools.square_pad_white_pixels(img)
        assert result.size == (200, 200)

    def test_portrait(self) -> None:
        """Test padding portrait image."""
        img = _rgb_image((100, 200), (255, 0, 0))
        result = imagetools.square_pad_white_pixels(img)
        assert result.size == (200, 200)

    def test_already_square(self) -> None:
        """Test already square image stays unchanged."""
        img = _rgb_image((100, 100), (255, 0, 0))
        result = imagetools.square_pad_white_pixels(img)
        assert result.size == (100, 100)
        # pixel data unchanged
        assert result.getpixel((50, 50)) == (255, 0, 0)

    def test_pads_with_white(self) -> None:
        """Test padding with white."""
        img = _rgb_image((100, 200), (255, 0, 0))
        result = imagetools.square_pad_white_pixels(img)
        assert result.getpixel((0, 0)) == (255, 255, 255)  # left pad is white

    def test_centers_content(self) -> None:
        """Test content is centered after padding."""
        img = _rgb_image((100, 200), (255, 0, 0))
        result = imagetools.square_pad_white_pixels(img)
        # Original horizontal center at x=50 remains at x=50
        # Original vertical center at y=100 shifts to y=100 in new 200x200
        assert result.getpixel((50, 100)) == (255, 0, 0)


# ===================================================================
# convert_image
# ===================================================================


class TestConvertImage:
    """Tests for convert_image."""

    def test_jpeg_rgb(self) -> None:
        """Test JPEG conversion from RGB."""
        img = _rgb_image((100, 100))
        result = imagetools.convert_image(img, "JPEG")
        assert result.mode == "RGB"
        assert result.size == (100, 100)

    def test_png_rgb(self) -> None:
        """Test PNG conversion from RGB."""
        img = _rgb_image((100, 100))
        result = imagetools.convert_image(img, "PNG")
        assert result.mode == "RGB"

    def test_png_rgba_preserved(self) -> None:
        """Test PNG preserves RGBA."""
        img = _rgba_image((100, 100))
        result = imagetools.convert_image(img, "PNG")
        assert result.mode == "RGBA"

    def test_webp_rgba_preserved(self) -> None:
        """Test WEBP preserves RGBA."""
        img = _rgba_image((100, 100))
        result = imagetools.convert_image(img, "WEBP")
        assert result.mode == "RGBA"

    def test_jpeg_flattens_rgba(self) -> None:
        """Test JPEG flattens RGBA to RGB."""
        img = _rgba_image((100, 100))
        result = imagetools.convert_image(img, "JPEG")
        assert result.mode == "RGB"

    def test_bmp_flattens_rgba(self) -> None:
        """Test BMP flattens RGBA to RGB."""
        img = _rgba_image((100, 100))
        result = imagetools.convert_image(img, "BMP")
        assert result.mode == "RGB"

    def test_gif_flattens_rgba(self) -> None:
        """Test GIF flattens RGBA to RGB."""
        img = _rgba_image((100, 100))
        result = imagetools.convert_image(img, "GIF")
        assert result.mode == "RGB"

    def test_jpeg_rgba_custom_bg(self) -> None:
        """Test JPEG with custom background color."""
        img = _rgba_image((100, 100))
        result = imagetools.convert_image(img, "JPEG", bg_color=(0, 0, 0))
        assert result.mode == "RGB"

    def test_webp_rgb(self) -> None:
        """Test WEBP conversion from RGB."""
        img = _rgb_image((100, 100))
        result = imagetools.convert_image(img, "WEBP")
        assert result.mode == "RGB"


# ===================================================================
# convert_image_bytes
# ===================================================================


class TestConvertImageBytes:
    """Tests for convert_image_bytes."""

    def test_jpeg_magic_bytes(self) -> None:
        """Test JPEG magic bytes."""
        img = _rgb_image((100, 100))
        buf = imagetools.convert_image_bytes(img, "JPEG")
        assert buf.getvalue()[:3] == b"\xff\xd8\xff"

    def test_png_magic_bytes(self) -> None:
        """Test PNG magic bytes."""
        img = _rgb_image((100, 100))
        buf = imagetools.convert_image_bytes(img, "PNG")
        assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_webp_magic_bytes(self) -> None:
        """Test WEBP magic bytes."""
        img = _rgb_image((100, 100))
        buf = imagetools.convert_image_bytes(img, "WEBP")
        assert buf.getvalue()[:4] == b"RIFF"

    def test_bmp_magic_bytes(self) -> None:
        """Test BMP magic bytes."""
        img = _rgb_image((100, 100))
        buf = imagetools.convert_image_bytes(img, "BMP")
        assert buf.getvalue()[:2] == b"BM"

    def test_gif_magic_bytes(self) -> None:
        """Test GIF magic bytes."""
        img = _rgb_image((100, 100))
        buf = imagetools.convert_image_bytes(img, "GIF")
        assert buf.getvalue()[:3] == b"GIF"

    def test_lower_quality_smaller_file(self) -> None:
        """Test lower quality produces smaller file."""
        img = _rgb_image((500, 500))
        buf_low = imagetools.convert_image_bytes(img, "JPEG", quality=10)
        buf_high = imagetools.convert_image_bytes(img, "JPEG", quality=95)
        assert len(buf_low.getvalue()) < len(buf_high.getvalue())

    def test_seek_zero(self) -> None:
        """Test buffer is seeked to position 0."""
        img = _rgb_image((100, 100))
        buf = imagetools.convert_image_bytes(img, "PNG")
        assert buf.tell() == 0


# ===================================================================
# strip_metadata
# ===================================================================


class TestStripMetadata:
    """Tests for strip_metadata."""

    def test_returns_converted_image(self) -> None:
        """Test returns converted image."""
        img = _rgb_image((100, 100))
        result = imagetools.strip_metadata(img, "JPEG")
        assert result.mode == "RGB"
        assert result.size == (100, 100)

    def test_round_trips_png(self) -> None:
        """Test round-trip with PNG preserves RGBA."""
        img = _rgba_image((100, 100))
        result = imagetools.strip_metadata(img, "PNG")
        assert result.mode == "RGBA"


# ===================================================================
# image_to_base64
# ===================================================================


class TestImageToBase64:
    """Tests for image_to_base64."""

    def test_with_header_png(self) -> None:
        """Test PNG with base64 header."""
        img = _rgb_image((100, 100))
        result = imagetools.image_to_base64(img, "PNG")
        assert result.startswith("data:image/PNG;base64,")

    def test_without_header(self) -> None:
        """Test PNG without base64 header."""
        img = _rgb_image((100, 100))
        result = imagetools.image_to_base64(
            img, "PNG", include_base64_header=False
        )
        assert not result.startswith("data:")
        base64.b64decode(result)

    def test_jpeg_format(self) -> None:
        """Test JPEG format."""
        img = _rgb_image((100, 100))
        result = imagetools.image_to_base64(img, "JPEG")
        assert result.startswith("data:image/JPEG;base64,")

    def test_webp_format(self) -> None:
        """Test WEBP format."""
        img = _rgb_image((100, 100))
        result = imagetools.image_to_base64(img, "WEBP")
        assert result.startswith("data:image/WEBP;base64,")

    def test_decodes_back(self) -> None:
        """Test round-trip decodes back."""
        img = _rgb_image((100, 100))
        encoded = imagetools.image_to_base64(img, "PNG")
        header, _, b64_data = encoded.partition(",")
        assert header == "data:image/PNG;base64"
        decoded = base64.b64decode(b64_data)
        loaded = Image.open(BytesIO(decoded))
        assert loaded.size == (100, 100)


# ===================================================================
# load_from_base64
# ===================================================================


class TestLoadFromBase64:
    """Tests for load_from_base64."""

    def test_valid_png(self) -> None:
        """Test loading valid PNG."""
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        loaded = imagetools.load_from_base64(b64)
        assert loaded.size == (100, 100)

    def test_valid_jpeg(self) -> None:
        """Test loading valid JPEG."""
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "JPEG")
        loaded = imagetools.load_from_base64(b64)
        assert loaded.size == (100, 100)

    def test_padding_not_needed(self) -> None:
        """Base64 string with length % 4 == 0."""
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        loaded = imagetools.load_from_base64(b64)
        assert loaded.size == (100, 100)

    def test_invalid_no_data_header(self) -> None:
        """Test invalid base64 with no data header."""
        with pytest.raises(ValueError, match="Invalid base64 encoded string"):
            imagetools.load_from_base64("data:image/png;base64")

    def test_invalid_no_image_prefix(self) -> None:
        """Test invalid base64 with no image prefix."""
        with pytest.raises(ValueError, match="Invalid base64 encoded string"):
            imagetools.load_from_base64("not an image string")

    def test_invalid_missing_comma(self) -> None:
        """Test invalid base64 missing comma."""
        with pytest.raises(ValueError, match="Invalid base64 encoded string"):
            imagetools.load_from_base64("data:image/png;base64ABCD")


# ===================================================================
# load_from_url  (async)
# ===================================================================


@pytest.mark.asyncio
class TestLoadFromUrl:
    """Tests for load_from_url."""

    async def test_loads_image(self) -> None:
        """Test loading image from URL."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await imagetools.load_from_url(
                "https://example.com/img.png"
            )
            assert result.size == (100, 100)

    async def test_raises_on_http_error(self) -> None:
        """Test raises on HTTP error."""
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.raise_for_status.side_effect = (
            imagetools.httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
        )

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with (
            patch(
                "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
                return_value=mock_client,
            ),
            pytest.raises(imagetools.httpx.HTTPStatusError),
        ):
            await imagetools.load_from_url("https://example.com/not-found")

    async def test_passes_kwargs(self) -> None:
        """Test kwargs are passed through."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await imagetools.load_from_url(
                "https://example.com/img.png",
                follow_redirects=False,
                timeout=5.0,
            )
            mock_client.get.assert_called_with(
                "https://example.com/img.png",
                follow_redirects=False,
                timeout=5.0,
            )


# ===================================================================
# get_image_metadata  (async)
# ===================================================================


@pytest.mark.asyncio
class TestGetImageMetadata:
    """Tests for get_image_metadata."""

    async def test_from_base64(self) -> None:
        """Test metadata from base64."""
        img = _rgb_image((100, 100), (255, 0, 0))
        b64 = imagetools.image_to_base64(img, "PNG")
        meta = await imagetools.get_image_metadata(b64)
        assert meta["width"] == 100
        assert meta["height"] == 100
        assert meta["file_type"] == "PNG"
        assert meta["content_type"] == "image/PNG"
        assert meta["mode"] == "RGB"

    async def test_with_range_request(self) -> None:
        """Test metadata with range request."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {
            "Content-Type": "image/png",
            "Content-Length": str(len(img_bytes)),
        }

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            meta = await imagetools.get_image_metadata(
                "https://example.com/img.png", use_range=True
            )
            assert meta["width"] == 100
            assert meta["height"] == 100
            assert meta["content_type"] == "image/png"
            assert meta["content_length"] == len(img_bytes)
            assert meta["file_type"] == "PNG"
            # range header sent
            call_headers = mock_client.get.call_args[1].get("headers", {})
            assert "Range" in call_headers

    async def test_without_exif(self) -> None:
        """Test metadata without exif."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "image/png"}

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            meta = await imagetools.get_image_metadata(
                "https://example.com/img.png",
                use_range=False,
                with_exif=False,
            )
            assert "exif" not in meta

    async def test_fallback_on_failed_range(self) -> None:
        """Test fallback on failed range request."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")

        # range response — too short to parse
        mock_range = MagicMock(spec=imagetools.httpx.Response)
        mock_range.content = b"too short"
        mock_range.raise_for_status = MagicMock()
        mock_range.headers = {"Content-Type": "image/png"}

        # full download — valid image
        mock_full = MagicMock(spec=imagetools.httpx.Response)
        mock_full.content = img_bytes
        mock_full.raise_for_status = MagicMock()
        mock_full.headers = {
            "Content-Type": "image/png",
            "Content-Length": str(len(img_bytes)),
        }

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.side_effect = [mock_range, mock_full]
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            meta = await imagetools.get_image_metadata(
                "https://example.com/img.png",
                use_range=True,
                fallback=True,
            )
            assert meta["width"] == 100
            assert meta["height"] == 100

    async def test_no_fallback_raises_value_error(self) -> None:
        """Test no fallback raises ValueError."""
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = b"unparseable"
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "image/png"}

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with (
            patch(
                "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
                return_value=mock_client,
            ),
            pytest.raises(
                ValueError, match="Could not determine image dimensions"
            ),
        ):
            await imagetools.get_image_metadata(
                "https://example.com/img.png",
                use_range=True,
                fallback=False,
            )

    async def test_fallback_still_fails_raises(self) -> None:
        """Test fallback still failing raises error."""
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = b"still unparseable"
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "image/png"}

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with (
            patch(
                "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
                return_value=mock_client,
            ),
            pytest.raises(
                ValueError,
                match="Could not determine image dimensions after"
                " full download",
            ),
        ):
            await imagetools.get_image_metadata(
                "https://example.com/img.png",
                use_range=True,
                fallback=True,
            )

    async def test_http_error_propagates(self) -> None:
        """Test HTTP error propagates."""
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.raise_for_status.side_effect = (
            imagetools.httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
        )

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with (
            patch(
                "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
                return_value=mock_client,
            ),
            pytest.raises(imagetools.httpx.HTTPStatusError),
        ):
            await imagetools.get_image_metadata("https://example.com/img.png")


# ===================================================================
# compress_image
# ===================================================================


class TestCompressImage:
    """Tests for compress_image."""

    def test_under_limit_returns_unchanged(self) -> None:
        """Test under limit returns unchanged."""
        img = _rgb_image((10, 10))
        result = imagetools.compress_image(img, max_size_kb=999_999)
        assert result.size == (10, 10)

    def test_over_limit_resizes_down(self) -> None:
        """A large detailed image with a tight size limit triggers resizing."""
        img = Image.new("RGB", (1000, 1000), (255, 0, 0))
        draw = ImageDraw.Draw(img)
        for x in range(0, 1000, 20):
            draw.line([(x, 0), (x, 1000)], fill=(0, 255, 0))
            draw.line([(0, x), (1000, x)], fill=(0, 0, 255))
        result = imagetools.compress_image(img, max_size_kb=1, quality=90)
        assert result.size[0] <= 1000
        assert result.size[1] <= 1000

    def test_png_format(self) -> None:
        """Test PNG format compression."""
        img = _rgb_image((100, 100))
        result = imagetools.compress_image(
            img, max_size_kb=999_999, image_format="PNG"
        )
        assert result.size == (100, 100)

    def test_webp_format(self) -> None:
        """Test WEBP format compression."""
        img = _rgb_image((100, 100))
        result = imagetools.compress_image(
            img, max_size_kb=999_999, image_format="WEBP"
        )
        assert result.size == (100, 100)


# ===================================================================
# download_image  (async)
# ===================================================================


@pytest.mark.asyncio
class TestDownloadImage:
    """Tests for download_image."""

    async def test_from_base64_no_constraints(self) -> None:
        """Test download from base64 without constraints."""
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image(b64)
        assert result.size == (100, 100)
        assert result.mode == "RGB"

    async def test_from_base64_with_max_width(self) -> None:
        """Test download from base64 with max width."""
        img = _rgb_image((200, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image(b64, max_width=100)
        assert result.size == (100, 50)

    async def test_from_base64_with_max_size(self) -> None:
        """Test download from base64 with max size."""
        img = _rgb_image((10, 10))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image(b64, max_size_kb=999_999)
        assert result.size == (10, 10)

    async def test_from_base64_strips_metadata(self) -> None:
        """Test download from base64 strips metadata."""
        img = _rgba_image((50, 50))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image(b64)
        # strip_metadata via convert_image default JPEG flattens RGBA → RGB
        assert result.mode == "RGB"

    async def test_from_url(self) -> None:
        """Test download from URL."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await imagetools.download_image(
                "https://example.com/img.png",
                max_width=50,
            )
            assert result.size[0] <= 50
            assert result.mode == "RGB"

    async def test_from_url_strips_metadata(self) -> None:
        """Test download from URL strips metadata."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await imagetools.download_image(
                "https://example.com/img.png",
            )
            assert result.mode == "RGB"


# ===================================================================
# download_image_base64  (async)
# ===================================================================


@pytest.mark.asyncio
class TestDownloadImageBase64:
    """Tests for download_image_base64."""

    async def test_from_base64_default_jpeg(self) -> None:
        """Test default JPEG format."""
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image_base64(b64)
        assert result.startswith("data:image/JPEG;base64,")

    async def test_from_base64_without_header(self) -> None:
        """Test without base64 header."""
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image_base64(
            b64, include_base64_header=False
        )
        assert not result.startswith("data:")

    async def test_from_url(self) -> None:
        """Test download from URL."""
        img = _rgb_image((100, 100))
        img_bytes = _image_bytes(img, "PNG")
        mock_resp = MagicMock(spec=imagetools.httpx.Response)
        mock_resp.content = img_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=imagetools.httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client

        with patch(
            "src.fastapi_mongo_base.utils.imagetools.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await imagetools.download_image_base64(
                "https://example.com/img.png",
                max_width=50,
            )
            assert result.startswith("data:image/JPEG;base64,")

    async def test_format_param_mismatch(self) -> None:
        """
        Known bug: image_format is passed as ``format``.

        This does not match ``image_format`` parameter of image_to_base64,
        so the value is silently ignored and JPEG is always used.
        """
        img = _rgb_image((100, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image_base64(
            b64, image_format="PNG"
        )
        assert result.startswith("data:image/JPEG;base64,"), (
            "format is ignored, always JPEG"
        )

    async def test_with_max_size_and_width(self) -> None:
        """Test with max size and width."""
        img = _rgb_image((200, 100))
        b64 = imagetools.image_to_base64(img, "PNG")
        result = await imagetools.download_image_base64(
            b64, max_width=100, max_size_kb=999_999
        )
        data_part = result.split(",")[1]
        loaded = Image.open(BytesIO(base64.b64decode(data_part)))
        assert loaded.size == (100, 50)
