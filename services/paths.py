from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


APP_DIR_NAME = "NexarComercio"
LEGACY_DIR_NAMES = (
    "NexarTienda",
    "Nexar Tienda",
)
NEW_DB_NAME = "nexar_comercio.db"
LEGACY_DB_NAMES = (
    "tienda.db",
    "nexar_tienda.db",
    "database.db",
    NEW_DB_NAME,
)
MIGRATION_LOG_NAME = "path_migration.log"


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "si"}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_dir()


def _user_data_base_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data)
    if os.name == "nt":
        return Path(Path.home() / "AppData" / "Local")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def is_portable_mode() -> bool:
    return _is_truthy(os.getenv("NEXAR_PORTABLE_MODE")) or _is_truthy(os.getenv("NEXAR_PORTABLE"))


def _resolve_requested_root() -> tuple[Path, str]:
    custom_dir = os.getenv("NEXAR_DATA_DIR", "").strip()
    if custom_dir:
        return Path(custom_dir).expanduser(), "custom"

    if is_portable_mode():
        return bundle_dir() / "portable_data" / APP_DIR_NAME, "portable"

    if not is_frozen() and not _is_truthy(os.getenv("NEXAR_USE_USER_DATA")):
        return project_dir(), "development"

    return _user_data_base_dir() / APP_DIR_NAME, "user_data"


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def restrict_permissions(path: Path, *, directory: bool = False) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o700 if directory else 0o600)
    except Exception:
        pass


def _append_text(path: Path, message: str) -> None:
    _safe_mkdir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(message.rstrip() + "\n")
    restrict_permissions(path)


