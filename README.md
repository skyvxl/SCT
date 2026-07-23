# Seamless Co-op Mod Manager

A Windows desktop manager for Elden Ring Seamless Co-op, rebuilt with PySide6.

The current development milestone reconstructs the application interface. Game
launching, save management, memory editing, backups, and updates are not active
yet.

## Development

```powershell
uv sync --dev
uv run scmm
uv run python -m unittest discover -s tests -v
```

## Credits

This project continues work based on Phantom Toolkit by **2Pz**.

See and [`LICENSE`](LICENSE).
