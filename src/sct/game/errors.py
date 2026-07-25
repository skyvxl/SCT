from __future__ import annotations


class GameRuntimeError(RuntimeError):
    """Base error for low-level game runtime operations."""


class GameProcessNotFound(GameRuntimeError):
    def __init__(self, process_name: str) -> None:
        super().__init__(f"Process not found: {process_name}")
        self.process_name = process_name


class GameModuleNotFound(GameRuntimeError):
    def __init__(self, module_name: str) -> None:
        super().__init__(f"Module not found in process: {module_name}")
        self.module_name = module_name


class SignatureConfigError(GameRuntimeError):
    pass


class SignatureNotFound(SignatureConfigError):
    def __init__(self, symbol: str) -> None:
        super().__init__(f"Signature not configured for symbol: {symbol}")
        self.symbol = symbol


class PatternNotFound(GameRuntimeError):
    def __init__(self, symbol: str) -> None:
        super().__init__(f"AOB pattern for '{symbol}' was not found")
        self.symbol = symbol


class PatternNotUnique(GameRuntimeError):
    def __init__(self, symbol: str, matches: int) -> None:
        super().__init__(f"AOB pattern for '{symbol}' is not unique: {matches} matches")
        self.symbol = symbol
        self.matches = matches
