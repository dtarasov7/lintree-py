# lintree-py

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)

`lintree-py.py` is a single-file Python 3.8 terminal disk usage visualizer inspired by lintree. It scans a directory tree, computes disk usage, and renders an interactive colored treemap directly in the terminal.

The implementation uses only the Python standard library.

## Features

- Concurrent filesystem scanner with bounded worker threads.
- Directory exclusions by name or path, plus NFS/CIFS/SMB mount exclusions.
- Wide horizontal treemap layout by default, plus original square layout.
- Color coding by file type: source code, web files, documents, images, video, audio, archives, data, binaries, directories, and other files.
- Brightness scaling by file size so larger items stand out.
- Interactive drill-down into directories and back navigation.
- Breadcrumb bar showing the current location.
- Sidebar with selected item name, type, size, path, parent percentage, and top children.
- Scan mode indicator on the progress screen and status bar.
- Keyboard and mouse selection support where the terminal supports mouse reporting.
- Linux, macOS, and Windows support using ANSI escape sequences and standard-library input handling.

## Requirements

- Python 3.8 or newer.
- A terminal with ANSI color support. Truecolor-capable terminals provide the best result.

No third-party packages are required.

## Usage

```bash
python3.8 lintree-py.py
python3.8 lintree-py.py /var/log
python3.8 lintree-py.py --fast ~/Downloads
python3.8 lintree-py.py --layout square /var/log
python3.8 lintree-py.py --layout wide /var/log
python3.8 lintree-py.py --exclude-dir node_modules --exclude-dir .git .
python3.8 lintree-py.py --exclude-network-fs /
```

## Options

```text
path                  Directory to scan. Defaults to the current directory.
--fast                Use more scanner workers. `-fast` is kept as a compatibility alias.
--layout wide         Prefer wide horizontal cells. This is the default.
--layout square       Use the original squarified layout.
--horizontal          Alias for --layout wide.
--square              Alias for --layout square.
--exclude-dir VALUE   Skip directories by basename or path. Repeat or use commas.
--exclude-network-fs  Skip directories on NFS, CIFS, or SMB filesystems.
--exclude-fs-type T   Skip mounted filesystems by type. Repeat or use commas.
-v, --version         Show version.
-h, --help            Show help.
```

## Controls

| Key | Action |
|---|---|
| `↑` `↓` / `j` `k` | Move through cells in visual reading order |
| `←` `→` | Move spatially inside the current visual row |
| `Enter` / `l` | Open selected directory |
| `Backspace` / `h` | Go back |
| `o` | Toggle wide/square layout |
| `?` | Toggle help overlay |
| `q` / `Ctrl+C` | Quit |
| Mouse click | Select a cell |

## Layout Modes

`wide` mode is optimized for terminal readability. Large cells are placed as wide horizontal areas, and smaller cells are grouped into lower rows. This makes labels easier to read on very wide terminals.

`square` mode keeps the original squarified treemap behavior, which favors compact rectangles with balanced aspect ratios.

## Architecture

The project is intentionally kept as one file:

- `ConcurrentScanner` builds a `FileNode` tree using worker threads.
- `compute_sizes_and_sort` computes aggregate directory sizes and counts.
- `layout_treemap` converts top-level children into treemap rectangles.
- `Canvas` renders an off-screen frame into ANSI truecolor output.
- `TerminalController` manages raw terminal mode and keyboard/mouse input.
- `LintreeApp` coordinates scanning, navigation, layout, and rendering.

PlantUML diagrams are available in `diagramms/`.

## Notes

- Symlinks are skipped to avoid cycles.
- `--exclude-dir` accepts a plain basename such as `node_modules` or a path such as `/mnt/cache`.
- `--exclude-network-fs` skips NFS/NFS4, CIFS, SMBFS, SMB3, and fuse.smbnetfs mounts before scanning them.
- `--exclude-fs-type` can exclude any mounted filesystem type visible to the OS mount table.
- On Unix, disk usage prefers allocated blocks (`st_blocks * 512`) when available.
- On Windows, logical file size is used when allocated block metadata is unavailable.
- `/proc`, `/sys`, `/dev`, and `/run` are skipped on Unix when scanning from root-like paths.

## Author

**Tarasov Dmitry**
- Email: dtarasov7@gmail.com

## Attribution
Parts of this code were generated with assistance
