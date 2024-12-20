from enum import Enum


class Language(str, Enum):
    English = "English"
    Persian = "Persian"

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_

    @property
    def fa(self):
        return {
            Language.English: "انگلیسی",
            Language.Persian: "فارسی",
        }[self]

    @property
    def abbreviation(self):
        return {
            Language.English: "en",
            Language.Persian: "fa",
        }[self]

    def get_dict(self):
        return {
            "en": self.name,
            "fa": self.fa,
            "value": self.value,
            "abbreviation": self.abbreviation,
        }

    @classmethod
    def get_choices(cls):
        return [item.get_dict() for item in cls]
