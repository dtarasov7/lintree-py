#!/usr/bin/env python3
"""lintree-py: terminal disk usage treemap visualizer.

This single-file Python 3.8 program mirrors the core lintree experience without
third-party dependencies: concurrent filesystem scanning, wide/square treemap
layouts, file-type colors, breadcrumb navigation, and an interactive sidebar.

Русский: однофайловый TUI-визуализатор дискового пространства без внешних
зависимостей, с одновременным сканированием и интерактивной treemap-картой.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
import queue
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Sequence, Tuple, Union

# English: terminal input is platform-specific, so imports are optional.
# Русский: ввод из терминала зависит от платформы, поэтому импорты опциональны.
try:
    import termios
    import tty
except ImportError:  # pragma: no cover - unavailable on Windows.
    termios = None  # type: ignore
    tty = None  # type: ignore

try:
    import msvcrt
except ImportError:  # pragma: no cover - unavailable on Unix.
    msvcrt = None  # type: ignore


__VERSION__ = "1.0.0"

# English: layout constants mirror the Go lintree proportions.
# Русский: константы раскладки повторяют пропорции оригинального lintree на Go.
SIDEBAR_WIDTH = 30
BREADCRUMB_H = 1
STATUS_BAR_H = 1
MAX_VISIBLE_CELLS = 200
REDRAW_INTERVAL = 0.10
PROGRESS_INTERVAL = 0.20
CELL_ASPECT = 2.0
DEFAULT_NETWORK_FS_TYPES = {"nfs", "nfs4", "cifs", "smbfs", "smb3", "fuse.smbnetfs"}

RGB = Tuple[int, int, int]
Style = Tuple[RGB, RGB, bool]
Key = Union[str, Tuple[str, int, int]]


BG_MAIN = (20, 22, 26)
BG_BAR = (40, 44, 52)
BG_SIDEBAR = (33, 37, 43)
BG_SEPARATOR = (50, 55, 65)
FG_TEXT = (171, 178, 191)
FG_DIM = (92, 99, 112)
FG_MUTED = (130, 137, 151)
ACCENT = (86, 182, 194)
AMBER = (229, 192, 123)
RED = (224, 108, 117)

STYLE_MAIN: Style = (FG_TEXT, BG_MAIN, False)
STYLE_BAR: Style = (FG_MUTED, BG_BAR, False)
STYLE_SIDEBAR: Style = (FG_TEXT, BG_SIDEBAR, False)


CAT_DIRECTORY = "directory"
CAT_CODE = "code"
CAT_WEB = "web"
CAT_DOCUMENT = "document"
CAT_IMAGE = "image"
CAT_VIDEO = "video"
CAT_AUDIO = "audio"
CAT_ARCHIVE = "archive"
CAT_DATA = "data"
CAT_BINARY = "binary"
CAT_OTHER = "other"


# English: category colors are intentionally stable because users learn them visually.
# Русский: цвета категорий стабильны, чтобы пользователь быстро запоминал типы файлов.
CATEGORY_COLORS: Dict[str, RGB] = {
    CAT_DIRECTORY: (86, 182, 194),
    CAT_CODE: (91, 141, 239),
    CAT_WEB: (45, 184, 153),
    CAT_DOCUMENT: (152, 195, 121),
    CAT_IMAGE: (229, 192, 123),
    CAT_VIDEO: (198, 120, 221),
    CAT_AUDIO: (232, 105, 154),
    CAT_ARCHIVE: (224, 108, 117),
    CAT_DATA: (209, 154, 102),
    CAT_BINARY: (211, 95, 85),
    CAT_OTHER: (92, 99, 112),
}

CATEGORY_LABELS: Dict[str, str] = {
    CAT_DIRECTORY: "Directory",
    CAT_CODE: "Source Code",
    CAT_WEB: "Web",
    CAT_DOCUMENT: "Document",
    CAT_IMAGE: "Image",
    CAT_VIDEO: "Video",
    CAT_AUDIO: "Audio",
    CAT_ARCHIVE: "Archive",
    CAT_DATA: "Data",
    CAT_BINARY: "Binary",
    CAT_OTHER: "Other",
}

EXT_CATEGORIES: Dict[str, str] = {
    # Code.
    ".go": CAT_CODE,
    ".rs": CAT_CODE,
    ".py": CAT_CODE,
    ".js": CAT_CODE,
    ".ts": CAT_CODE,
    ".c": CAT_CODE,
    ".cpp": CAT_CODE,
    ".h": CAT_CODE,
    ".java": CAT_CODE,
    ".rb": CAT_CODE,
    ".php": CAT_CODE,
    ".swift": CAT_CODE,
    ".kt": CAT_CODE,
    ".scala": CAT_CODE,
    ".lua": CAT_CODE,
    ".sh": CAT_CODE,
    ".bash": CAT_CODE,
    ".zsh": CAT_CODE,
    ".fish": CAT_CODE,
    ".vim": CAT_CODE,
    ".el": CAT_CODE,
    ".clj": CAT_CODE,
    ".ex": CAT_CODE,
    ".erl": CAT_CODE,
    ".hs": CAT_CODE,
    ".ml": CAT_CODE,
    ".r": CAT_CODE,
    ".m": CAT_CODE,
    ".cs": CAT_CODE,
    ".dart": CAT_CODE,
    ".zig": CAT_CODE,
    ".nim": CAT_CODE,
    # Web.
    ".html": CAT_WEB,
    ".css": CAT_WEB,
    ".scss": CAT_WEB,
    ".sass": CAT_WEB,
    ".less": CAT_WEB,
    ".vue": CAT_WEB,
    ".svelte": CAT_WEB,
    ".jsx": CAT_WEB,
    ".tsx": CAT_WEB,
    ".wasm": CAT_WEB,
    # Documents.
    ".pdf": CAT_DOCUMENT,
    ".doc": CAT_DOCUMENT,
    ".docx": CAT_DOCUMENT,
    ".txt": CAT_DOCUMENT,
    ".md": CAT_DOCUMENT,
    ".rst": CAT_DOCUMENT,
    ".tex": CAT_DOCUMENT,
    ".rtf": CAT_DOCUMENT,
    ".odt": CAT_DOCUMENT,
    ".epub": CAT_DOCUMENT,
    ".pages": CAT_DOCUMENT,
    # Images.
    ".png": CAT_IMAGE,
    ".jpg": CAT_IMAGE,
    ".jpeg": CAT_IMAGE,
    ".gif": CAT_IMAGE,
    ".webp": CAT_IMAGE,
    ".svg": CAT_IMAGE,
    ".bmp": CAT_IMAGE,
    ".ico": CAT_IMAGE,
    ".tiff": CAT_IMAGE,
    ".psd": CAT_IMAGE,
    ".ai": CAT_IMAGE,
    ".raw": CAT_IMAGE,
    ".heic": CAT_IMAGE,
    # Video.
    ".mp4": CAT_VIDEO,
    ".mkv": CAT_VIDEO,
    ".avi": CAT_VIDEO,
    ".mov": CAT_VIDEO,
    ".wmv": CAT_VIDEO,
    ".flv": CAT_VIDEO,
    ".webm": CAT_VIDEO,
    ".m4v": CAT_VIDEO,
    ".3gp": CAT_VIDEO,
    # Audio.
    ".mp3": CAT_AUDIO,
    ".flac": CAT_AUDIO,
    ".wav": CAT_AUDIO,
    ".ogg": CAT_AUDIO,
    ".aac": CAT_AUDIO,
    ".wma": CAT_AUDIO,
    ".m4a": CAT_AUDIO,
    ".opus": CAT_AUDIO,
    # Archives.
    ".zip": CAT_ARCHIVE,
    ".tar": CAT_ARCHIVE,
    ".gz": CAT_ARCHIVE,
    ".bz2": CAT_ARCHIVE,
    ".xz": CAT_ARCHIVE,
    ".7z": CAT_ARCHIVE,
    ".rar": CAT_ARCHIVE,
    ".zst": CAT_ARCHIVE,
    ".lz4": CAT_ARCHIVE,
    ".deb": CAT_ARCHIVE,
    ".rpm": CAT_ARCHIVE,
    ".snap": CAT_ARCHIVE,
    ".appimage": CAT_ARCHIVE,
    ".dmg": CAT_ARCHIVE,
    ".iso": CAT_ARCHIVE,
    # Data.
    ".json": CAT_DATA,
    ".xml": CAT_DATA,
    ".csv": CAT_DATA,
    ".sql": CAT_DATA,
    ".db": CAT_DATA,
    ".sqlite": CAT_DATA,
    ".yaml": CAT_DATA,
    ".yml": CAT_DATA,
    ".toml": CAT_DATA,
    ".ini": CAT_DATA,
    ".conf": CAT_DATA,
    ".cfg": CAT_DATA,
    ".parquet": CAT_DATA,
    ".avro": CAT_DATA,
    ".proto": CAT_DATA,
    # Binaries.
    ".exe": CAT_BINARY,
    ".dll": CAT_BINARY,
    ".so": CAT_BINARY,
    ".dylib": CAT_BINARY,
    ".o": CAT_BINARY,
    ".a": CAT_BINARY,
    ".lib": CAT_BINARY,
    ".bin": CAT_BINARY,
    ".class": CAT_BINARY,
    ".pyc": CAT_BINARY,
}


def count_text(value: int) -> str:
    """Format an integer with comma separators.

    Args:
        value (int): Integer value to format.

    Returns:
        str: Decimal text with thousands separated by commas.
    """

    return f"{value:,}"


def size_text(num_bytes: int) -> str:
    """Format bytes as a binary human-readable size.

    Args:
        num_bytes (int): Byte count, expected to be non-negative.

    Returns:
        str: Size text using B, KiB, MiB, GiB, or TiB.
    """

    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(max(0, num_bytes))
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def rune_len(text: str) -> int:
    """Return display length approximation for terminal text.

    Args:
        text: Unicode text.

    Returns:
        Character count; wide glyph handling is intentionally minimal.
    """

    return len(text)


def truncate(text: str, max_width: int) -> str:
    """Trim text to a width, appending an ellipsis when possible.

    Args:
        text (str): Source text.
        max_width (int): Maximum number of displayed characters.

    Returns:
        str: Original or shortened text.
    """

    if max_width <= 0:
        return ""
    if rune_len(text) <= max_width:
        return text
    if max_width == 1:
        return text[:1]
    return text[: max_width - 1] + "…"


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an integer to a closed range.

    Args:
        value: Integer to limit.
        low: Lower bound.
        high: Upper bound.

    Returns:
        Integer within the requested range.
    """

    return max(low, min(high, value))


