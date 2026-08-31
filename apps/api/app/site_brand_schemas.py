import re
import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
LOCALE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
ISO_COUNTRY_CODES = frozenset(
    """AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL
    BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW
    CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF
    GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ
    IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU
    LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC
    NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE
    RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD
    TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU
    WF WS YE YT ZA ZM ZW""".split()
)
ISO_CURRENCY_CODES = frozenset(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB
    BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC CUP
    CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW
    KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR
    MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG
    QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL
    THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES
    VND VUV WST XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA
    XXX YER ZAR ZMW ZWG""".split()
)


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    brighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (brighter + 0.05) / (darker + 0.05)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteBrandPalette(StrictModel):
    accent: str = "#ff5c35"
    accent_hover: str = "#ff7657"
    on_accent: Literal["#000000", "#ffffff"] = "#000000"
    surface: str = "#090909"
    surface_elevated: str = "#171310"
    text: str = "#f7f2ea"
    text_muted: str = "#b8afa6"

    @field_validator("accent", "accent_hover", "surface", "surface_elevated", "text", "text_muted")
    @classmethod
    def valid_hex_color(cls, value: str) -> str:
        if not HEX_COLOR.fullmatch(value):
            raise ValueError("Colors must use the #RRGGBB format")
        return value.lower()

    @model_validator(mode="after")
    def accessible_contrast(self):
        surfaces = (
            ("surface", self.surface),
            ("elevated surface", self.surface_elevated),
        )
        for label, background in surfaces:
            if _contrast(self.text, background) < 4.5:
                raise ValueError(
                    f"Primary text must have at least 4.5:1 contrast against the {label}"
                )
            if _contrast(self.text_muted, background) < 4.5:
                raise ValueError(
                    f"Muted text must have at least 4.5:1 contrast against the {label}"
                )
            if _contrast(self.accent, background) < 4.5:
                raise ValueError(f"Accent must have at least 4.5:1 contrast against the {label}")
            if _contrast(self.accent_hover, background) < 4.5:
                raise ValueError(
                    f"Hover accent must have at least 4.5:1 contrast against the {label}"
                )
        button_text_candidates = ("#000000", "#ffffff")
        usable_button_text = [
            candidate
            for candidate in button_text_candidates
            if _contrast(candidate, self.accent) >= 4.5
            and _contrast(candidate, self.accent_hover) >= 4.5
        ]
        if not usable_button_text:
            raise ValueError(
                "Accent and hover accent must share readable black or white button text"
            )
        self.on_accent = max(
            usable_button_text,
            key=lambda candidate: min(
                _contrast(candidate, self.accent),
                _contrast(candidate, self.accent_hover),
            ),
        )
        return self


class SiteBrandPalettePatch(StrictModel):
    accent: str | None = None
    accent_hover: str | None = None
    surface: str | None = None
    surface_elevated: str | None = None
    text: str | None = None
    text_muted: str | None = None

    @field_validator("accent", "accent_hover", "surface", "surface_elevated", "text", "text_muted")
    @classmethod
    def valid_hex_color(cls, value: str | None) -> str | None:
        if value is not None and not HEX_COLOR.fullmatch(value):
            raise ValueError("Colors must use the #RRGGBB format")
        return value.lower() if value else value


class SiteBrandLocale(StrictModel):
    default_locale: str = "en-US"
    home_market: str = "US"
    currency: str = "USD"

    @field_validator("default_locale")
    @classmethod
    def valid_locale(cls, value: str) -> str:
        value = value.strip()
        if not LOCALE.fullmatch(value):
            raise ValueError("Default locale must be a valid BCP 47 language tag")
        parts = value.split("-")
        return "-".join(
            part.lower() if index == 0 else part.upper() if len(part) == 2 else part
            for index, part in enumerate(parts)
        )

    @field_validator("home_market")
    @classmethod
    def valid_market(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in ISO_COUNTRY_CODES:
            raise ValueError("Home market must be an ISO 3166-1 alpha-2 code")
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in ISO_CURRENCY_CODES:
            raise ValueError("Currency must be an ISO 4217 alpha-3 code")
        return value


class SiteBrandLocalePatch(StrictModel):
    default_locale: str | None = None
    home_market: str | None = None
    currency: str | None = None

    @field_validator("default_locale")
    @classmethod
    def valid_locale(cls, value: str | None) -> str | None:
        return SiteBrandLocale.valid_locale(value) if value is not None else None

    @field_validator("home_market")
    @classmethod
    def valid_market(cls, value: str | None) -> str | None:
        return SiteBrandLocale.valid_market(value) if value is not None else None

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        return SiteBrandLocale.valid_currency(value) if value is not None else None


SiteBrandLogoVariant = Literal[
    "iris",
    "marquee",
    "prism",
    "orbit",
    "film-frame",
    "eclipse",
    "stencil",
    "signal",
    "portal",
    "monolith",
    "ribbon",
    "beam",
]


class SiteBrandLogoMark(StrictModel):
    """A versioned, data-only recipe rendered by trusted first-party UI code."""

    renderer_version: Literal[1] = 1
    glyph: str = Field(min_length=1, max_length=1, pattern=r"^[A-Za-z]$")
    variant: SiteBrandLogoVariant

    @field_validator("renderer_version", mode="before")
    @classmethod
    def exact_renderer_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("Logo mark renderer version must be the integer 1")
        return value


class SiteBrandEditableConfig(StrictModel):
    business_name: str = Field(default="Aperture", min_length=2, max_length=60)
    short_name: str = Field(default="Aperture", min_length=2, max_length=24)
    tagline: str | None = Field(default="Stories worth staying for.", max_length=120)
    description: str | None = Field(
        default="A cinematic home for films and series.", max_length=280
    )
    palette: SiteBrandPalette = Field(default_factory=SiteBrandPalette)
    locale: SiteBrandLocale = Field(default_factory=SiteBrandLocale)
    logo_mark: SiteBrandLogoMark | None = None

    @field_validator("business_name", "short_name", "tagline", "description")
    @classmethod
    def clean_copy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            return None
        if any(ord(character) < 32 for character in cleaned):
            raise ValueError("Brand copy cannot contain control characters")
        return cleaned

    @model_validator(mode="after")
    def required_names(self):
        if self.business_name is None or self.short_name is None:
            raise ValueError("Business name and short name are required")
        return self


class SiteBrandConfigPatch(StrictModel):
    business_name: str | None = Field(default=None, min_length=2, max_length=60)
    short_name: str | None = Field(default=None, min_length=2, max_length=24)
    tagline: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=280)
    palette: SiteBrandPalettePatch | None = None
    locale: SiteBrandLocalePatch | None = None
    logo_mark: SiteBrandLogoMark | None = None

    @field_validator("business_name", "short_name", "tagline", "description")
    @classmethod
    def clean_copy(cls, value: str | None) -> str | None:
        return SiteBrandEditableConfig.clean_copy(value)


class SiteBrandAdminConfig(SiteBrandEditableConfig):
    logo_url: str | None = None
    logo_revision: int = 0


class SiteBrandPatchRequest(StrictModel):
    revision: int = Field(ge=0)
    current_step: int | None = Field(default=None, ge=1, le=5)
    completed_steps: list[int] | None = Field(default=None, max_length=5)
    config: SiteBrandConfigPatch | None = None

    @field_validator("completed_steps")
    @classmethod
    def valid_completed_steps(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        normalized = sorted(set(value))
        if normalized != value or any(step < 1 or step > 5 for step in normalized):
            raise ValueError("Completed steps must be unique, ordered stage numbers from 1 to 5")
        if normalized and normalized != list(range(1, normalized[-1] + 1)):
            raise ValueError("Completed steps must form a continuous sequence beginning with 1")
        return normalized

    @model_validator(mode="after")
    def includes_change(self):
        if self.current_step is None and self.completed_steps is None and self.config is None:
            raise ValueError("At least one setup value must be supplied")
        return self


class SiteBrandPublishRequest(StrictModel):
    revision: int = Field(ge=0)


class SiteBrandAdminResponse(StrictModel):
    schema_version: Literal[1] = 1
    revision: int
    status: Literal["draft", "published"]
    current_step: int
    completed_steps: list[int]
    config: SiteBrandAdminConfig
    updated_at: datetime
    published_at: datetime | None


class SiteBrandPublicResponse(StrictModel):
    schema_version: Literal[1] = 1
    revision: int
    business_name: str
    short_name: str
    tagline: str | None
    description: str | None
    logo_url: str | None
    logo_revision: int
    logo_mark: SiteBrandLogoMark | None = None
    palette: SiteBrandPalette
    locale: SiteBrandLocale
    published_at: datetime | None


BrandCopyTone = Literal["cinematic", "warm", "bold", "refined", "playful", "mysterious"]


def _clean_assistant_copy(value: object) -> object:
    if value is None or not isinstance(value, str):
        return value
    normalized = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in normalized):
        raise ValueError("Copy guidance cannot contain control or invisible format characters")
    cleaned = " ".join(normalized.split())
    return cleaned or None


class BrandCopyAssistRequest(StrictModel):
    business_name: str = Field(min_length=2, max_length=60)
    short_name: str | None = Field(default=None, min_length=2, max_length=24)
    existing_tagline: str | None = Field(default=None, max_length=120)
    existing_description: str | None = Field(default=None, max_length=280)
    audience: str | None = Field(default=None, max_length=160)
    themes: list[str] = Field(default_factory=list, max_length=6)
    tone: BrandCopyTone = "cinematic"
    additional_direction: str | None = Field(default=None, max_length=240)

    @field_validator(
        "business_name",
        "short_name",
        "existing_tagline",
        "existing_description",
        "audience",
        "additional_direction",
        mode="before",
    )
    @classmethod
    def clean_guidance(cls, value: object) -> object:
        return _clean_assistant_copy(value)

    @field_validator("themes", mode="before")
    @classmethod
    def clean_themes(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        cleaned: list[object] = []
        for theme in value:
            cleaned.append(_clean_assistant_copy(theme) if isinstance(theme, str) else theme)
        return cleaned

    @field_validator("themes")
    @classmethod
    def valid_themes(cls, value: list[str]) -> list[str]:
        if any(not theme or len(theme) > 40 for theme in value):
            raise ValueError("Each theme must contain between 1 and 40 characters")
        if len({theme.casefold() for theme in value}) != len(value):
            raise ValueError("Themes must be unique")
        return value


class BrandCopySuggestion(StrictModel):
    tagline: str = Field(min_length=4, max_length=120)
    description: str = Field(min_length=20, max_length=280)
    short_name: str = Field(min_length=2, max_length=24)
    tone_direction: str = Field(min_length=4, max_length=120)

    @field_validator("tagline", "description", "short_name", "tone_direction", mode="before")
    @classmethod
    def clean_generated_copy(cls, value: object) -> object:
        cleaned = _clean_assistant_copy(value)
        if not isinstance(cleaned, str):
            return cleaned
        if "<" in cleaned or ">" in cleaned:
            raise ValueError("Generated brand copy must be plain text")
        return cleaned


class BrandCopySuggestionSet(StrictModel):
    suggestions: list[BrandCopySuggestion] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def distinct_suggestions(self):
        taglines = {suggestion.tagline.casefold() for suggestion in self.suggestions}
        if len(taglines) != len(self.suggestions):
            raise ValueError("Generated taglines must be distinct")
        return self


class BrandCopyAssistResponse(BrandCopySuggestionSet):
    generated_by: Literal["ai"] = "ai"
