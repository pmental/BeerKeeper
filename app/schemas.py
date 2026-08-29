import datetime as dt
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------- Auth ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class AuthConfigOut(BaseModel):
    password_auth_enabled: bool
    oidc_enabled: bool
    oidc_button_label: str
    registration_enabled: bool


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


class BeerIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brewery_id: Optional[int] = None
    new_brewery_name: Optional[str] = None
    style: Optional[str] = None
    abv: Optional[float] = Field(default=None, ge=0, le=100)
    description: Optional[str] = None
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


# ---------- Cellar entries ----------

class CellarEntryIn(BaseModel):
    beer_id: Optional[int] = None
    beer: Optional[BeerIn] = None  # allow creating the beer inline
    location: str = Field(default="cellar", pattern="^(cellar|fridge)$")
    custom_location: Optional[str] = None
    quantity: int = Field(default=1, ge=0)
    size_oz: Optional[float] = Field(default=None, ge=0)
    bottle_date: Optional[dt.date] = None
    best_before: Optional[dt.date] = None
    batch_notes: Optional[str] = None
    trade_status: str = Field(default="none", pattern="^(none|ft|iso)$")


class CellarEntryPatch(BaseModel):
    location: Optional[str] = Field(default=None, pattern="^(cellar|fridge)$")
    custom_location: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    size_oz: Optional[float] = Field(default=None, ge=0)
    bottle_date: Optional[dt.date] = None
    best_before: Optional[dt.date] = None
    batch_notes: Optional[str] = None
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
    note: Optional[str] = None
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
    note: Optional[str] = None
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
    notes: Optional[str] = None


# ---------- Account ----------

class AccountOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
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
    password: str = Field(min_length=8, max_length=200)
    is_admin: bool = False


class AdminUserPatch(BaseModel):
    is_admin: Optional[bool] = None


class AdminPasswordResetIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


class InstanceSettingsOut(BaseModel):
    registration_enabled: bool
    # Read-only context from env-var config, shown for admin visibility -
    # these need a restart to change, not editable here.
    password_auth_enabled: bool
    oidc_enabled: bool


class InstanceSettingsPatch(BaseModel):
    registration_enabled: Optional[bool] = None