def go_round(value: float) -> int:
    """Round non-negative values like Go's math.Round.

    Args:
        value: Non-negative floating-point value.

    Returns:
        Integer rounded half away from zero.
    """

    return int(math.floor(value + 0.5))


def dim_color(color: RGB, factor: float) -> RGB:
    """Scale RGB brightness.

    Args:
        color: RGB tuple.
        factor: Brightness multiplier.

    Returns:
        Dimmed RGB tuple.
    """

    return (
        clamp(int(color[0] * factor), 0, 255),
        clamp(int(color[1] * factor), 0, 255),
        clamp(int(color[2] * factor), 0, 255),
    )


def contrast_fg(bg: RGB) -> RGB:
    """Choose readable foreground color for a background.

    Args:
        bg: Background RGB tuple.

    Returns:
        Dark or light RGB tuple.
    """

    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    if lum > 128:
        return (20, 20, 20)
    return (240, 240, 240)


def style(fg: RGB, bg: RGB, bold: bool = False) -> Style:
    """Create an immutable terminal style tuple.

    Args:
        fg: Foreground RGB tuple.
        bg: Background RGB tuple.
        bold: Whether to render bold text.

    Returns:
        Style tuple used by the canvas.
    """

    return (fg, bg, bold)


def category_for(name: str, is_dir: bool) -> str:
    """Return file category for a name.

    Args:
        name (str): File or directory name.
        is_dir (bool): True when the node is a directory.

    Returns:
        str: Category identifier used for labels and colors.
    """

    if is_dir:
        return CAT_DIRECTORY
    _, ext = os.path.splitext(name)
    return EXT_CATEGORIES.get(ext.lower(), CAT_OTHER)


def color_for(name: str, is_dir: bool) -> RGB:
    """Return base RGB color for a node.

    Args:
        name: File or directory name.
        is_dir: True when the node is a directory.

    Returns:
        RGB tuple for the category.
    """

    return CATEGORY_COLORS[category_for(name, is_dir)]


def stat_disk_size(stat_result: os.stat_result) -> int:
    """Return disk usage size from stat metadata.

    Args:
        stat_result (os.stat_result): Result from os.stat or DirEntry.stat.

    Returns:
        int: Allocated disk bytes on Unix when available, otherwise logical size.
    """

    blocks = getattr(stat_result, "st_blocks", None)
    if blocks is not None:
        return int(blocks) * 512
    return int(stat_result.st_size)


def split_option_values(values: Optional[Sequence[str]]) -> List[str]:
    """Split repeatable comma-friendly CLI option values.

    Args:
        values (Optional[Sequence[str]]): Raw argparse values.

    Returns:
        List[str]: Non-empty trimmed values.
    """

    result: List[str] = []
    if not values:
        return result
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                result.append(item)
    return result


def looks_like_path(value: str) -> bool:
    """Detect whether an exclusion value is a path rather than a plain name.

    Args:
        value (str): User-provided exclusion value.

    Returns:
        bool: True when the value contains path syntax.
    """

    return (
        os.path.isabs(value)
        or os.sep in value
        or (os.altsep is not None and os.altsep in value)
        or "\\" in value
        or bool(os.path.splitdrive(value)[0])
    )


def normalize_path(path: str) -> str:
    """Normalize a path for exact and subtree comparisons.

    Args:
        path (str): Path to normalize.

    Returns:
        str: Absolute, case-normalized path.
    """

    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def path_is_within(path: str, parent: str) -> bool:
    """Check whether path is equal to or inside parent.

    Args:
        path (str): Candidate path.
        parent (str): Parent path.

    Returns:
        bool: True when path is parent or a descendant.
    """

    try:
        return os.path.commonpath([path, parent]) == parent
    except ValueError:
        return False


class MountEntry:
    """Mounted filesystem descriptor used for exclusion checks.

    Русский: описание смонтированной ФС для проверки исключений.

    Args:
        path (str): Mount point path.
        fs_type (str): Filesystem type, for example nfs4 or cifs.
    """

    __slots__ = ("path", "fs_type")

    def __init__(self, path: str, fs_type: str) -> None:
        self.path = normalize_path(path)
        self.fs_type = fs_type.lower()


def decode_mount_path(path: str) -> str:
    """Decode Linux mount table path escapes.

    Args:
        path (str): Escaped mount path.

    Returns:
        str: Decoded path.
    """

    return (
        path.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def load_mount_table() -> List[MountEntry]:
    """Load local mount table when the platform exposes filesystem types.

    Returns:
        List[MountEntry]: Mount points sorted from deepest to shallowest.
    """

    if os.name == "nt":
        return []

    entries = load_linux_mountinfo()
    if not entries:
        entries = load_proc_mounts()
    if not entries:
        entries = load_mount_command()
    entries.sort(key=lambda item: len(item.path), reverse=True)
    return entries


def load_linux_mountinfo() -> List[MountEntry]:
    """Parse Linux /proc/self/mountinfo.

    Returns:
        List[MountEntry]: Parsed mount points, or an empty list when unavailable.
    """

    mountinfo = "/proc/self/mountinfo"
    if not os.path.exists(mountinfo):
        return []
    entries: List[MountEntry] = []
    try:
        with open(mountinfo, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if " - " not in line:
                    continue
                before, after = line.rstrip("\n").split(" - ", 1)
                before_fields = before.split()
                after_fields = after.split()
                if len(before_fields) < 5 or not after_fields:
                    continue
                entries.append(MountEntry(decode_mount_path(before_fields[4]), after_fields[0]))
    except OSError:
        return []
    return entries


def load_proc_mounts() -> List[MountEntry]:
    """Parse /proc/mounts as a fallback mount table.

    Returns:
        List[MountEntry]: Parsed mount points, or an empty list when unavailable.
    """

    mounts = "/proc/mounts"
    if not os.path.exists(mounts):
        return []
    entries: List[MountEntry] = []
    try:
        with open(mounts, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) >= 3:
                    entries.append(MountEntry(decode_mount_path(fields[1]), fields[2]))
    except OSError:
        return []
    return entries


def load_mount_command() -> List[MountEntry]:
    """Parse portable mount command output for macOS and BSD-like systems.

    Returns:
        List[MountEntry]: Parsed mount points, or an empty list when unavailable.
    """

    try:
        output = subprocess.check_output(["mount"], stderr=subprocess.DEVNULL, universal_newlines=True)
    except (OSError, subprocess.SubprocessError):
        return []

    entries: List[MountEntry] = []
    for line in output.splitlines():
        match = re.match(r"^.+ on (.+) \(([^,\s)]+)", line)
        if match:
            entries.append(MountEntry(match.group(1), match.group(2)))
    return entries


def windows_path_is_remote(path: str) -> bool:
    """Detect UNC or mapped network-drive paths on Windows.

    Args:
        path (str): Absolute path.

    Returns:
        bool: True when Windows reports the path as remote.
    """

    if not path:
        return False
    if path.startswith("\\\\"):
        return True
    try:
        drive, _tail = os.path.splitdrive(path)
        if not drive:
            return False
        root = drive + "\\"
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))  # type: ignore[attr-defined]
        return int(drive_type) == 4
    except (AttributeError, OSError, ValueError):
        return False


class FileNode:
    """Filesystem tree node used by scanning and rendering.

    Русский: узел дерева файловой системы для сканера, раскладки и панели.

    Args:
        name (str): Display name; the root stores its absolute path.
        is_dir (bool): True for directories.
        parent (Optional[FileNode]): Parent node or None for the root.
    """

    __slots__ = (
        "name",
        "size",
        "is_dir",
        "children",
        "parent",
        "file_count",
        "dir_count",
        "error",
    )

    def __init__(self, name: str, is_dir: bool, parent: Optional["FileNode"] = None) -> None:
        self.name = name
        self.size = 0
        self.is_dir = is_dir
        self.children: List[FileNode] = []
        self.parent = parent
        self.file_count = 0
        self.dir_count = 0
        self.error: Optional[str] = None

    def path(self) -> str:
        """Build full path by walking parents.

        Returns:
            str: Absolute path text for normal nodes; virtual aggregate nodes include
            their synthetic name.
        """

        parts: List[str] = []
        node: Optional[FileNode] = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        parts.reverse()
        if len(parts) == 1:
            return parts[0]
        return os.path.join(*parts)

    def top_children(self, limit: int) -> List["FileNode"]:
        """Return largest children and an aggregate remainder.

        Args:
            limit (int): Maximum number of real children to keep.

        Returns:
            List[FileNode]: Child list with optional synthetic "(N other)" node.
        """

        if len(self.children) <= limit:
            return self.children
        top = list(self.children[:limit])
        other_size = 0
        other_files = 0
        other_dirs = 0
        for child in self.children[limit:]:
            other_size += child.size
            other_files += child.file_count
            other_dirs += child.dir_count
            if child.is_dir:
                other_dirs += 1
            else:
                other_files += 1
        if other_size > 0:
            other = FileNode(f"({len(self.children) - limit} other)", True, self)
            other.size = other_size
            other.file_count = other_files
            other.dir_count = other_dirs
            top.append(other)
        return top


