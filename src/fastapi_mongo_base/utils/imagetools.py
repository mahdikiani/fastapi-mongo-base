import base64
import itertools
from fractions import Fraction
from io import BytesIO
from typing import Literal

import httpx
from PIL import ExifTags, Image, ImageFile


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


def is_aspect_ratio_valid(
    image: Image.Image, *, target_ratio: float = 1, tolerance: float = 0.05
) -> bool:
    width, height = image.size
    aspect_ratio = width / height
    if aspect_ratio > (target_ratio + tolerance) or aspect_ratio < (
        target_ratio - tolerance
    ):
        return False
    return True


def has_white_border(image: Image.Image, *, ratio: float = 0.9) -> bool:
    # check if 90% of pixels of side pixels are white (lighter than 250, 250, 250)
    width, height = image.size

    pixels = []
    for i in range(width):
        pixels.append(image.getpixel((i, 0)))
        pixels.append(image.getpixel((i, height - 1)))
    for j in range(height):
        pixels.append(image.getpixel((0, j)))
        pixels.append(image.getpixel((width - 1, j)))

    white_pixels = [p for p in pixels if all(x > 240 for x in p)]
    if len(white_pixels) / len(pixels) > ratio:
        return True
    return False


def square_pad_white_pixels(image: Image.Image) -> Image.Image:
    width, height = image.size
    max_side = max(width, height)
    pos_x, pos_y = (max_side - width) // 2, (max_side - height) // 2

    new_image = Image.new("RGB", (max_side, max_side), "white")
    new_image.paste(image, (pos_x, pos_y))
    return new_image


def convert_image(
    image: Image.Image,
    format: Literal["JPEG", "PNG", "WEBP", "BMP", "GIF"] = "JPEG",
    *,
    bg_color: tuple[int, int, int] = (255, 255, 255),
    **kwargs,
) -> Image.Image:
    """
    Converts an image to the specified format while handling transparency correctly.

    - If the format supports transparency (PNG, WEBP), it preserves the alpha channel.
    - If the format does NOT support transparency (JPEG, BMP, GIF), it removes transparency
      by compositing the image on a background color.

    Parameters:
    - image: PIL.Image.Image - The input image.
    - format: str - Target format (JPEG, PNG, WEBP, BMP, GIF).
    - bg_color: tuple (R, G, B) - Background color for formats that do not support transparency.

    Returns:
    - Converted Image.Image
    """

    supports_transparency = format in ("PNG", "WEBP")
    has_transparency = image.mode in ("RGBA", "LA")
    if supports_transparency:
        return image.convert("RGBA") if has_transparency else image.convert("RGB")

    if has_transparency:
        background = Image.new("RGB", image.size, bg_color)
        return Image.alpha_composite(background.convert("RGBA"), image).convert("RGB")

    return image.convert("RGB")


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


async def get_image_metadata(
    url: str,
    *,
    use_range: bool = True,
    fallback: bool = True,  # if range request fails, try downloading the full file
    max_bytes: int = 65536,  # how many bytes to try with range request
    with_exif: bool = True,
    **kwargs,
) -> dict:
    """
    Fetches an image URL and returns its metadata.

    Parameters:
        url (str): URL of the image.
        use_range (bool): Whether to try a range request to download only a header part.
        max_bytes (int): Maximum number of bytes to request in a range request.
        fallback (bool): If range request does not provide enough data, download the full file.

    Returns:
        dict: Dictionary with image metadata (e.g., width, height, file_type, and content_type).

    Raises:
        ValueError: If the image metadata could not be determined.
        httpx.HTTPError: If there is an error fetching the image.
    """
    if url.startswith("data:image"):
        image = load_from_base64(url)
        return {
            "width": image.width,
            "height": image.height,
            "file_type": image.format,
            "content_type": url.split(":")[1].split(";")[0],
            "mode": image.mode,
        }

    async with httpx.AsyncClient() as client:
        headers = {}
        if use_range:
            headers["Range"] = f"bytes=0-{max_bytes - 1}"

        try:
            response = await client.get(url, headers=headers, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise

        # Try to parse the partial content using Pillow's incremental parser.
        content = BytesIO(response.content)
        parser = ImageFile.Parser()
        parser.feed(content.getvalue())
        if parser.image:
            image = parser.image
        elif use_range and fallback:
            # If we didn't get enough data from the range request, try a full download.
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            content = BytesIO(response.content)
            parser = ImageFile.Parser()
            parser.feed(content.getvalue())
            if parser.image:
                image = parser.image
            else:
                raise ValueError(
                    "Could not determine image dimensions after full download"
                )
        else:
            raise ValueError(
                "Could not determine image dimensions with range request data"
            )

        width, height = image.size
        file_type = getattr(image, "format", None)
        content_type = response.headers.get("Content-Type")

        metadata = {
            "width": width,
            "height": height,
            "file_type": file_type,
            "content_type": content_type,
        }

        # Optionally add image mode
        metadata["mode"] = image.mode

        # File size from header if available (content-length)
        if "Content-Length" in response.headers:
            metadata["content_length"] = int(response.headers["Content-Length"])

        # Extract EXIF data if available (common in JPEG images)
        if with_exif:
            exif = image._getexif() if hasattr(image, "_getexif") else None
            if exif:
                # Convert EXIF tag IDs to names for readability
                exif_data = {
                    ExifTags.TAGS.get(tag, tag): value for tag, value in exif.items()
                }
                metadata["exif"] = exif_data

        # Optionally include any additional info from Pillow's info dictionary
        if image.info:
            metadata["info"] = image.info

        return metadata


def compress_image(
    image: Image.Image,
    max_size_kb: int,
    *,
    format: Literal["JPEG", "PNG", "WEBP"] = "JPEG",
    quality: int = 90,
    **kwargs,
) -> Image.Image:
    """Compress image to fit within max_size_kb."""
    while True:
        buffered = convert_image_bytes(image, format, quality)
        encoded = base64.b64encode(buffered.getvalue()).decode()
        if len(encoded) <= max_size_kb * 1024:
            break
        new_width = int(image.width * 4 / 5)
        new_height = int(image.height * 4 / 5)
        image = resize_image(image, new_width, new_height)
    return image


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
