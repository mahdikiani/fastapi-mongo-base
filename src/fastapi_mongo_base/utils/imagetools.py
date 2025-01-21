import base64
import itertools
from fractions import Fraction
from io import BytesIO
from typing import Literal

import httpx
from aiocache import cached
from PIL import Image


def rgb_to_hex(rgb):
    """Convert RGB color to HEX."""
    r = min(255, max(0, rgb[0]))
    g = min(255, max(0, rgb[1]))
    b = min(255, max(0, rgb[2]))
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


def rgb_to_xyz(rgb):
    r, g, b = rgb

    # Normalize the RGB values to the range [0, 1]
    r = r / 255.0
    g = g / 255.0
    b = b / 255.0

    # Apply the gamma correction (inverse of sRGB companding)
    if r > 0.04045:
        r = ((r + 0.055) / 1.055) ** 2.4
    else:
        r = r / 12.92

    if g > 0.04045:
        g = ((g + 0.055) / 1.055) ** 2.4
    else:
        g = g / 12.92

    if b > 0.04045:
        b = ((b + 0.055) / 1.055) ** 2.4
    else:
        b = b / 12.92

    # Convert to XYZ using the RGB to XYZ matrix transformation
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    return (x, y, z)


def xyz_to_lab(xyz):
    x, y, z = xyz

    # Define the reference white point
    x_ref = 0.95047
    y_ref = 1.00000
    z_ref = 1.08883

    # Normalize the XYZ values by the reference white point
    x = x / x_ref
    y = y / y_ref
    z = z / z_ref

    # Apply the LAB transformation
    def f(t):
        if t > 0.008856:
            return t ** (1 / 3)
        else:
            return (7.787 * t) + (16 / 116)

    l = 116 * f(y) - 16
    a = 500 * (f(x) - f(y))
    b = 200 * (f(y) - f(z))

    return (l, a, b)


def rgb_to_lab(rgb):
    xyz = rgb_to_xyz(rgb)
    lab = xyz_to_lab(xyz)
    return lab


def add_watermark_to_image(
    background_image_path: str | bytes | Image.Image,
    watermark_image_path: str,
    position: tuple[int, int] = (0, 0),
    resize: tuple[int, int] = None,
) -> Image:
    """
    Add an watermark image to a background image at a specified position using PIL.

    :param background_image_path: Path to the background image.
    :param watermark_image_path: Path to the watermark image.
    :param position: A tuple (x, y) representing the position to place the watermark.
    :param resize: A tuple (w, h) representing the target size of placed watermark.
    :return: An Image object with the watermark added.
    """

    background = Image.open(background_image_path)
    w, h = background.size
    watermark = Image.open(watermark_image_path)

    position = (w + position[0]) % w, (h + position[1]) % h

    if resize:
        watermark = watermark.resize((50, 50))

    background.paste(watermark, position[0], position[1], watermark)

    return background


def get_aspect_ratio_str(width: int, height: int) -> str:
    fr = Fraction(height, width)
    return f"{fr.denominator}:{fr.numerator}"


def resize_image(
    image: Image.Image | BytesIO, new_width=384, new_height=None
) -> Image.Image:
    if isinstance(image, BytesIO):
        image = Image.open(image)

    if new_width is None and new_height is None:
        return image

    original_width, original_height = image.size
    aspect_ratio = original_height / original_width

    if new_height is None:
        new_height = int(aspect_ratio * new_width)
    elif new_width is None:
        new_width = int(new_height / aspect_ratio)

    resized_image = image.resize((new_width, new_height))
    return resized_image


