#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime
import os
from typing import List, Optional
import logging

DEFAULT_DB_PATH = "/home/Bot/Desktop/techmac_calibration.db"
FALLBACK_DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/techmac_calibration.db")

class CalibrationDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = DEFAULT_DB_PATH

            # Try to ensure the parent directory exists
            try:
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                open(db_path, 'a').close()
            except Exception:
                print(f"WARNING! Falling back to local DB path: {FALLBACK_DB_PATH}")
                db_path = os.path.abspath(FALLBACK_DB_PATH)
                os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create chamber_offsets table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chamber_offsets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chamber_id INTEGER NOT NULL,
                    offset_value REAL NOT NULL,
                    offset_date TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0
                )
            ''')
            
            conn.commit()

    def save_chamber_offset(self, chamber_id: int, offset: float) -> bool:
        """
        Save an offset value for a chamber.
        
        Args:
            chamber_id: Chamber ID (0-2)
            offset: Offset value in mbar
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # First deactivate any existing offsets for this chamber
                cursor.execute(
                    "UPDATE chamber_offsets SET is_active = 0 WHERE chamber_id = ? AND is_active = 1",
                    (chamber_id,)
                )
                
                # Insert the new offset
                cursor.execute(
                    """
                    INSERT INTO chamber_offsets (chamber_id, offset_value, offset_date, is_active)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        chamber_id,
                        offset,
                        datetime.now().isoformat(),
                        1
                    )
                )
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"Error saving chamber offset: {e}")
            return False

    def get_active_chamber_offset(self, chamber_id: int) -> Optional[float]:
        """
        Get the active offset for a chamber.
        
        Args:
            chamber_id: Chamber ID (0-2)
            
        Returns:
            Offset value if available, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    """
                    SELECT offset_value
                    FROM chamber_offsets
                    WHERE chamber_id = ? AND is_active = 1
                    """,
                    (chamber_id,)
                )
                
                row = cursor.fetchone()
                
                if row:
                    return row[0]
                    
                return None
                
        except Exception as e:
            print(f"Error getting active chamber offset: {e}")
            return None

    def get_chamber_offset_history(self, chamber_id: int, limit: int = 10) -> List[dict]:
        """
        Get offset history for a chamber.
        
        Args:
            chamber_id: Chamber ID (0-2)
            limit: Maximum number of records to return
            
        Returns:
            List of offset dictionaries
        """
        offsets = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    """
                    SELECT offset_value, offset_date, is_active
                    FROM chamber_offsets
                    WHERE chamber_id = ?
                    ORDER BY offset_date DESC
                    LIMIT ?
                    """,
                    (chamber_id, limit)
                )
                
                rows = cursor.fetchall()
                
                for row in rows:
                    offset_info = {
                        'offset': row[0],
                        'date': datetime.fromisoformat(row[1]),
                        'is_active': bool(row[2])
                    }
                    offsets.append(offset_info)
                    
                return offsets
                
        except Exception as e:
            print(f"Error getting chamber offset history: {e}")
            return []