def compute_sizes_and_sort(root: FileNode) -> None:
    """Compute aggregate sizes and sort children in-place.

    Args:
        root (FileNode): Root of the scanned filesystem tree.

    Returns:
        None: The tree is mutated with aggregate counters and sorted children.
    """

    # English: iterative post-order avoids Python recursion limits on deep trees.
    # Русский: итеративный обход не упирается в лимит рекурсии на глубоких деревьях.
    stack: List[Tuple[FileNode, bool]] = [(root, False)]
    while stack:
        node, visited = stack.pop()
        if not node.is_dir:
            node.file_count = 0
            node.dir_count = 0
            continue
        if not visited:
            stack.append((node, True))
            for child in node.children:
                stack.append((child, False))
            continue

        total = 0
        files = 0
        dirs = 0
        for child in node.children:
            total += child.size
            if child.is_dir:
                dirs += 1 + child.dir_count
                files += child.file_count
            else:
                files += 1
        node.size = total
        node.file_count = files
        node.dir_count = dirs
        node.children.sort(key=lambda item: item.size, reverse=True)


class Progress:
    """Thread-safe scan progress snapshot container.

    Русский: контейнер снимка прогресса, который безопасно читать из TUI.
    """

    __slots__ = ("dirs_scanned", "files_found", "bytes_found", "current_path")

    def __init__(self) -> None:
        self.dirs_scanned = 0
        self.files_found = 0
        self.bytes_found = 0
        self.current_path = ""


class ConcurrentScanner:
    """Concurrent filesystem scanner with a fixed worker pool.

    Русский: одновременный сканер с ограниченным пулом рабочих потоков.

    Args:
        root_path (str): Directory to scan.
        fast (bool): Use more workers when True.
        cancel_event (threading.Event): Event used to request cancellation.
        exclude_dir_values (Optional[Sequence[str]]): Directory names or paths to skip.
        exclude_network_fs (bool): Skip directories on NFS/CIFS/SMB-like filesystems.
        exclude_fs_types (Optional[Sequence[str]]): Extra filesystem types to skip.
    """

    def __init__(
        self,
        root_path: str,
        fast: bool,
        cancel_event: threading.Event,
        exclude_dir_values: Optional[Sequence[str]] = None,
        exclude_network_fs: bool = False,
        exclude_fs_types: Optional[Sequence[str]] = None,
    ) -> None:
        self.root_path = os.path.abspath(os.path.expanduser(root_path))
        self.fast = fast
        self.cancel_event = cancel_event
        self.progress = Progress()
        self.progress.current_path = self.root_path
        self._progress_lock = threading.Lock()
        self._work: "queue.Queue[Optional[Tuple[FileNode, str]]]" = queue.Queue()
        self._pending = 0
        self._pending_cond = threading.Condition()
        self._workers: List[threading.Thread] = []
        self._skip_dir_paths = {normalize_path(path) for path in ("/proc", "/sys", "/dev", "/run")}
        self._exclude_dir_names: set = set()
        self._exclude_dir_paths: List[str] = []
        user_fs_types = {fs_type.lower() for fs_type in split_option_values(exclude_fs_types)}
        self._excluded_fs_types = set(DEFAULT_NETWORK_FS_TYPES if exclude_network_fs else [])
        self._excluded_fs_types.update(user_fs_types)
        self._exclude_windows_remote = exclude_network_fs or bool(user_fs_types.intersection(DEFAULT_NETWORK_FS_TYPES))
        self._mount_table = load_mount_table() if self._excluded_fs_types else []
        self._configure_dir_exclusions(exclude_dir_values)

    def _configure_dir_exclusions(self, values: Optional[Sequence[str]]) -> None:
        """Normalize directory exclusion values.

        Args:
            values (Optional[Sequence[str]]): Directory names or paths.

        Returns:
            None: Updates name and path exclusion collections.
        """

        for value in split_option_values(values):
            if looks_like_path(value):
                self._exclude_dir_paths.append(normalize_path(value))
            else:
                self._exclude_dir_names.add(os.path.normcase(value))

    def scan(self) -> Optional[FileNode]:
        """Scan the filesystem tree.

        Returns:
            Optional[FileNode]: Root FileNode on success, or None when cancelled.

        Raises:
            OSError: Propagated only for unexpected worker setup failures.
        """

        root = FileNode(self.root_path, True)
        if self._should_exclude_dir(root.name, self.root_path):
            return root
        worker_count = os.cpu_count() or 4
        if self.fast:
            worker_count *= 2
        worker_count = clamp(worker_count, 4, 32)

        # English: workers are bounded so huge trees do not create unbounded threads.
        # Русский: число потоков ограничено, чтобы огромные деревья не плодили потоки без контроля.
        for idx in range(worker_count):
            thread = threading.Thread(target=self._worker, name=f"lintree-scan-{idx}", daemon=True)
            self._workers.append(thread)
            thread.start()

        self._add_work(root, self.root_path)

        with self._pending_cond:
            while self._pending > 0 and not self.cancel_event.is_set():
                self._pending_cond.wait(0.1)

        for _ in self._workers:
            self._work.put(None)
        for thread in self._workers:
            thread.join()

        if self.cancel_event.is_set():
            return None

        compute_sizes_and_sort(root)
        return root

    def snapshot(self) -> Progress:
        """Return a copy of scan progress.

        Returns:
            Progress: Progress object safe for UI reads.
        """

        with self._progress_lock:
            snap = Progress()
            snap.dirs_scanned = self.progress.dirs_scanned
            snap.files_found = self.progress.files_found
            snap.bytes_found = self.progress.bytes_found
            snap.current_path = self.progress.current_path
            return snap

    def _add_work(self, node: FileNode, path: str) -> None:
        """Queue a directory for worker processing.

        Args:
            node (FileNode): Directory node.
            path (str): Absolute path to scan.

        Returns:
            None.
        """

        if self.cancel_event.is_set():
            return
        with self._pending_cond:
            self._pending += 1
        self._work.put((node, path))

    def _worker(self) -> None:
        """Process queued directories until a sentinel is received.

        Returns:
            None: Worker exits when it receives None.
        """

        while True:
            item = self._work.get()
            if item is None:
                return
            node, path = item
            try:
                if not self.cancel_event.is_set():
                    self._process_dir(node, path)
            finally:
                # English: pending is decremented even when a directory read fails.
                # Русский: pending уменьшается даже при ошибке чтения каталога.
                with self._pending_cond:
                    self._pending -= 1
                    if self._pending <= 0:
                        self._pending_cond.notify_all()

    def _process_dir(self, node: FileNode, dir_path: str) -> None:
        """Read a single directory and enqueue child directories.

        Args:
            node (FileNode): Directory node to populate.
            dir_path (str): Absolute path to the directory.

        Returns:
            None: Permission and stat errors are stored on affected nodes.
        """

        if os.name != "nt" and normalize_path(dir_path) in self._skip_dir_paths:
            return

        try:
            entries_iter = os.scandir(dir_path)
        except OSError as exc:
            node.error = str(exc)
            return

        with entries_iter as entries:
            with self._progress_lock:
                self.progress.dirs_scanned += 1
                self.progress.current_path = dir_path

            for entry in entries:
                if self.cancel_event.is_set():
                    return
                try:
                    # English: skipping symlinks avoids cycles and cross-device surprises.
                    # Русский: пропуск symlink защищает от циклов и неожиданных переходов.
                    if entry.is_symlink():
                        continue
                except OSError:
                    continue

                name = entry.name
                child_path = entry.path
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError as exc:
                    child = FileNode(name, False, node)
                    child.error = str(exc)
                    node.children.append(child)
                    continue

                if is_dir:
                    if self._should_exclude_dir(name, child_path):
                        continue
                    child = FileNode(name, is_dir, node)
                    node.children.append(child)
                    self._add_work(child, child_path)
                    continue

                child = FileNode(name, is_dir, node)
                node.children.append(child)
                try:
                    child.size = stat_disk_size(entry.stat(follow_symlinks=False))
                except OSError as exc:
                    child.error = str(exc)
                    child.size = 0

                with self._progress_lock:
                    self.progress.files_found += 1
                    self.progress.bytes_found += child.size

    def _should_exclude_dir(self, name: str, path: str) -> bool:
        """Check whether a directory should be skipped before scanning.

        Args:
            name (str): Directory basename.
            path (str): Directory path.

        Returns:
            bool: True when the directory should not be scanned or counted.
        """

        normalized_path = normalize_path(path)
        basename = os.path.basename(os.path.normpath(path)) or name
        if os.name != "nt" and normalized_path in self._skip_dir_paths:
            return True
        if os.path.normcase(basename) in self._exclude_dir_names:
            return True
        for excluded_path in self._exclude_dir_paths:
            if path_is_within(normalized_path, excluded_path):
                return True
        if self._is_excluded_fs_path(normalized_path):
            return True
        return False

    def _is_excluded_fs_path(self, normalized_path: str) -> bool:
        """Check whether a path is on an excluded filesystem type.

        Args:
            normalized_path (str): Absolute normalized path.

        Returns:
            bool: True when filesystem type exclusion applies.
        """

        if not self._excluded_fs_types:
            return False
        if os.name == "nt":
            return self._exclude_windows_remote and windows_path_is_remote(normalized_path)
        fs_type = self._fs_type_for_path(normalized_path)
        return fs_type in self._excluded_fs_types

    def _fs_type_for_path(self, normalized_path: str) -> str:
        """Find filesystem type for a path using the loaded mount table.

        Args:
            normalized_path (str): Absolute normalized path.

        Returns:
            str: Filesystem type or an empty string when unknown.
        """

        # English: mount table is sorted deepest-first, so the first prefix wins.
        # Русский: таблица mount отсортирована от глубоких путей к корню, первый префикс подходит.
        for entry in self._mount_table:
            if path_is_within(normalized_path, entry.path):
                return entry.fs_type
        return ""


