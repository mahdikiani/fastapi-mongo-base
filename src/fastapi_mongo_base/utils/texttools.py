"""Text utilities for FastAPI MongoDB base package."""

import re
import secrets
import string
import unicodedata
import uuid
from urllib.parse import urlparse


def json_extractor(text: str) -> dict[str, object]:
    """
    Extract JSON object from text string.

    Args:
        text: Text containing JSON.

    Returns:
        Parsed JSON dictionary.

    """
    import json

    json_string = text[text.find("{") : text.rfind("}") + 1]
    return json.loads(json_string)


def format_string_keys(text: str) -> set[str]:
    """
    Extract format string keys from a format string.

    Args:
        text: Format string (e.g., "Hello {name}!").

    Returns:
        Set of format key names.

    """
    return {t[1] for t in string.Formatter().parse(text) if t[1]}


def format_string_fixer(**kwargs: object) -> list[dict[str, object]]:
    """
    Convert parallel lists into list of dictionaries.

    Args:
        **kwargs: Keyword arguments where values are lists of equal length.

    Returns:
        List of dictionaries, each containing one value from each list.

    """
    list_length = len(next(iter(kwargs.values())))

    # Initialize the target list
    target = []

    # Iterate over each index of the lists
    for i in range(list_length):
        # Create a new dictionary for each index
        entry = {key: kwargs[key][i] for key in kwargs}
        # Append the new dictionary to the target list
        target.append(entry)

    return target


