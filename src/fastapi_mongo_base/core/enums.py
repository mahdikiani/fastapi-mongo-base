from enum import StrEnum


class Language(StrEnum):
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
    # Chinese = "Chinese"
    Vietnamese = "Vietnamese"
    Indonesian = "Indonesian"

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_

    @property
    def _info(self):
        return {
            Language.English: {
                "fa": "انگلیسی",
                "en": "English",
                "abbreviation": "en",
            },
            Language.Persian: {
                "fa": "فارسی",
                "en": "Persian",
                "abbreviation": "fa",
            },
            Language.Arabic: {
                "fa": "عربی",
                "en": "Arabic",
                "abbreviation": "ar",
            },
            Language.Turkish: {
                "fa": "ترکی",
                "en": "Turkish",
                "abbreviation": "tr",
            },
            Language.French: {
                "fa": "فرانسه",
                "en": "French",
                "abbreviation": "fr",
            },
            Language.Spanish: {
                "fa": "اسپانیایی",
                "en": "Spanish",
                "abbreviation": "es",
            },
            Language.German: {
                "fa": "آلمانی",
                "en": "German",
                "abbreviation": "de",
            },
            Language.Italian: {
                "fa": "ایتالیایی",
                "en": "Italian",
                "abbreviation": "it",
            },
            Language.Portuguese: {
                "fa": "پرتغالی",
                "en": "Portuguese",
                "abbreviation": "pt",
            },
            Language.Dutch: {
                "fa": "هالندی",
                "en": "Dutch",
                "abbreviation": "nl",
            },
            Language.Russian: {
                "fa": "روسی",
                "en": "Russian",
                "abbreviation": "ru",
            },
            Language.Polish: {
                "fa": "لهستانی",
                "en": "Polish",
                "abbreviation": "pl",
            },
            Language.Romanian: {
                "fa": "رومانیایی",
                "en": "Romanian",
                "abbreviation": "ro",
            },
            Language.Bulgarian: {
                "fa": "بلغاری",
                "en": "Bulgarian",
                "abbreviation": "bg",
            },
            Language.Hungarian: {
                "fa": "مجارستانی",
                "en": "Hungarian",
                "abbreviation": "hu",
            },
            Language.Czech: {
                "fa": "چک",
                "en": "Czech",
                "abbreviation": "cs",
            },
            Language.Greek: {
                "fa": "یونانی",
                "en": "Greek",
                "abbreviation": "el",
            },
            Language.Hebrew: {
                "fa": "عبری",
                "en": "Hebrew",
                "abbreviation": "he",
            },
            Language.Japanese: {
                "fa": "ژاپنی",
                "en": "Japanese",
                "abbreviation": "ja",
            },
            Language.Korean: {
                "fa": "کره ای",
                "en": "Korean",
                "abbreviation": "ko",
            },
            # Language.Chinese: {
            #     "fa": "چینی",
            #     "en": "Chinese",
            #     "abbreviation": "zh",
            # },
            Language.Vietnamese: {
                "fa": "ویتنامی",
                "en": "Vietnamese",
                "abbreviation": "vi",
            },
            Language.Indonesian: {
                "fa": "اندونزیایی",
                "en": "Indonesian",
                "abbreviation": "id",
            },
        }[self]

    @property
    def fa(self):
        return self._info["fa"]

    @property
    def en(self):
        return self._info["en"]

    @property
    def abbreviation(self):
        return self._info["abbreviation"]

    def get_dict(self):
        return self._info | {"value": self.value}

    @classmethod
    def get_choices(cls):
        return [item.get_dict() for item in cls]
