from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.config.settings import settings
from src.i18n import Language, translate


class Screen(StrEnum):
    MAIN = "main"
    BUY = "buy"
    FAVORITES = "favorites"
    PROFILE = "profile"
    SUPPORT = "support"
    REVIEWS = "reviews"
    INFO = "info"
    FAQ = "faq"


class InlineButtonSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    text_key: str = Field(min_length=1, max_length=64)
    text_kwargs: dict[str, str] = Field(default_factory=dict)
    target: Screen | None = None
    url: str | None = None
    style: Literal["success", "danger", "primary"] | None = None


class ScreenMediaSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    cache_key: str = Field(min_length=1)


class MenuViewSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    text_key: str = Field(min_length=1, max_length=64)
    text_kwargs: dict[str, str] = Field(default_factory=dict)
    buttons: tuple[tuple[InlineButtonSchema, ...], ...] = Field(min_length=1)
    media: ScreenMediaSchema | None = None


class ResolvedInlineButtonSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=64)
    target: Screen | None = None
    url: str | None = None


class ResolvedMenuViewSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    buttons: tuple[tuple[ResolvedInlineButtonSchema, ...], ...] = Field(min_length=1)
    media: ScreenMediaSchema | None = None


BUY_SCREEN_MEDIA = ScreenMediaSchema(path=settings.buy_image_path, cache_key="buy")
CATALOG_FILTER_SCREEN_MEDIA = ScreenMediaSchema(path=settings.filter_image_path, cache_key="catalog-filter")
CATALOG_RESULTS_SCREEN_MEDIA = ScreenMediaSchema(path=settings.catalog_image_path, cache_key="catalog-results")
CATALOG_ACCOUNT_SCREEN_MEDIA = ScreenMediaSchema(path=settings.account_image_path, cache_key="catalog-account")
FAQ_SCREEN_MEDIA = ScreenMediaSchema(path=settings.faq_image_path, cache_key="faq")


def button(*, text_key: str, target: Screen, **kwargs) -> InlineButtonSchema:
    return InlineButtonSchema(text_key=text_key, target=target, **kwargs)


def url_button(*, text_key: str, url: str, **kwargs) -> InlineButtonSchema:
    return InlineButtonSchema(text_key=text_key, url=url, **kwargs)


def back_row(target: Screen) -> tuple[InlineButtonSchema, ...]:
    return (button(text_key="back", target=target),)


def back_to_main_row() -> tuple[InlineButtonSchema, ...]:
    return (button(text_key="back_to_main_menu", target=Screen.MAIN),)


def render_menu_view(screen: Screen, language: Language) -> ResolvedMenuViewSchema:
    view = MENU_VIEWS[screen]

    return ResolvedMenuViewSchema(
        text=translate(language, view.text_key, **view.text_kwargs),
        buttons=tuple(
            tuple(
                ResolvedInlineButtonSchema(
                    text=translate(language, button.text_key, **button.text_kwargs),
                    target=button.target,
                    url=button.url,
                )
                for button in row
            )
            for row in view.buttons
        ),
        media=view.media,
    )


MENU_VIEWS: dict[Screen, MenuViewSchema] = {
    Screen.MAIN: MenuViewSchema(
        text_key="menu_main_text",
        media=ScreenMediaSchema(path=settings.menu_image_path, cache_key="menu"),
        buttons=(
            (
                button(text_key="menu_button_buy", target=Screen.BUY),
                button(text_key="menu_button_favorites", target=Screen.FAVORITES),
            ),
            (
                button(text_key="menu_button_profile", target=Screen.PROFILE),
                button(text_key="menu_button_support", target=Screen.SUPPORT),
            ),
            (
                button(text_key="menu_button_reviews", target=Screen.REVIEWS),
                button(text_key="menu_button_info", target=Screen.INFO),
            ),
        ),
    ),
    Screen.INFO: MenuViewSchema(
        text_key="menu_info_text",
        media=ScreenMediaSchema(path=settings.info_image_path, cache_key="info"),
        buttons=(
            (url_button(text_key="menu_button_privacy", url="https://telegra.ph/Politika-konfidencialnosti-06-21-31"),),
            (url_button(text_key="menu_button_terms", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"),),
            (button(text_key="menu_button_faq", target=Screen.FAQ),),
            back_row(Screen.MAIN),
        ),
    ),
    Screen.BUY: MenuViewSchema(
        text_key="menu_buy_text",
        buttons=(back_row(Screen.MAIN),),
    ),
    Screen.FAVORITES: MenuViewSchema(
        text_key="menu_favorites_text",
        media=ScreenMediaSchema(path=settings.favorites_image_path, cache_key="favorites"),
        buttons=(back_row(Screen.MAIN),),
    ),
    Screen.PROFILE: MenuViewSchema(
        text_key="profile_title",
        media=ScreenMediaSchema(path=settings.profile_image_path, cache_key="profile"),
        buttons=(back_row(Screen.MAIN),),
    ),
    Screen.REVIEWS: MenuViewSchema(
        text_key="menu_reviews_text",
        media=ScreenMediaSchema(path=settings.reviews_image_path, cache_key="reviews"),
        buttons=(back_row(Screen.MAIN),),
    ),
    Screen.SUPPORT: MenuViewSchema(
        text_key="menu_support_text",
        media=ScreenMediaSchema(path=settings.support_image_path, cache_key="support"),
        text_kwargs={"support_tag_name": settings.support_tag_name},
        buttons=(back_row(Screen.MAIN),),
    ),
    Screen.FAQ: MenuViewSchema(
        text_key="menu_faq_text",
        media=FAQ_SCREEN_MEDIA,
        buttons=(back_row(Screen.INFO), back_to_main_row()),
    ),
}
