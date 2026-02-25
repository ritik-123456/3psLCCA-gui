"""
SafeChunkEngine v3.0

Project structure:
  chunks/x.lcca              — current save
  chunks_bak/x.lcca.bak      — previous save
  chunks_bak/x.lcca.ebak     — one before that
  manifest.json              — chunk registry + SHA256 hashes
  version.json               — project metadata
  wal.log                    — crash protection, cleared on clean close
  checkpoints/
    manual/                  — user-created checkpoints, last 10
    auto/                    — auto on clean close if content changed, last 5
  .lock                      — pid lock
"""

import json
import hashlib
import os
import copy
import threading
import time
import shutil
import zipfile
import psutil
import re
import zlib
import functools
from pathlib import Path
from typing import Optional, Callable


# ── Constants ─────────────────────────────────────────────────────────────────

LCCA_EXT = ".lcca"
BAK_EXT = ".lcca.bak"
EBAK_EXT = ".lcca.ebak"
MAGIC = b"\x4c\x43\x43\x41"  # LCCA in hex
ENGINE_VER = "3.0.0"
MANUAL_CHECKPOINT_RETENTION = 10
AUTO_CHECKPOINT_RETENTION = 5
MIN_ROTATE_AGE = 0.0  # 0 = always rotate on save (set to 30.0 for production)


# ── Encoding ──────────────────────────────────────────────────────────────────


def _encode(data: dict, readable: bool = True) -> bytes:
    """
    Encodes a dict to bytes.
    readable=True  (default) — plain UTF-8 JSON
    readable=False           — MAGIC + zlib compressed JSON (binary, unreadable)
    """
    if readable:
        return json.dumps(data, indent=4).encode("utf-8")
    compressed = zlib.compress(
        json.dumps(data, separators=(",", ":")).encode("utf-8"),
        level=6,
    )
    return MAGIC + compressed


def _decode(raw: bytes) -> dict:
    """
    Decodes bytes to dict.
    Supports both binary LCCA format and plain JSON (dev mode).
    Raises ValueError if file is not a valid LCCA or JSON file.
    """
    if raw[:4] == MAGIC:
        return json.loads(zlib.decompress(raw[4:]).decode("utf-8"))
    # Try plain JSON (dev/readable mode)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("Not a valid LCCA file.")


# ── Decorator ─────────────────────────────────────────────────────────────────


