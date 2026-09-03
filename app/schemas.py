import datetime as dt
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator


def _check_password_byte_length(value: str) -> str:
    # bcrypt's actual limit is 72 *bytes*, not characters - a password
    # using accented letters, emoji, or non-Latin scripts can hit that
    # well under the 200-character limit below. Enforcing it here, with
    # a clear message, beats letting the hashing call fail on its own:
    # older bcrypt silently truncated instead of erroring, so this also
    # closes a real (if minor) gap where a too-long password used to
    # hash to something other than what the user actually typed.
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password can't be longer than 72 bytes - about 72 plain characters, fewer if it includes accents, emoji, or non-Latin scripts.")
    return value


PasswordStr = Annotated[str, Field(min_length=8, max_length=200), AfterValidator(_check_password_byte_length)]


# ---------- Auth ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr
    password: PasswordStr


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: PasswordStr


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: PasswordStr


class AuthConfigOut(BaseModel):
    password_auth_enabled: bool
    oidc_enabled: bool
    oidc_button_label: str
    registration_enabled: bool
    smtp_enabled: bool


# ---------- Brewery / Beer ----------

class BreweryOut(BaseModel):
    id: int
    name: str
    website: Optional[str] = None

    class Config:
        from_attributes = True


class BreweryIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: Optional[str] = None


class AdminBreweryOut(BaseModel):
    id: int
    name: str
    website: Optional[str] = None
    beer_count: int


class AdminBreweryPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    website: Optional[str] = None


class AdminBreweryImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


class BeerIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brewery_id: Optional[int] = None
    new_brewery_name: Optional[str] = None
    style: Optional[str] = Field(default=None, max_length=120)
    abv: Optional[float] = Field(default=None, ge=0, le=100)
    description: Optional[str] = Field(default=None, max_length=4000)
    reference_url: Optional[str] = None

    @field_validator("new_brewery_name")
    @classmethod
    def strip_blank(cls, v):
        if v is not None and not v.strip():
            return None
        return v


class BeerOut(BaseModel):
    id: int
    name: str
    style: Optional[str] = None
    abv: Optional[float] = None
    description: Optional[str] = None
    reference_url: Optional[str] = None
    brewery: BreweryOut

    class Config:
        from_attributes = True


class AdminBeerOut(BaseModel):
    id: int
    name: str
    style: Optional[str] = None
    abv: Optional[float] = None
    reference_url: Optional[str] = None
    brewery: BreweryOut
    usage_count: int


class AdminBeerIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brewery_id: int
    style: Optional[str] = Field(default=None, max_length=120)
    abv: Optional[float] = Field(default=None, ge=0, le=100)
    reference_url: Optional[str] = None


class AdminBeerPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    brewery_id: Optional[int] = None
    style: Optional[str] = Field(default=None, max_length=120)
    abv: Optional[float] = Field(default=None, ge=0, le=100)
    reference_url: Optional[str] = None


class AdminBeerStyleOut(BaseModel):
    id: int
    name: str


class AdminBeerStyleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AdminBeerStylePatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)


# ---------- Cellar entries ----------

class CellarEntryIn(BaseModel):
    beer_id: Optional[int] = None
    beer: Optional[BeerIn] = None  # allow creating the beer inline
    location: str = Field(default="cellar", pattern="^(cellar|fridge)$")
    custom_location: Optional[str] = Field(default=None, max_length=120)
    quantity: int = Field(default=1, ge=0)
    size_oz: Optional[float] = Field(default=None, ge=0)
    bottle_date: Optional[dt.date] = None
    best_before: Optional[dt.date] = None
    batch_notes: Optional[str] = Field(default=None, max_length=4000)
    trade_status: str = Field(default="none", pattern="^(none|ft|iso)$")


class CellarEntryPatch(BaseModel):
    location: Optional[str] = Field(default=None, pattern="^(cellar|fridge)$")
    custom_location: Optional[str] = Field(default=None, max_length=120)
    quantity: Optional[int] = Field(default=None, ge=0)
    size_oz: Optional[float] = Field(default=None, ge=0)
    bottle_date: Optional[dt.date] = None
    best_before: Optional[dt.date] = None
    batch_notes: Optional[str] = Field(default=None, max_length=4000)
    trade_status: Optional[str] = Field(default=None, pattern="^(none|ft|iso)$")


class CellarEntryOut(BaseModel):
    id: int
    location: str
    custom_location: Optional[str] = None
    quantity: int
    size_oz: Optional[float] = None
    bottle_date: Optional[dt.date] = None
    best_before: Optional[dt.date] = None
    batch_notes: Optional[str] = None
    trade_status: str
    beer: BeerOut
    updated_at: dt.datetime

    class Config:
        from_attributes = True


class DrinkIn(BaseModel):
    quantity: int = Field(default=1, ge=1)
    note: Optional[str] = Field(default=None, max_length=4000)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    consumed_on: Optional[dt.date] = None
    delete_if_empty: bool = False


