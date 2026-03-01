"""
utils/wpi_manager.py

WPIProfile dataclass and WPIManager for loading, verifying,
and managing WPI adjustment ratio profiles.

Integrity states:
    OK          - hash verified
    MISMATCH    - data tampered, entry unlisted
    MISSING     - no hash stored, entry unlisted
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional
from .wpi_hash import compute_hash, verify_hash


# ── Integrity State ───────────────────────────────────────────────────────────


class IntegrityState(Enum):
    OK = auto()        # hash verified
    MISMATCH = auto()  # data tampered → unlist
    MISSING = auto()   # no hash stored → unlist


# ── WPI Data structure keys ───────────────────────────────────────────────────

VEHICLES = [
    "small_cars",
    "big_cars",
    "two_wheelers",
    "o_buses",
    "d_buses",
    "lcv",
    "hcv",
    "mcv",
]

VEHICLE_COST_KEYS = [
    "propertyDamage",
    "tyreCost",
    "spareParts",
    "fixedDepreciation",
]

FUEL_KEYS = ["petrol", "diesel", "engine_oil", "other_oil", "grease"]
MEDICAL_KEYS = ["fatal", "major", "minor"]
PASSENGER_CREW_KEYS = ["passenger", "crew"]


def empty_data() -> dict:
    """Return a zeroed WPI data block with correct structure."""
    return {
        "fuelCost": {k: 1.0 for k in FUEL_KEYS},
        "vehicleCost": {
            sub: {v: 1.0 for v in VEHICLES}
            for sub in VEHICLE_COST_KEYS
        },
        "commodityHoldingCost": {v: 1.0 for v in VEHICLES},
        "passengerCrewCost": {k: 1.0 for k in PASSENGER_CREW_KEYS},
        "medicalCost": {k: 1.0 for k in MEDICAL_KEYS},
        "votCost": {v: 1.0 for v in VEHICLES},
    }


# ── WPIProfile ────────────────────────────────────────────────────────────────


@dataclass
class WPIProfile:
    id: str
    name: str
    year: int
    is_custom: bool
    remark: str
    hash: str
    data: dict
    integrity: IntegrityState = field(default=IntegrityState.MISSING, init=False)

    def __post_init__(self):
        self._check_integrity()

    def _check_integrity(self):
        if not self.hash:
            self.integrity = IntegrityState.MISSING
        elif verify_hash(self.data, self.hash):
            self.integrity = IntegrityState.OK
        else:
            self.integrity = IntegrityState.MISMATCH

    def is_listed(self) -> bool:
        """DB entries must pass integrity. Custom entries always listed."""
        if self.is_custom:
            return True
        return self.integrity == IntegrityState.OK

    def to_dict(self) -> dict:
        """Serialize back to JSON-compatible dict."""
        return {
            "metadata": {
                "id": self.id,
                "name": self.name,
                "year": self.year,
                "is_custom": self.is_custom,
                "remark": self.remark,
                "hash": self.hash,
            },
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WPIProfile":
        m = d["metadata"]
        return cls(
            id=m["id"],
            name=m["name"],
            year=m.get("year", 0),
            is_custom=m.get("is_custom", True),
            remark=m.get("remark", ""),
            hash=m.get("hash", ""),
            data=d["data"],
        )

    def make_custom_copy(self, new_name: str) -> "WPIProfile":
        """Clone this profile as a new custom entry with a fresh id."""
        copy = WPIProfile(
            id=f"wpi_custom_{uuid.uuid4().hex[:8]}",
            name=new_name,
            year=self.year,
            is_custom=True,
            remark=f"Derived from '{self.name}'",
            hash="",
            data=json.loads(json.dumps(self.data)),  # deep copy
        )
        copy.stamp_hash()
        return copy

    def stamp_hash(self):
        """Compute and store hash from current data (for custom profiles)."""
        self.hash = compute_hash(self.data)
        self.integrity = IntegrityState.OK


# ── WPIManager ────────────────────────────────────────────────────────────────


class WPIManager:
    """
    Manages DB and custom WPI profiles.

    DB profiles are loaded from wpi_db.json (read-only, hash-verified).
    Custom profiles are stored per-project (passed in as a list of dicts).
    """

    def __init__(self, db_path: Path):
        self._db_profiles: list[WPIProfile] = []
        self._custom_profiles: list[WPIProfile] = []
        self._unlisted: list[WPIProfile] = []  # failed integrity
        self._load_db(db_path)

    # ── DB loading ────────────────────────────────────────────────────────────

    def _load_db(self, db_path: Path):
        if not db_path.exists():
            raise FileNotFoundError(f"WPI DB not found: {db_path}")

        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)

        for entry in db.get("entries", []):
            profile = WPIProfile.from_dict(entry)
            if profile.is_listed():
                self._db_profiles.append(profile)
            else:
                self._unlisted.append(profile)

    # ── Custom profile management ─────────────────────────────────────────────

    def load_custom_profiles(self, raw: list[dict]):
        """Load custom profiles from project data."""
        self._custom_profiles.clear()
        for entry in raw:
            profile = WPIProfile.from_dict(entry)
            self._custom_profiles.append(profile)

    def dump_custom_profiles(self) -> list[dict]:
        """Serialize custom profiles for saving into project."""
        return [p.to_dict() for p in self._custom_profiles]

    def add_custom(self, profile: WPIProfile):
        self._custom_profiles.append(profile)

    def delete_custom(self, profile_id: str):
        self._custom_profiles = [
            p for p in self._custom_profiles if p.id != profile_id
        ]

    def save_custom(self, profile: WPIProfile):
        """Update existing custom profile in place."""
        profile.stamp_hash()
        for i, p in enumerate(self._custom_profiles):
            if p.id == profile.id:
                self._custom_profiles[i] = profile
                return
        # Not found — add as new
        self._custom_profiles.append(profile)

    # ── Queries ───────────────────────────────────────────────────────────────

    def all_listed(self) -> list[WPIProfile]:
        """All profiles available for selection (DB + custom)."""
        return self._db_profiles + self._custom_profiles

    def get_by_id(self, profile_id: str) -> Optional[WPIProfile]:
        for p in self.all_listed():
            if p.id == profile_id:
                return p
        return None

    def is_name_taken(self, name: str, exclude_id: str = "") -> bool:
        for p in self.all_listed():
            if p.id == exclude_id:
                continue
            if p.name.strip().lower() == name.strip().lower():
                return True
        return False

    def suggest_custom_name(self, base_name: str) -> str:
        """Suggest a unique name like '2024-user', '2024-user-2', etc."""
        candidate = f"{base_name}-user"
        if not self.is_name_taken(candidate):
            return candidate
        i = 2
        while self.is_name_taken(f"{candidate}-{i}"):
            i += 1
        return f"{candidate}-{i}"

    @property
    def unlisted(self) -> list[WPIProfile]:
        """Profiles that failed integrity check (for logging/warning)."""
        return self._unlisted