def requires_active(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._engine_active:
            self._log(f"Blocked: '{func.__name__}' called on inactive engine.")
            return None
        return func(self, *args, **kwargs)

    return wrapper


# ── Engine ────────────────────────────────────────────────────────────────────


class SafeChunkEngine:
    """
    SafeChunk Engine v3.0

    - Auto-saves every 1-2s via debounce + force-save timers
    - Rolling 3-copy backup per chunk (.lcca / .lcca.bak / .lcca.ebak)
    - WAL for crash protection
    - SHA256 integrity check on open
    - Auto-checkpoint on clean close (last 5 kept)
    - readable=True mode for development (plain JSON output)
    """

    VERSION = ENGINE_VER

    def __init__(
        self,
        project_id: str,
        display_name: str = None,
        app_version: str = "1.0.0",
        debounce_delay: float = 1.0,
        force_save_delay: float = 2.0,
        base_dir: str = "user_projects",
        readable: bool = True,
    ):
        # ── Identity ──────────────────────────────────────────────────────────
        self.project_id = project_id
        self.display_name = display_name or project_id
        self.app_version = app_version
        self.debounce_delay = debounce_delay
        self.force_save_delay = force_save_delay
        self.base_dir_path = Path(base_dir).resolve()
        self.readable = readable  # dev mode: saves as plain JSON

        # ── Paths ─────────────────────────────────────────────────────────────
        self.project_path = self.base_dir_path / self.project_id
        self.chunks_path = self.project_path / "chunks"
        self.chunks_bak_path = self.project_path / "chunks_bak"
        self.checkpoint_path = self.project_path / "checkpoints"
        self.checkpoint_manual = self.checkpoint_path / "manual"
        self.checkpoint_auto = self.checkpoint_path / "auto"
        self.manifest_path = self.project_path / "manifest.json"
        self.version_path = self.project_path / "version.json"
        self.lock_path = self.project_path / ".lock"
        self.wal_path = self.project_path / "wal.log"

        # ── Threading ─────────────────────────────────────────────────────────
        self._write_lock = threading.Lock()
        self._debounce_timer = None
        self._force_save_timer = None

        # ── State ─────────────────────────────────────────────────────────────
        self._staged_data = {}  # chunk_name → dict (uncompressed)
        self._session_dirty = False
        self._engine_active = False
        self.log_history = []

        # ── Callbacks ─────────────────────────────────────────────────────────
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_sync: Optional[Callable[[], None]] = None
        self.on_fault: Optional[Callable[[str], None]] = None
        self.on_dirty: Optional[Callable[[bool], None]] = None

        # ── Boot ──────────────────────────────────────────────────────────────
        self._initialize_env()
        self.attach()

    # --------------------------------------------------------------------------
    # ENVIRONMENT
    # --------------------------------------------------------------------------

    def _initialize_env(self):
        """Creates folder structure."""
        for path in [
            self.chunks_path,
            self.chunks_bak_path,
            self.checkpoint_manual,
            self.checkpoint_auto,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _startup_gc(self):
        """
        Runs on attach. Removes:
          - Stale *.tmp files left by a crashed atomic write
          - Orphaned .bak/.ebak files whose .lcca no longer exists
        """
        # Stale tmp files
        for tmp in self.chunks_path.glob("*.tmp"):
            try:
                tmp.unlink()
                self._log(f"GC: Removed stale tmp: {tmp.name}")
            except Exception:
                pass

        # Orphaned backups
        current = {
            f.name[: -len(LCCA_EXT)] for f in self.chunks_path.glob(f"*{LCCA_EXT}")
        }
        for ext in (BAK_EXT, EBAK_EXT):
            for f in self.chunks_bak_path.glob(f"*{ext}"):
                stem = f.name[: -len(ext)]
                if stem not in current:
                    try:
                        f.unlink()
                        self._log(f"GC: Removed orphan: {f.name}")
                    except Exception:
                        pass

    # --------------------------------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------------------------------

    def attach(self):
        """Claims lock, replays WAL, verifies chunk integrity, declares active."""

        # ── Lock check ────────────────────────────────────────────────────────
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text().split(":")[1].strip())
                if psutil.pid_exists(pid):
                    self._engine_active = False
                    self._log("ATTACH_DENIED: Project is open in another window.")
                    return
                self._log(f"Removing stale lock from PID {pid}.")
                self.lock_path.unlink()
            except Exception as e:
                self._log(f"Lock read error: {e}")

        try:
            # ── Read existing version.json ────────────────────────────────────
            existing_version = {}
            if self.version_path.exists():
                try:
                    existing_version = json.loads(self.version_path.read_text())
                except Exception:
                    pass

            # ── Preserve display_name ─────────────────────────────────────────
            saved_name = existing_version.get("display_name", "").strip()
            if self.display_name and self.display_name != self.project_id:
                final_name = self.display_name
            elif saved_name and saved_name != self.project_id:
                final_name = saved_name
            else:
                final_name = self.project_id
            self.display_name = final_name

            # ── Claim lock ────────────────────────────────────────────────────
            self.lock_path.write_text(f"PID: {os.getpid()}")

            # ── Mark session unclean immediately ──────────────────────────────
            # If we crash before detach(), clean_close stays False on disk
            self._write_version(existing_version, clean_close=False)

            # ── Startup GC ────────────────────────────────────────────────────
            self._startup_gc()

            # ── WAL replay ────────────────────────────────────────────────────
            replayed = self._wal_replay()
            if replayed:
                self._session_dirty = True

            # ── Integrity check (only when last session was clean) ─────────────
            last_clean = existing_version.get("clean_close", True)
            if last_clean:
                damaged = self._verify_chunks()
                if damaged:
                    self._log(
                        f"Integrity: {len(damaged)} chunk(s) failed hash check "
                        f"{damaged} — restoring from backup."
                    )
                    for name in damaged:
                        self._restore_chunk_from_backup(name)

            self._engine_active = True
            self._log(
                f"Engine v{self.VERSION} attached to "
                f"'{self.display_name}' ({self.project_id})."
                + (f" WAL replayed {replayed} entries." if replayed else "")
                + (" [readable mode]" if self.readable else "")
            )

        except Exception as e:
            self._engine_active = False
            self._handle_error(f"Critical attach failure: {e}")

    def detach(self):
        """
        Safe close sequence:
          1. Force sync all staged data
          2. Cancel timers
          3. Update manifest hashes
          4. Auto-checkpoint if session was dirty
          5. Clear WAL
          6. Write clean version.json
          7. Remove stale tmps (final cleanup)
          8. Release lock
        """
        if not self._engine_active:
            return

        self._log("Detaching. Final sync...")
        self.force_sync()

        # ── Cancel timers ─────────────────────────────────────────────────────
        with self._write_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            if self._force_save_timer:
                self._force_save_timer.cancel()
                self._force_save_timer = None

        # ── Update manifest hashes ────────────────────────────────────────────
        self._update_manifest_hashes()

        # ── Auto-checkpoint if content changed since last checkpoint ──────────
        if self._session_dirty and self._checkpoint_needed():
            try:
                self._create_auto_checkpoint()
                self._log("Auto-close checkpoint created.")
            except Exception as e:
                self._log(f"Auto-close checkpoint failed: {e}")

        # ── Clear WAL ─────────────────────────────────────────────────────────
        self._wal_clear()

        # ── Final GC: remove any stale tmps ──────────────────────────────────
        for tmp in self.chunks_path.glob("*.tmp"):
            try:
                tmp.unlink()
            except Exception:
                pass

        # ── Write clean version.json ──────────────────────────────────────────
        existing = {}
        if self.version_path.exists():
            try:
                existing = json.loads(self.version_path.read_text())
            except Exception:
                pass
        self._write_version(existing, clean_close=True)

        # ── Release lock ──────────────────────────────────────────────────────
        if self.lock_path.exists():
            self.lock_path.unlink()

        self._engine_active = False
        self._log("Engine detached cleanly.")

    def is_active(self) -> bool:
        return self._engine_active

    def is_dirty(self) -> bool:
        with self._write_lock:
            return bool(self._staged_data)

    # --------------------------------------------------------------------------
    # VERSION.JSON
    # --------------------------------------------------------------------------

    def _write_version(self, base: dict, clean_close: bool):
        """Writes version.json merging base dict with current engine state."""
        data = {
            **base,
            "engine_version": self.VERSION,
            "app_version": self.app_version,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "readable": self.readable,
            "clean_close": clean_close,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            self.version_path.write_text(json.dumps(data, indent=4))
        except Exception as e:
            self._log(f"version.json write failed: {e}")

    # --------------------------------------------------------------------------
    # MANIFEST
    # --------------------------------------------------------------------------

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {"chunks": {}}
        try:
            return json.loads(self.manifest_path.read_text())
        except Exception:
            return {"chunks": {}}

    def _save_manifest(self, manifest: dict):
        tmp = self.manifest_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(manifest, indent=4))
            tmp.replace(self.manifest_path)
        except Exception as e:
            self._log(f"Manifest save failed: {e}")

    def _update_manifest_hashes(self):
        """
        Computes SHA256 of every .lcca file and writes to manifest.json.
        Called on detach() — enables integrity check on next open.
        """
        manifest = self._load_manifest()
        chunks = manifest.get("chunks", {})

        for lcca in self.chunks_path.glob(f"*{LCCA_EXT}"):
            chunk_name = lcca.name[: -len(LCCA_EXT)]
            try:
                file_hash = hashlib.sha256(lcca.read_bytes()).hexdigest()
                chunks[chunk_name] = {
                    "hash": file_hash,
                    "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            except Exception as e:
                self._log(f"Hash failed for {chunk_name}: {e}")

        manifest["chunks"] = chunks
        manifest["project_id"] = self.project_id
        manifest["engine_version"] = self.VERSION
        manifest["hashes_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_manifest(manifest)
        self._log("Manifest hashes updated.")

    def _verify_chunks(self) -> list[str]:
        """
        Verifies each .lcca file against stored SHA256 in manifest.
        Returns list of chunk names that failed — empty list means all good.
        """
        manifest = self._load_manifest()
        chunks = manifest.get("chunks", {})
        damaged = []

        for chunk_name, info in chunks.items():
            if not isinstance(info, dict):
                continue
            stored_hash = info.get("hash")
            if not stored_hash:
                continue
            lcca = self.chunks_path / f"{chunk_name}{LCCA_EXT}"
            if not lcca.exists():
                damaged.append(chunk_name)
                continue
            try:
                if hashlib.sha256(lcca.read_bytes()).hexdigest() != stored_hash:
                    damaged.append(chunk_name)
            except Exception:
                damaged.append(chunk_name)

        return damaged

    def _restore_chunk_from_backup(self, chunk_name: str) -> bool:
        """
        Attempts to restore a damaged .lcca from .bak then .ebak.
        Returns True if a readable backup was found and restored.
        """
        lcca = self.chunks_path / f"{chunk_name}{LCCA_EXT}"
        bak = self.chunks_bak_path / f"{chunk_name}{BAK_EXT}"
        ebak = self.chunks_bak_path / f"{chunk_name}{EBAK_EXT}"

        for src, label in [(bak, ".bak"), (ebak, ".ebak")]:
            if not src.exists():
                continue
            try:
                _decode(src.read_bytes())  # verify readable before restoring
                shutil.copy2(src, lcca)
                self._log(f"Restored {chunk_name} from {label}.")
                return True
            except Exception as e:
                self._log(f"{label} unreadable for {chunk_name}: {e}")

        self._log(f"No readable backup found for {chunk_name}.")
        return False

    # --------------------------------------------------------------------------
    # WAL (WRITE-AHEAD LOG)
    # --------------------------------------------------------------------------

    def _wal_append(self, chunk_name: str, data: dict):
        """Synchronously appends a WAL entry before any disk write."""
        try:
            entry = json.dumps(
                {"chunk": chunk_name, "ts": time.time(), "data": data},
                separators=(",", ":"),
            )
            crc = zlib.crc32(entry.encode()) & 0xFFFFFFFF
            record = json.dumps({"e": entry, "crc": crc}, separators=(",", ":")) + "\n"
            with open(self.wal_path, "a", encoding="utf-8") as f:
                f.write(record)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            self._log(f"WAL append failed: {e}")

    def _wal_remove(self, chunk_name: str):
        """Removes committed entries for a chunk from WAL."""
        if not self.wal_path.exists():
            return
        try:
            lines = self.wal_path.read_text(encoding="utf-8").splitlines()
            remaining = []
            for line in lines:
                try:
                    rec = json.loads(line)
                    entry = json.loads(rec["e"])
                    if entry.get("chunk") != chunk_name:
                        remaining.append(line)
                except Exception:
                    remaining.append(line)
            if remaining:
                self.wal_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                self.wal_path.unlink()
        except Exception as e:
            self._log(f"WAL remove failed: {e}")

    def _wal_replay(self) -> int:
        """
        Replays uncommitted WAL entries into _staged_data.
        Called on attach if WAL exists.
        Returns number of entries successfully replayed.
        """
        if not self.wal_path.exists():
            return 0

        replayed = 0
        try:
            for line in self.wal_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    raw = rec["e"]
                    actual_crc = zlib.crc32(raw.encode()) & 0xFFFFFFFF
                    if actual_crc != rec["crc"]:
                        self._log("WAL: CRC mismatch — skipping corrupt entry.")
                        continue
                    entry = json.loads(raw)
                    chunk_name = entry.get("chunk", "").strip()
                    data = entry.get("data")
                    if chunk_name and data is not None:
                        self._staged_data[chunk_name] = data
                        replayed += 1
                except Exception as e:
                    self._log(f"WAL: Skipping unreadable entry: {e}")
        except Exception as e:
            self._log(f"WAL replay failed: {e}")

        return replayed

    def _wal_clear(self):
        """Removes WAL file on clean close."""
        try:
            if self.wal_path.exists():
                self.wal_path.unlink()
                self._log("WAL cleared.")
        except Exception as e:
            self._log(f"WAL clear failed: {e}")

    # --------------------------------------------------------------------------
    # CORE DATA OPERATIONS
    # --------------------------------------------------------------------------

    @requires_active
    def stage_update(self, data: dict, chunk_name: str):
        """
        Buffers data in memory and triggers debounce + force-save timers.
        Appends to WAL immediately for crash protection.
        """
        if not chunk_name or not chunk_name.strip():
            self._log("WARNING: stage_update called with empty chunk_name. Ignored.")
            return

        with self._write_lock:
            self._staged_data[chunk_name] = copy.deepcopy(data)
            self._wal_append(chunk_name, data)

            # Debounce — resets on every call
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                self.debounce_delay, self._commit_to_disk
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

            # Force-save — fires once per burst, guaranteed
            if self._force_save_timer is None:
                self._force_save_timer = threading.Timer(
                    self.force_save_delay, self._force_save_from_timer
                )
                self._force_save_timer.daemon = True
                self._force_save_timer.start()

        if self.on_dirty:
            self.on_dirty(True)
        if self.on_status:
            self.on_status("Unsaved changes...")

    @requires_active
    def fetch_chunk(self, chunk_name: str) -> dict:
        """
        Returns chunk data.
        Priority: staged memory → .lcca → .lcca.bak → .lcca.ebak → {}
        """
        with self._write_lock:
            if chunk_name in self._staged_data:
                return copy.deepcopy(self._staged_data[chunk_name])
        return self._read_chunk_with_fallback(chunk_name)

    # Alias for backward compatibility
    read_chunk = fetch_chunk

    def _read_chunk_with_fallback(self, chunk_name: str) -> dict:
        """Reads .lcca with automatic fallback to .bak then .ebak."""
        lcca = self.chunks_path / f"{chunk_name}{LCCA_EXT}"
        bak = self.chunks_bak_path / f"{chunk_name}{BAK_EXT}"
        ebak = self.chunks_bak_path / f"{chunk_name}{EBAK_EXT}"

        for src, label in [(lcca, ".lcca"), (bak, ".bak"), (ebak, ".ebak")]:
            if not src.exists():
                continue
            try:
                return _decode(src.read_bytes())
            except Exception as e:
                self._log(f"Read failed {chunk_name}{label}: {e}. Trying next.")

        self._log(f"All copies unreadable for: {chunk_name}.")
        return {}

    @requires_active
    def force_sync(self):
        """Immediately flushes all staged data to disk."""
        with self._write_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            if self._force_save_timer:
                self._force_save_timer.cancel()
                self._force_save_timer = None
        self._commit_to_disk()

    def _force_save_from_timer(self):
        with self._write_lock:
            self._force_save_timer = None
        self._commit_to_disk()
        self._log(f"Force-save fired after {self.force_save_delay}s.")

    # --------------------------------------------------------------------------
    # ATOMIC WRITE + ROTATION
    # --------------------------------------------------------------------------

    def _commit_to_disk(self):
        """Writes all staged chunks to disk atomically with rotation."""
        with self._write_lock:
            if not self._staged_data or not self._engine_active:
                return

            failed = []
            for chunk_name, data in list(self._staged_data.items()):
                try:
                    self._write_chunk(chunk_name, data)
                    del self._staged_data[chunk_name]
                    self._wal_remove(chunk_name)
                except Exception as e:
                    failed.append(chunk_name)
                    self._log(f"Commit failed for {chunk_name}: {e}")

            self._debounce_timer = None
            self._session_dirty = True

            if failed:
                self._handle_error(f"Commit failed for: {failed}")
            else:
                if self.on_dirty:
                    self.on_dirty(False)
                if self.on_sync:
                    self.on_sync()
                self._log("Commit successful.")

    def _write_chunk(self, chunk_name: str, data: dict):
        """
        Atomic write with rolling rotation:
          .lcca.bak  → .lcca.ebak   (shift back)
          .lcca      → .lcca.bak    (current becomes previous)
          new data   → .lcca        (write new current)
          lcca       → .lcca.bak   (mirror of current, always same as lcca)

        On every save:
          lcca  = current
          bak   = mirror of current (written together)
          ebak  = previous current
        """
        lcca = self.chunks_path / f"{chunk_name}{LCCA_EXT}"
        bak = self.chunks_bak_path / f"{chunk_name}{BAK_EXT}"
        ebak = self.chunks_bak_path / f"{chunk_name}{EBAK_EXT}"

        encoded = _encode(data, readable=self.readable)

        # Skip if content unchanged
        if lcca.exists():
            try:
                if lcca.read_bytes() == encoded:
                    return
            except Exception:
                pass

        # Current lcca → ebak before overwriting
        if lcca.exists():
            shutil.copy2(lcca, ebak)

        # Atomic write: tmp → fsync → rename
        tmp = lcca.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(lcca)

        # Mirror current lcca → bak (safety copy, always same as lcca)
        shutil.copy2(lcca, bak)

    # --------------------------------------------------------------------------
    # CHECKPOINTS
    # --------------------------------------------------------------------------

    def _checkpoint_needed(self) -> bool:
        """
        Returns True if current chunk state differs from last auto checkpoint.
        Compares manifest hashes — cheap and accurate.
        Always returns True if no checkpoint exists yet.
        """
        last_cps = sorted(
            self.checkpoint_auto.glob("cp_*.zip"),
            key=os.path.getmtime,
            reverse=True,
        )
        if not last_cps:
            return True

        try:
            with zipfile.ZipFile(last_cps[0], "r") as zf:
                if "manifest.json" not in zf.namelist():
                    return True
                old_manifest = json.loads(zf.read("manifest.json"))

            current_manifest = self._load_manifest()

            old_hashes = {
                k: v.get("hash") if isinstance(v, dict) else v
                for k, v in old_manifest.get("chunks", {}).items()
            }
            current_hashes = {
                k: v.get("hash") if isinstance(v, dict) else v
                for k, v in current_manifest.get("chunks", {}).items()
            }
            return old_hashes != current_hashes

        except Exception:
            return True  # if anything fails, create checkpoint to be safe

    def _create_auto_checkpoint(self) -> str | None:
        """Creates an auto checkpoint in checkpoints/auto/."""
        return self._write_checkpoint(
            folder=self.checkpoint_auto,
            label="auto_close",
            notes="Automatic checkpoint on clean close.",
            retention=AUTO_CHECKPOINT_RETENTION,
        )

    @requires_active
    def create_checkpoint(self, label: str = "manual", notes: str = "") -> str | None:
        """
        Creates a manual checkpoint in checkpoints/manual/.
        Keeps last MANUAL_CHECKPOINT_RETENTION checkpoints.
        """
        return self._write_checkpoint(
            folder=self.checkpoint_manual,
            label=label,
            notes=notes,
            retention=MANUAL_CHECKPOINT_RETENTION,
        )

    def _write_checkpoint(
        self,
        folder: Path,
        label: str,
        notes: str,
        retention: int,
    ) -> str | None:
        """
        Core checkpoint writer.
        Writes ZIP + SHA256 to specified folder, enforces retention.
        """
        self.force_sync()

        clean_label = re.sub(r"[^\w\-_]", "_", label)[:30]
        timestamp = (
            time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        )
        zip_name = f"cp_{clean_label}_{timestamp}.zip"
        zip_path = folder / zip_name

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in self.chunks_path.glob(f"*{LCCA_EXT}"):
                    zf.write(f, arcname=f"chunks/{f.name}")
                for f in self.chunks_bak_path.iterdir():
                    if f.is_file():
                        zf.write(f, arcname=f"chunks_bak/{f.name}")
                if self.manifest_path.exists():
                    zf.write(self.manifest_path, arcname="manifest.json")
                if self.version_path.exists():
                    zf.write(self.version_path, arcname="version.json")
                zf.writestr(
                    "checkpoint_meta.json",
                    json.dumps(
                        {
                            "label": label,
                            "notes": notes,
                            "timestamp": timestamp,
                            "project_id": self.project_id,
                            "engine_ver": self.VERSION,
                            "app_ver": self.app_version,
                            "readable": self.readable,
                            "type": (
                                "auto" if folder == self.checkpoint_auto else "manual"
                            ),
                        },
                        indent=4,
                    ),
                )

            # Write SHA256 alongside ZIP
            sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            (folder / f"{zip_name}.sha256").write_text(sha)

            # Enforce retention for this folder only
            zips = sorted(folder.glob("cp_*.zip"), key=os.path.getmtime)
            while len(zips) > retention:
                oldest = zips.pop(0)
                oldest.unlink()
                sha_file = folder / f"{oldest.name}.sha256"
                if sha_file.exists():
                    sha_file.unlink()

            self._log(f"Checkpoint created: {folder.name}/{zip_name}")
            return zip_name

        except Exception as e:
            self._handle_error(f"Checkpoint failed: {e}")
            return None

    def _resolve_checkpoint_path(self, zip_name: str) -> Path | None:
        """Finds which folder (manual/auto) a checkpoint lives in."""
        for folder in (self.checkpoint_manual, self.checkpoint_auto):
            p = folder / zip_name
            if p.exists():
                return p
        return None

    def verify_checkpoint(self, zip_name: str) -> bool:
        """
        Verifies checkpoint SHA256.
        Returns True if verified or no .sha256 exists (legacy).
        Returns False if hash mismatch or file missing.
        """
        zip_path = self._resolve_checkpoint_path(zip_name)
        if zip_path is None:
            return False

        sha_path = zip_path.parent / f"{zip_name}.sha256"
        if not sha_path.exists():
            return True  # legacy — no hash file, trust it

        try:
            stored = sha_path.read_text().strip()
            actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            return stored == actual
        except Exception:
            return False

    @requires_active
    def restore_checkpoint(self, zip_name: str) -> bool:
        """
        Restores project from checkpoint ZIP.
        Verifies SHA256 before extracting.
        """
        zip_path = self._resolve_checkpoint_path(zip_name)
        if zip_path is None:
            self._log(f"Checkpoint not found: {zip_name}")
            return False

        if not self.verify_checkpoint(zip_name):
            self._log(f"Restore aborted: {zip_name} failed SHA256 verification.")
            return False

        staging = self.project_path / "_restore_staging"
        try:
            with self._write_lock:
                if self._debounce_timer:
                    self._debounce_timer.cancel()
                if self._force_save_timer:
                    self._force_save_timer.cancel()
                self._staged_data.clear()

            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir()

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(path=staging)

            if (staging / "chunks").exists():
                if self.chunks_path.exists():
                    shutil.rmtree(self.chunks_path)
                shutil.move(str(staging / "chunks"), str(self.chunks_path))

            if (staging / "chunks_bak").exists():
                if self.chunks_bak_path.exists():
                    shutil.rmtree(self.chunks_bak_path)
                shutil.move(str(staging / "chunks_bak"), str(self.chunks_bak_path))

            if (staging / "manifest.json").exists():
                shutil.move(str(staging / "manifest.json"), str(self.manifest_path))

            shutil.rmtree(staging, ignore_errors=True)
            self._wal_clear()
            self._log(f"Restored from checkpoint: {zip_name}")
            return True

        except Exception as e:
            shutil.rmtree(staging, ignore_errors=True)
            self._handle_error(f"Restore failed: {e}")
            return False

    def list_checkpoints(self) -> list[dict]:
        """
        Lists all checkpoints (manual + auto) with metadata and verification.
        Unverified checkpoints include a warning message.
        """
        results = []
        sources = [
            (self.checkpoint_manual, "manual"),
            (self.checkpoint_auto, "auto"),
        ]

        for folder, cp_type in sources:
            for zp in folder.glob("cp_*.zip"):
                try:
                    verified = self.verify_checkpoint(zp.name)
                    meta = {}
                    try:
                        with zipfile.ZipFile(zp, "r") as zf:
                            meta = json.loads(zf.read("checkpoint_meta.json"))
                    except Exception:
                        pass

                    results.append(
                        {
                            "filename": zp.name,
                            "type": cp_type,
                            "label": meta.get("label", ""),
                            "date": meta.get("timestamp", ""),
                            "notes": meta.get("notes", ""),
                            "verified": verified,
                            "warning": (
                                ""
                                if verified
                                else "Integrity of this checkpoint could not be verified."
                            ),
                            "size_kb": round(zp.stat().st_size / 1024, 1),
                        }
                    )
                except Exception:
                    continue

        return sorted(results, key=lambda x: x["date"], reverse=True)

    # --------------------------------------------------------------------------
    # ROLLBACK HELPERS
    # --------------------------------------------------------------------------

    def get_rollback_options(self, chunk_name: str) -> list[dict]:
        """
        Returns available rollback copies for a chunk with timestamps.
        Used by UI to show user their options.
        """
        options = []

        lcca = self.chunks_path / f"{chunk_name}{LCCA_EXT}"
        bak = self.chunks_bak_path / f"{chunk_name}{BAK_EXT}"
        ebak = self.chunks_bak_path / f"{chunk_name}{EBAK_EXT}"

        for path, label in [
            (lcca, "Current"),
            (bak, "Previous save"),
            (ebak, "Earlier save"),
        ]:
            if path.exists():
                try:
                    mtime = path.stat().st_mtime
                    _decode(path.read_bytes())  # verify readable
                    options.append(
                        {
                            "label": label,
                            "file": path.name,
                            "path": str(path),
                            "saved_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.localtime(mtime)
                            ),
                            "readable": True,
                        }
                    )
                except Exception:
                    options.append(
                        {
                            "label": label,
                            "file": path.name,
                            "path": str(path),
                            "saved_at": "unknown",
                            "readable": False,
                        }
                    )

        return options

    def rollback_chunk(self, chunk_name: str, source_path: str) -> bool:
        """
        Rolls back a chunk to a specific copy (by file path).
        source_path must be one of the paths returned by get_rollback_options().
        """
        src = Path(source_path)
        lcca = self.chunks_path / f"{chunk_name}{LCCA_EXT}"

        if not src.exists():
            self._log(f"Rollback source not found: {source_path}")
            return False

        try:
            _decode(src.read_bytes())  # verify source is readable
            shutil.copy2(src, lcca)
            # Clear staged data for this chunk so next read gets rolled-back version
            with self._write_lock:
                self._staged_data.pop(chunk_name, None)
            self._log(f"Rolled back {chunk_name} from {src.name}.")
            return True
        except Exception as e:
            self._log(f"Rollback failed for {chunk_name}: {e}")
            return False

    # --------------------------------------------------------------------------
    # PROJECT MANAGEMENT
    # --------------------------------------------------------------------------

    def rename(self, new_display_name: str) -> bool:
        if not new_display_name.strip():
            return False
        self.display_name = new_display_name.strip()
        try:
            existing = {}
            if self.version_path.exists():
                existing = json.loads(self.version_path.read_text())
            existing["display_name"] = self.display_name
            self.version_path.write_text(json.dumps(existing, indent=4))
            self._log(f"Renamed to '{self.display_name}'.")
            return True
        except Exception as e:
            self._handle_error(f"Rename failed: {e}")
            return False

    def delete_project(self, confirmed: bool = False) -> bool:
        if not confirmed:
            return False
        try:
            self.detach()
            if self.project_path.exists():
                shutil.rmtree(self.project_path)
            return True
        except Exception as e:
            self._handle_error(f"Delete failed: {e}")
            return False

    # --------------------------------------------------------------------------
    # FACTORY METHODS
    # --------------------------------------------------------------------------

    @classmethod
    def new(
        cls,
        project_id: str = None,
        display_name: str = None,
        base_dir: str = "user_projects",
        readable: bool = True,
        **kwargs,
    ):
        """Creates a new project with a unique folder."""
        root = Path(base_dir)
        root.mkdir(parents=True, exist_ok=True)

        base_name = project_id or "new_project"
        target_id = base_name
        counter = 1
        while (root / target_id).exists():
            target_id = f"{base_name}_{counter}"
            counter += 1

        try:
            instance = cls(
                target_id,
                display_name=display_name,
                base_dir=str(root),
                readable=readable,
                **kwargs,
            )
            return instance, "SUCCESS"
        except Exception as e:
            return None, f"FAILED_TO_CREATE: {e}"

    @classmethod
    def open(
        cls,
        project_id: str,
        base_dir: str = "user_projects",
        readable: bool = True,
        **kwargs,
    ):
        """Opens an existing project, cleaning stale locks automatically."""
        root = Path(base_dir)
        if not (root / project_id).exists():
            return None, "PROJECT_NOT_FOUND"

        lock = root / project_id / ".lock"
        if lock.exists():
            try:
                pid = int(lock.read_text().split(":")[1].strip())
                if not psutil.pid_exists(pid):
                    lock.unlink()
            except Exception:
                try:
                    lock.unlink()
                except Exception:
                    pass

        # Read readable mode from version.json if not explicitly passed
        vf = root / project_id / "version.json"
        if vf.exists() and not readable:
            try:
                readable = json.loads(vf.read_text()).get("readable", True)
            except Exception:
                pass

        try:
            instance = cls(
                project_id,
                base_dir=str(root),
                readable=readable,
                **kwargs,
            )
            if not instance.is_active():
                return None, "PROJECT_ALREADY_OPEN"
            return instance, "SUCCESS"
        except Exception as e:
            return None, f"OPEN_ERROR: {e}"

    # --------------------------------------------------------------------------
    # STATIC HELPERS
    # --------------------------------------------------------------------------

    @staticmethod
    def list_all_projects(base_dir: str = "user_projects") -> list[dict]:
        """
        Lightweight scan — reads only version.json and filesystem metadata.
        Safe to call frequently from the home screen.
        """
        root = Path(base_dir)
        if not root.exists():
            return []

        results = []
        for item in root.iterdir():
            if not item.is_dir():
                continue
            if not (item / "chunks").exists():
                continue

            info = {
                "project_id": item.name,
                "display_name": item.name,
                "created_at": None,
                "last_modified": None,
                "status": "ok",
            }

            # Lock status
            lock = item / ".lock"
            if lock.exists():
                try:
                    pid = int(lock.read_text().split(":")[1].strip())
                    if psutil.pid_exists(pid):
                        info["status"] = "locked"
                except Exception:
                    pass

            # version.json
            vf = item / "version.json"
            if vf.exists():
                try:
                    data = json.loads(vf.read_text())
                    name = data.get("display_name", "").strip()
                    if name and name != item.name:
                        info["display_name"] = name
                    if not data.get("clean_close", True) and info["status"] == "ok":
                        info["status"] = "crashed"
                except Exception:
                    info["status"] = "corrupted"

            # Timestamps
            try:
                st = item.stat()
                info["created_at"] = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(st.st_ctime)
                )
                info["last_modified"] = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(st.st_mtime)
                )
            except Exception:
                pass

            results.append(info)

        return results

    @staticmethod
    def get_project_info(
        project_id: str,
        base_dir: str = "user_projects",
    ) -> dict | None:
        """Deep scan of a single project for the detail/info panel."""
        root = Path(base_dir)
        item = root / project_id
        if not item.exists():
            return None

        info = {
            "project_id": project_id,
            "display_name": project_id,
            "status": "ok",
            "created_at": None,
            "last_modified": None,
            "app_version": None,
            "engine_version": None,
            "chunk_count": 0,
            "checkpoint_count": 0,
            "last_checkpoint_date": None,
            "clean_close": True,
            "readable": False,
            "size_kb": 0,
        }

        vf = item / "version.json"
        if vf.exists():
            try:
                data = json.loads(vf.read_text())
                info["display_name"] = data.get("display_name", project_id)
                info["app_version"] = data.get("app_version")
                info["engine_version"] = data.get("engine_version")
                info["clean_close"] = data.get("clean_close", True)
                info["readable"] = data.get("readable", False)
                if not info["clean_close"]:
                    info["status"] = "crashed"
            except Exception:
                info["status"] = "corrupted"

        lock = item / ".lock"
        if lock.exists():
            try:
                pid = int(lock.read_text().split(":")[1].strip())
                if psutil.pid_exists(pid):
                    info["status"] = "locked"
            except Exception:
                pass

        chunks_path = item / "chunks"
        if chunks_path.exists():
            info["chunk_count"] = len(list(chunks_path.glob("*.lcca")))

        cp_path = item / "checkpoints"
        if cp_path.exists():
            zips = sorted(
                list((cp_path / "manual").glob("cp_*.zip"))
                + list((cp_path / "auto").glob("cp_*.zip")),
                key=os.path.getmtime,
                reverse=True,
            )
            info["checkpoint_count"] = len(zips)
            if zips:
                info["last_checkpoint_date"] = time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(os.path.getmtime(zips[0])),
                )

        try:
            info["size_kb"] = round(
                sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) / 1024,
                1,
            )
        except Exception:
            pass

        try:
            st = item.stat()
            info["created_at"] = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(st.st_ctime)
            )
            info["last_modified"] = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(st.st_mtime)
            )
        except Exception:
            pass

        return info

    # --------------------------------------------------------------------------
    # DIAGNOSTICS
    # --------------------------------------------------------------------------

    def get_health_report(self) -> dict:
        return {
            "active": self._engine_active,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "version": self.VERSION,
            "app_version": self.app_version,
            "readable_mode": self.readable,
            "chunk_count": len(list(self.chunks_path.glob(f"*{LCCA_EXT}"))),
            "checkpoint_count": (
                len(list(self.checkpoint_manual.glob("cp_*.zip")))
                + len(list(self.checkpoint_auto.glob("cp_*.zip")))
            ),
            "pending_syncs": len(self._staged_data),
            "wal_exists": self.wal_path.exists(),
            "session_dirty": self._session_dirty,
        }

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------------------------

    def _log(self, message: str):
        msg = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.log_history.append(msg)
        if len(self.log_history) > 100:
            self.log_history.pop(0)
        if self.on_status:
            self.on_status(message)
        else:
            print(msg)

    def _handle_error(self, message: str):
        self._log(f"FAULT: {message}")
        if self.on_fault:
            self.on_fault(message)