class ScanJob:
    """Background scan runner used by the TUI.

    Русский: обертка над сканером, которая запускает его в фоне для TUI.

    Args:
        root_path (str): Directory to scan.
        fast (bool): Use extra scanner workers when True.
        exclude_dir_values (Optional[Sequence[str]]): Directory names or paths to skip.
        exclude_network_fs (bool): Skip NFS/CIFS/SMB-like filesystems.
        exclude_fs_types (Optional[Sequence[str]]): Extra filesystem types to skip.
    """

    def __init__(
        self,
        root_path: str,
        fast: bool,
        exclude_dir_values: Optional[Sequence[str]] = None,
        exclude_network_fs: bool = False,
        exclude_fs_types: Optional[Sequence[str]] = None,
    ) -> None:
        self.cancel_event = threading.Event()
        self.scanner = ConcurrentScanner(
            root_path,
            fast,
            self.cancel_event,
            exclude_dir_values,
            exclude_network_fs,
            exclude_fs_types,
        )
        self.root: Optional[FileNode] = None
        self.error: Optional[Exception] = None
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, name="lintree-scan-main", daemon=True)

    def start(self) -> None:
        """Start the background scan thread."""

        self.thread.start()

    def cancel(self) -> None:
        """Request cancellation and briefly wait for the scan manager."""

        self.cancel_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def progress(self) -> Progress:
        """Return latest scanner progress.

        Returns:
            Progress snapshot.
        """

        return self.scanner.snapshot()

    def _run(self) -> None:
        """Run the scanner and store result or error."""

        try:
            self.root = self.scanner.scan()
        except Exception as exc:  # Keep TUI alive long enough to restore terminal.
            self.error = exc
        finally:
            self.done.set()


class Rect:
    """Terminal rectangle in cell coordinates.

    Русский: прямоугольник в координатах терминальных ячеек.
    """

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def area(self) -> int:
        """Return rectangle area in terminal cells."""

        return self.w * self.h


class Cell:
    """Treemap cell linking a filesystem node to a rectangle.

    Русский: ячейка treemap, связывающая FileNode и прямоугольник.
    """

    __slots__ = ("node", "rect", "depth")

    def __init__(self, node: FileNode, rect: Rect, depth: int) -> None:
        self.node = node
        self.rect = rect
        self.depth = depth


class RowItem:
    """Internal item used by the squarified treemap algorithm.

    Русский: внутренний элемент строки алгоритма treemap.
    """

    __slots__ = ("node", "size")

    def __init__(self, node: FileNode, size: int) -> None:
        self.node = node
        self.size = size


def layout_treemap(
    nodes: Sequence[FileNode],
    bounds: Rect,
    depth: int = 0,
    wide_layout: bool = False,
) -> List[Cell]:
    """Compute treemap layout for visible filesystem nodes.

    Русский: вычисляет treemap-раскладку для видимых узлов.

    Args:
        nodes (Sequence[FileNode]): Nodes to lay out; zero-size nodes are ignored.
        bounds (Rect): Rectangle to fill.
        depth (int): Nesting depth label retained for parity with lintree.
        wide_layout (bool): Prefer horizontal strips so major areas are wider than tall.

    Returns:
        List[Cell]: Treemap cells clipped to bounds.
    """

    if bounds.w < 1 or bounds.h < 1 or not nodes:
        return []
    filtered = [node for node in nodes if node.size > 0]
    total_size = sum(node.size for node in filtered)
    if total_size <= 0:
        return []
    return _squarify(filtered, total_size, bounds, depth, wide_layout)


def _squarify(
    nodes: Sequence[FileNode],
    total_size: int,
    bounds: Rect,
    depth: int,
    wide_layout: bool,
) -> List[Cell]:
    """Arrange nodes using the Bruls-Huizing-van Wijk squarify strategy.

    Args:
        nodes (Sequence[FileNode]): Positive-size nodes sorted by size.
        total_size (int): Total size of nodes in the current area.
        bounds (Rect): Rectangle to fill.
        depth (int): Treemap nesting depth.
        wide_layout (bool): Force wide horizontal rows when True.

    Returns:
        List[Cell]: Computed treemap cells.
    """

    remaining = Rect(bounds.x, bounds.y, bounds.w, bounds.h)
    remaining_size = total_size
    cells: List[Cell] = []
    index = 0

    while index < len(nodes) and remaining.w > 0 and remaining.h > 0:
        row = [RowItem(nodes[index], nodes[index].size)]
        row_size = nodes[index].size
        index += 1

        while index < len(nodes):
            candidate = nodes[index]
            candidate_row = row + [RowItem(candidate, candidate.size)]
            new_size = row_size + candidate.size
            # English: wide mode rejects rows that would create tall slivers.
            # Русский: wide-режим не добавляет элемент, если он даст высокую щель.
            if wide_layout and not _wide_row_is_landscape(candidate_row, new_size, remaining, remaining_size):
                break
            if _worst_ratio(row, row_size, remaining, remaining_size, wide_layout) >= _worst_ratio(
                candidate_row, new_size, remaining, remaining_size, wide_layout
            ):
                row.append(RowItem(candidate, candidate.size))
                row_size = new_size
                index += 1
            else:
                break

        horizontal_strip = _row_uses_horizontal_strip(remaining, wide_layout)
        consumed = _layout_row(row, row_size, remaining, remaining_size, depth, cells, horizontal_strip)

        if horizontal_strip:
            remaining.y += consumed
            remaining.h -= consumed
        else:
            remaining.x += consumed
            remaining.w -= consumed
        remaining_size -= row_size

    return cells


def _row_uses_horizontal_strip(bounds: Rect, wide_layout: bool) -> bool:
    """Decide whether the next row is a horizontal strip.

    Args:
        bounds: Remaining rectangle.
        wide_layout: Force a wide/landscape-oriented layout when True.

    Returns:
        True when the strip consumes height and items run left-to-right.
    """

    if wide_layout:
        return True

    # English: original lintree behavior chooses the shorter visual side.
    # Русский: исходное поведение lintree выбирает более короткую визуальную сторону.
    effective_w = float(bounds.w) * CELL_ASPECT
    effective_h = float(bounds.h)
    return effective_w <= effective_h


def _wide_row_is_landscape(
    row: Sequence[RowItem],
    row_size: int,
    bounds: Rect,
    total_size: int,
) -> bool:
    """Check whether a horizontal row keeps all items wider than tall.

    Args:
        row (Sequence[RowItem]): Candidate row items.
        row_size (int): Total row size.
        bounds (Rect): Remaining rectangle.
        total_size (int): Remaining total size.

    Returns:
        bool: True when every candidate cell has width greater than or equal to height.
    """

    if not row or row_size <= 0 or total_size <= 0 or bounds.w <= 0 or bounds.h <= 0:
        return False

    strip_h = clamp(go_round(float(bounds.h) * float(row_size) / float(total_size)), 1, bounds.h)
    x = bounds.x
    for idx, item in enumerate(row):
        frac = float(item.size) / float(row_size)
        item_w = max(1, go_round(float(bounds.w) * frac))
        if idx == len(row) - 1:
            item_w = bounds.w - (x - bounds.x)
        if item_w < strip_h:
            return False
        x += item_w
    return True


def _worst_ratio(
    row: Sequence[RowItem],
    row_size: int,
    bounds: Rect,
    total_size: int,
    wide_layout: bool,
) -> float:
    """Return the worst aspect ratio for a candidate treemap row.

    Args:
        row (Sequence[RowItem]): Candidate row.
        row_size (int): Sum of item sizes in the row.
        bounds (Rect): Remaining rectangle.
        total_size (int): Remaining total size.
        wide_layout (bool): Whether wide row rules are active.

    Returns:
        float: Worst aspect ratio, or infinity for invalid input.
    """

    if not row or total_size <= 0 or row_size <= 0:
        return float("inf")

    total_area = float(bounds.w * bounds.h)
    row_area = total_area * float(row_size) / float(total_size)
    effective_w = float(bounds.w) * CELL_ASPECT
    effective_h = float(bounds.h)
    strip_len = effective_w if _row_uses_horizontal_strip(bounds, wide_layout) else effective_h
    if strip_len <= 0:
        return float("inf")

    worst = 0.0
    for item in row:
        frac = float(item.size) / float(row_size)
        item_area = row_area * frac
        if item_area <= 0:
            continue
        item_len = strip_len * frac
        strip_width = row_area / strip_len
        if item_len <= 0 or strip_width <= 0:
            continue
        ratio = item_len / strip_width
        if ratio < 1:
            ratio = 1 / ratio
        worst = max(worst, ratio)
    return worst


