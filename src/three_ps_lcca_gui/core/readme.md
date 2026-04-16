# SafeChunkEngine v3.0

A crash-safe, auto-saving chunk storage engine for Python applications. Designed to protect user data with rolling backups, write-ahead logging, SHA256 integrity checks, and automatic checkpoints - all with zero manual save button required. Supports both structured data (chunks) and binary files (blobs: images, PDFs, ZIPs, etc.).

---

## Table of Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Creating vs Opening a Project](#creating-vs-opening-a-project)
- [Reading and Writing Data](#reading-and-writing-data)
- [Chunks - What Are They?](#chunks--what-are-they)
- [Auto-Save Behaviour](#auto-save-behaviour)
- [Closing a Project](#closing-a-project)
- [Blob Storage - Binary Files](#blob-storage--binary-files)
- [Checkpoints](#checkpoints)
- [Rollback - Per-Chunk Undo](#rollback--per-chunk-undo)
- [Callbacks / Event Hooks](#callbacks--event-hooks)
- [Project Discovery](#project-discovery)
- [Project Management](#project-management)
- [Diagnostics](#diagnostics)
- [Readable Mode (Dev/Debug)](#readable-mode-devdebug)
- [File Structure on Disk](#file-structure-on-disk)
- [Error Handling](#error-handling)
- [Full API Reference](#full-api-reference)
- [Constants Reference](#constants-reference)

---

## How It Works

The engine manages two types of storage:

**Chunks** - structured data stored as named dicts. When you call `stage_update()`, the engine:
1. Buffers the data in memory
2. Immediately writes it to a **Write-Ahead Log (WAL)** for crash safety
3. After a short debounce delay, atomically flushes it to disk
4. Rotates backup copies so you always have 3 versions of every chunk

**Blobs** - binary files (images, PDFs, ZIPs, etc.) stored as-is. When you call `store_blob()`, the engine:
1. Streams the file directly to disk - no memory staging, no WAL
2. Uses atomic tmp → fsync → rename to prevent partial writes
3. Auto-increments the name on collision so nothing is silently overwritten
4. Records a SHA256 hash in `blob_manifest.json` for integrity checking on open

If the process crashes mid-write, the WAL is replayed on the next open and chunk data is recovered automatically. Corrupt chunks are detected via SHA256 and restored from backups. Corrupt or missing blobs fire `on_fault` with a re-upload prompt.

---

## Installation

```bash
pip install psutil
```

Then copy `safechunk_engine.py` into your project.

```python
from safechunk_engine import SafeChunkEngine
```

---

## Quick Start

```python
from safechunk_engine import SafeChunkEngine

# Create a new project
engine, status = SafeChunkEngine.new(
    project_id="my_project",
    display_name="My Project",
)
print(status)  # "SUCCESS"

# Write structured data
engine.stage_update({"score": 100, "level": 3}, chunk_name="game_state")

# Read it back
data = engine.fetch_chunk("game_state")
print(data)  # {"score": 100, "level": 3}

# Store a binary file
name = engine.store_blob("assets/avatar.jpg")
print(name)  # "avatar.jpg"

# Read it back
image_bytes = engine.fetch_blob("avatar.jpg")

# Close cleanly
engine.detach()
```

---

## Creating vs Opening a Project

### `SafeChunkEngine.new()` - Create a fresh project

```python
engine, status = SafeChunkEngine.new(
    project_id="my_project",       # Folder name on disk
    display_name="My Project",     # Human-readable name (optional)
    base_dir="user_projects",      # Root directory for all projects (optional)
    readable=False,                # Binary mode (default). See Readable Mode section.
    app_version="1.0.0",           # Your app's version string (optional)
    debounce_delay=1.0,            # Seconds to wait before saving after last change (optional)
    force_save_delay=2.0,          # Maximum seconds before a forced save (optional)
)
```

If `my_project` already exists, the engine auto-increments: `my_project_1`, `my_project_2`, etc.

**Returns:** `(engine_instance, status_string)`

| Status | Meaning |
|---|---|
| `"SUCCESS"` | Project created and engine active |
| `"FAILED_TO_CREATE: ..."` | Creation failed with reason |

### `SafeChunkEngine.open()` - Open an existing project

```python
engine, status = SafeChunkEngine.open(
    project_id="my_project",
    base_dir="user_projects",  # Must match where it was created
)
```

On open, the engine automatically:
- Cleans any stale lock left by a previous crash
- Replays the WAL to recover unsaved chunk changes
- Runs SHA256 integrity checks on all chunks and restores damaged ones from backups
- Runs SHA256 integrity checks on all blobs and fires `on_fault` for any that are missing or corrupt

**Returns:** `(engine_instance, status_string)`

| Status | Meaning |
|---|---|
| `"SUCCESS"` | Project opened and engine active |
| `"PROJECT_NOT_FOUND"` | No folder exists for this project_id |
| `"PROJECT_ALREADY_OPEN"` | Another process holds the lock |
| `"OPEN_ERROR: ..."` | Unexpected failure with reason |

> **Note:** The `readable` mode is locked to whatever was set when the project was first created. Passing a different value is silently ignored and the stored setting is enforced.

---

## Reading and Writing Data

### Writing - `stage_update()`

```python
engine.stage_update(data, chunk_name)
```

Buffers `data` (a plain Python dict) in memory and schedules it to be flushed to disk. Writing to WAL happens synchronously and immediately for crash safety.

```python
engine.stage_update({"username": "alice", "level": 5}, chunk_name="user_profile")
engine.stage_update({"items": ["sword", "shield"]}, chunk_name="inventory")
engine.stage_update({"x": 120, "y": 340, "map": "dungeon_1"}, chunk_name="position")
```

- Each call resets the debounce timer
- The force-save timer guarantees a write within `force_save_delay` seconds regardless
- Calling with an empty `chunk_name` is a no-op and logs a warning

### Reading - `fetch_chunk()` / `read_chunk()`

```python
data = engine.fetch_chunk(chunk_name)
# or equivalently:
data = engine.read_chunk(chunk_name)  # alias for backward compatibility
```

Returns the data for a chunk as a dict. If there are unsaved changes for this chunk in memory, those are returned (most up-to-date version). Otherwise it falls back through the file copies in order:

```
staged memory  →  .lcca (current)  →  .lcca.bak (previous)  →  .lcca.ebak (earlier)  →  {}
```

Returns an empty dict `{}` if no data exists for that chunk anywhere.

### Force flushing - `force_sync()`

```python
engine.force_sync()
```

Immediately writes all staged (in-memory) data to disk. Cancels any pending timers. Use this before any critical operation that requires the latest data to be on disk.

### Checking dirty state - `is_dirty()`

```python
if engine.is_dirty():
    print("There are unsaved changes in memory")
```

Returns `True` if there is staged data in memory that has not yet been committed to disk.

---

## Chunks - What Are They?

A **chunk** is just a named dict saved as a single file. You decide how to split your data into chunks. Smaller, logically separate chunks are better than one giant chunk, because:

- Each chunk is saved independently - a write to `inventory` does not rewrite `user_profile`
- Each chunk gets its own 3-copy rolling backup
- Rollback works at the chunk level

**Example chunk design for a game:**

```python
engine.stage_update({"hp": 80, "mp": 40, "class": "mage"}, chunk_name="stats")
engine.stage_update({"gold": 500, "items": ["potion", "staff"]}, chunk_name="inventory")
engine.stage_update({"chapter": 2, "quests_done": ["intro", "caves"]}, chunk_name="progress")
engine.stage_update({"x": 100, "y": 200, "map": "forest"}, chunk_name="position")
```

Chunk names must be non-empty strings. Avoid path separators or special characters.

> **Chunks are for structured data only.** Do not store images, PDFs, or other binary files as Base64 inside a chunk - use [Blob Storage](#blob-storage--binary-files) instead.

---

## Auto-Save Behaviour

You never need to call a save function explicitly. The engine saves chunks automatically using two timers that work together:

**Debounce timer** (`debounce_delay`, default 1.0s): Every call to `stage_update()` resets this timer. The save fires 1 second after the *last* change. This prevents writing on every keystroke during rapid edits.

**Force-save timer** (`force_save_delay`, default 2.0s): Started on the *first* change in a burst. Fires once after 2 seconds regardless of how many changes are still coming. This guarantees data is never stuck in memory for too long.

```
User typing:    [change] [change] [change] [change] [change] [change]
Debounce:          |reset  |reset   |reset   |reset   |reset   |---1s--> SAVE
Force-save:        |-------------------2s------------------> SAVE
```

**To customise timing:**

```python
engine, _ = SafeChunkEngine.new(
    project_id="my_project",
    debounce_delay=0.5,   # Save 0.5s after last change
    force_save_delay=3.0, # But no later than 3s after first change
)
```

> Auto-save applies to chunks only. Blobs are written to disk immediately and synchronously on every `store_blob()` call - there is no staging or timer involved.

---

## Closing a Project

Always call `detach()` when you're done with a project:

```python
engine.detach()
```

On clean close, the engine:
1. Flushes all staged chunk data to disk
2. Cancels pending timers
3. Updates SHA256 hashes in `manifest.json` and `blob_manifest.json`
4. Creates an auto-checkpoint (chunks only) if chunk content changed since the last one
5. Clears the WAL
6. Writes `clean_close: true` to `version.json`
7. Releases the `.lock` file

If the process is killed without calling `detach()`, the engine will detect this on the next `open()` and recover via WAL replay and integrity checks.

---

## Blob Storage - Binary Files

Blobs are for binary files that cannot be stored as JSON - images, PDFs, ZIP archives, audio files, and so on. They are managed separately from chunks with a simpler, direct-to-disk design.

**Key differences from chunks:**

| | Chunks | Blobs |
|---|---|---|
| Data type | Python dict | Raw bytes / file path |
| Write path | Staged in memory → WAL → disk | Streamed directly to disk |
| Auto-save | Debounced (1–2s delay) | Immediate, synchronous |
| Backup copies | 3 (`.lcca`, `.bak`, `.ebak`) | None - re-upload if lost |
| Crash recovery | WAL replay + backup restore | SHA256 check → re-upload prompt |
| In checkpoints | Always included | Optional (`include_blobs=True`) |

### Storing a blob - `store_blob()`

```python
# From a file path (recommended - streamed, never fully loaded into memory)
name = engine.store_blob("documents/report.pdf")
name = engine.store_blob(Path("/uploads/photo.jpg"))

# From raw bytes (blob_name required - no filename to derive from)
name = engine.store_blob(raw_bytes, blob_name="scan.png")

# Returns the actual name it was stored under
print(name)  # "report.pdf"
```

`blob_name` is optional for file paths - it is derived automatically from the filename.

#### Collision handling (default: auto-increment)

If a blob with the same name already exists, the engine automatically increments the name rather than overwriting silently:

```python
engine.store_blob("report.pdf")   # → stored as "report.pdf"
engine.store_blob("report.pdf")   # → stored as "report_1.pdf"
engine.store_blob("report.pdf")   # → stored as "report_2.pdf"
```

The returned name always tells you exactly where it was stored. Save it into a chunk to track it:

```python
name = engine.store_blob("report.pdf")
engine.stage_update({"report": name}, chunk_name="attachments")
```

#### Explicit overwrite

```python
# Replace an existing blob intentionally
name = engine.store_blob("report.pdf", overwrite=True)
```

#### Failure cases

`store_blob()` returns `None` and fires `on_fault` if:
- Source file path does not exist
- `data` is bytes but no `blob_name` was provided
- `blob_name` is blank
- Disk write fails

### Reading a blob - `fetch_blob()`

```python
pdf_bytes = engine.fetch_blob("report.pdf")
if pdf_bytes is None:
    # File is missing - on_fault was already fired
    pass
```

Returns `None` and fires `on_fault` if the blob is missing or unreadable.

### Deleting a blob - `delete_blob()`

```python
success = engine.delete_blob("old_report.pdf")
```

Removes the `.blob` file from disk and its entry from `blob_manifest.json`. Returns `False` if the blob does not exist.

### Listing all blobs - `list_blobs()`

```python
for blob in engine.list_blobs():
    print(blob)
# {"blob_name": "report.pdf", "size_kb": 842.3, "saved_at": "2024-03-15 14:30"}
# {"blob_name": "avatar.jpg", "size_kb": 124.1, "saved_at": "2024-03-15 09:00"}
```

### What happens if a blob file is deleted?

On the next `open()`, the engine checks all blob hashes against `blob_manifest.json`. If any blob is missing or corrupt, `on_fault` fires:

```
"2 blob(s) are missing or corrupt: ['report.pdf', 'avatar.jpg'].
 These files need to be re-uploaded."
```

The engine boots normally - blobs are not recoverable from backups, but the user is told exactly which files need re-uploading.

---

## Checkpoints

Checkpoints are full project snapshots saved as ZIP files. They capture all chunk files, backups, and metadata at a point in time.

### Two checkpoint modes

| Mode | Contents | Speed | Use for |
|---|---|---|---|
| Chunks only (default) | Chunks + chunk backups + blob hashes | Fast | Auto-close, frequent saves |
| Full (`include_blobs=True`) | Everything above + all blob files | Slow (depends on blob sizes) | Before major changes, true full backup |

> **Blob hashes are always recorded in `checkpoint_meta.json`** regardless of mode. This means even a chunks-only checkpoint knows which blobs existed and what their content was - so a restore can warn about mismatches.

### Manual Checkpoints - `create_checkpoint()`

```python
# Fast - chunks only (default)
zip_name = engine.create_checkpoint(
    label="before_refactor",
    notes="Stable build",
)

# Full snapshot - includes all blobs
zip_name = engine.create_checkpoint(
    label="full_backup",
    notes="Before major migration",
    include_blobs=True,
)

print(zip_name)  # "cp_before_refactor_20240315_143022_001.zip"
```

- Up to **10 manual checkpoints** are kept; oldest is deleted when limit is exceeded
- Always force-syncs before creating the ZIP
- Returns the ZIP filename on success, `None` on failure

### Auto Checkpoints

Created automatically on `detach()` if chunk data changed since the last auto-checkpoint. Always chunks-only - never hangs on close regardless of blob sizes. Up to **5 auto-checkpoints** are kept.

### Listing Checkpoints - `list_checkpoints()`

```python
checkpoints = engine.list_checkpoints()
for cp in checkpoints:
    print(cp)
```

Each entry:

```python
{
    "filename": "cp_full_backup_20240315_143022_001.zip",
    "type": "manual",           # or "auto"
    "label": "full_backup",
    "date": "20240315_143022_001",
    "notes": "Before major migration",
    "verified": True,           # SHA256 passed
    "includes_blobs": True,     # whether blob files are in the ZIP
    "blob_count": 15,           # how many blobs were tracked at checkpoint time
    "warning": "",              # non-empty if verification failed
    "size_kb": 284300.4,
}
```

Results are sorted newest-first.

### Verifying a Checkpoint - `verify_checkpoint()`

```python
ok = engine.verify_checkpoint("cp_full_backup_20240315_143022_001.zip")
```

Returns `True` if SHA256 matches, `False` if the ZIP is missing or tampered.

### Restoring a Checkpoint - `restore_checkpoint()`

```python
success = engine.restore_checkpoint("cp_full_backup_20240315_143022_001.zip")
```

Verifies SHA256 first, then restores:

**If checkpoint includes blobs** (`includes_blobs: true`): chunks and blobs on disk are both fully replaced. Exact point-in-time restore.

**If checkpoint does not include blobs**: chunks are restored, blobs on disk are left untouched. The engine then compares current blob hashes against what was recorded at checkpoint time:

- **Missing blobs** → `on_fault` fires: `"2 blob(s) expected by this checkpoint are missing: ['report.pdf']. Re-upload them."`
- **Mismatched blobs** → status log: `"1 blob(s) on disk differ from checkpoint state: ['photo.jpg']."`
- **All match** → silent

```python
# Typical restore flow
checkpoints = engine.list_checkpoints()
for cp in checkpoints:
    if cp["verified"]:
        engine.restore_checkpoint(cp["filename"])
        break
```

---

## Rollback - Per-Chunk Undo

Every chunk keeps 3 copies on disk. You can roll back any individual chunk independently without affecting the rest of the project or any blobs.

### Step 1 - See what's available

```python
options = engine.get_rollback_options("inventory")
for opt in options:
    print(opt)
```

Returns a list of available copies:

```python
[
    {"label": "Current",       "file": "inventory.lcca",      "saved_at": "2024-03-15 14:30:22", ...},
    {"label": "Previous save", "file": "inventory.lcca.bak",  "saved_at": "2024-03-15 14:28:05", ...},
    {"label": "Earlier save",  "file": "inventory.lcca.ebak", "saved_at": "2024-03-15 14:25:11", ...},
]
```

### Step 2 - Roll back to a specific copy

```python
source = options[1]  # "Previous save"
success = engine.rollback_chunk("inventory", source_path=source["path"])
```

After rollback, `fetch_chunk("inventory")` immediately returns the rolled-back version. Only that chunk is affected.

> Blob rollback is not supported - blobs have no backup copies. Use a full checkpoint (`include_blobs=True`) if you need point-in-time blob recovery.

---

## Callbacks / Event Hooks

Assign Python callables to these attributes to receive engine events in your UI:

```python
engine.on_status = lambda msg: status_bar.setText(msg)
engine.on_sync   = lambda: save_indicator.hide()
engine.on_fault  = lambda msg: show_error_dialog(msg)
engine.on_dirty  = lambda dirty: save_indicator.setVisible(dirty)
```

| Callback | Signature | When it fires |
|---|---|---|
| `on_status` | `(message: str) → None` | Any log message - status updates, warnings, info |
| `on_sync` | `() → None` | After a successful flush of chunks to disk |
| `on_fault` | `(message: str) → None` | Any error - corrupt chunks, missing blobs, blob name conflicts, write failures |
| `on_dirty` | `(dirty: bool) → None` | When dirty state changes - `True` = unsaved changes, `False` = clean |

`on_fault` fires for both chunk and blob problems. The message always describes what happened and what to do. If `on_status` is not set, all log messages are printed to stdout.

---

## Project Discovery

### List all projects - `list_all_projects()`

```python
projects = SafeChunkEngine.list_all_projects(base_dir="user_projects")
```

Each entry:

```python
{
    "project_id": "my_project",
    "display_name": "My Project",
    "created_at": "2024-03-10 09:00",
    "last_modified": "2024-03-15 14:30",
    "status": "ok",   # "ok" | "locked" | "crashed" | "corrupted"
}
```

### Deep info on one project - `get_project_info()`

```python
info = SafeChunkEngine.get_project_info("my_project", base_dir="user_projects")
```

```python
{
    "project_id": "my_project",
    "display_name": "My Project",
    "status": "ok",
    "created_at": "2024-03-10 09:00",
    "last_modified": "2024-03-15 14:30",
    "app_version": "1.0.0",
    "engine_version": "3.0.0",
    "chunk_count": 4,
    "checkpoint_count": 3,
    "last_checkpoint_date": "2024-03-15 14:00",
    "clean_close": True,
    "readable": False,
    "size_kb": 128.4,
}
```

Returns `None` if the project folder does not exist.

---

## Project Management

### Rename - `rename()`

Updates the display name stored in `version.json`. Does not rename the folder on disk.

```python
engine.rename("My Awesome Project")
```

### Delete - `delete_project()`

Detaches the engine and permanently deletes the entire project folder including all chunks, blobs, and checkpoints.

```python
success = engine.delete_project(confirmed=True)  # confirmed=True required
```

> ⚠️ **This is irreversible.** All chunks, blobs, backups, and checkpoints are deleted.

### Check active state - `is_active()`

```python
if engine.is_active():
    engine.stage_update(data, "chunk")
```

Returns `True` if the engine successfully attached. Any method decorated with `@requires_active` silently returns `None` and logs a warning if called on an inactive engine.

---

## Diagnostics

### Health report - `get_health_report()`

```python
report = engine.get_health_report()
```

```python
{
    "active": True,
    "project_id": "my_project",
    "display_name": "My Project",
    "version": "3.0.0",
    "app_version": "1.0.0",
    "readable_mode": False,
    "chunk_count": 4,
    "checkpoint_count": 3,
    "pending_syncs": 1,      # chunks staged but not yet flushed
    "wal_exists": False,     # True if WAL has uncommitted entries
    "session_dirty": True,   # True if anything was written this session
}
```

### Log history

```python
for line in engine.log_history:
    print(line)
# [14:30:22] Engine v3.0.0 attached to 'My Project' (my_project).
# [14:30:25] Blob stored: 'report.pdf' (842.3 KB).
# [14:30:28] Commit successful.
```

Up to 100 log entries are kept in memory at any time.

---

## Readable Mode (Dev/Debug)

By default, chunks are saved in binary LCCA format (MAGIC header + zlib-compressed JSON). This is smaller and not human-readable.

For debugging, enable readable mode when creating a project:

```python
engine, _ = SafeChunkEngine.new(
    project_id="debug_project",
    readable=True,  # Saves plain JSON - open with any text editor
)
```

> **Important:** `readable` mode is locked permanently for a project at creation time. You cannot switch an existing binary project to readable or vice versa. Blobs are always stored as raw binary regardless of this setting.

---

## File Structure on Disk

```
user_projects/
└── my_project/
    ├── chunks/
    │   ├── user_profile.lcca       ← current chunk (binary or JSON)
    │   ├── inventory.lcca
    │   └── position.lcca
    ├── chunks_bak/
    │   ├── user_profile.lcca.bak   ← previous save
    │   ├── user_profile.lcca.ebak  ← one before that
    │   ├── inventory.lcca.bak
    │   └── inventory.lcca.ebak
    ├── blobs/
    │   ├── report.pdf.blob         ← binary file, single copy
    │   ├── report_1.pdf.blob       ← second upload auto-incremented
    │   └── avatar.jpg.blob
    ├── checkpoints/
    │   ├── manual/
    │   │   ├── cp_full_backup_20240315_143022_001.zip      ← includes blobs
    │   │   ├── cp_full_backup_20240315_143022_001.zip.sha256
    │   │   ├── cp_before_refactor_20240315_140000_000.zip  ← chunks only
    │   │   └── cp_before_refactor_20240315_140000_000.zip.sha256
    │   └── auto/
    │       ├── cp_auto_close_20240315_150000_000.zip       ← always chunks only
    │       └── cp_auto_close_20240315_150000_000.zip.sha256
    ├── manifest.json               ← SHA256 hashes of all chunks
    ├── blob_manifest.json          ← SHA256 hashes + metadata of all blobs
    ├── version.json                ← project metadata + clean_close flag
    ├── project_meta.json           ← author / editor history
    └── .lock                       ← PID lock (deleted on clean close)
```

`wal.log` appears here only during an active session or after a crash. It is deleted on clean close.

---

## Error Handling

The engine never raises exceptions to the caller. All errors are routed through `on_fault` (or printed to stdout if not set) and stored in `engine.log_history`.

Always check the status string from factory methods:

```python
engine, status = SafeChunkEngine.open("my_project")
if status != "SUCCESS":
    print(f"Could not open project: {status}")
    engine = None
```

Wire up `on_fault` to surface errors in your UI - it covers both chunk and blob problems:

```python
engine.on_fault = lambda msg: show_error_dialog(f"Storage error: {msg}")
```

For operations on an inactive engine, all `@requires_active` methods return `None` silently:

```python
if engine and engine.is_active():
    engine.stage_update(data, "chunk")
```

---

## Full API Reference

### Factory Methods

| Method | Returns | Description |
|---|---|---|
| `SafeChunkEngine.new(project_id, display_name, base_dir, readable, **kwargs)` | `(engine, status)` | Create a new project |
| `SafeChunkEngine.open(project_id, base_dir, readable, **kwargs)` | `(engine, status)` | Open an existing project |

### Lifecycle

| Method | Returns | Description |
|---|---|---|
| `attach()` | `None` | Activate engine - called automatically by `__init__` |
| `detach()` | `None` | Safe close - flush, checkpoint, clear WAL, release lock |
| `is_active()` | `bool` | Whether engine is active and usable |
| `is_dirty()` | `bool` | Whether there are unsaved staged chunk changes in memory |

### Core Data (Chunks)

| Method | Returns | Description |
|---|---|---|
| `stage_update(data, chunk_name)` | `None` | Buffer dict + WAL write + trigger auto-save |
| `fetch_chunk(chunk_name)` | `dict` | Read chunk (memory → disk → backup fallback) |
| `read_chunk(chunk_name)` | `dict` | Alias for `fetch_chunk` |
| `force_sync()` | `None` | Immediately flush all staged chunks to disk |

### Blob Storage (Binary Files)

| Method | Returns | Description |
|---|---|---|
| `store_blob(data, blob_name, overwrite)` | `str \| None` | Store binary file; auto-derives name from path; auto-increments on collision |
| `fetch_blob(blob_name)` | `bytes \| None` | Read blob bytes from disk |
| `delete_blob(blob_name)` | `bool` | Delete blob file and remove from manifest |
| `list_blobs()` | `list[dict]` | All blobs with name, size_kb, saved_at |

### Checkpoints

| Method | Returns | Description |
|---|---|---|
| `create_checkpoint(label, notes, include_blobs)` | `str \| None` | Create manual checkpoint; `include_blobs=False` default (chunks only); keep last 10 |
| `verify_checkpoint(zip_name)` | `bool` | Verify checkpoint SHA256 |
| `restore_checkpoint(zip_name)` | `bool` | Restore project; warns on blob mismatches when blobs not included |
| `list_checkpoints()` | `list[dict]` | All checkpoints with metadata, sorted newest-first |

### Rollback (Chunks only)

| Method | Returns | Description |
|---|---|---|
| `get_rollback_options(chunk_name)` | `list[dict]` | Available file copies (current / previous / earlier) with timestamps |
| `rollback_chunk(chunk_name, source_path)` | `bool` | Restore chunk from a specific copy |

### Project Management

| Method | Returns | Description |
|---|---|---|
| `rename(new_display_name)` | `bool` | Update display name in version.json |
| `delete_project(confirmed=False)` | `bool` | Permanently delete entire project folder |

### Discovery & Diagnostics

| Method | Returns | Description |
|---|---|---|
| `list_all_projects(base_dir)` | `list[dict]` | Lightweight scan of all projects (static) |
| `get_project_info(project_id, base_dir)` | `dict \| None` | Deep info on one project (static) |
| `get_health_report()` | `dict` | Engine state, counts, WAL status |

---

## Constants Reference

| Constant | Default | Description |
|---|---|---|
| `ENGINE_VER` | `"3.0.0"` | Engine version string |
| `MANUAL_CHECKPOINT_RETENTION` | `10` | Max manual checkpoints kept per project |
| `AUTO_CHECKPOINT_RETENTION` | `5` | Max auto checkpoints kept per project |
| `MIN_ROTATE_AGE` | `0.0` | Min seconds between backup rotations (0 = always rotate) |
| `LCCA_EXT` | `".lcca"` | Extension for current chunk files |
| `BAK_EXT` | `".lcca.bak"` | Extension for previous chunk save |
| `EBAK_EXT` | `".lcca.ebak"` | Extension for earlier chunk save |
| `BLOB_EXT` | `".blob"` | Extension for blob files |
| `MAGIC` | `b"\x4c\x43\x43\x41"` | Binary file header (`LCCA` in ASCII) |