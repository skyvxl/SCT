# Seamless Co-op Toolkit

A Windows desktop toolkit for Elden Ring Seamless Co-op, rebuilt with PySide6.

The current development milestone reconstructs the application interface. Game
launching, save management, memory editing, backups, and updates are not active
yet.

## User interface

The screenshots below show what the program looks like now. I restored this
interface using old versions of Seamless Co-op Mod Manager (SCMM) by **2Pz** as
a reference. Some parts may change during development.

### Main screen

![Main screen](docs/images/main.png)

### Seamless Co-op settings

![Seamless Co-op settings](docs/images/seamless.png)

### Current game

![Current game](docs/images/current_game.png)

### Save backups

![Save backups](docs/images/saves.png)

### Character manager

![Character manager](docs/images/characters.png)

### Toolkit settings

![Toolkit settings](docs/images/settings.png)

### Cheat table

![Cheat table](docs/images/cheats.png)

### Player stats and equipment

![Player stats and equipment](docs/images/stats.png)

## Development

```powershell
uv sync --dev
uv run sct
uv run python -m unittest discover -s tests -v
```

## Credits

This project continues work based on Phantom Toolkit by **2Pz**.

See [`LICENSE`](LICENSE).