class MoveIn(BaseModel):
    location: str = Field(pattern="^(cellar|fridge)$")


# ---------- Consumption log ----------

class ConsumptionLogOut(BaseModel):
    id: int
    quantity: int
    consumed_on: dt.date
    note: Optional[str] = None
    rating: Optional[float] = None
    beer: BeerOut

    class Config:
        from_attributes = True


class ConsumptionLogIn(BaseModel):
    beer_id: int
    quantity: int = Field(default=1, ge=1)
    consumed_on: Optional[dt.date] = None
    note: Optional[str] = Field(default=None, max_length=4000)
    rating: Optional[float] = Field(default=None, ge=0, le=5)


class ConsumptionLogPatch(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=1)
    consumed_on: Optional[dt.date] = None
    note: Optional[str] = Field(default=None, max_length=4000)
    rating: Optional[float] = Field(default=None, ge=0, le=5)


# ---------- Wanted (not owned) ----------

class WantedEntryOut(BaseModel):
    id: int
    notes: Optional[str] = None
    created_at: dt.datetime
    beer: BeerOut

    class Config:
        from_attributes = True


class WantedEntryIn(BaseModel):
    beer_id: Optional[int] = None
    beer: Optional[BeerIn] = None  # allow creating the beer inline, same as CellarEntryIn
    notes: Optional[str] = Field(default=None, max_length=4000)


# ---------- Account ----------

class AccountOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email: EmailStr
    is_admin: bool
    default_sort: str
    unit_system: str
    show_fridge_column: bool
    show_location_column: bool
    trading_enabled: bool
    messaging_enabled: bool
    cellar_public: bool
    notes_public: bool
    drinkby_public: bool

    class Config:
        from_attributes = True


class AccountPatch(BaseModel):
    default_sort: Optional[str] = Field(default=None, pattern="^(beer|brewery|drinkby)$")
    unit_system: Optional[str] = Field(default=None, pattern="^(imperial|metric)$")
    show_fridge_column: Optional[bool] = None
    show_location_column: Optional[bool] = None
    trading_enabled: Optional[bool] = None
    messaging_enabled: Optional[bool] = None
    cellar_public: Optional[bool] = None
    notes_public: Optional[bool] = None
    drinkby_public: Optional[bool] = None
    email: Optional[EmailStr] = None
    # Required (and checked) only when email is being changed - a stolen
    # token shouldn't be enough on its own to redirect an account's
    # password-reset emails somewhere an attacker controls.
    current_password: Optional[str] = None


# ---------- Public ----------

class PublicUserOut(BaseModel):
    username: str
    display_name: Optional[str] = None
    cellar_count: int
    trading_enabled: bool


class RecentConsumedOut(BaseModel):
    username: str
    display_name: Optional[str] = None
    beer_name: str
    brewery_name: str
    consumed_on: dt.date


# ---------- Admin ----------

class AdminUserOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    email: str  # plain str, not EmailStr: admin listing must never 500 over one bad legacy row
    is_admin: bool
    has_oidc: bool
    created_at: dt.datetime
    cellar_count: int


class AdminUserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr
    password: PasswordStr
    is_admin: bool = False
    send_welcome_email: bool = True


class AdminUserPatch(BaseModel):
    is_admin: Optional[bool] = None


class AdminPasswordResetIn(BaseModel):
    new_password: PasswordStr


class InstanceSettingsOut(BaseModel):
    registration_enabled: bool
    # Read-only context from env-var config, shown for admin visibility -
    # these need a restart to change, not editable here.
    password_auth_enabled: bool
    oidc_enabled: bool

    # Raw values as stored in the database - None/empty means "not
    # overridden here, falls back to the matching CELLAR_SMTP_* env var if
    # one is set". The password itself is never returned, only whether
    # one is currently stored here.
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_security: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password_set: bool = False
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    smtp_skip_cert_verify: Optional[bool] = None

    # Whether sending actually works right now, after merging the above
    # with any env var defaults, plus a human-readable summary of what's
    # actually in effect (e.g. "smtp.example.com:587 via starttls").
    smtp_enabled: bool
    smtp_effective_summary: Optional[str] = None


class InstanceSettingsPatch(BaseModel):
    registration_enabled: Optional[bool] = None
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: Optional[int] = None
    smtp_security: Optional[str] = Field(default=None, pattern="^(starttls|ssl|none)$")
    smtp_username: Optional[str] = Field(default=None, max_length=255)
    smtp_password: Optional[str] = Field(default=None, max_length=255)
    smtp_from_email: Optional[str] = Field(default=None, max_length=255)
    smtp_from_name: Optional[str] = Field(default=None, max_length=255)
    smtp_skip_cert_verify: Optional[bool] = None


class SmtpTestIn(BaseModel):
    to_email: EmailStr
