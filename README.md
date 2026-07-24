# Seamless Co-op Toolkit

A Windows desktop toolkit for Elden Ring Seamless Co-op, rebuilt with PySide6.

The current development milestone reconstructs the application interface. Game
launching, save management, memory editing, backups, and updates are not active
yet.

## Development

```powershell
uv sync --dev
uv run sct
uv run python -m unittest discover -s tests -v
```

## Credits

This project continues work based on Phantom Toolkit by **2Pz**.

See [`LICENSE`](LICENSE).
