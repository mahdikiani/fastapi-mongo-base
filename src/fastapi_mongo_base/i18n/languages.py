"""Supported content languages with display metadata."""

from enum import StrEnum

LANGUAGE_INFO: dict[str, dict[str, str]] = {
    "English": {"fa": "انگلیسی", "en": "English", "abbreviation": "en"},
    "Persian": {"fa": "فارسی", "en": "Persian", "abbreviation": "fa"},
    "Arabic": {"fa": "عربی", "en": "Arabic", "abbreviation": "ar"},
    "Turkish": {"fa": "ترکی", "en": "Turkish", "abbreviation": "tr"},
    "French": {"fa": "فرانسه", "en": "French", "abbreviation": "fr"},
    "Spanish": {"fa": "اسپانیایی", "en": "Spanish", "abbreviation": "es"},
    "German": {"fa": "آلمانی", "en": "German", "abbreviation": "de"},
    "Italian": {"fa": "ایتالیایی", "en": "Italian", "abbreviation": "it"},
    "Portuguese": {"fa": "پرتغالی", "en": "Portuguese", "abbreviation": "pt"},
    "Dutch": {"fa": "هالندی", "en": "Dutch", "abbreviation": "nl"},
    "Russian": {"fa": "روسی", "en": "Russian", "abbreviation": "ru"},
    "Polish": {"fa": "لهستانی", "en": "Polish", "abbreviation": "pl"},
    "Romanian": {"fa": "رومانیایی", "en": "Romanian", "abbreviation": "ro"},
    "Bulgarian": {"fa": "بلغاری", "en": "Bulgarian", "abbreviation": "bg"},
    "Hungarian": {"fa": "مجارستانی", "en": "Hungarian", "abbreviation": "hu"},
    "Czech": {"fa": "چک", "en": "Czech", "abbreviation": "cs"},
    "Greek": {"fa": "یونانی", "en": "Greek", "abbreviation": "el"},
    "Hebrew": {"fa": "عبری", "en": "Hebrew", "abbreviation": "he"},
    "Japanese": {"fa": "ژاپنی", "en": "Japanese", "abbreviation": "ja"},
    "Korean": {"fa": "کره ای", "en": "Korean", "abbreviation": "ko"},
    "Vietnamese": {"fa": "ویتنامی", "en": "Vietnamese", "abbreviation": "vi"},
    "Indonesian": {
        "fa": "اندونزیایی",
        "en": "Indonesian",
        "abbreviation": "id",
    },
}

_LANGUAGE_BY_CODE: dict[str, "Language"] = {}


class Language(StrEnum):
    """Catalog of supported content languages."""

    English = "English"
    Persian = "Persian"
    Arabic = "Arabic"
    Turkish = "Turkish"
    French = "French"
    Spanish = "Spanish"
    German = "German"
    Italian = "Italian"
    Portuguese = "Portuguese"
    Dutch = "Dutch"
    Russian = "Russian"
    Polish = "Polish"
    Romanian = "Romanian"
    Bulgarian = "Bulgarian"
    Hungarian = "Hungarian"
    Czech = "Czech"
    Greek = "Greek"
    Hebrew = "Hebrew"
    Japanese = "Japanese"
    Korean = "Korean"
    Vietnamese = "Vietnamese"
    Indonesian = "Indonesian"

    @classmethod
    def _ensure_code_index(cls) -> dict[str, "Language"]:
        if not _LANGUAGE_BY_CODE:
            _LANGUAGE_BY_CODE.update({item.code: item for item in cls})
        return _LANGUAGE_BY_CODE

    @classmethod
    def has_value(cls, value: str) -> bool:
        """Return True when ``value`` matches a language display name."""
        return value in cls._value2member_map_

    @classmethod
    def has_code(cls, code: str) -> bool:
        """Return True when ``code`` matches a language locale code."""
        return cls.from_code(code) is not None

    @classmethod
    def from_code(cls, code: str) -> "Language | None":
        """Resolve a language from a locale code like ``fa`` or ``fa-IR``."""
        normalized = code.strip().split("-", maxsplit=1)[0].lower()
        return cls._ensure_code_index().get(normalized)

    @classmethod
    def codes(cls) -> tuple[str, ...]:
        """Return all supported locale codes in enum definition order."""
        return tuple(item.code for item in cls)

    @property
    def info(self) -> dict[str, str]:
        """Display metadata for this language."""
        return LANGUAGE_INFO[self.value]

    @property
    def fa(self) -> str:
        """Persian display name."""
        return self.info["fa"]

    @property
    def en(self) -> str:
        """English display name."""
        return self.info["en"]

    @property
    def abbreviation(self) -> str:
        """Locale code for this language (for example ``en``, ``fa``)."""
        return self.info["abbreviation"]

    @property
    def code(self) -> str:
        """Alias for :attr:`abbreviation`."""
        return self.abbreviation

    def get_dict(self) -> dict[str, str]:
        """Return metadata plus the enum display value."""
        return self.info | {"value": self.value}

    @classmethod
    def get_choices(cls) -> list[dict[str, str]]:
        """Return all languages as API-friendly dictionaries."""
        return [item.get_dict() for item in cls]
