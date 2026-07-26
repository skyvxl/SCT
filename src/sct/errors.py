from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sct.localization import TranslationService


class LocalizedError(RuntimeError):
    def __init__(
            self,
            code: str,
            debug_message: str,
            *,
            params: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(debug_message)
        self.code = code
        self.params = dict(params or {})


def localized_error_message(
        translator: TranslationService,
        error: BaseException,
        *,
        fallback_key: str = "errors.unexpected",
) -> str:
    if isinstance(error, LocalizedError):
        return translator.translate(f"errors.{error.code}", **error.params)
    return translator.translate(fallback_key)
