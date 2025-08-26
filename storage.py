#!/usr/bin/env python3
import csv
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List


def iso_now() -> str:
    """Generate ISO timestamp for current UTC time"""
    return datetime.now(timezone.utc).isoformat()


class StorageBackend(ABC):
    """Abstract base class for storage backends"""
    
    @abstractmethod
    def read_artists_ledger(self) -> Dict[str, Dict]:
        """Read artists ledger into a dict keyed by MBID"""
        pass
    
    @abstractmethod
    def write_artists_ledger(self, ledger: Dict[str, Dict]) -> None:
        """Write artists ledger from dict"""
        pass
    
    @abstractmethod
    def read_release_groups_ledger(self) -> Dict[str, Dict]:
        """Read release groups ledger into a dict keyed by RG MBID"""
        pass
    
    @abstractmethod
    def write_release_groups_ledger(self, ledger: Dict[str, Dict]) -> None:
        """Write release groups ledger from dict"""
        pass
    
    @abstractmethod
    def exists(self) -> bool:
        """Check if storage exists (for first-run detection)"""
        pass


class CSVStorage(StorageBackend):
    """CSV file storage backend (original implementation)"""
    
    def __init__(self, artists_csv_path: str, release_groups_csv_path: str):
        self.artists_csv_path = artists_csv_path
        self.release_groups_csv_path = release_groups_csv_path
    
    def read_artists_ledger(self) -> Dict[str, Dict]:
        """Read existing artists CSV into a dict keyed by MBID."""
        ledger: Dict[str, Dict] = {}
        if not os.path.exists(self.artists_csv_path):
            return ledger
        
        with open(self.artists_csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mbid = (row.get("mbid") or "").strip()
                if not mbid:
                    continue
                ledger[mbid] = {
                    "mbid": mbid,
                    "artist_name": row.get("artist_name", ""),
                    "status": (row.get("status") or "").lower().strip(),
                    "attempts": int((row.get("attempts") or "0") or 0),
                    "last_status_code": row.get("last_status_code", ""),
                    "last_checked": row.get("last_checked", ""),
                    # Text search fields (with backwards compatibility)
                    "text_search_attempted": row.get("text_search_attempted", "").lower() in ("true", "1"),
                    "text_search_success": row.get("text_search_success", "").lower() in ("true", "1"),
                    "text_search_last_checked": row.get("text_search_last_checked", ""),
                }
        return ledger

    def write_artists_ledger(self, ledger: Dict[str, Dict]) -> None:
        """Write the artists ledger dict back to CSV atomically."""
        os.makedirs(os.path.dirname(self.artists_csv_path) or ".", exist_ok=True)
        fieldnames = ["mbid", "artist_name", "status", "attempts", "last_status_code", "last_checked",
                      "text_search_attempted", "text_search_success", "text_search_last_checked"]
        tmp_path = self.artists_csv_path + ".tmp"
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for _, row in sorted(ledger.items(), key=lambda kv: (kv[1].get("artist_name", ""), kv[0])):
                writer.writerow(row)
        os.replace(tmp_path, self.artists_csv_path)

    def read_release_groups_ledger(self) -> Dict[str, Dict]:
        """Read existing release groups CSV into a dict keyed by RG MBID."""
        ledger: Dict[str, Dict] = {}
        if not os.path.exists(self.release_groups_csv_path):
            return ledger
        
        with open(self.release_groups_csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rg_mbid = (row.get("rg_mbid") or "").strip()
                if not rg_mbid:
                    continue
                ledger[rg_mbid] = {
                    "rg_mbid": rg_mbid,
                    "rg_title": row.get("rg_title", ""),
                    "artist_mbid": row.get("artist_mbid", ""),
                    "artist_name": row.get("artist_name", ""),
                    "artist_cache_status": row.get("artist_cache_status", ""),
                    "status": (row.get("status") or "").lower().strip(),
                    "attempts": int((row.get("attempts") or "0") or 0),
                    "last_status_code": row.get("last_status_code", ""),
                    "last_checked": row.get("last_checked", ""),
                }
        return ledger

    def write_release_groups_ledger(self, ledger: Dict[str, Dict]) -> None:
        """Write the release groups ledger dict back to CSV atomically."""
        os.makedirs(os.path.dirname(self.release_groups_csv_path) or ".", exist_ok=True)
        fieldnames = ["rg_mbid", "rg_title", "artist_mbid", "artist_name", "artist_cache_status", 
                      "status", "attempts", "last_status_code", "last_checked"]
        tmp_path = self.release_groups_csv_path + ".tmp"
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for _, row in sorted(ledger.items(), key=lambda kv: (kv[1].get("artist_name", ""), kv[1].get("rg_title", ""), kv[0])):
                writer.writerow(row)
        os.replace(tmp_path, self.release_groups_csv_path)

    def exists(self) -> bool:
        """Check if CSV files exist"""
        return os.path.exists(self.artists_csv_path)


class SQLiteStorage(StorageBackend):
    """SQLite database storage backend"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database with tables and handle migrations"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            # Create tables with basic structure first
            conn.execute("""
                CREATE TABLE IF NOT EXISTS artists (
                    mbid TEXT PRIMARY KEY,
                    artist_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_status_code TEXT NOT NULL DEFAULT '',
                    last_checked TEXT NOT NULL DEFAULT ''
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS release_groups (
                    rg_mbid TEXT PRIMARY KEY,
                    rg_title TEXT NOT NULL,
                    artist_mbid TEXT NOT NULL,
                    artist_name TEXT NOT NULL,
                    artist_cache_status TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_status_code TEXT NOT NULL DEFAULT '',
                    last_checked TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (artist_mbid) REFERENCES artists (mbid)
                )
            """)
            
            # Add text search columns if they don't exist (migration)
            try:
                conn.execute("ALTER TABLE artists ADD COLUMN text_search_attempted INTEGER NOT NULL DEFAULT 0")
                print("Added text_search_attempted column to artists table")
            except sqlite3.OperationalError:
                # Column already exists, which is fine
                pass
            
            try:
                conn.execute("ALTER TABLE artists ADD COLUMN text_search_success INTEGER NOT NULL DEFAULT 0")
                print("Added text_search_success column to artists table")
            except sqlite3.OperationalError:
                # Column already exists, which is fine
                pass
            
            try:
                conn.execute("ALTER TABLE artists ADD COLUMN text_search_last_checked TEXT NOT NULL DEFAULT ''")
                print("Added text_search_last_checked column to artists table")
            except sqlite3.OperationalError:
                # Column already exists, which is fine
                pass
            
            # Create indexes for performance (only after columns exist)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_artists_status ON artists (status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_artists_text_search ON artists (text_search_attempted, text_search_success)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rg_status ON release_groups (status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rg_artist_status ON release_groups (artist_cache_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rg_artist_mbid ON release_groups (artist_mbid)")
            
            conn.commit()

    def read_artists_ledger(self) -> Dict[str, Dict]:
        """Read artists from SQLite into a dict keyed by MBID."""
        ledger: Dict[str, Dict] = {}
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT mbid, artist_name, status, attempts, last_status_code, last_checked,
                       text_search_attempted, text_search_success, text_search_last_checked
                FROM artists
                ORDER BY artist_name, mbid
            """)
            
            for row in cursor:
                ledger[row["mbid"]] = {
                    "mbid": row["mbid"],
                    "artist_name": row["artist_name"],
                    "status": row["status"].lower().strip(),
                    "attempts": row["attempts"],
                    "last_status_code": row["last_status_code"],
                    "last_checked": row["last_checked"],
                    "text_search_attempted": bool(row["text_search_attempted"]),
                    "text_search_success": bool(row["text_search_success"]),
                    "text_search_last_checked": row["text_search_last_checked"],
                }
        
        return ledger

    def write_artists_ledger(self, ledger: Dict[str, Dict]) -> None:
        """Write artists ledger to SQLite with upsert logic."""
        with sqlite3.connect(self.db_path) as conn:
            for mbid, data in ledger.items():
                conn.execute("""
                    INSERT OR REPLACE INTO artists 
                    (mbid, artist_name, status, attempts, last_status_code, last_checked,
                     text_search_attempted, text_search_success, text_search_last_checked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["mbid"],
                    data["artist_name"],
                    data["status"],
                    data["attempts"],
                    data["last_status_code"],
                    data["last_checked"],
                    int(data.get("text_search_attempted", False)),
                    int(data.get("text_search_success", False)),
                    data.get("text_search_last_checked", "")
                ))
            conn.commit()

    def read_release_groups_ledger(self) -> Dict[str, Dict]:
        """Read release groups from SQLite into a dict keyed by RG MBID."""
        ledger: Dict[str, Dict] = {}
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT rg_mbid, rg_title, artist_mbid, artist_name, artist_cache_status,
                       status, attempts, last_status_code, last_checked
                FROM release_groups
                ORDER BY artist_name, rg_title, rg_mbid
            """)
            
            for row in cursor:
                ledger[row["rg_mbid"]] = {
                    "rg_mbid": row["rg_mbid"],
                    "rg_title": row["rg_title"],
                    "artist_mbid": row["artist_mbid"],
                    "artist_name": row["artist_name"],
                    "artist_cache_status": row["artist_cache_status"],
                    "status": row["status"].lower().strip(),
                    "attempts": row["attempts"],
                    "last_status_code": row["last_status_code"],
                    "last_checked": row["last_checked"],
                }
        
        return ledger

    def write_release_groups_ledger(self, ledger: Dict[str, Dict]) -> None:
        """Write release groups ledger to SQLite with upsert logic."""
        with sqlite3.connect(self.db_path) as conn:
            for rg_mbid, data in ledger.items():
                conn.execute("""
                    INSERT OR REPLACE INTO release_groups 
                    (rg_mbid, rg_title, artist_mbid, artist_name, artist_cache_status,
                     status, attempts, last_status_code, last_checked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["rg_mbid"],
                    data["rg_title"],
                    data["artist_mbid"],
                    data["artist_name"],
                    data["artist_cache_status"],
                    data["status"],
                    data["attempts"],
                    data["last_status_code"],
                    data["last_checked"]
                ))
            conn.commit()

    def exists(self) -> bool:
        """Check if SQLite database exists and has data"""
        if not os.path.exists(self.db_path):
            return False
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM artists")
                return cursor.fetchone()[0] > 0
        except sqlite3.Error:
            return False

    def update_release_groups_artist_status(self, artists_ledger: Dict[str, Dict]) -> None:
        """Efficiently update artist_cache_status in release groups based on current artist statuses"""
        with sqlite3.connect(self.db_path) as conn:
            for artist_mbid, artist_data in artists_ledger.items():
                conn.execute("""
                    UPDATE release_groups 
                    SET artist_cache_status = ?
                    WHERE artist_mbid = ?
                """, (artist_data.get("status", ""), artist_mbid))
            conn.commit()


def create_storage_backend(cfg: dict) -> StorageBackend:
    """Factory function to create appropriate storage backend based on config"""
    storage_type = cfg.get("storage_type", "csv").lower()
    
    if storage_type == "sqlite":
        return SQLiteStorage(cfg.get("db_path", "/data/mbid_cache.db"))
    elif storage_type == "csv":
        return CSVStorage(
            cfg.get("artists_csv_path", "/data/mbid-artists.csv"),
            cfg.get("release_groups_csv_path", "/data/mbid-releasegroups.csv")
        )
    else:
        raise ValueError(f"Unknown storage type: {storage_type}. Use 'csv' or 'sqlite'.")