def _is_valid_sqlite_file(path: Path) -> bool:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with path.open("rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except Exception:
        return False


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _legacy_root_candidates(target_root: Path) -> list[Path]:
    candidates: list[Path] = []
    bases = {
        _user_data_base_dir(),
        project_dir(),
    }
    if os.name == "nt":
        bases.add(Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming"))
    for base in bases:
        for name in LEGACY_DIR_NAMES:
            candidates.append(base / name)
    return candidates


def _legacy_db_candidates(root: Path) -> list[Path]:
    candidates = [root / db_name for db_name in LEGACY_DB_NAMES]
    data_dir = root / "data"
    candidates.extend(data_dir / db_name for db_name in LEGACY_DB_NAMES)
    return candidates


def _collect_legacy_layouts(target_root: Path) -> list[tuple[Path, Path]]:
    layouts: list[tuple[Path, Path]] = []
    seen: set[tuple[str, str]] = set()

    explicit_roots = []
    for root in _legacy_root_candidates(target_root):
        db_path = _first_existing(_legacy_db_candidates(root))
        if db_path:
            key = (str(root.resolve()), str(db_path.resolve()))
            if key not in seen:
                seen.add(key)
                explicit_roots.append((root, db_path))

    repo_root = project_dir()
    repo_db = _first_existing(_legacy_db_candidates(repo_root))
    if repo_db:
        key = (str(repo_root.resolve()), str(repo_db.resolve()))
        if key not in seen:
            seen.add(key)
            explicit_roots.append((repo_root, repo_db))

    for root, db_path in explicit_roots:
        if root.resolve() == target_root.resolve() and db_path.name == NEW_DB_NAME and db_path.parent.name == "data":
            continue
        layouts.append((root, db_path))
    return layouts


@dataclass(frozen=True)
class PathLayout:
    mode: str
    root: Path
    data_dir: Path
    database_path: Path
    logs_dir: Path
    backups_dir: Path
    config_dir: Path
    cache_dir: Path
    licenses_dir: Path
    exports_dir: Path
    updates_dir: Path
    active_root: Path
    active_database_path: Path
    using_fallback: bool
    migration_performed: bool
    migration_source: Path | None
    migration_log_path: Path
    migration_error: str | None


_LAYOUT_CACHE: PathLayout | None = None


def _build_layout(root: Path, mode: str) -> PathLayout:
    root = root.expanduser().resolve()
    data_dir = root / "data"
    logs_dir = root / "logs"
    backups_dir = root / "backups"
    config_dir = root / "config"
    cache_dir = root / "cache"
    licenses_dir = root / "licenses"
    exports_dir = root / "exports"
    updates_dir = cache_dir / "updates"
    database_path = data_dir / NEW_DB_NAME
    migration_log_path = logs_dir / MIGRATION_LOG_NAME
    return PathLayout(
        mode=mode,
        root=root,
        data_dir=data_dir,
        database_path=database_path,
        logs_dir=logs_dir,
        backups_dir=backups_dir,
        config_dir=config_dir,
        cache_dir=cache_dir,
        licenses_dir=licenses_dir,
        exports_dir=exports_dir,
        updates_dir=updates_dir,
        active_root=root,
        active_database_path=database_path,
        using_fallback=False,
        migration_performed=False,
        migration_source=None,
        migration_log_path=migration_log_path,
        migration_error=None,
    )


def _ensure_layout_dirs(layout: PathLayout) -> None:
    for directory in (
        layout.root,
        layout.data_dir,
        layout.logs_dir,
        layout.backups_dir,
        layout.config_dir,
        layout.cache_dir,
        layout.licenses_dir,
        layout.exports_dir,
        layout.updates_dir,
    ):
        _safe_mkdir(directory)
        restrict_permissions(directory, directory=True)


def _copy_file_if_missing(source: Path, target: Path) -> bool:
    if not source.exists() or target.exists():
        return False
    _safe_mkdir(target.parent)
    shutil.copy2(source, target)
    restrict_permissions(target)
    return True


def _copy_tree_if_missing(source: Path, target: Path) -> bool:
    if not source.exists() or target.exists():
        return False
    shutil.copytree(source, target)
    return True


def _migrate_from_legacy(layout: PathLayout, legacy_root: Path, legacy_db: Path) -> tuple[bool, str]:
    migrated_items: list[str] = []

    if _is_valid_sqlite_file(legacy_db) and not layout.database_path.exists():
        _copy_file_if_missing(legacy_db, layout.database_path)
        migrated_items.append(f"db:{legacy_db.name}->{layout.database_path.name}")

    file_pairs = (
        (legacy_root / "license.json", layout.licenses_dir / "license.json"),
        (legacy_root / "secret.key", layout.config_dir / "secret.key"),
        (legacy_root / "license_cache.json", layout.cache_dir / "license_cache.json"),
    )
    for source, target in file_pairs:
        if _copy_file_if_missing(source, target):
            migrated_items.append(f"file:{source.name}")

    dir_pairs = (
        (legacy_root / "logs", layout.logs_dir),
        (legacy_root / "respaldo", layout.backups_dir),
        (legacy_root / "backups", layout.backups_dir),
        (legacy_root / "licenses", layout.licenses_dir),
        (legacy_root / "config", layout.config_dir),
        (legacy_root / "cache", layout.cache_dir),
        (legacy_root / "exports", layout.exports_dir),
        (legacy_root / "updates", layout.updates_dir),
    )
    for source, target in dir_pairs:
        if _copy_tree_if_missing(source, target):
            migrated_items.append(f"dir:{source.name}")

    message = ", ".join(migrated_items) if migrated_items else "sin cambios necesarios"
    return True, message


def _resolve_layout() -> PathLayout:
    root, mode = _resolve_requested_root()
    layout = _build_layout(root, mode)
    _ensure_layout_dirs(layout)

    if layout.database_path.exists():
        return layout

    for legacy_root, legacy_db in _collect_legacy_layouts(layout.root):
        if not _is_valid_sqlite_file(legacy_db):
            continue
        try:
            ok, detail = _migrate_from_legacy(layout, legacy_root, legacy_db)
            if ok and layout.database_path.exists():
                _append_text(
                    layout.migration_log_path,
                    f"[migration] source={legacy_root} target={layout.root} detail={detail}",
                )
                return PathLayout(**{**layout.__dict__, "migration_performed": True, "migration_source": legacy_root})
        except Exception as exc:
            fallback_log = layout.migration_log_path
            error = f"{type(exc).__name__}: {exc}"
            _append_text(
                fallback_log,
                f"[migration-error] source={legacy_root} target={layout.root} error={error}",
            )
            return PathLayout(
                **{
                    **layout.__dict__,
                    "active_root": legacy_root,
                    "active_database_path": legacy_db,
                    "using_fallback": True,
                    "migration_source": legacy_root,
                    "migration_error": error,
                }
            )

    return layout


def get_path_layout() -> PathLayout:
    global _LAYOUT_CACHE
    if _LAYOUT_CACHE is None:
        _LAYOUT_CACHE = _resolve_layout()
    return _LAYOUT_CACHE


def reset_path_layout_cache() -> None:
    global _LAYOUT_CACHE
    _LAYOUT_CACHE = None


def get_app_data_dir() -> Path:
    return get_path_layout().active_root


def get_database_path() -> Path:
    return get_path_layout().active_database_path


def get_logs_dir() -> Path:
    return get_path_layout().logs_dir


def get_backups_dir() -> Path:
    return get_path_layout().backups_dir


def get_config_dir() -> Path:
    return get_path_layout().config_dir


def get_cache_dir() -> Path:
    return get_path_layout().cache_dir


def get_licenses_dir() -> Path:
    return get_path_layout().licenses_dir


def get_exports_dir() -> Path:
    return get_path_layout().exports_dir


def get_updates_dir() -> Path:
    return get_path_layout().updates_dir