def escape_markdown(text: str) -> str:
    """
    Escape markdown special characters in text.

    Args:
        text: Text to escape.

    Returns:
        Escaped text string.

    """
    replacements = [
        ("_", r"\_"),
        ("*", r"\*"),
        ("[", r"\["),
        ("]", r"\]"),
        ("(", r"\("),
        (")", r"\)"),
        ("~", r"\~"),
        # ("`", r"\`"), # noqa: ERA001
        (">", r"\>"),
        ("#", r"\#"),
        ("+", r"\+"),
        ("-", r"\-"),
        ("=", r"\="),
        ("|", r"\|"),
        ("{", r"\{"),
        ("}", r"\}"),
        (".", r"\."),
        ("!", r"\!"),
        ("=", r"\="),
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text


def _split_sentence(
    sentence: str,
    max_chunk_size: int,
    current_chunk: str,
) -> str:
    """Split a sentence into chunks."""
    if len(sentence) > max_chunk_size:
        # Split sentence into words
        words = sentence.split(" ")
        for word in words:
            if (
                len(current_chunk) + len(word) + 1 > max_chunk_size
                and current_chunk
            ):
                return current_chunk.strip()
            current_chunk += word + " "
    else:
        current_chunk += sentence + " "

    return current_chunk


def _split_paragraph(
    paragraph: str,
    max_chunk_size: int,
    current_chunk: str,
) -> tuple[list[str], str]:
    """Split a paragraph into chunks."""
    chunks = []

    if (
        len(current_chunk) + len(paragraph) + 1 > max_chunk_size
        and current_chunk
    ):
        if current_chunk.count("```") % 2 == 1:
            chunks.append(current_chunk[: current_chunk.rfind("```")].strip())
            current_chunk = current_chunk[current_chunk.rfind("```") :]
            return chunks, current_chunk

        chunks.append(current_chunk.strip())
        current_chunk = ""
        return chunks, current_chunk

    if len(paragraph) > max_chunk_size:
        # Split paragraph into sentences
        sentences = re.split(r"(?<=[.!?]) +", paragraph)
        for sentence in sentences:
            if (
                len(current_chunk) + len(sentence) + 1 > max_chunk_size
                and current_chunk
            ):
                chunks.append(current_chunk.strip())
                current_chunk = ""

            current_chunk = _split_sentence(
                sentence,
                max_chunk_size,
                current_chunk,
            )
    else:
        current_chunk += paragraph + "\n"

    return chunks, current_chunk


def split_text(text: str, max_chunk_size: int = 4096) -> list[str]:
    """Split text into chunks while preserving structure."""
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        new_chunks, current_chunk = _split_paragraph(
            paragraph,
            max_chunk_size,
            current_chunk,
        )
        chunks.extend(new_chunks)

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def replace_unicode_digits(match: re.Match) -> str:
    """
    Replace Unicode digits with English ASCII digits.

    Args:
        match: Match object.

    Returns:
        String with Unicode digits replaced with English ASCII digits.

    """
    char = match.group()
    return str(unicodedata.digit(char))


def convert_to_english_digits(input_str: str) -> str:
    """
    Convert Unicode digits to English ASCII digits.

    Args:
        input_str: String with Unicode digits.

    Returns:
        String with ASCII digits.

    """
    non_ascii_digit_pattern = re.compile(r"\d", re.UNICODE)
    return non_ascii_digit_pattern.sub(replace_unicode_digits, input_str)


regex = re.compile(
    r"^(https?|ftp):\/\/"  # http:// or https:// or ftp://
    r"(?"
    r":(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
    # r"localhost|"  # or localhost...
    # r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"  # or IPv4... # noqa: ERA001
    # r"\[?[A-F0-9]*:[A-F0-9:]+\]?"  # or IPv6...   # noqa: ERA001
    r")"
    r"(?::\d+)?"  # optional port
    r"(?:\/[-A-Z0-9+&@#\/%=~_|$]*)*$",
    re.IGNORECASE,
)
phone_regex = re.compile(
    r"^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$",
)
email_regex = re.compile(r"^[a-zA-Z\._]+@[a-zA-Z0-9\.-_]+\.[a-zA-Z]{2,}$")
username_regex = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{2,16}$")


def is_valid_uuid(val: str) -> bool:
    """
    Check if string is a valid UUID.

    Args:
        val: String to validate.

    Returns:
        True if valid UUID, False otherwise.

    """
    try:
        uuid.UUID(str(val))
    except ValueError:
        return False
    return True


def is_valid_url(url: str) -> bool:
    """
    Check if string is a valid URL.

    Args:
        url: String to validate.

    Returns:
        True if valid URL, False otherwise.

    """
    # Check if the URL matches the regex
    if re.match(regex, url) is None:
        return False

    # Additional check using urllib.parse to ensure proper scheme and netloc
    parsed_url = urlparse(url)
    return all([parsed_url.scheme, parsed_url.netloc])


def is_username(username: str) -> bool:
    """
    Check if string matches username pattern.

    Args:
        username: String to validate.

    Returns:
        True if valid username format, False otherwise.

    """
    return bool(username_regex.search(username))


def is_email(email: str) -> bool:
    """
    Check if string matches email pattern.

    Args:
        email: String to validate.

    Returns:
        True if valid email format, False otherwise.

    """
    return bool(email_regex.search(email))


def is_phone(phone: str) -> bool:
    """
    Check if string matches phone number pattern.

    Args:
        phone: String to validate.

    Returns:
        True if valid phone format, False otherwise.

    """
    return bool(phone_regex.search(phone))


def generate_random_chars(
    length: int = 6,
    characters: str = string.ascii_letters + string.digits,
) -> str:
    """
    Generate random string of specified length.

    Args:
        length: Length of random string (default: 6).
        characters: Character set to use (default: alphanumeric).

    Returns:
        Random string.

    """
    # Generate the random characters
    return "".join(secrets.choice(characters) for _ in range(length))


def whitespace_for_replace(match: re.Match) -> str:
    """
    Replace whitespace with a space.

    Args:
        match: Match object.

    Returns:
        String with whitespace replaced with a space.

    """
    if "\n" in match.group():
        return "\n"
    return " "


def remove_whitespace(text: str) -> str:
    """
    Remove extra whitespace, preserving newlines.

    Args:
        text: Text to process.

    Returns:
        Text with normalized whitespace.

    """
    return re.sub(r"\s+", whitespace_for_replace, text)


def sanitize_filename(
    draft_name: str,
    max_length: int = 0,
    space_remover: bool = True,
) -> str:
    """
    Sanitize filename by removing invalid characters.

    Args:
        draft_name: Original filename or URL.
        max_length: Maximum length (0 for no limit).
        space_remover: Whether to replace spaces with underscores.

    Returns:
        Sanitized filename.

    """
    # get filename from URL
    if draft_name.startswith("http"):
        url_parts = urlparse(draft_name)
        draft_name = url_parts.path

    # Remove path and extension
    draft_name = draft_name.split("/")[-1].strip()
    dotted_name = draft_name.split(".")
    pure_name = ".".join(
        dotted_name[:-1] if len(dotted_name) > 1 else dotted_name,
    )

    # Remove invalid characters and replace spaces with underscores
    # Valid characters: alphanumeric, underscores, and periods and spaces
    sanitized = re.sub(r"[^a-zA-Z0-9_. ]", "", pure_name)

    if max_length > 0:
        position = pure_name.find(" ", max_length * 4 // 5)
        if position > max_length * 6 // 5 or position == -1:
            position = max_length
        sanitized = sanitized[:position]  # Limit to 100 characters

    if space_remover:
        # Replace spaces with underscores
        sanitized = sanitized.replace(" ", "_")

    return sanitized