def _layout_row(
    row: Sequence[RowItem],
    row_size: int,
    bounds: Rect,
    total_size: int,
    depth: int,
    cells: List[Cell],
    horizontal_strip: bool,
) -> int:
    """Append cells for one treemap row and return consumed width or height.

    Args:
        row (Sequence[RowItem]): Items in the row.
        row_size (int): Sum of item sizes in the row.
        bounds (Rect): Remaining rectangle.
        total_size (int): Remaining total size.
        depth (int): Treemap nesting depth.
        cells (List[Cell]): Output list to append to.
        horizontal_strip (bool): True when row consumes height.

    Returns:
        int: Consumed height for horizontal strips or consumed width otherwise.
    """

    if not row or total_size <= 0:
        return 0
    row_frac = float(row_size) / float(total_size)

    if horizontal_strip:
        strip_h = clamp(go_round(float(bounds.h) * row_frac), 1, bounds.h)
        x = bounds.x
        for idx, item in enumerate(row):
            frac = float(item.size) / float(row_size)
            w = max(1, go_round(float(bounds.w) * frac))
            if idx == len(row) - 1:
                w = bounds.w - (x - bounds.x)
            if w <= 0:
                continue
            if x - bounds.x + w > bounds.w:
                w = bounds.w - (x - bounds.x)
            cells.append(Cell(item.node, Rect(x, bounds.y, w, strip_h), depth))
            x += w
        return strip_h

    strip_w = clamp(go_round(float(bounds.w) * row_frac), 1, bounds.w)
    y = bounds.y
    for idx, item in enumerate(row):
        frac = float(item.size) / float(row_size)
        h = max(1, go_round(float(bounds.h) * frac))
        if idx == len(row) - 1:
            h = bounds.h - (y - bounds.y)
        if h <= 0:
            continue
        if y - bounds.y + h > bounds.h:
            h = bounds.h - (y - bounds.y)
        cells.append(Cell(item.node, Rect(bounds.x, y, strip_w, h), depth))
        y += h
    return strip_w


class Canvas:
    """Off-screen terminal canvas rendered with ANSI truecolor sequences.

    Русский: буфер кадра в памяти перед выводом ANSI-последовательностей.
    """

    def __init__(self, width: int, height: int, base_style: Style = STYLE_MAIN) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.chars: List[List[str]] = [[" "] * self.width for _ in range(self.height)]
        self.styles: List[List[Style]] = [[base_style] * self.width for _ in range(self.height)]

    def set(self, x: int, y: int, char: str, draw_style: Style) -> None:
        """Set one terminal cell if it is inside bounds."""

        if 0 <= x < self.width and 0 <= y < self.height:
            self.chars[y][x] = char[0] if char else " "
            self.styles[y][x] = draw_style

    def fill_rect(self, x: int, y: int, w: int, h: int, char: str, draw_style: Style) -> None:
        """Fill a clipped rectangle with one character and style."""

        if w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        ch = char[0] if char else " "
        for yy in range(y0, y1):
            row_chars = self.chars[yy]
            row_styles = self.styles[yy]
            for xx in range(x0, x1):
                row_chars[xx] = ch
                row_styles[xx] = draw_style

    def text(self, x: int, y: int, text: str, draw_style: Style, max_width: Optional[int] = None) -> None:
        """Draw clipped text at a position."""

        if y < 0 or y >= self.height or x >= self.width:
            return
        if max_width is not None:
            text = truncate(text, max_width)
        for idx, char in enumerate(text):
            xx = x + idx
            if xx >= self.width:
                break
            if xx >= 0:
                self.set(xx, y, char, draw_style)

    def render(self) -> str:
        """Convert the canvas to ANSI escape sequences.

        Returns:
            str: Full terminal frame with cursor positioning and SGR styles.
        """

        chunks: List[str] = ["\x1b[?25l"]
        for y in range(self.height):
            chunks.append(f"\x1b[{y + 1};1H")
            x = 0
            while x < self.width:
                current_style = self.styles[y][x]
                start = x
                # English: group cells with identical style to reduce ANSI output.
                # Русский: объединяем одинаковые стили, чтобы уменьшить объем ANSI-вывода.
                while x < self.width and self.styles[y][x] == current_style:
                    x += 1
                chunks.append(ansi_for_style(current_style))
                chunks.append("".join(self.chars[y][start:x]))
        chunks.append("\x1b[0m")
        return "".join(chunks)


def ansi_for_style(draw_style: Style) -> str:
    """Build ANSI SGR sequence for a style."""

    fg, bg, bold = draw_style
    codes = ["0"]
    if bold:
        codes.append("1")
    codes.extend(
        [
            f"38;2;{fg[0]};{fg[1]};{fg[2]}",
            f"48;2;{bg[0]};{bg[1]};{bg[2]}",
        ]
    )
    return "\x1b[" + ";".join(codes) + "m"