def split_image(image: Image.Image, sections=(2, 2), **kwargs) -> list[Image.Image]:
    parts = []
    for i, j in itertools.product(range(sections[0]), range(sections[1])):
        x = j * image.width // sections[0]
        y = i * image.height // sections[1]
        region = image.crop(
            (x, y, x + image.width // sections[0], y + image.height // sections[1])
        )
        parts.append(region)
    return parts


def convert_image(
    image: Image.Image, format: Literal["JPEG", "PNG", "WEBP", "BMP", "GIF"] = "JPEG"
) -> Image.Image:
    color_mode = "RGB" if format not in ("PNG", "WEBP") else "RGBA"
    return image.convert(color_mode)


def convert_image_bytes(
    image: Image.Image,
    format: Literal["JPEG", "PNG", "WEBP", "BMP", "GIF"] = "JPEG",
    quality=None,
) -> BytesIO:
    image_bytes = BytesIO()
    convert_image(image, format).save(
        image_bytes,
        format=format,
        **{"quality": quality} if quality else {},
    )
    image_bytes.seek(0)
    return image_bytes


def strip_metadata(
    image: Image.Image,
    format: Literal["JPEG", "PNG", "WEBP", "BMP", "GIF"] = "JPEG",
) -> Image.Image:
    """Strip metadata from the image by re-creating it in memory."""
    return convert_image(image, format)


def image_to_base64(
    image: Image.Image,
    format: Literal["JPEG", "PNG", "WEBP", "BMP", "GIF"] = "JPEG",
    quality: int = 90,
    *,
    include_base64_header: bool = True,
    **kwargs,
) -> str:
    buffered = convert_image_bytes(image, format, quality)
    base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    if include_base64_header:
        return f"data:image/{format};base64,{base64_str}"
    return base64_str


def load_from_base64(encoded: str) -> Image.Image:
    """Load an image from a base64 encoded string."""
    encoded = encoded.split(",")[1]
    encoded += "=" * (4 - len(encoded) % 4)
    buffered = BytesIO(base64.b64decode(encoded))
    return Image.open(buffered)


async def load_from_url(url: str, **kwargs) -> Image.Image:
    follow_redirects = kwargs.pop("follow_redirects", True)
    """Load an image from a URL."""
    async with httpx.AsyncClient() as client:
        r = await client.get(url, follow_redirects=follow_redirects, **kwargs)
        r.raise_for_status()
    buffered = BytesIO(r.content)
    return Image.open(buffered)


def compress_image(image: Image.Image, max_size_kb: int) -> Image.Image:
    """Compress image to fit within max_size_kb."""
    while True:
        buffered = BytesIO()
        image.save(buffered, format="JPEG", optimize=True, quality=85)
        encoded = base64.b64encode(buffered.getvalue()).decode()
        if len(encoded) <= max_size_kb * 1024:
            break
        new_width = int(image.width * 4 / 5)
        new_height = int(image.height * 4 / 5)
        image = resize_image(image, new_width, new_height)
    return image


@cached(ttl=60 * 60 * 24)
async def download_image(
    url: str, max_width: int | None = None, max_size_kb: int | None = None, **kwargs
) -> Image.Image:
    """Fetch, resize, remove metadata, and compress an image to fit the specified constraints."""
    # Load image from either base64 or URL
    image = (
        load_from_base64(url)
        if url.startswith("data:image")
        else await load_from_url(url, **kwargs)
    )

    # Prepare image (convert to RGB and strip metadata)
    image = strip_metadata(image)

    if max_size_kb is None and max_width is None:
        return image

    # Resize if needed
    if max_width is not None:
        image = resize_image(image, max_width)

    # Compress if needed
    if max_size_kb is not None:
        image = compress_image(image, max_size_kb)

    return image


@cached(ttl=60 * 60 * 24)
async def download_image_base64(
    url: str,
    max_width: int | None = None,
    max_size_kb: int | None = None,
    *,
    format: Literal["JPEG", "PNG", "WEBP", "BMP", "GIF"] = "JPEG",
    quality: int = None,
    include_base64_header: bool = True,
    **kwargs,
) -> str:
    image = await download_image(url, max_width, max_size_kb, **kwargs)
    return image_to_base64(
        image,
        format=format,
        quality=quality,
        include_base64_header=include_base64_header,
        **kwargs,
    )
