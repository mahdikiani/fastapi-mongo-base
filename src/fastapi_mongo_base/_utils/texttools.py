import random
import re
import string
import unicodedata
import uuid
from urllib.parse import urlparse


def backtick_formatter(text: str):
    text = text.strip().strip("```json").strip("```").strip()
    return text


def format_string_keys(text: str) -> set[str]:
    return {t[1] for t in string.Formatter().parse(text) if t[1]}


def format_string_fixer(**kwargs):
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


def escape_markdown(text: str):
    replacements = [
        ("_", r"\_"),
        ("*", r"\*"),
        ("[", r"\["),
        ("]", r"\]"),
        ("(", r"\("),
        (")", r"\)"),
        ("~", r"\~"),
        # ("`", r"\`"),
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


def split_text(text: str, max_chunk_size=4096):
    # Split text into paragraphs
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 1 > max_chunk_size:
            if current_chunk:
                if current_chunk.count("```") % 2 == 1:
                    chunks.append(current_chunk[: current_chunk.rfind("```")].strip())
                    current_chunk = current_chunk[current_chunk.rfind("```") :]
                    continue

                chunks.append(current_chunk.strip())
                current_chunk = ""
                continue

        if len(paragraph) > max_chunk_size:
            # Split paragraph into sentences
            sentences = re.split(r"(?<=[.!?]) +", paragraph)
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 > max_chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
                if len(sentence) > max_chunk_size:
                    # Split sentence into words
                    words = sentence.split(" ")
                    for word in words:
                        if len(current_chunk) + len(word) + 1 > max_chunk_size:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = ""
                        current_chunk += word + " "
                else:
                    current_chunk += sentence + " "
        else:
            current_chunk += paragraph + "\n"
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def replace_unicode_digits(match: re.Match) -> str:
    char = match.group()
    return unicodedata.digit(char)


def convert_to_english_digits(input_str: str):
    non_ascii_digit_pattern = re.compile(r"\d", re.UNICODE)
    return non_ascii_digit_pattern.sub(replace_unicode_digits, input_str)


regex = re.compile(
    r"^(https?|ftp):\/\/"  # http:// or https:// or ftp://
    r"(?"
    r":(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
    # r"localhost|"  # or localhost...
    # r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"  # or IPv4...
    # r"\[?[A-F0-9]*:[A-F0-9:]+\]?"  # or IPv6...
    r")"
    r"(?::\d+)?"  # optional port
    r"(?:\/[-A-Z0-9+&@#\/%=~_|$]*)*$",
    re.IGNORECASE,
)
phone_regex = re.compile(r"^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$")
email_regex = re.compile(r"^[a-zA-Z\._]+@[a-zA-Z0-9\.-_]+\.[a-zA-Z]{2,}$")
username_regex = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{2,16}$")


def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


def is_valid_url(url):
    # Check if the URL matches the regex
    if re.match(regex, url) is None:
        return False

    # Additional check using urllib.parse to ensure proper scheme and netloc
    parsed_url = urlparse(url)
    return all([parsed_url.scheme, parsed_url.netloc])


def is_username(username):
    return username_regex.search(username)


def is_email(email):
    return email_regex.search(email)


def is_phone(phone):
    return phone_regex.search(phone)


def generate_random_chars(length=6, characters=string.ascii_letters + string.digits):
    # Generate the random characters
    return "".join(random.choices(characters, k=length))


def replace_whitespace(match: re.Match) -> str:
    if "\n" in match.group():
        return "\n"
    else:
        return " "


def remove_whitespace(text: str) -> str:
    return re.sub(r"\s+", replace_whitespace, text)
