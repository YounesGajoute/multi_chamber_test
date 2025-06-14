#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced Test Result Database module for the Multi-Chamber Test application.

This module provides a TestResultDatabase class that handles storage and retrieval
of test results with user ID information for printing requirements.

ENHANCED: Now includes user ID storage and retrieval for printer integration.
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from multi_chamber_test.core.roles import get_current_username

# You can customize this path or pull it from your constants
DEFAULT_DB_PATH = os.path.expanduser("~/multi_chamber_test/data/test_results.db")
MAX_RECORDS = 1000


class TestResultDatabase:
    """
    Enhanced SQLite store for test results with user ID support.
    Keeps only the last MAX_RECORDS runs with rotation.
    Stores minimal data needed for printing and record keeping.
    """

    def __init__(self, db_path: Optional[str] = None, max_records: int = MAX_RECORDS):
        """
        Initialize the test result database.
        
        Args:
            db_path: Path to the SQLite database file
            max_records: Maximum number of records to keep (rotates old records)
        """
        self.logger = logging.getLogger('TestResultDatabase')
        self._setup_logger()
        
        if db_path is None:
            db_path = DEFAULT_DB_PATH
            
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self.max_records = max_records
        self._init_db()
        
        self.logger.info(f"TestResultDatabase initialized at {db_path} with max {max_records} records")

    def _setup_logger(self):
        """Configure logging for the database."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)

    def _init_db(self):
        """Initialize the database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Enable foreign keys for cascade delete
                cursor.execute("PRAGMA foreign_keys = ON")
                
                # Table for overall test runs
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_results (
                        id             INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp      TEXT    NOT NULL,
                        operator_id    TEXT    NOT NULL DEFAULT 'N/A',
                        operator_name  TEXT    DEFAULT 'N/A',
                        reference      TEXT    DEFAULT 'N/A',
                        test_mode      TEXT    NOT NULL DEFAULT 'manual',
                        test_duration  INTEGER NOT NULL DEFAULT 0,
                        overall_result INTEGER NOT NULL DEFAULT 0,
                        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table for per-chamber results
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chamber_results (
                        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                        test_id            INTEGER NOT NULL,
                        chamber_id         INTEGER NOT NULL,
                        enabled            INTEGER NOT NULL DEFAULT 0,
                        pressure_target    REAL    NOT NULL DEFAULT 0.0,
                        pressure_threshold REAL    NOT NULL DEFAULT 0.0,
                        pressure_tolerance REAL    NOT NULL DEFAULT 0.0,
                        final_pressure     REAL    NOT NULL DEFAULT 0.0,
                        result             INTEGER NOT NULL DEFAULT 0,
                        FOREIGN KEY(test_id) REFERENCES test_results(id) ON DELETE CASCADE
                    )
                """)
                
                # Create indices for better performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_test_results_timestamp 
                    ON test_results(timestamp)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_test_results_operator 
                    ON test_results(operator_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_test_results_reference 
                    ON test_results(reference)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chamber_results_test_id 
                    ON chamber_results(test_id)
                """)
                
                conn.commit()
                self.logger.info("Database schema initialized successfully")
                
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
            raise

    def save_test_result(self, record: Dict[str, Any]) -> bool:
        """
        Insert a new test run plus its chamber data, then trim old runs.
        
        Args:
            record: Dictionary containing test result data:
                {
                    'timestamp': ISO8601 string,
                    'operator_id': str (user ID for printing),
                    'reference': str,
                    'test_mode': str,
                    'test_duration': int,
                    'overall_result': bool,
                    'chambers': [
                        {
                            'chamber_id': int,
                            'enabled': bool,
                            'pressure_target': float,
                            'pressure_threshold': float,
                            'pressure_tolerance': float,
                            'final_pressure': float,
                            'result': bool
                        },
                        ...
                    ]
                }
                
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            # Get current operator info if not provided
            operator_id = record.get('operator_id', 'N/A')
            operator_name = get_current_username() or "N/A"
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Enable foreign keys
                cursor.execute("PRAGMA foreign_keys = ON")
                
                # Insert overall test result
                cursor.execute("""
                    INSERT INTO test_results
                      (timestamp, operator_id, operator_name, reference, test_mode, test_duration, overall_result)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    record['timestamp'],
                    operator_id,
                    operator_name,
                    record.get('reference', 'N/A'),
                    record.get('test_mode', 'manual'),
                    record.get('test_duration', 0),
                    1 if record.get('overall_result', False) else 0
                ))
                
                test_id = cursor.lastrowid
                
                # Insert each chamber result
                for chamber in record.get('chambers', []):
                    cursor.execute("""
                        INSERT INTO chamber_results
                          (test_id, chamber_id, enabled, pressure_target,
                           pressure_threshold, pressure_tolerance,
                           final_pressure, result)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        test_id,
                        chamber.get('chamber_id', 0),
                        1 if chamber.get('enabled', False) else 0,
                        chamber.get('pressure_target', 0.0),
                        chamber.get('pressure_threshold', 0.0),
                        chamber.get('pressure_tolerance', 0.0),
                        chamber.get('final_pressure', 0.0),
                        1 if chamber.get('result', False) else 0
                    ))
                
                # Rotate old records if we exceed max_records
                cursor.execute("SELECT COUNT(*) FROM test_results")
                total = cursor.fetchone()[0]
                
                if total > self.max_records:
                    overflow = total - self.max_records
                    self.logger.info(f"Rotating {overflow} old test records")
                    
                    # Delete oldest records (foreign key constraints will cascade delete chamber_results)
                    cursor.execute("""
                        DELETE FROM test_results
                        WHERE id IN (
                            SELECT id FROM test_results
                            ORDER BY timestamp ASC, id ASC
                            LIMIT ?
                        )
                    """, (overflow,))
                
                conn.commit()
                
                self.logger.info(f"Saved test result with ID {test_id} for operator {operator_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error saving test result: {e}")
            return False

    def get_all_results(self) -> List[Dict[str, Any]]:
        """
        Fetch every stored test run (oldest first) as a list of dicts.
        
        Returns:
            List of dictionaries containing test results:
            {
                'id', 'timestamp', 'operator_id', 'operator_name', 'reference', 
                'test_mode', 'test_duration', 'overall_result', 'chambers': [...]
            }
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all test results ordered by timestamp
                cursor.execute("""
                    SELECT id, timestamp, operator_id, operator_name, reference, 
                           test_mode, test_duration, overall_result
                    FROM test_results 
                    ORDER BY timestamp ASC, id ASC
                """)
                
                rows = cursor.fetchall()
                results = []
                
                for row in rows:
                    test_id, timestamp, operator_id, operator_name, reference, test_mode, duration, overall = row
                    
                    # Get chamber results for this test
                    cursor.execute("""
                        SELECT chamber_id, enabled, pressure_target,
                               pressure_threshold, pressure_tolerance,
                               final_pressure, result
                        FROM chamber_results
                        WHERE test_id = ?
                        ORDER BY chamber_id ASC
                    """, (test_id,))
                    
                    chambers = []
                    for chamber_row in cursor.fetchall():
                        chambers.append({
                            'chamber_id': chamber_row[0],
                            'enabled': bool(chamber_row[1]),
                            'pressure_target': chamber_row[2],
                            'pressure_threshold': chamber_row[3],
                            'pressure_tolerance': chamber_row[4],
                            'final_pressure': chamber_row[5],
                            'result': bool(chamber_row[6])
                        })
                    
                    # Build result record
                    results.append({
                        'id': test_id,
                        'timestamp': timestamp,
                        'operator_id': operator_id,
                        'operator_name': operator_name,
                        'reference': reference,
                        'test_mode': test_mode,
                        'test_duration': duration,
                        'overall_result': bool(overall),
                        'chambers': chambers
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error retrieving test results: {e}")
            return []

    def get_recent_results(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent test results.
        
        Args:
            count: Number of recent results to retrieve
            
        Returns:
            List of recent test results, most recent first
        """
        all_results = self.get_all_results()
        return all_results[-count:][::-1]  # Get last N items, reverse for most recent first

    def get_results_by_operator(self, operator_id: str) -> List[Dict[str, Any]]:
        """
        Get test results for a specific operator.
        
        Args:
            operator_id: ID of the operator
            
        Returns:
            List of test results for the operator
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get test results for specific operator
                cursor.execute("""
                    SELECT id, timestamp, operator_id, operator_name, reference, 
                           test_mode, test_duration, overall_result
                    FROM test_results 
                    WHERE operator_id = ?
                    ORDER BY timestamp DESC
                """, (operator_id,))
                
                rows = cursor.fetchall()
                results = []
                
                for row in rows:
                    test_id, timestamp, operator_id, operator_name, reference, test_mode, duration, overall = row
                    
                    # Get chamber results for this test
                    cursor.execute("""
                        SELECT chamber_id, enabled, pressure_target,
                               pressure_threshold, pressure_tolerance,
                               final_pressure, result
                        FROM chamber_results
                        WHERE test_id = ?
                        ORDER BY chamber_id ASC
                    """, (test_id,))
                    
                    chambers = []
                    for chamber_row in cursor.fetchall():
                        chambers.append({
                            'chamber_id': chamber_row[0],
                            'enabled': bool(chamber_row[1]),
                            'pressure_target': chamber_row[2],
                            'pressure_threshold': chamber_row[3],
                            'pressure_tolerance': chamber_row[4],
                            'final_pressure': chamber_row[5],
                            'result': bool(chamber_row[6])
                        })
                    
                    results.append({
                        'id': test_id,
                        'timestamp': timestamp,
                        'operator_id': operator_id,
                        'operator_name': operator_name,
                        'reference': reference,
                        'test_mode': test_mode,
                        'test_duration': duration,
                        'overall_result': bool(overall),
                        'chambers': chambers
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error retrieving results by operator: {e}")
            return []

    def get_results_by_reference(self, reference: str) -> List[Dict[str, Any]]:
        """
        Get test results for a specific reference.
        
        Args:
            reference: Reference barcode
            
        Returns:
            List of test results for the reference
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get test results for specific reference
                cursor.execute("""
                    SELECT id, timestamp, operator_id, operator_name, reference, 
                           test_mode, test_duration, overall_result
                    FROM test_results 
                    WHERE reference = ?
                    ORDER BY timestamp DESC
                """, (reference,))
                
                rows = cursor.fetchall()
                results = []
                
                for row in rows:
                    test_id, timestamp, operator_id, operator_name, reference, test_mode, duration, overall = row
                    
                    # Get chamber results for this test
                    cursor.execute("""
                        SELECT chamber_id, enabled, pressure_target,
                               pressure_threshold, pressure_tolerance,
                               final_pressure, result
                        FROM chamber_results
                        WHERE test_id = ?
                        ORDER BY chamber_id ASC
                    """, (test_id,))
                    
                    chambers = []
                    for chamber_row in cursor.fetchall():
                        chambers.append({
                            'chamber_id': chamber_row[0],
                            'enabled': bool(chamber_row[1]),
                            'pressure_target': chamber_row[2],
                            'pressure_threshold': chamber_row[3],
                            'pressure_tolerance': chamber_row[4],
                            'final_pressure': chamber_row[5],
                            'result': bool(chamber_row[6])
                        })
                    
                    results.append({
                        'id': test_id,
                        'timestamp': timestamp,
                        'operator_id': operator_id,
                        'operator_name': operator_name,
                        'reference': reference,
                        'test_mode': test_mode,
                        'test_duration': duration,
                        'overall_result': bool(overall),
                        'chambers': chambers
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error retrieving results by reference: {e}")
            return []

    def get_results_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Get test results within a date range.
        
        Args:
            start_date: Start date in ISO format
            end_date: End date in ISO format
            
        Returns:
            List of test results within the date range
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get test results within date range
                cursor.execute("""
                    SELECT id, timestamp, operator_id, operator_name, reference, 
                           test_mode, test_duration, overall_result
                    FROM test_results 
                    WHERE timestamp BETWEEN ? AND ?
                    ORDER BY timestamp ASC, id ASC
                """, (start_date, end_date))
                
                rows = cursor.fetchall()
                results = []
                
                for row in rows:
                    test_id, timestamp, operator_id, operator_name, reference, test_mode, duration, overall = row
                    
                    # Get chamber results for this test
                    cursor.execute("""
                        SELECT chamber_id, enabled, pressure_target,
                               pressure_threshold, pressure_tolerance,
                               final_pressure, result
                        FROM chamber_results
                        WHERE test_id = ?
                        ORDER BY chamber_id ASC
                    """, (test_id,))
                    
                    chambers = []
                    for chamber_row in cursor.fetchall():
                        chambers.append({
                            'chamber_id': chamber_row[0],
                            'enabled': bool(chamber_row[1]),
                            'pressure_target': chamber_row[2],
                            'pressure_threshold': chamber_row[3],
                            'pressure_tolerance': chamber_row[4],
                            'final_pressure': chamber_row[5],
                            'result': bool(chamber_row[6])
                        })
                    
                    results.append({
                        'id': test_id,
                        'timestamp': timestamp,
                        'operator_id': operator_id,
                        'operator_name': operator_name,
                        'reference': reference,
                        'test_mode': test_mode,
                        'test_duration': duration,
                        'overall_result': bool(overall),
                        'chambers': chambers
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error retrieving results by date range: {e}")
            return []

    def get_test_statistics(self) -> Dict[str, Any]:
        """
        Get statistical information about stored test results.
        
        Returns:
            Dictionary containing statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get total test count
                cursor.execute("SELECT COUNT(*) FROM test_results")
                total_tests = cursor.fetchone()[0]
                
                # Get passed tests count
                cursor.execute("SELECT COUNT(*) FROM test_results WHERE overall_result = 1")
                passed_tests = cursor.fetchone()[0]
                
                failed_tests = total_tests - passed_tests
                
                # Get date range
                cursor.execute("""
                    SELECT MIN(timestamp), MAX(timestamp) 
                    FROM test_results
                """)
                date_range = cursor.fetchone()
                
                # Get unique operators count
                cursor.execute("""
                    SELECT COUNT(DISTINCT operator_id) 
                    FROM test_results 
                    WHERE operator_id != 'N/A'
                """)
                unique_operators = cursor.fetchone()[0]
                
                # Get unique references count
                cursor.execute("""
                    SELECT COUNT(DISTINCT reference) 
                    FROM test_results 
                    WHERE reference != 'N/A'
                """)
                unique_references = cursor.fetchone()[0]
                
                # Calculate pass rate
                pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
                
                return {
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'pass_rate': pass_rate,
                    'earliest_test': date_range[0] if date_range else None,
                    'latest_test': date_range[1] if date_range else None,
                    'unique_operators': unique_operators,
                    'unique_references': unique_references
                }
                
        except Exception as e:
            self.logger.error(f"Error getting test statistics: {e}")
            return {
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'pass_rate': 0.0,
                'earliest_test': None,
                'latest_test': None,
                'unique_operators': 0,
                'unique_references': 0
            }

    def get_operator_statistics(self, operator_id: str) -> Dict[str, Any]:
        """
        Get statistics for a specific operator.
        
        Args:
            operator_id: ID of the operator
            
        Returns:
            Dictionary containing operator-specific statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get total tests for operator
                cursor.execute("""
                    SELECT COUNT(*) FROM test_results 
                    WHERE operator_id = ?
                """, (operator_id,))
                total_tests = cursor.fetchone()[0]
                
                # Get passed tests for operator
                cursor.execute("""
                    SELECT COUNT(*) FROM test_results 
                    WHERE operator_id = ? AND overall_result = 1
                """, (operator_id,))
                passed_tests = cursor.fetchone()[0]
                
                failed_tests = total_tests - passed_tests
                
                # Get date range for operator
                cursor.execute("""
                    SELECT MIN(timestamp), MAX(timestamp) 
                    FROM test_results
                    WHERE operator_id = ?
                """, (operator_id,))
                date_range = cursor.fetchone()
                
                # Calculate pass rate
                pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
                
                return {
                    'operator_id': operator_id,
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'pass_rate': pass_rate,
                    'first_test': date_range[0] if date_range else None,
                    'last_test': date_range[1] if date_range else None
                }
                
        except Exception as e:
            self.logger.error(f"Error getting operator statistics: {e}")
            return {
                'operator_id': operator_id,
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'pass_rate': 0.0,
                'first_test': None,
                'last_test': None
            }

    def delete_old_records(self, days_old: int = 90) -> int:
        """
        Delete test records older than specified days.
        
        Args:
            days_old: Number of days to keep records for
            
        Returns:
            Number of records deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cutoff_str = cutoff_date.isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Enable foreign keys for cascade delete
                cursor.execute("PRAGMA foreign_keys = ON")
                
                # Count records to be deleted
                cursor.execute("""
                    SELECT COUNT(*) FROM test_results 
                    WHERE timestamp < ?
                """, (cutoff_str,))
                
                count = cursor.fetchone()[0]
                
                if count > 0:
                    # Delete old records
                    cursor.execute("""
                        DELETE FROM test_results 
                        WHERE timestamp < ?
                    """, (cutoff_str,))
                    
                    conn.commit()
                    self.logger.info(f"Deleted {count} test records older than {days_old} days")
                
                return count
                
        except Exception as e:
            self.logger.error(f"Error deleting old records: {e}")
            return 0

    def vacuum_database(self) -> bool:
        """
        Vacuum the database to reclaim space and optimize performance.
        
        Returns:
            bool: True if vacuum was successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("VACUUM")
                self.logger.info("Database vacuum completed successfully")
                return True
        except Exception as e:
            self.logger.error(f"Error vacuuming database: {e}")
            return False

    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the database.
        
        Returns:
            Dictionary containing database information
        """
        try:
            info = {
                'database_path': self.db_path,
                'max_records': self.max_records,
                'file_size': os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            }
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get record counts
                cursor.execute("SELECT COUNT(*) FROM test_results")
                info['total_records'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM chamber_results")
                info['total_chamber_records'] = cursor.fetchone()[0]
                
                # Get SQLite version
                cursor.execute("SELECT sqlite_version()")
                info['sqlite_version'] = cursor.fetchone()[0]
            
            return info
            
        except Exception as e:
            self.logger.error(f"Error getting database info: {e}")
            return {
                'database_path': self.db_path,
                'error': str(e)
            }

    def export_to_json(self, filepath: str, test_ids: Optional[List[int]] = None) -> bool:
        """
        Export test results to a JSON file.
        
        Args:
            filepath: Path to save the JSON file
            test_ids: Optional list of test IDs to export (None for all)
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            import json
            
            # Get the data to export
            if test_ids:
                all_results = self.get_all_results()
                results = [r for r in all_results if r['id'] in test_ids]
            else:
                results = self.get_all_results()
            
            # Create export data structure
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'database_info': self.get_database_info(),
                'statistics': self.get_test_statistics(),
                'test_count': len(results),
                'test_results': results
            }
            
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            self.logger.info(f"Exported {len(results)} test results to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting to JSON: {e}")
            return False

    def import_from_json(self, filepath: str) -> int:
        """
        Import test results from a JSON file.
        
        Args:
            filepath: Path to the JSON file to import
            
        Returns:
            Number of records imported
        """
        try:
            import json
            
            with open(filepath, 'r') as f:
                import_data = json.load(f)
            
            if 'test_results' not in import_data:
                self.logger.error("Invalid JSON format: missing 'test_results' key")
                return 0
            
            imported_count = 0
            
            for record in import_data['test_results']:
                # Remove the 'id' field as it will be auto-generated
                if 'id' in record:
                    del record['id']
                
                # Save the record
                if self.save_test_result(record):
                    imported_count += 1
            
            self.logger.info(f"Imported {imported_count} test results from {filepath}")
            return imported_count
            
        except Exception as e:
            self.logger.error(f"Error importing from JSON: {e}")
            return 0