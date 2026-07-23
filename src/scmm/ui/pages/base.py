from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from scmm.localization import TranslationService


@dataclass(slots=True)
class TextBinding:
    setter: Callable[[str], None]
    key: str
    args: tuple[object, ...]
    kwargs: dict[str, object]


class LocalizedPage(QWidget):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__()
        self.translator = translator
        self._bindings: list[TextBinding] = []
        translator.language_changed.connect(lambda _locale: self.retranslate_ui())

    @property
    def translation_keys(self) -> tuple[str, ...]:
        return tuple(binding.key for binding in self._bindings)

    def bind(
        self,
        setter: Callable[[str], None],
        key: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        binding = TextBinding(setter, key, args, kwargs)
        self._bindings.append(binding)
        setter(self.translator.translate(key, *args, **kwargs))

    def retranslate_ui(self) -> None:
        for binding in self._bindings:
            binding.setter(self.translator.translate(binding.key, *binding.args, **binding.kwargs))
