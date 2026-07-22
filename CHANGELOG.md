# Changelog

All notable changes to this project are documented in this file.

## [1.2.0] - 2026-07-01

### Added

- Added interactive `m` hotkey to switch the treemap display metric between disk size and file count.
- Added active metric support for treemap layout, top-child aggregation, cell brightness, cell labels, `% Parent`, and sidebar top items.
- Added visible `m:size` / `m:files` status indicator and help text for the display metric toggle.

## [1.1.0] - 2026-06-22

### Changed

- Reworked keyboard navigation: arrow keys now move spatially, while `j` and `k` move through the visual reading order.
- Replaced selected-cell half-block borders with clearer semigraphic box-drawing borders.
- Made `--fast` the primary documented fast-scan flag while keeping `-fast` as a compatibility alias.
- Added scan mode indicators to the scan progress screen and status bar.
- Updated README controls and feature descriptions.

## [1.0.0] - 2026-06-22

### Added

- Initial single-file Python 3.8 TUI implementation.
- Concurrent filesystem scanner with bounded worker threads.
- Wide and square treemap layout modes.
- File type color coding and size-based brightness.
- Interactive directory navigation, breadcrumbs, status bar, and sidebar.
- Directory exclusions by name or path.
- NFS/CIFS/SMB and custom filesystem type exclusions.
- Linux, macOS, and Windows terminal support without third-party packages.
- English and Russian README files.
- English and Russian PlantUML architecture diagrams.