class TerminalController:
    """Terminal mode manager for ANSI rendering and keyboard input.

    Русский: управляет raw-режимом, альтернативным экраном и вводом.
    """

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"
        self.stdin_fd: Optional[int] = None
        self.old_term_attrs: Optional[List[object]] = None
        self.old_windows_mode: Optional[int] = None
        self._input_buffer = b""

    def __enter__(self) -> "TerminalController":
        """Enter alternate screen, raw input mode, and mouse reporting.

        Returns:
            TerminalController: Active controller.

        Raises:
            RuntimeError: If POSIX terminal controls are unavailable.
        """

        if self.is_windows:
            self._enable_windows_vt()
        else:
            if termios is None or tty is None:
                raise RuntimeError("POSIX terminal control is unavailable")
            self.stdin_fd = sys.stdin.fileno()
            self.old_term_attrs = termios.tcgetattr(self.stdin_fd)
            tty.setraw(self.stdin_fd)

        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[?25l\x1b[?1000h\x1b[?1006h")
        sys.stdout.flush()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Restore terminal state."""

        sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if (
            not self.is_windows
            and termios is not None
            and self.stdin_fd is not None
            and self.old_term_attrs is not None
        ):
            termios.tcsetattr(self.stdin_fd, termios.TCSADRAIN, self.old_term_attrs)
        if self.is_windows and self.old_windows_mode is not None:
            self._restore_windows_mode()

    def size(self) -> Tuple[int, int]:
        """Return current terminal size."""

        term_size = shutil.get_terminal_size((80, 24))
        return term_size.columns, term_size.lines

    def write(self, text: str) -> None:
        """Write text to stdout and flush."""

        sys.stdout.write(text)
        sys.stdout.flush()

    def read_key(self, timeout: float) -> Optional[Key]:
        """Read a key or mouse event without blocking longer than timeout."""

        if self.is_windows:
            return self._read_windows_key(timeout)
        return self._read_posix_key(timeout)

    def _read_posix_key(self, timeout: float) -> Optional[Key]:
        """Read and parse POSIX terminal input."""

        parsed = self._parse_input_buffer()
        if parsed is not None:
            return parsed

        if self.stdin_fd is None:
            return None
        readable, _, _ = select.select([self.stdin_fd], [], [], timeout)
        if not readable:
            return None
        try:
            self._input_buffer += os.read(self.stdin_fd, 64)
        except OSError:
            return None
        return self._parse_input_buffer()

    def _parse_input_buffer(self) -> Optional[Key]:
        """Parse one key from the POSIX input buffer.

        Returns:
            Optional[Key]: Parsed key, mouse event, or None when input is incomplete.
        """

        data = self._input_buffer
        if not data:
            return None

        if data.startswith(b"\x1b[<"):
            # English: SGR mouse mode sends ESC [ < button ; x ; y M/m.
            # Русский: SGR mouse mode присылает ESC [ < button ; x ; y M/m.
            end_candidates = [pos for pos in (data.find(b"M"), data.find(b"m")) if pos != -1]
            if not end_candidates:
                return None
            end = min(end_candidates)
            seq = data[: end + 1]
            self._input_buffer = data[end + 1 :]
            try:
                body = seq[3:-1].decode("ascii")
                button_s, x_s, y_s = body.split(";")
                button = int(button_s)
                x = int(x_s) - 1
                y = int(y_s) - 1
            except (ValueError, UnicodeDecodeError):
                return None
            if seq.endswith(b"M") and button & 3 == 0:
                return ("mouse", x, y)
            return None

        arrow_map = {
            b"\x1b[A": "up",
            b"\x1b[B": "down",
            b"\x1b[C": "right",
            b"\x1b[D": "left",
        }
        for seq, key in arrow_map.items():
            if data.startswith(seq):
                self._input_buffer = data[len(seq) :]
                return key

        if data.startswith(b"\x1b[3~"):
            self._input_buffer = data[4:]
            return "delete"

        first = data[0]
        self._input_buffer = data[1:]
        if first == 0x1B:
            return "esc"
        if first == 0x03:
            return "ctrl_c"
        if first in (0x0A, 0x0D):
            return "enter"
        if first in (0x7F, 0x08):
            return "backspace"
        if 32 <= first <= 126:
            return chr(first)
        return None

    def _read_windows_key(self, timeout: float) -> Optional[Key]:
        """Read and parse Windows console keyboard input."""

        if msvcrt is None:
            return None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not msvcrt.kbhit():
                time.sleep(0.01)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                code = msvcrt.getwch()
                return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(code)
            if ch == "\x03":
                return "ctrl_c"
            if ch == "\r":
                return "enter"
            if ch == "\x08":
                return "backspace"
            if ch == "\x1b":
                return "esc"
            return ch
        return None

    def _enable_windows_vt(self) -> None:
        """Enable virtual terminal sequences on modern Windows consoles."""

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            self.old_windows_mode = int(mode.value)
            kernel32.SetConsoleMode(handle, mode.value | 0x0004 | 0x0008)

    def _restore_windows_mode(self) -> None:
        """Restore original Windows console mode."""

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        kernel32.SetConsoleMode(handle, self.old_windows_mode)


class LintreeApp:
    """Interactive disk usage treemap application.

    Русский: главный класс TUI, связывает сканирование, раскладку и ввод.

    Args:
        root_path (str): Directory to scan.
        fast (bool): Use extra scanner workers when True.
        wide_layout (bool): Start with landscape-oriented treemap rows when True.
        exclude_dir_values (Optional[Sequence[str]]): Directory names or paths to skip.
        exclude_network_fs (bool): Skip NFS/CIFS/SMB-like filesystems.
        exclude_fs_types (Optional[Sequence[str]]): Extra filesystem types to skip.
    """

    def __init__(
        self,
        root_path: str,
        fast: bool,
        wide_layout: bool = True,
        exclude_dir_values: Optional[Sequence[str]] = None,
        exclude_network_fs: bool = False,
        exclude_fs_types: Optional[Sequence[str]] = None,
    ) -> None:
        self.root_path = root_path
        self.fast = fast
        self.wide_layout = wide_layout
        self.scan_job = ScanJob(root_path, fast, exclude_dir_values, exclude_network_fs, exclude_fs_types)
        self.root: Optional[FileNode] = None
        self.focus: Optional[FileNode] = None
        self.nav_stack: List[FileNode] = []
        self.cursor = 0
        self.cells: List[Cell] = []
        self.scanning = True
        self.progress = Progress()
        self.width = 80
        self.height = 24
        self.show_help = False
        self.dirty = True
        self.progress_phase = 0
        self._last_progress_tick = 0.0

    def run(self) -> None:
        """Start scanning and run the interactive TUI until quit.

        Returns:
            None: The method exits after a quit event.

        Raises:
            Exception: Re-raises scan errors after terminal restoration.
        """

        self.scan_job.start()
        try:
            with TerminalController() as terminal:
                self.width, self.height = terminal.size()
                last_redraw = 0.0
                while True:
                    now = time.monotonic()
                    self._notice_resize(terminal)
                    self._notice_scan_result()

                    key = terminal.read_key(0.02)
                    if key is not None:
                        if self._process_input(key):
                            break
                        self.dirty = True

                    # English: progress is polled at a lower rate than key input.
                    # Русский: прогресс читается реже, чем клавиатурный ввод.
                    if self.scanning and now - self._last_progress_tick >= PROGRESS_INTERVAL:
                        self.progress = self.scan_job.progress()
                        self.progress_phase += 1
                        self._last_progress_tick = now
                        self.dirty = True

                    if self.dirty and now - last_redraw >= REDRAW_INTERVAL:
                        terminal.write(self._draw())
                        last_redraw = now
                        self.dirty = False

                    if self.scan_job.error is not None:
                        raise self.scan_job.error
        finally:
            if self.scanning:
                self.scan_job.cancel()

    def _notice_resize(self, terminal: TerminalController) -> None:
        """Update layout when terminal size changes."""

        width, height = terminal.size()
        if width != self.width or height != self.height:
            self.width = width
            self.height = height
            self._rebuild_layout()
            self.dirty = True

    def _notice_scan_result(self) -> None:
        """Switch from progress screen to treemap once scanning completes."""

        if not self.scanning or not self.scan_job.done.is_set():
            return
        if self.scan_job.error is not None:
            return
        if self.scan_job.root is not None:
            self.root = self.scan_job.root
            self.focus = self.root
            self.scanning = False
            self.cursor = 0
            self._rebuild_layout()
            self.dirty = True

    def _process_input(self, key: Key) -> bool:
        """Handle a keyboard or mouse event.

        Args:
            key (Key): Parsed key string or ("mouse", x, y) tuple.

        Returns:
            bool: True when the application should quit.
        """

        if self.show_help:
            self.show_help = False
            return False

        if isinstance(key, tuple):
            self._handle_mouse(key[1], key[2])
            return False

        if self.scanning:
            return key in ("q", "Q", "ctrl_c", "esc")

        if key in ("q", "Q", "ctrl_c"):
            return True
        if key == "esc":
            if self.focus is not None and self.root is not None and self.focus is not self.root:
                self._go_back()
                return False
            return True
        if key == "enter" or key == "l":
            self._drill_in()
        elif key == "backspace" or key == "h":
            self._go_back()
        elif key == "up" or key == "k":
            self._move_cursor(-1, horizontal=False)
        elif key == "down" or key == "j":
            self._move_cursor(1, horizontal=False)
        elif key == "left":
            self._move_cursor(-1, horizontal=True)
        elif key == "right":
            self._move_cursor(1, horizontal=True)
        elif key == "o" or key == "O":
            self._toggle_layout()
        elif key == "?":
            self.show_help = True
        return False

    def _handle_mouse(self, x: int, y: int) -> None:
        """Select a treemap cell under the mouse."""

        for idx, cell in enumerate(self.cells):
            rect = cell.rect
            if rect.x <= x < rect.x + rect.w and rect.y + BREADCRUMB_H <= y < rect.y + rect.h + BREADCRUMB_H:
                self.cursor = idx
                break

    def _move_cursor(self, delta: int, horizontal: bool) -> None:
        """Move selection in visual order or spatially between cells.

        Args:
            delta (int): Direction; negative moves backward/left, positive forward/right.
            horizontal (bool): True for spatial left/right movement.

        Returns:
            None: Cursor is updated in-place when a target exists.
        """

        if not self.cells:
            return
        if not horizontal:
            ordered = self._visual_order_indices()
            try:
                order_pos = ordered.index(self.cursor)
            except ValueError:
                order_pos = 0
            order_pos = clamp(order_pos + delta, 0, len(ordered) - 1)
            self.cursor = ordered[order_pos]
            return

        current = self.cells[self.cursor].rect
        cur_mid_x = current.x + current.w // 2
        cur_mid_y = current.y + current.h // 2
        best = -1
        best_score: Optional[Tuple[int, int, int, int]] = None
        for idx, cell in enumerate(self.cells):
            if idx == self.cursor:
                continue
            rect = cell.rect
            mid_x = rect.x + rect.w // 2
            mid_y = rect.y + rect.h // 2
            if (delta > 0 and mid_x <= cur_mid_x) or (delta < 0 and mid_x >= cur_mid_x):
                continue
            score = self._horizontal_nav_score(current, rect, cur_mid_x, cur_mid_y, delta)
            if best_score is None or score < best_score:
                best_score = score
                best = idx
        if best >= 0:
            self.cursor = best

    def _visual_order_indices(self) -> List[int]:
        """Return cell indices in screen reading order.

        Returns:
            Indices sorted from top to bottom, and left to right inside a row.
        """

        # English: layout construction order can differ from the visual rows in wide mode.
        # Русский: порядок создания ячеек может отличаться от видимых строк в wide-режиме.
        return sorted(range(len(self.cells)), key=lambda idx: (self.cells[idx].rect.y, self.cells[idx].rect.x, idx))

    def _horizontal_nav_score(
        self,
        current: Rect,
        candidate: Rect,
        cur_mid_x: int,
        cur_mid_y: int,
        delta: int,
    ) -> Tuple[int, int, int, int]:
        """Score a left/right navigation candidate.

        Args:
            current (Rect): Currently selected rectangle.
            candidate (Rect): Candidate rectangle.
            cur_mid_x (int): Current rectangle center X.
            cur_mid_y (int): Current rectangle center Y.
            delta (int): Direction, negative for left and positive for right.

        Returns:
            Tuple[int, int, int, int]: Sortable score; smaller means a better spatial neighbor.
        """

        # English: vertical overlap keeps navigation inside the same visual row.
        # Русский: вертикальное пересечение удерживает переход в той же визуальной строке.
        vertical_overlap = max(
            0,
            min(current.y + current.h, candidate.y + candidate.h) - max(current.y, candidate.y),
        )
        same_band_penalty = 0 if vertical_overlap > 0 else 1

        if delta > 0:
            horizontal_gap = max(0, candidate.x - (current.x + current.w))
        else:
            horizontal_gap = max(0, current.x - (candidate.x + candidate.w))

        cand_mid_x = candidate.x + candidate.w // 2
        cand_mid_y = candidate.y + candidate.h // 2
        cross_axis_distance = 0 if vertical_overlap > 0 else abs(cand_mid_y - cur_mid_y)
        main_axis_distance = abs(cand_mid_x - cur_mid_x)

        return (same_band_penalty, horizontal_gap, cross_axis_distance, main_axis_distance)

    def _drill_in(self) -> None:
        """Enter the selected directory."""

        if not self.cells or self.cursor >= len(self.cells) or self.focus is None:
            return
        node = self.cells[self.cursor].node
        if node.is_dir and node.children:
            self.nav_stack.append(self.focus)
            self.focus = node
            self.cursor = 0
            self._rebuild_layout()

    def _go_back(self) -> None:
        """Return to the previous directory in navigation history."""

        if self.nav_stack:
            self.focus = self.nav_stack.pop()
            self.cursor = 0
            self._rebuild_layout()

    def _toggle_layout(self) -> None:
        """Switch between wide and square treemap orientation.

        Returns:
            None: Layout and cursor are updated in-place.
        """

        selected = self.cells[self.cursor].node if self.cells and self.cursor < len(self.cells) else None
        self.wide_layout = not self.wide_layout
        self._rebuild_layout()
        if selected is not None:
            # English: keep the same selected node if it remains visible after relayout.
            # Русский: сохраняем выбранный узел, если он остался видимым после перестроения.
            for idx, cell in enumerate(self.cells):
                if cell.node is selected:
                    self.cursor = idx
                    break

    def _rebuild_layout(self) -> None:
        """Recompute visible treemap cells for the focused directory.

        Returns:
            None: Updates self.cells and clamps the cursor.
        """

        if self.focus is None:
            self.cells = []
            return
        tm_w = self.width - SIDEBAR_WIDTH
        if tm_w < 10:
            # English: hide the sidebar on narrow terminals.
            # Русский: на узких терминалах боковая панель скрывается.
            tm_w = self.width
        tm_h = self.height - BREADCRUMB_H - STATUS_BAR_H
        if tm_h < 3:
            tm_h = 3
        children = self.focus.top_children(MAX_VISIBLE_CELLS)
        self.cells = layout_treemap(children, Rect(0, 0, tm_w, tm_h), 0, self.wide_layout)
        if self.cursor >= len(self.cells):
            self.cursor = max(0, len(self.cells) - 1)

    def _draw(self) -> str:
        """Render the current application state."""

        canvas = Canvas(self.width, self.height, STYLE_MAIN)
        if self.scanning:
            self._draw_scan_progress(canvas)
        elif self.focus is not None:
            self._draw_breadcrumb(canvas)
            self._draw_treemap(canvas)
            self._draw_sidebar(canvas)
            self._draw_status_bar(canvas)
            if self.show_help:
                self._draw_help(canvas)
        return canvas.render()

    def _draw_scan_progress(self, canvas: Canvas) -> None:
        """Draw animated scanner progress screen."""

        dim = style(FG_DIM, BG_MAIN)
        accent = style(ACCENT, BG_MAIN, True)
        y = max(1, self.height // 2 - 3)
        spinner = "|/-\\"[self.progress_phase % 4]
        scan_mode = "FAST" if self.fast else "normal"
        title = f"{spinner}  Scanning filesystem...  [{scan_mode}]"
        canvas.text(max(0, (self.width - rune_len(title)) // 2), y, title, accent)
        y += 2

        bar_width = clamp(self.width - 8, 10, 60)
        bar = self._progress_bar(bar_width)
        canvas.text(max(0, (self.width - rune_len(bar)) // 2), y, bar, style(ACCENT, BG_MAIN))
        y += 2

        stats = (
            f"Dirs: {count_text(self.progress.dirs_scanned)}  "
            f"Files: {count_text(self.progress.files_found)}  "
            f"Size: {size_text(self.progress.bytes_found)}  "
            f"Mode: {scan_mode}"
        )
        canvas.text(max(0, (self.width - rune_len(stats)) // 2), y, stats, style(ACCENT, BG_MAIN))
        y += 2

        path = self.progress.current_path
        max_w = max(10, self.width - 6)
        if rune_len(path) > max_w:
            path = "..." + path[-(max_w - 3) :]
        canvas.text(max(0, (self.width - rune_len(path)) // 2), y, path, dim)

    def _progress_bar(self, width: int) -> str:
        """Build an indeterminate progress bar."""

        highlight = max(3, width // 4)
        travel = max(1, width - highlight)
        cycle = travel * 2
        pos = self.progress_phase % cycle
        if pos > travel:
            pos = cycle - pos
        chars = ["["]
        for idx in range(width):
            chars.append("█" if pos <= idx < pos + highlight else "░")
        chars.append("]")
        return "".join(chars)

    def _draw_breadcrumb(self, canvas: Canvas) -> None:
        """Draw breadcrumb bar for the focused directory."""

        if self.focus is None:
            return
        bar_style = STYLE_BAR
        canvas.fill_rect(0, 0, self.width, 1, " ", bar_style)

        parts: List[str] = []
        node: Optional[FileNode] = self.focus
        while node is not None:
            parts.insert(0, node.name)
            node = node.parent

        size = size_text(self.focus.size)
        available = max(1, self.width - rune_len(size) - 3)
        crumbs = collapse_breadcrumb(parts, " › ", available)

        x = 1
        for idx, part in enumerate(crumbs):
            if idx > 0:
                canvas.text(x, 0, " › ", style(FG_DIM, BG_BAR))
                x += 3
            part_style = style(ACCENT, BG_BAR, True) if idx == len(crumbs) - 1 else bar_style
            canvas.text(x, 0, part, part_style)
            x += rune_len(part)

        canvas.text(self.width - rune_len(size) - 1, 0, size, style(AMBER, BG_BAR))

    def _draw_treemap(self, canvas: Canvas) -> None:
        """Draw colored treemap cells and labels."""

        if not self.cells:
            if self.focus is not None:
                message = "No readable files in this directory"
                canvas.text(max(0, (self.width - rune_len(message)) // 2), self.height // 2, message, style(FG_DIM, BG_MAIN))
            return

        max_size = max(cell.node.size for cell in self.cells) or 1
        for idx, cell in enumerate(self.cells):
            rect = cell.rect
            base = color_for(cell.node.name, cell.node.is_dir)
            brightness = min(1.0, 0.65 + 0.35 * (float(cell.node.size) / float(max_size)))
            bg = dim_color(base, brightness)
            fg = contrast_fg(bg)
            selected = idx == self.cursor
            if selected:
                bg = base
                fg = contrast_fg(bg)
            cell_style = style(fg, bg, False)
            y0 = rect.y + BREADCRUMB_H
            canvas.fill_rect(rect.x, y0, rect.w, rect.h, " ", cell_style)

            if selected:
                border = style((20, 20, 20), AMBER)
                for dx in range(rect.w):
                    canvas.set(rect.x + dx, y0, "▀", border)
                    canvas.set(rect.x + dx, y0 + rect.h - 1, "▄", border)
                for dy in range(rect.h):
                    canvas.set(rect.x, y0 + dy, "▐", border)
                    canvas.set(rect.x + rect.w - 1, y0 + dy, "▌", border)
            else:
                border = style(fg, dim_color(bg, 0.5))
                if rect.w > 1:
                    canvas.fill_rect(rect.x + rect.w - 1, y0, 1, rect.h, " ", border)
                if rect.h > 1:
                    canvas.fill_rect(rect.x, y0 + rect.h - 1, rect.w, 1, " ", border)

            if rect.w >= 4 and rect.h >= 1:
                label = truncate(cell.node.name, rect.w - 2)
                label_y = y0 if rect.h == 1 else y0 + 1
                canvas.text(rect.x + 1, label_y, label, style(fg, bg, True))
                if rect.h >= 3 and rect.w >= 6:
                    size = size_text(cell.node.size)
                    if rune_len(size) <= rect.w - 2:
                        canvas.text(rect.x + 1, y0 + 2, size, style(fg, bg))

    def _draw_sidebar(self, canvas: Canvas) -> None:
        """Draw selected-node details in the right sidebar."""

        tm_w = self.width - SIDEBAR_WIDTH
        if tm_w < 10:
            return
        x0 = tm_w
        canvas.fill_rect(x0, 0, SIDEBAR_WIDTH, self.height, " ", STYLE_SIDEBAR)
        canvas.fill_rect(x0, 0, 1, self.height, "│", style(BG_SEPARATOR, BG_SEPARATOR))
        if not self.cells or self.cursor >= len(self.cells):
            return

        node = self.cells[self.cursor].node
        y = BREADCRUMB_H + 1
        pad = x0 + 2
        width = SIDEBAR_WIDTH - 3
        label_style = style(FG_DIM, BG_SIDEBAR)
        value_style = STYLE_SIDEBAR
        title_style = style(ACCENT, BG_SIDEBAR, True)
        div_style = style((62, 68, 81), BG_SIDEBAR)

        y = self._sidebar_line(canvas, pad, y, truncate(node.name, width), title_style)
        y = self._sidebar_divider(canvas, pad, y, width, div_style)
        label_w = 10

        cat = category_for(node.name, node.is_dir)
        y = self._sidebar_kv(canvas, pad, y, label_w, "Type", CATEGORY_LABELS[cat], label_style, style(CATEGORY_COLORS[cat], BG_SIDEBAR))
        y = self._sidebar_kv(canvas, pad, y, label_w, "Size", size_text(node.size), label_style, style(RED, BG_SIDEBAR, True))
        if node.is_dir:
            y = self._sidebar_kv(canvas, pad, y, label_w, "Files", count_text(node.file_count), label_style, value_style)
            y = self._sidebar_kv(canvas, pad, y, label_w, "Folders", count_text(node.dir_count), label_style, value_style)
        if self.focus is not None and self.focus.size > 0:
            pct = float(node.size) / float(self.focus.size) * 100.0
            y = self._sidebar_kv(canvas, pad, y, label_w, "% Parent", f"{pct:.1f}%", label_style, value_style)

        y = self._sidebar_divider(canvas, pad, y, width, div_style)
        y = self._sidebar_line(canvas, pad, y, "Path", label_style)
        for chunk in wrap_text(node.path(), width):
            y = self._sidebar_line(canvas, pad, y, chunk, style(FG_MUTED, BG_SIDEBAR))

        y = self._sidebar_divider(canvas, pad, y, width, div_style)
        if node.is_dir and node.children and y < self.height - 1:
            y = self._sidebar_line(canvas, pad, y, "Top Items", title_style)
            max_items = min(10, max(0, self.height - 2 - y))
            for child in node.children[:max_items]:
                child_color = color_for(child.name, child.is_dir)
                size = size_text(child.size)
                max_name = max(4, width - rune_len(size) - 3)
                name = "▪ " + truncate(child.name, max_name)
                y = self._sidebar_line(canvas, pad, y, name, style(child_color, BG_SIDEBAR))
                canvas.text(pad + width - rune_len(size), y - 1, size, value_style)

    def _sidebar_line(self, canvas: Canvas, x: int, y: int, text: str, line_style: Style) -> int:
        """Draw one sidebar line and return the next y."""

        if y < self.height:
            canvas.text(x, y, text, line_style)
        return y + 1

    def _sidebar_kv(
        self,
        canvas: Canvas,
        x: int,
        y: int,
        label_width: int,
        label: str,
        value: str,
        label_style: Style,
        value_style: Style,
    ) -> int:
        """Draw one sidebar key-value line."""

        if y < self.height:
            canvas.text(x, y, label, label_style)
            canvas.text(x + label_width, y, value, value_style)
        return y + 1

    def _sidebar_divider(self, canvas: Canvas, x: int, y: int, width: int, div_style: Style) -> int:
        """Draw a horizontal sidebar divider."""

        if y < self.height:
            canvas.text(x, y, "─" * max(0, width), div_style)
        return y + 1

    def _draw_status_bar(self, canvas: Canvas) -> None:
        """Draw bottom status/help bar."""

        if self.focus is None:
            return
        y = self.height - 1
        canvas.fill_rect(0, y, self.width, 1, " ", STYLE_BAR)
        left = f" {size_text(self.focus.size)}  {count_text(self.focus.file_count)} files  {count_text(self.focus.dir_count)} dirs"
        layout_name = "wide" if self.wide_layout else "square"
        scan_mode = "fast" if self.fast else "normal"
        right = f"scan:{scan_mode}  o:{layout_name}  arrows:move  Enter:open  Bksp:back  ?:help  q:quit "
        max_left = max(0, self.width - rune_len(right) - 1)
        canvas.text(0, y, truncate(left, max_left), STYLE_BAR)
        if rune_len(right) < self.width:
            canvas.text(self.width - rune_len(right), y, right, STYLE_BAR)

    def _draw_help(self, canvas: Canvas) -> None:
        """Draw modal help overlay."""

        canvas.fill_rect(0, 0, self.width, self.height, " ", style(FG_DIM, BG_MAIN))
        sections = [
            ("Navigation", [("↑↓ / j k", "Navigate cells"), ("←→", "Spatial move"), ("Enter / l", "Drill into dir"), ("Bksp / h", "Go back")]),
            ("Actions", [("o", "Toggle layout"), ("Esc", "Back / quit"), ("?", "Toggle help"), ("q / Ctrl+C", "Quit")]),
        ]
        inner_w = 34
        key_col = 14
        total_lines = 1 + sum(1 + len(entries) + 1 for _, entries in sections) + 1
        box_h = total_lines + 2
        box_w = inner_w + 4
        start_x = max(0, (self.width - box_w) // 2)
        start_y = max(0, (self.height - box_h) // 2)
        border = style(ACCENT, BG_SIDEBAR)
        text_style = STYLE_SIDEBAR
        heading = style(AMBER, BG_SIDEBAR, True)
        key_style = style(ACCENT, BG_SIDEBAR)
        dim = style(FG_DIM, BG_SIDEBAR)

        canvas.fill_rect(start_x, start_y, box_w, box_h, " ", text_style)
        self._box(canvas, start_x, start_y, box_w, box_h, border)
        y = start_y + 1
        title = "LINTREE HELP"
        canvas.text(start_x + 2 + max(0, (inner_w - rune_len(title)) // 2), y, title, heading)
        y += 1
        for title, entries in sections:
            self._box_separator(canvas, start_x, y, box_w, border)
            y += 1
            canvas.text(start_x + 2, y, title, heading)
            y += 1
            for key, desc in entries:
                canvas.text(start_x + 2, y, key, key_style)
                canvas.text(start_x + 2 + key_col, y, desc, text_style)
                y += 1
        footer = "Press any key to close"
        canvas.text(start_x + 2 + max(0, (inner_w - rune_len(footer)) // 2), y, footer, dim)

    def _box(self, canvas: Canvas, x: int, y: int, w: int, h: int, box_style: Style) -> None:
        """Draw a rectangular Unicode box."""

        if w < 2 or h < 2:
            return
        canvas.set(x, y, "╔", box_style)
        canvas.set(x + w - 1, y, "╗", box_style)
        canvas.set(x, y + h - 1, "╚", box_style)
        canvas.set(x + w - 1, y + h - 1, "╝", box_style)
        for dx in range(1, w - 1):
            canvas.set(x + dx, y, "═", box_style)
            canvas.set(x + dx, y + h - 1, "═", box_style)
        for dy in range(1, h - 1):
            canvas.set(x, y + dy, "║", box_style)
            canvas.set(x + w - 1, y + dy, "║", box_style)

    def _box_separator(self, canvas: Canvas, x: int, y: int, w: int, sep_style: Style) -> None:
        """Draw a horizontal separator inside a Unicode box."""

        if w < 2:
            return
        canvas.set(x, y, "╠", sep_style)
        canvas.set(x + w - 1, y, "╣", sep_style)
        for dx in range(1, w - 1):
            canvas.set(x + dx, y, "═", sep_style)


def collapse_breadcrumb(parts: Sequence[str], separator: str, max_width: int) -> List[str]:
    """Collapse breadcrumb parts to fit available width.

    Args:
        parts (Sequence[str]): Path components.
        separator (str): Separator text.
        max_width (int): Available width.

    Returns:
        List[str]: Possibly collapsed breadcrumb parts.
    """

    if not parts:
        return []
    sep_len = rune_len(separator)
    full = sum(rune_len(part) for part in parts) + sep_len * max(0, len(parts) - 1)
    if full <= max_width:
        return list(parts)
    if len(parts) > 3:
        collapsed = [parts[0], "…"] + list(parts[-2:])
        width = sum(rune_len(part) for part in collapsed) + sep_len * (len(collapsed) - 1)
        if width <= max_width:
            return collapsed
    fallback = ["…", parts[-1]]
    width = rune_len("…") + sep_len + rune_len(parts[-1])
    if width <= max_width:
        return fallback
    return [truncate(parts[-1], max_width)]


def wrap_text(text: str, width: int) -> List[str]:
    """Wrap text into fixed-width chunks.

    Args:
        text (str): Text to wrap.
        width (int): Chunk width.

    Returns:
        List[str]: Chunks, at least one item for non-empty text.
    """

    if width <= 0:
        return []
    if not text:
        return [""]
    return [text[idx : idx + width] for idx in range(0, len(text), width)]


def validate_root(path: str) -> str:
    """Validate that a path exists and is a directory.

    Args:
        path (str): User-provided path.

    Returns:
        str: Absolute directory path.

    Raises:
        ValueError: If the path does not exist or is not a directory.
    """

    expanded = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(expanded):
        raise ValueError(f"{path}: no such directory")
    if not os.path.isdir(expanded):
        raise ValueError(f"{path}: not a directory")
    return expanded


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser.

    Returns:
        argparse.ArgumentParser: Configured argparse parser.
    """

    parser = argparse.ArgumentParser(
        prog="lintree-py.py",
        description="Terminal disk usage visualizer. Think WinDirStat, but in your terminal.",
        add_help=False,
    )
    parser.add_argument("path", nargs="?", default=".", help="directory to scan (default: current directory)")
    parser.add_argument("--fast", "-fast", action="store_true", help="use more scanner workers")
    parser.add_argument("--layout", choices=("wide", "square"), default="wide", help="treemap orientation")
    parser.add_argument("--horizontal", dest="layout", action="store_const", const="wide", help="prefer wide horizontal cells")
    parser.add_argument("--square", dest="layout", action="store_const", const="square", help="use original squarified layout")
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        metavar="NAME_OR_PATH",
        help="skip directories by basename or path; repeat or use comma-separated values",
    )
    parser.add_argument(
        "--exclude-network-fs",
        action="store_true",
        help="skip directories located on NFS, CIFS, or SMB filesystems",
    )
    parser.add_argument(
        "--exclude-fs-type",
        action="append",
        default=[],
        metavar="TYPE",
        help="skip mounted filesystems by type; repeat or use comma-separated values",
    )
    parser.add_argument("-v", "--version", action="store_true", help="show version")
    parser.add_argument("-h", "--help", action="store_true", help="show help")
    return parser


def print_usage() -> None:
    """Print command-line usage and controls.

    Returns:
        None: Writes help text to stdout.
    """

    print(
        """lintree-py - Terminal disk usage visualizer

Usage:
  python3 lintree-py.py [path]                 Scan and visualize disk usage
  python3 lintree-py.py --fast [path]          Fast scan mode (more workers)
  python3 lintree-py.py --layout square [path] Original squarified layout
  python3 lintree-py.py --layout wide [path]   Wide horizontal layout (default)
  python3 lintree-py.py --exclude-dir NAME     Skip directories by name or path
  python3 lintree-py.py --exclude-network-fs   Skip NFS/CIFS/SMB mounts
  python3 lintree-py.py --exclude-fs-type TYPE Skip mounts by filesystem type
  python3 lintree-py.py -v                     Show version
  python3 lintree-py.py -h                     Show this help

Compatibility:
  -fast is accepted as an alias for --fast.

Controls:
  arrows / j k        Navigate cells
  left/right arrows   Spatial movement
  Enter / l           Drill into directory
  Backspace / h       Go back
  o                   Toggle wide/square layout
  ?                   Help overlay
  q / Ctrl+C          Quit
"""
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments, validate input, and run the TUI.

    Args:
        argv (Optional[Sequence[str]]): Optional argument sequence without program name.

    Returns:
        int: Process exit code.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.help:
        print_usage()
        return 0
    if args.version:
        print(f"lintree-py {__VERSION__}")
        return 0

    try:
        root_path = validate_root(args.path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # English: keep SIGINT as a key event in raw mode where possible.
    # Русский: SIGINT обрабатываем как клавишу, чтобы терминал корректно восстановился.
    old_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda _signum, _frame: None)
    try:
        app = LintreeApp(
            root_path,
            args.fast,
            args.layout == "wide",
            args.exclude_dir,
            args.exclude_network_fs,
            args.exclude_fs_type,
        )
        app.run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, old_sigint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
