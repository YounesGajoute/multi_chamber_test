#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Logger module for the Multi-Chamber Test application.

This module provides a TestLogger class for recording and managing
test results, with database-only storage (no CSV files).

MODIFIED: Now saves only to database via TestResultDatabase, not CSV files.
Maintains minimal data needed for printing with user ID information.
"""

import logging
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union

from multi_chamber_test.config.constants import RESULTS_DIR
from multi_chamber_test.database.test_result_db import TestResultDatabase


class TestLogger:
    """
    Logger for test results with database-only storage.
    
    This class maintains test results in the database and provides
    methods to retrieve and manage test data. It focuses on storing
    only the essential data needed for printing and record keeping.
    
    MODIFIED: No longer saves to CSV files, uses database only.
    """
    
    def __init__(self, results_dir: str = RESULTS_DIR):
        """
        Initialize the TestLogger with database storage.
        
        Args:
            results_dir: Directory for any temporary files (kept for compatibility)
        """
        self.logger = logging.getLogger('TestLogger')
        self._setup_logger()
        
        self.results_dir = results_dir
        
        # Ensure results directory exists (for compatibility)
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Initialize database connection
        self.test_db = TestResultDatabase()
        
        # Initialize counters for statistics
        self.stats = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'last_test_time': None
        }
        
        # Load existing statistics from database
        self._load_statistics()
        
        self.logger.info("TestLogger initialized with database-only storage")
    
    def _setup_logger(self):
        """Configure logging for the test logger."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _load_statistics(self):
        """Load statistics from the database."""
        try:
            # Get all test results to calculate statistics
            all_results = self.test_db.get_all_results()
            
            self.stats['total_tests'] = len(all_results)
            self.stats['passed_tests'] = sum(1 for result in all_results if result['overall_result'])
            self.stats['failed_tests'] = self.stats['total_tests'] - self.stats['passed_tests']
            
            if all_results:
                # Get the most recent test timestamp
                self.stats['last_test_time'] = all_results[-1]['timestamp']
            
            self.logger.info(f"Loaded statistics: {self.stats['total_tests']} total tests")
            
        except Exception as e:
            self.logger.error(f"Error loading statistics from database: {e}")
            # Keep default values if database read fails
    
    def log_test_result(self, test_data: Dict[str, Any]) -> bool:
        """
        Log a test result to the database.
        
        Args:
            test_data: Dictionary containing test result data with keys:
                      'timestamp': Test timestamp (datetime or str)
                      'reference': Reference barcode (str or None)
                      'test_mode': Test mode ('manual' or 'reference')
                      'test_duration': Test duration in seconds (int)
                      'overall_result': Overall test result (bool)
                      'operator_id': User ID who ran the test (str)
                      'chambers': List of dictionaries with chamber-specific results:
                          'chamber_id': Chamber identifier (int, 0-2)
                          'enabled': Whether the chamber was enabled for the test (bool)
                          'pressure_target': Target pressure in mbar (float)
                          'pressure_threshold': Threshold pressure in mbar (float)
                          'pressure_tolerance': Acceptable pressure variation in mbar (float)
                          'final_pressure': Final pressure reading in mbar (float)
                          'result': Chamber-specific test result (bool)
            
        Returns:
            bool: True if the test result was logged successfully, False otherwise
        """
        try:
            # Ensure timestamp is in the correct format
            if isinstance(test_data.get('timestamp'), datetime):
                timestamp = test_data['timestamp']
            elif isinstance(test_data.get('timestamp'), str):
                try:
                    timestamp = datetime.fromisoformat(test_data['timestamp'])
                except ValueError:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            
            # Format the record with standardized structure for database
            record = {
                'timestamp': timestamp.isoformat(),
                'reference': test_data.get('reference', 'N/A'),
                'test_mode': test_data.get('test_mode', 'manual'),
                'test_duration': test_data.get('test_duration', 0),
                'overall_result': bool(test_data.get('overall_result', False)),
                'operator_id': test_data.get('operator_id', 'N/A'),  # Include user ID
                'chambers': []
            }
            
            # Process chamber-specific data (only essential fields for printing)
            chambers_data = test_data.get('chambers', [])
            for chamber_data in chambers_data:
                chamber_record = {
                    'chamber_id': chamber_data.get('chamber_id', 0),
                    'enabled': bool(chamber_data.get('enabled', True)),
                    'pressure_target': float(chamber_data.get('pressure_target', 0.0)),
                    'pressure_threshold': float(chamber_data.get('pressure_threshold', 0.0)),
                    'pressure_tolerance': float(chamber_data.get('pressure_tolerance', 0.0)),
                    'final_pressure': float(chamber_data.get('final_pressure', 0.0)),
                    'result': bool(chamber_data.get('result', False))
                }
                record['chambers'].append(chamber_record)
            
            # Save to database
            self.test_db.save_test_result(record)
            
            # Update local statistics
            self.stats['total_tests'] += 1
            if record['overall_result']:
                self.stats['passed_tests'] += 1
            else:
                self.stats['failed_tests'] += 1
            self.stats['last_test_time'] = record['timestamp']
            
            self.logger.info(f"Logged test result to database: {record['overall_result']} for reference {record['reference']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error logging test result to database: {e}")
            return False
    
    def log_test(self, test_data: Dict[str, Any]) -> bool:
        """
        Alias for log_test_result for backward compatibility.
        
        Args:
            test_data: Test data dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.log_test_result(test_data)
    
    def get_recent_tests(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent test results from the database.
        
        Args:
            count: Number of recent test results to retrieve
            
        Returns:
            List of dictionaries containing test results, most recent first
        """
        try:
            all_results = self.test_db.get_all_results()
            # Return the last 'count' items, reversed to get most recent first
            return all_results[-count:][::-1]
        except Exception as e:
            self.logger.error(f"Error getting recent tests: {e}")
            return []
    
    def get_test_by_reference(self, reference: str) -> List[Dict[str, Any]]:
        """
        Get test results for a specific reference barcode from the database.
        
        Args:
            reference: Reference barcode to search for
            
        Returns:
            List of dictionaries containing matching test results
        """
        if not reference:
            return []
            
        try:
            all_results = self.test_db.get_all_results()
            return [
                record for record in all_results
                if record['reference'] == reference
            ]
        except Exception as e:
            self.logger.error(f"Error searching tests by reference: {e}")
            return []
    
    def get_test_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about test results.
        
        Returns:
            Dictionary containing test statistics
        """
        # Calculate pass rate
        pass_rate = 0.0
        if self.stats['total_tests'] > 0:
            pass_rate = (self.stats['passed_tests'] / self.stats['total_tests']) * 100
        
        # Get total records from database for accuracy
        try:
            all_results = self.test_db.get_all_results()
            db_record_count = len(all_results)
        except Exception as e:
            self.logger.error(f"Error getting database record count: {e}")
            db_record_count = self.stats['total_tests']
        
        # Return comprehensive statistics
        return {
            'total_tests': self.stats['total_tests'],
            'passed_tests': self.stats['passed_tests'],
            'failed_tests': self.stats['failed_tests'],
            'pass_rate': pass_rate,
            'last_test_time': self.stats['last_test_time'],
            'record_count': db_record_count
        }
    
    def get_all_test_results(self) -> List[Dict[str, Any]]:
        """
        Get all test results from the database.
        
        Returns:
            List of all test results
        """
        try:
            return self.test_db.get_all_results()
        except Exception as e:
            self.logger.error(f"Error getting all test results: {e}")
            return []
    
    def get_test_by_id(self, test_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific test result by ID.
        
        Args:
            test_id: Database ID of the test
            
        Returns:
            Test result dictionary or None if not found
        """
        try:
            all_results = self.test_db.get_all_results()
            for result in all_results:
                if result.get('id') == test_id:
                    return result
            return None
        except Exception as e:
            self.logger.error(f"Error getting test by ID: {e}")
            return None
    
    def export_to_csv(self, path: str, test_records: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Export test results to CSV file (kept for compatibility/manual export).
        
        Args:
            path: Path to save the CSV file
            test_records: Optional list of records to export (defaults to all)
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            import csv
            
            # Get records to export
            if test_records is None:
                test_records = self.get_all_test_results()
            
            if not test_records:
                self.logger.warning("No test records to export")
                return False
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Prepare data for CSV export (flatten nested structures)
            flattened_records = []
            for record in test_records:
                for chamber in record['chambers']:
                    flat_record = {
                        'timestamp': record['timestamp'],
                        'operator_id': record.get('operator_id', 'N/A'),
                        'reference': record['reference'],
                        'test_mode': record['test_mode'],
                        'test_duration': record['test_duration'],
                        'overall_result': 'PASS' if record['overall_result'] else 'FAIL',
                        'chamber_id': chamber['chamber_id'] + 1,  # Convert to 1-based for display
                        'chamber_enabled': chamber['enabled'],
                        'pressure_target': chamber['pressure_target'],
                        'pressure_threshold': chamber['pressure_threshold'],
                        'pressure_tolerance': chamber['pressure_tolerance'],
                        'final_pressure': chamber['final_pressure'],
                        'chamber_result': 'PASS' if chamber['result'] else 'FAIL'
                    }
                    flattened_records.append(flat_record)
            
            # Write to CSV
            with open(path, 'w', newline='') as csvfile:
                if not flattened_records:
                    self.logger.warning("No flattened records to write to CSV")
                    return False
                    
                fieldnames = flattened_records[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                writer.writerows(flattened_records)
            
            self.logger.info(f"Exported {len(flattened_records)} test records to {path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting test results to CSV: {e}")
            return False
    
    def save_to_csv(self, path: Optional[str] = None) -> bool:
        """
        Save all test results to a CSV file (kept for backward compatibility).
        
        Args:
            path: Path to save the CSV file (optional, generates default if None)
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            # Generate default filename if not provided
            if not path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"test_results_{timestamp}.csv"
                path = os.path.join(self.results_dir, filename)
            
            return self.export_to_csv(path)
            
        except Exception as e:
            self.logger.error(f"Error saving test results to CSV: {e}")
            return False
    
    def save_detailed_test_to_csv(self, test_id: int, path: Optional[str] = None) -> bool:
        """
        Save detailed data for a specific test to a CSV file.
        
        Args:
            test_id: ID of the test in the database
            path: Path to save the CSV file (optional, generates default if None)
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            # Get the specific test record
            test_record = self.get_test_by_id(test_id)
            if not test_record:
                self.logger.error(f"Test with ID {test_id} not found")
                return False
            
            # Generate default filename if not provided
            if not path:
                timestamp = datetime.fromisoformat(test_record['timestamp']).strftime("%Y%m%d_%H%M%S")
                ref = test_record['reference'].replace(' ', '_')
                filename = f"test_detail_{ref}_{timestamp}.csv"
                path = os.path.join(self.results_dir, filename)
            
            # Export single record
            return self.export_to_csv(path, [test_record])
            
        except Exception as e:
            self.logger.error(f"Error saving detailed test to CSV: {e}")
            return False
    
    def save_last_test_to_csv(self, path: Optional[str] = None) -> bool:
        """
        Save the most recent test result to a CSV file.
        
        Args:
            path: Path to save the CSV file (optional, generates default if None)
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            recent_tests = self.get_recent_tests(1)
            if not recent_tests:
                self.logger.warning("No test records available")
                return False
            
            return self.export_to_csv(path, recent_tests)
            
        except Exception as e:
            self.logger.error(f"Error saving last test to CSV: {e}")
            return False
    
    def export_pressure_logs(self, test_id: int, path: Optional[str] = None) -> bool:
        """
        Export pressure logs for a specific test to a CSV file.
        Note: Since we're not storing detailed pressure logs in the database,
        this method provides a summary instead.
        
        Args:
            test_id: ID of the test in the database
            path: Path to save the CSV file (optional, generates default if None)
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            # Get the specific test record
            test_record = self.get_test_by_id(test_id)
            if not test_record:
                self.logger.error(f"Test with ID {test_id} not found")
                return False
            
            # Generate default filename if not provided
            if not path:
                timestamp = datetime.fromisoformat(test_record['timestamp']).strftime("%Y%m%d_%H%M%S")
                ref = test_record['reference'].replace(' ', '_')
                filename = f"test_summary_{ref}_{timestamp}.csv"
                path = os.path.join(self.results_dir, filename)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Write a summary since we don't have detailed pressure logs
            import csv
            with open(path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Test Summary'])
                writer.writerow(['Timestamp', test_record['timestamp']])
                writer.writerow(['Operator ID', test_record.get('operator_id', 'N/A')])
                writer.writerow(['Reference', test_record['reference']])
                writer.writerow(['Test Mode', test_record['test_mode']])
                writer.writerow(['Test Duration', test_record['test_duration']])
                writer.writerow(['Overall Result', 'PASS' if test_record['overall_result'] else 'FAIL'])
                writer.writerow([])
                
                writer.writerow(['Chamber', 'Enabled', 'Target (mbar)', 'Threshold (mbar)', 
                                'Tolerance (mbar)', 'Final Pressure (mbar)', 'Result'])
                
                for chamber in test_record['chambers']:
                    writer.writerow([
                        f"Chamber {chamber['chamber_id'] + 1}",
                        'Yes' if chamber['enabled'] else 'No',
                        chamber['pressure_target'],
                        chamber['pressure_threshold'],
                        chamber['pressure_tolerance'],
                        chamber['final_pressure'],
                        'PASS' if chamber['result'] else 'FAIL'
                    ])
            
            self.logger.info(f"Saved test summary to {path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting test summary: {e}")
            return False
    
    def clear_records(self) -> bool:
        """
        Clear all test records from database.
        WARNING: This will permanently delete all test data!
        
        Returns:
            bool: True if records were cleared successfully
        """
        try:
            # Note: This would require implementing a clear method in TestResultDatabase
            # For safety, we'll just reset local statistics
            self.stats = {
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'last_test_time': None
            }
            self.logger.warning("Statistics reset - database records not deleted (safety measure)")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing records: {e}")
            return False
    
    def export_json(self, path: Optional[str] = None, count: int = None) -> bool:
        """
        Export test records to a JSON file.
        
        Args:
            path: Path to save the JSON file (optional, generates default if None)
            count: Number of most recent records to export (None for all)
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            import json
            
            # Generate default filename if not provided
            if not path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"test_results_{timestamp}.json"
                path = os.path.join(self.results_dir, filename)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Get records to export
            if count is None:
                records_to_export = self.get_all_test_results()
            else:
                records_to_export = self.get_recent_tests(count)
            
            # Create JSON data structure
            json_data = {
                'export_timestamp': datetime.now().isoformat(),
                'statistics': self.get_test_statistics(),
                'records': records_to_export
            }
            
            with open(path, 'w') as jsonfile:
                json.dump(json_data, jsonfile, indent=2)
            
            self.logger.info(f"Exported {len(records_to_export)} test records to {path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting test records to JSON: {e}")
            return False
    
    def get_tests_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get test results within a specific date range.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            List of test results within the date range
        """
        try:
            all_results = self.get_all_test_results()
            filtered_results = []
            
            for result in all_results:
                try:
                    test_date = datetime.fromisoformat(result['timestamp'])
                    if start_date <= test_date <= end_date:
                        filtered_results.append(result)
                except ValueError:
                    # Skip records with invalid timestamps
                    continue
            
            return filtered_results
            
        except Exception as e:
            self.logger.error(f"Error filtering tests by date range: {e}")
            return []
    
    def get_tests_by_operator(self, operator_id: str) -> List[Dict[str, Any]]:
        """
        Get test results for a specific operator.
        
        Args:
            operator_id: ID of the operator
            
        Returns:
            List of test results for the operator
        """
        try:
            all_results = self.get_all_test_results()
            return [
                result for result in all_results
                if result.get('operator_id') == operator_id
            ]
        except Exception as e:
            self.logger.error(f"Error filtering tests by operator: {e}")
            return []
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the database storage.
        
        Returns:
            Dictionary with database information
        """
        try:
            all_results = self.get_all_test_results()
            
            info = {
                'database_path': getattr(self.test_db, 'db_path', 'Unknown'),
                'total_records': len(all_results),
                'max_records': getattr(self.test_db, 'max_records', 'Unknown'),
                'oldest_test': all_results[0]['timestamp'] if all_results else None,
                'newest_test': all_results[-1]['timestamp'] if all_results else None
            }
            
            return info
            
        except Exception as e:
            self.logger.error(f"Error getting database info: {e}")
            return {'error': str(e)}