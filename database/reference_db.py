#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reference Database module for the Multi-Chamber Test application.

This module provides a ReferenceDatabase class for managing test references
stored in a SQLite database, supporting operations like adding, updating,
loading, and deleting references identified by barcodes.
"""


import os
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union

from multi_chamber_test.config.constants import PRESSURE_DEFAULTS, TIME_DEFAULTS

DEFAULT_DB_PATH = "/home/Bot/Desktop/techmac_reference.db"
FALLBACK_DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/techmac_reference.db")


class ReferenceDatabase:
    """
    Manager for test reference profiles stored in SQLite.
    
    This class provides methods to store, retrieve, and manage test reference profiles
    in a SQLite database. Each reference is identified by a unique barcode and contains
    test parameters for all chambers.
    """
    
    def __init__(self, db_path: Optional[str] = None):
            self.logger = logging.getLogger('ReferenceDatabase')
            self._setup_logger()
    
            if db_path is None:
                db_path = DEFAULT_DB_PATH
                try:
                    os.makedirs(os.path.dirname(db_path), exist_ok=True)
                    open(db_path, 'a').close()
                except Exception as e:
                    self.logger.warning(f"Fallback triggered for DB path due to: {e}")
                    db_path = os.path.abspath(FALLBACK_DB_PATH)
                    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
            self.db_path = db_path
            self._init_database()
    
    
    def _setup_logger(self):
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
    
            if not self.logger.handlers:
                self.logger.addHandler(handler)
    
            self.logger.setLevel(logging.INFO)
    
    def _ensure_dir_exists(self):
        """Ensure the directory for the database file exists."""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        except Exception as e:
            self.logger.error(f"Error creating database directory: {e}")
            raise
    
    def _init_database(self):
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
    
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS ref_table (
                            barcode TEXT PRIMARY KEY,
                            ch1_pressure_target REAL DEFAULT 150.0,
                            ch1_pressure_threshold REAL DEFAULT 5.0,
                            ch1_pressure_tolerance REAL DEFAULT 2.0,
                            ch1_enabled INTEGER DEFAULT 1,
                            ch2_pressure_target REAL DEFAULT 150.0,
                            ch2_pressure_threshold REAL DEFAULT 5.0,
                            ch2_pressure_tolerance REAL DEFAULT 2.0,
                            ch2_enabled INTEGER DEFAULT 1,
                            ch3_pressure_target REAL DEFAULT 150.0,
                            ch3_pressure_threshold REAL DEFAULT 5.0,
                            ch3_pressure_tolerance REAL DEFAULT 2.0,
                            ch3_enabled INTEGER DEFAULT 1,
                            test_duration INTEGER DEFAULT 90,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    self.logger.info("Reference database initialized successfully")
            except sqlite3.Error as e:
                self.logger.error(f"SQLite error initializing database: {e}")
                raise
            except Exception as e:
                self.logger.error(f"General error initializing database: {e}")
                raise
    
    def save_reference(self, barcode: str, chamber_settings: List[Dict[str, Any]], 
                      test_duration: int = TIME_DEFAULTS['TEST_DURATION']) -> bool:
        """
        Save a reference profile to the database.
        
        Args:
            barcode: Reference barcode identifier
            chamber_settings: List of dictionaries containing settings for each chamber (1-3)
                             Each dict should have keys: 'pressure_target', 'pressure_threshold',
                             'pressure_tolerance', 'enabled'
            test_duration: Test duration in seconds
            
        Returns:
            bool: True if reference was saved successfully, False otherwise
        """
        if not barcode:
            self.logger.error("Cannot save reference: Empty barcode")
            return False
            
        if len(chamber_settings) != 3:
            self.logger.error(f"Expected 3 chamber settings, got {len(chamber_settings)}")
            return False
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO ref_table
                    (barcode, 
                     ch1_pressure_target, ch1_pressure_threshold, ch1_pressure_tolerance, ch1_enabled,
                     ch2_pressure_target, ch2_pressure_threshold, ch2_pressure_tolerance, ch2_enabled,
                     ch3_pressure_target, ch3_pressure_threshold, ch3_pressure_tolerance, ch3_enabled,
                     test_duration, created_at, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                           COALESCE((SELECT created_at FROM ref_table WHERE barcode = ?), datetime('now')), 
                           datetime('now'))
                ''', (
                    barcode,
                    # Chamber 1 parameters
                    chamber_settings[0]['pressure_target'],
                    chamber_settings[0]['pressure_threshold'],
                    chamber_settings[0]['pressure_tolerance'],
                    1 if chamber_settings[0]['enabled'] else 0,
                    # Chamber 2 parameters
                    chamber_settings[1]['pressure_target'],
                    chamber_settings[1]['pressure_threshold'],
                    chamber_settings[1]['pressure_tolerance'],
                    1 if chamber_settings[1]['enabled'] else 0,
                    # Chamber 3 parameters
                    chamber_settings[2]['pressure_target'],
                    chamber_settings[2]['pressure_threshold'],
                    chamber_settings[2]['pressure_tolerance'],
                    1 if chamber_settings[2]['enabled'] else 0,
                    # Test duration
                    test_duration,
                    # For preserving original created_at timestamp on update
                    barcode
                ))
                
                conn.commit()
                self.logger.info(f"Reference '{barcode}' saved successfully")
                return True
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error saving reference: {e}")
            return False
        except Exception as e:
            self.logger.error(f"General error saving reference: {e}")
            return False
    
    def load_reference(self, barcode: str) -> Optional[Dict[str, Any]]:
        """
        Load a reference profile from the database.
        
        Args:
            barcode: Reference barcode identifier
            
        Returns:
            Dict containing reference settings or None if not found
        """
        if not barcode:
            self.logger.error("Cannot load reference: Empty barcode")
            return None
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT ch1_pressure_target, ch1_pressure_threshold, ch1_pressure_tolerance, ch1_enabled,
                           ch2_pressure_target, ch2_pressure_threshold, ch2_pressure_tolerance, ch2_enabled,
                           ch3_pressure_target, ch3_pressure_threshold, ch3_pressure_tolerance, ch3_enabled,
                           test_duration
                    FROM ref_table
                    WHERE barcode = ?
                ''', (barcode,))
                
                result = cursor.fetchone()
                if result:
                    # Update last used timestamp
                    cursor.execute('''
                        UPDATE ref_table
                        SET last_used = datetime('now')
                        WHERE barcode = ?
                    ''', (barcode,))
                    conn.commit()
                    
                    # Format the result as a dictionary
                    reference_data = {
                        'barcode': barcode,
                        'test_duration': result[12],
                        'chambers': [
                            {
                                'pressure_target': result[0],
                                'pressure_threshold': result[1],
                                'pressure_tolerance': result[2],
                                'enabled': bool(result[3])
                            },
                            {
                                'pressure_target': result[4],
                                'pressure_threshold': result[5],
                                'pressure_tolerance': result[6],
                                'enabled': bool(result[7])
                            },
                            {
                                'pressure_target': result[8],
                                'pressure_threshold': result[9],
                                'pressure_tolerance': result[10],
                                'enabled': bool(result[11])
                            }
                        ]
                    }
                    
                    self.logger.info(f"Reference '{barcode}' loaded successfully")
                    return reference_data
                else:
                    self.logger.warning(f"Reference '{barcode}' not found")
                    return None
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error loading reference: {e}")
            return None
        except Exception as e:
            self.logger.error(f"General error loading reference: {e}")
            return None
    
    def delete_reference(self, barcode: str) -> bool:
        """
        Delete a reference profile from the database.
        
        Args:
            barcode: Reference barcode identifier
            
        Returns:
            bool: True if reference was deleted successfully, False otherwise
        """
        if not barcode:
            self.logger.error("Cannot delete reference: Empty barcode")
            return False
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM ref_table WHERE barcode = ?', (barcode,))
                conn.commit()
                
                if cursor.rowcount > 0:
                    self.logger.info(f"Reference '{barcode}' deleted successfully")
                    return True
                else:
                    self.logger.warning(f"Reference '{barcode}' not found for deletion")
                    return False
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error deleting reference: {e}")
            return False
        except Exception as e:
            self.logger.error(f"General error deleting reference: {e}")
            return False
    
    def get_all_references(self) -> List[Dict[str, Any]]:
        """
        Get all reference profiles from the database.
        
        Returns:
            List of dictionaries containing reference data
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Enable dictionary access for rows
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT barcode,
                           ch1_pressure_target, ch1_pressure_threshold, ch1_pressure_tolerance, ch1_enabled,
                           ch2_pressure_target, ch2_pressure_threshold, ch2_pressure_tolerance, ch2_enabled,
                           ch3_pressure_target, ch3_pressure_threshold, ch3_pressure_tolerance, ch3_enabled,
                           test_duration, created_at, last_used
                    FROM ref_table
                    ORDER BY last_used DESC
                ''')
                
                results = []
                for row in cursor.fetchall():
                    reference_data = {
                        'barcode': row['barcode'],
                        'test_duration': row['test_duration'],
                        'created_at': row['created_at'],
                        'last_used': row['last_used'],
                        'chambers': [
                            {
                                'pressure_target': row['ch1_pressure_target'],
                                'pressure_threshold': row['ch1_pressure_threshold'],
                                'pressure_tolerance': row['ch1_pressure_tolerance'],
                                'enabled': bool(row['ch1_enabled'])
                            },
                            {
                                'pressure_target': row['ch2_pressure_target'],
                                'pressure_threshold': row['ch2_pressure_threshold'],
                                'pressure_tolerance': row['ch2_pressure_tolerance'],
                                'enabled': bool(row['ch2_enabled'])
                            },
                            {
                                'pressure_target': row['ch3_pressure_target'],
                                'pressure_threshold': row['ch3_pressure_threshold'],
                                'pressure_tolerance': row['ch3_pressure_tolerance'],
                                'enabled': bool(row['ch3_enabled'])
                            }
                        ]
                    }
                    results.append(reference_data)
                
                self.logger.info(f"Retrieved {len(results)} references")
                return results
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error retrieving references: {e}")
            return []
        except Exception as e:
            self.logger.error(f"General error retrieving references: {e}")
            return []
    
    def get_references_by_barcode_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """
        Search for references with barcodes matching a pattern.
        
        Args:
            pattern: SQL LIKE pattern for barcode matching (e.g., "ABC%")
            
        Returns:
            List of dictionaries containing matching reference data
        """
        if not pattern:
            return self.get_all_references()
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Enable dictionary access for rows
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT barcode,
                           ch1_pressure_target, ch1_pressure_threshold, ch1_pressure_tolerance, ch1_enabled,
                           ch2_pressure_target, ch2_pressure_threshold, ch2_pressure_tolerance, ch2_enabled,
                           ch3_pressure_target, ch3_pressure_threshold, ch3_pressure_tolerance, ch3_enabled,
                           test_duration, created_at, last_used
                    FROM ref_table
                    WHERE barcode LIKE ?
                    ORDER BY last_used DESC
                ''', (pattern,))
                
                results = []
                for row in cursor.fetchall():
                    reference_data = {
                        'barcode': row['barcode'],
                        'test_duration': row['test_duration'],
                        'created_at': row['created_at'],
                        'last_used': row['last_used'],
                        'chambers': [
                            {
                                'pressure_target': row['ch1_pressure_target'],
                                'pressure_threshold': row['ch1_pressure_threshold'],
                                'pressure_tolerance': row['ch1_pressure_tolerance'],
                                'enabled': bool(row['ch1_enabled'])
                            },
                            {
                                'pressure_target': row['ch2_pressure_target'],
                                'pressure_threshold': row['ch2_pressure_threshold'],
                                'pressure_tolerance': row['ch2_pressure_tolerance'],
                                'enabled': bool(row['ch2_enabled'])
                            },
                            {
                                'pressure_target': row['ch3_pressure_target'],
                                'pressure_threshold': row['ch3_pressure_threshold'],
                                'pressure_tolerance': row['ch3_pressure_tolerance'],
                                'enabled': bool(row['ch3_enabled'])
                            }
                        ]
                    }
                    results.append(reference_data)
                
                self.logger.info(f"Found {len(results)} references matching pattern '{pattern}'")
                return results
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error searching references: {e}")
            return []
        except Exception as e:
            self.logger.error(f"General error searching references: {e}")
            return []
    
    def reference_exists(self, barcode: str) -> bool:
        """
        Check if a reference with the given barcode exists.
        
        Args:
            barcode: Reference barcode identifier
            
        Returns:
            bool: True if reference exists, False otherwise
        """
        if not barcode:
            return False
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT 1 FROM ref_table WHERE barcode = ?', (barcode,))
                return cursor.fetchone() is not None
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error checking reference existence: {e}")
            return False
        except Exception as e:
            self.logger.error(f"General error checking reference existence: {e}")
            return False
    
    def get_reference_count(self) -> int:
        """
        Get the total number of references in the database.
        
        Returns:
            int: Number of references
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT COUNT(*) FROM ref_table')
                return cursor.fetchone()[0]
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error counting references: {e}")
            return 0
        except Exception as e:
            self.logger.error(f"General error counting references: {e}")
            return 0
    
    def get_most_recent_references(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recently used references.
        
        Args:
            limit: Maximum number of references to return
            
        Returns:
            List of dictionaries containing reference data
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Enable dictionary access for rows
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT barcode,
                           ch1_pressure_target, ch1_pressure_threshold, ch1_pressure_tolerance, ch1_enabled,
                           ch2_pressure_target, ch2_pressure_threshold, ch2_pressure_tolerance, ch2_enabled,
                           ch3_pressure_target, ch3_pressure_threshold, ch3_pressure_tolerance, ch3_enabled,
                           test_duration, created_at, last_used
                    FROM ref_table
                    ORDER BY last_used DESC
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    reference_data = {
                        'barcode': row['barcode'],
                        'test_duration': row['test_duration'],
                        'created_at': row['created_at'],
                        'last_used': row['last_used'],
                        'chambers': [
                            {
                                'pressure_target': row['ch1_pressure_target'],
                                'pressure_threshold': row['ch1_pressure_threshold'],
                                'pressure_tolerance': row['ch1_pressure_tolerance'],
                                'enabled': bool(row['ch1_enabled'])
                            },
                            {
                                'pressure_target': row['ch2_pressure_target'],
                                'pressure_threshold': row['ch2_pressure_threshold'],
                                'pressure_tolerance': row['ch2_pressure_tolerance'],
                                'enabled': bool(row['ch2_enabled'])
                            },
                            {
                                'pressure_target': row['ch3_pressure_target'],
                                'pressure_threshold': row['ch3_pressure_threshold'],
                                'pressure_tolerance': row['ch3_pressure_tolerance'],
                                'enabled': bool(row['ch3_enabled'])
                            }
                        ]
                    }
                    results.append(reference_data)
                
                self.logger.info(f"Retrieved {len(results)} most recent references")
                return results
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error retrieving recent references: {e}")
            return []
        except Exception as e:
            self.logger.error(f"General error retrieving recent references: {e}")
            return []
    
    def get_reference_usage_counts(self) -> Dict[str, int]:
        """
        Get usage counts for references (assuming additional usage tracking table exists).
        If not implemented, returns empty dictionary.
        
        Returns:
            Dict mapping barcodes to usage counts
        """
        # This is a placeholder for a more advanced implementation that would track
        # actual test runs with each reference. The current implementation doesn't
        # track this data.
        self.logger.warning("Reference usage count tracking not implemented")
        return {}
    
    def update_reference_statistics(self, barcode: str, test_result: bool) -> bool:
        """
        Update reference usage statistics (e.g., after a test run).
        This is a placeholder for a more advanced implementation.
        
        Args:
            barcode: Reference barcode identifier
            test_result: Whether the test passed (True) or failed (False)
            
        Returns:
            bool: True if statistics were updated successfully, False otherwise
        """
        # This is a placeholder for a more advanced implementation that would store
        # statistics about test runs with each reference.
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Simply update the last_used timestamp
                cursor.execute('''
                    UPDATE ref_table
                    SET last_used = datetime('now')
                    WHERE barcode = ?
                ''', (barcode,))
                
                conn.commit()
                return cursor.rowcount > 0
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error updating reference statistics: {e}")
            return False
        except Exception as e:
            self.logger.error(f"General error updating reference statistics: {e}")
            return False
    
    def import_references_from_csv(self, csv_path: str) -> Tuple[int, int]:
        """
        Import references from a CSV file.
        This is a placeholder for bulk import functionality.
        
        Args:
            csv_path: Path to the CSV file
            
        Returns:
            Tuple[int, int]: (Number of references imported, Number of errors)
        """
        self.logger.warning("CSV import functionality not implemented")
        return (0, 0)
    
    def export_references_to_csv(self, csv_path: str) -> bool:
        """
        Export all references to a CSV file.
        This is a placeholder for export functionality.
        
        Args:
            csv_path: Path to save the CSV file
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        self.logger.warning("CSV export functionality not implemented")
        return False
    
    def vacuum_database(self) -> bool:
        """
        Vacuum the SQLite database to optimize storage.
        
        Returns:
            bool: True if vacuum was successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("VACUUM")
                self.logger.info("Database vacuumed successfully")
                return True
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error during vacuum: {e}")
            return False
        except Exception as e:
            self.logger.error(f"General error during vacuum: {e}")
            return False
