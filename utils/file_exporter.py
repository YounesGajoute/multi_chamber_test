#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File Exporter for the Multi-Chamber Test application.

This module provides actual USB detection and file export functionality
for Raspberry Pi and Linux systems, replacing the mock implementation.
"""

import os
import shutil
import subprocess
import logging
import time
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


class FileExporter:
    """
    Utility class to export test result data to CSV on a USB stick or local path.
    """

    
    def __init__(self):
        """Initialize the USB file exporter."""
        self.logger = logging.getLogger('FileExporter')
        self._setup_logger()
        
        # USB detection settings
        self.mount_base = "/media"
        self.auto_mount_base = "/media/usb"
        self.supported_filesystems = ['vfat']  # Only support FAT32 filesystems
        
        # Cache for USB status to avoid repeated checks
        self._last_usb_check = 0
        self._usb_cache_duration = 2.0  # Cache for 2 seconds
        self._cached_usb_status = None
        self._cached_usb_path = None
        
        # Create auto-mount directory if it doesn't exist
        self._ensure_mount_directory()
    
    def _setup_logger(self):
        """Configure logging for the USB exporter."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _ensure_mount_directory(self):
        """Ensure the auto-mount directory exists."""
        try:
            os.makedirs(self.auto_mount_base, exist_ok=True)
            self.logger.debug(f"Mount directory ensured: {self.auto_mount_base}")
        except Exception as e:
            self.logger.error(f"Failed to create mount directory: {e}")
    
    def is_usb_connected(self) -> bool:
        """
        Check if a FAT32 USB drive is connected and accessible.
        
        Returns:
            True if a FAT32 USB drive is connected and accessible, False otherwise
        """
        current_time = time.time()
        
        # Use cached result if recent
        if (current_time - self._last_usb_check < self._usb_cache_duration and 
            self._cached_usb_status is not None):
            return self._cached_usb_status
        
        try:
            # Check for USB storage devices
            usb_devices = self._get_usb_storage_devices()
            
            if not usb_devices:
                self._cached_usb_status = False
                self._cached_usb_path = None
                self._last_usb_check = current_time
                return False
            
            # Check if any USB device is mounted and accessible
            for device in usb_devices:
                mount_point = self._get_mount_point(device)
                if mount_point and self._is_accessible(mount_point):
                    self._cached_usb_status = True
                    self._cached_usb_path = mount_point
                    self._last_usb_check = current_time
                    return True
                
                # Try to auto-mount if not mounted
                if self._try_auto_mount(device):
                    mount_point = self._get_mount_point(device)
                    if mount_point and self._is_accessible(mount_point):
                        self._cached_usb_status = True
                        self._cached_usb_path = mount_point
                        self._last_usb_check = current_time
                        return True
            
            self._cached_usb_status = False
            self._cached_usb_path = None
            self._last_usb_check = current_time
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking USB connection: {e}")
            self._cached_usb_status = False
            self._cached_usb_path = None
            self._last_usb_check = current_time
            return False
    
    def find_usb_path(self) -> Optional[str]:
        """
        Find the path to the first accessible FAT32 USB drive.
        
        Returns:
            Path to FAT32 USB drive or None if not found
        """
        # Use cached path if available and recent
        if self._cached_usb_path and self.is_usb_connected():
            return self._cached_usb_path
        
        try:
            usb_devices = self._get_usb_storage_devices()
            
            for device in usb_devices:
                mount_point = self._get_mount_point(device)
                if mount_point and self._is_accessible(mount_point):
                    return mount_point
                    
                # Try auto-mount
                if self._try_auto_mount(device):
                    mount_point = self._get_mount_point(device)
                    if mount_point and self._is_accessible(mount_point):
                        return mount_point
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding USB path: {e}")
            return None
    
    def _get_usb_storage_devices(self) -> List[str]:
        """
        Get list of USB storage device paths with FAT32 filesystem only.
        
        Returns:
            List of device paths (e.g., ['/dev/sda1', '/dev/sdb1']) with FAT32 filesystem
        """
        usb_devices = []
        
        try:
            # Use lsblk to get block devices
            result = subprocess.run(
                ['lsblk', '-J', '-o', 'NAME,TRAN,TYPE,MOUNTPOINT,FSTYPE'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                self.logger.warning("lsblk command failed")
                return usb_devices
            
            # Parse JSON output
            data = json.loads(result.stdout)
            
            for device in data.get('blockdevices', []):
                # Check if it's a USB device
                if device.get('tran') == 'usb' and device.get('type') == 'disk':
                    # Check for partitions
                    children = device.get('children', [])
                    if children:
                        for child in children:
                            fstype = child.get('fstype', '').lower()
                            # Only accept FAT32 (vfat) filesystems
                            if fstype == 'vfat':
                                device_path = f"/dev/{child['name']}"
                                usb_devices.append(device_path)
                                self.logger.debug(f"Found FAT32 USB device: {device_path}")
                            elif fstype and fstype != 'vfat':
                                self.logger.info(f"Skipping USB device {child['name']} with unsupported filesystem: {fstype}")
                    else:
                        # No partitions, check the device itself
                        fstype = device.get('fstype', '').lower()
                        if fstype == 'vfat':
                            device_path = f"/dev/{device['name']}"
                            usb_devices.append(device_path)
                            self.logger.debug(f"Found FAT32 USB device: {device_path}")
                        elif fstype:
                            self.logger.info(f"Skipping USB device {device['name']} with unsupported filesystem: {fstype}")
            
            if usb_devices:
                self.logger.info(f"Found {len(usb_devices)} FAT32 USB device(s)")
            else:
                self.logger.debug("No FAT32 USB devices found")
            
            return usb_devices
            
        except subprocess.TimeoutExpired:
            self.logger.error("lsblk command timed out")
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse lsblk output: {e}")
        except Exception as e:
            self.logger.error(f"Error getting USB devices: {e}")
        
        return usb_devices
    
    def _get_mount_point(self, device_path: str) -> Optional[str]:
        """
        Get the mount point for a device.
        
        Args:
            device_path: Path to the device (e.g., '/dev/sda1')
            
        Returns:
            Mount point path or None if not mounted
        """
        try:
            # Check if already mounted
            result = subprocess.run(
                ['findmnt', '-n', '-o', 'TARGET', device_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                mount_point = result.stdout.strip()
                if mount_point:
                    return mount_point
            
            return None
            
        except subprocess.TimeoutExpired:
            self.logger.error("findmnt command timed out")
        except Exception as e:
            self.logger.debug(f"Device {device_path} not mounted: {e}")
        
        return None
    
    def _try_auto_mount(self, device_path: str) -> bool:
        """
        Try to auto-mount a USB device.
        
        Args:
            device_path: Path to the device to mount
            
        Returns:
            True if mounting was successful, False otherwise
        """
        try:
            # Create unique mount point
            device_name = os.path.basename(device_path)
            mount_point = os.path.join(self.auto_mount_base, device_name)
            
            # Create mount point directory
            os.makedirs(mount_point, exist_ok=True)
            
            # Try to mount the device
            result = subprocess.run(
                ['sudo', 'mount', device_path, mount_point],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                self.logger.info(f"Successfully mounted {device_path} at {mount_point}")
                return True
            else:
                self.logger.warning(f"Failed to mount {device_path}: {result.stderr}")
                # Clean up empty mount point
                try:
                    os.rmdir(mount_point)
                except:
                    pass
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"Mount command timed out for {device_path}")
        except Exception as e:
            self.logger.error(f"Error auto-mounting {device_path}: {e}")
        
        return False
    
    def _is_accessible(self, path: str) -> bool:
        """
        Check if a path is accessible for writing.
        
        Args:
            path: Path to check
            
        Returns:
            True if path is accessible for writing, False otherwise
        """
        try:
            if not os.path.exists(path):
                return False
            
            if not os.path.isdir(path):
                return False
            
            # Check if we can write to the directory
            test_file = os.path.join(path, '.test_write')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                return True
            except:
                return False
                
        except Exception as e:
            self.logger.debug(f"Path {path} not accessible: {e}")
            return False
    
    def export_all_tests(self, test_data: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Export all test results to the FAT32 USB drive.
        
        Args:
            test_data: Optional test data to export. If None, will try to load from database.
            
        Returns:
            True if export was successful, False otherwise
        """
        usb_path = self.find_usb_path()
        if not usb_path:
            self.logger.error("No accessible FAT32 USB drive found for export")
            return False
        
        try:
            # Get test data if not provided
            if test_data is None:
                test_data = self._load_test_data()
            
            if not test_data:
                self.logger.warning("No test data available to export")
                return False
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"all_test_results_{timestamp}.csv"
            file_path = os.path.join(usb_path, filename)
            
            # Export to CSV
            success = self._export_to_csv(test_data, file_path)
            
            if success:
                self.logger.info(f"Successfully exported {len(test_data)} test records to {file_path}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error exporting all tests: {e}")
            return False
    
    def export_last_test(self, test_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Export the last test result to the FAT32 USB drive.
        
        Args:
            test_data: Optional test data to export. If None, will try to load from database.
            
        Returns:
            True if export was successful, False otherwise
        """
        usb_path = self.find_usb_path()
        if not usb_path:
            self.logger.error("No accessible FAT32 USB drive found for export")
            return False
        
        try:
            # Get last test data if not provided
            if test_data is None:
                all_tests = self._load_test_data()
                if not all_tests:
                    self.logger.warning("No test data available to export")
                    return False
                test_data = all_tests[-1]  # Get the last test
            
            # Generate filename with timestamp
            test_timestamp = test_data.get('timestamp', datetime.now().isoformat())
            # Clean timestamp for filename
            clean_timestamp = test_timestamp.replace(':', '-').replace(' ', '_')
            filename = f"test_result_{clean_timestamp}.csv"
            file_path = os.path.join(usb_path, filename)
            
            # Export single test to CSV
            success = self._export_to_csv([test_data], file_path)
            
            if success:
                self.logger.info(f"Successfully exported last test result to {file_path}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error exporting last test: {e}")
            return False
    
    def _load_test_data(self) -> List[Dict[str, Any]]:
        """
        Load test data from the TestResultDatabase.
        
        Returns:
            List of test data dictionaries
        """
        try:
            # Import the correct TestResultDatabase from your module structure
            # Based on the export settings import path, this should be the correct path
            from multi_chamber_test.database.test_result_db import TestResultDatabase
            
            self.logger.info("Loading test data from TestResultDatabase")
            db = TestResultDatabase()
            test_data = db.get_all_results()
            
            self.logger.info(f"Successfully loaded {len(test_data)} test records from database")
            return test_data
            
        except ImportError as e:
            self.logger.error(f"Failed to import TestResultDatabase: {e}")
            self.logger.warning("TestResultDatabase module not available")
            return []
        except Exception as e:
            self.logger.error(f"Error loading test data from database: {e}")
            return []
    
    def _export_to_csv(self, test_data: List[Dict[str, Any]], file_path: str) -> bool:
        """
        Export test data to a CSV file.
        
        Args:
            test_data: List of test data dictionaries
            file_path: Path to save the CSV file
            
        Returns:
            True if export was successful, False otherwise
        """
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header section
                writer.writerow(['Multi-Chamber Test Results Export'])
                writer.writerow(['Export Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow(['Total Records:', len(test_data)])
                writer.writerow([])  # Empty row
                
                # Write test summary header
                writer.writerow([
                    'Test ID', 'Timestamp', 'Operator ID', 'Operator Name', 'Test Mode', 'Reference',
                    'Duration (s)', 'Overall Result', 'Chamber 1 Result', 
                    'Chamber 2 Result', 'Chamber 3 Result'
                ])
                
                # Write test summary data
                for record in test_data:
                    # Get chamber results
                    chambers = record.get('chambers', [])
                    chamber_results = []
                    
                    for i in range(3):
                        if i < len(chambers):
                            chamber = chambers[i]
                            if chamber.get('enabled', False):
                                result = 'PASS' if chamber.get('result', False) else 'FAIL'
                                pressure = chamber.get('final_pressure', 0)
                                chamber_results.append(f"{result} ({pressure:.1f} mbar)")
                            else:
                                chamber_results.append('Disabled')
                        else:
                            chamber_results.append('N/A')
                    
                    writer.writerow([
                        record.get('id', ''),
                        record.get('timestamp', ''),
                        record.get('operator_id', 'N/A'),
                        record.get('operator_name', 'N/A'),
                        record.get('test_mode', 'Unknown'),
                        record.get('reference', 'N/A'),
                        record.get('test_duration', 0),
                        'PASS' if record.get('overall_result', False) else 'FAIL',
                        chamber_results[0],
                        chamber_results[1],
                        chamber_results[2]
                    ])
                
                # Write detailed chamber data section
                writer.writerow([])  # Empty row
                writer.writerow(['Detailed Chamber Data'])
                writer.writerow([
                    'Test ID', 'Chamber', 'Enabled', 'Target (mbar)', 
                    'Threshold (mbar)', 'Tolerance (mbar)', 'Start Pressure (mbar)',
                    'Final Pressure (mbar)', 'Result'
                ])
                
                # Write chamber details
                for record in test_data:
                    test_id = record.get('id', '')
                    chambers = record.get('chambers', [])
                    
                    for i, chamber in enumerate(chambers):
                        writer.writerow([
                            test_id,
                            f'Chamber {i + 1}',
                            'Yes' if chamber.get('enabled', False) else 'No',
                            chamber.get('pressure_target', 0),
                            chamber.get('pressure_threshold', 0),
                            chamber.get('pressure_tolerance', 0),
                            chamber.get('start_pressure', 0),
                            chamber.get('final_pressure', 0),
                            'PASS' if chamber.get('result', False) else 'FAIL'
                        ])
            
            self.logger.info(f"Successfully wrote CSV file to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error writing CSV file {file_path}: {e}")
            return False
    
    def get_usb_info(self) -> Dict[str, Any]:
        """
        Get detailed information about connected FAT32 USB drives.
        
        Returns:
            Dictionary with FAT32 USB drive information
        """
        info = {
            'connected': False,
            'path': None,
            'devices': [],
            'total_space': 0,
            'free_space': 0,
            'filesystem': 'FAT32'  # We only support FAT32
        }
        
        try:
            usb_devices = self._get_usb_storage_devices()
            info['devices'] = usb_devices
            
            if usb_devices:
                # Get info for the first accessible device
                for device in usb_devices:
                    mount_point = self._get_mount_point(device)
                    if mount_point and self._is_accessible(mount_point):
                        info['connected'] = True
                        info['path'] = mount_point
                        
                        # Get filesystem info
                        try:
                            stat = shutil.disk_usage(mount_point)
                            info['total_space'] = stat.total
                            info['free_space'] = stat.free
                            
                            # Get filesystem type (should be vfat/FAT32)
                            result = subprocess.run(
                                ['df', '-T', mount_point],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if result.returncode == 0:
                                lines = result.stdout.strip().split('\n')
                                if len(lines) > 1:
                                    columns = lines[1].split()
                                    if len(columns) > 1:
                                        filesystem_type = columns[1].lower()
                                        if filesystem_type == 'vfat':
                                            info['filesystem'] = 'FAT32'
                                        else:
                                            info['filesystem'] = filesystem_type.upper()
                        except:
                            pass
                        
                        break
            
        except Exception as e:
            self.logger.error(f"Error getting USB info: {e}")
        
        return info
    
    def safely_unmount_usb(self, device_path: Optional[str] = None) -> bool:
        """
        Safely unmount a FAT32 USB device.
        
        Args:
            device_path: Specific device to unmount, or None to unmount all FAT32 USB devices
            
        Returns:
            True if unmounting was successful, False otherwise
        """
        try:
            if device_path:
                devices_to_unmount = [device_path]
            else:
                devices_to_unmount = self._get_usb_storage_devices()
            
            success = True
            for device in devices_to_unmount:
                mount_point = self._get_mount_point(device)
                if mount_point:
                    try:
                        # Sync first
                        subprocess.run(['sync'], timeout=10)
                        
                        # Unmount
                        result = subprocess.run(
                            ['sudo', 'umount', mount_point],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        
                        if result.returncode == 0:
                            self.logger.info(f"Successfully unmounted {device} from {mount_point}")
                            
                            # Clean up mount point if we created it
                            if mount_point.startswith(self.auto_mount_base):
                                try:
                                    os.rmdir(mount_point)
                                except:
                                    pass
                        else:
                            self.logger.warning(f"Failed to unmount {device}: {result.stderr}")
                            success = False
                            
                    except subprocess.TimeoutExpired:
                        self.logger.error(f"Unmount command timed out for {device}")
                        success = False
                    except Exception as e:
                        self.logger.error(f"Error unmounting {device}: {e}")
                        success = False
            
            # Clear cache after unmounting
            self._cached_usb_status = None
            self._cached_usb_path = None
            self._last_usb_check = 0
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error in safely_unmount_usb: {e}")
            return False
    
    def check_usb_filesystem_compatibility(self) -> Dict[str, Any]:
        """
        Check if connected USB drives have compatible filesystems.
        
        Returns:
            Dictionary with compatibility information:
            {
                'compatible_devices': List[str],  # FAT32 devices
                'incompatible_devices': List[Dict],  # Non-FAT32 devices with their filesystem info
                'no_usb_devices': bool
            }
        """
        compatibility_info = {
            'compatible_devices': [],
            'incompatible_devices': [],
            'no_usb_devices': True
        }
        
        try:
            # Use lsblk to get all USB block devices (not just FAT32)
            result = subprocess.run(
                ['lsblk', '-J', '-o', 'NAME,TRAN,TYPE,MOUNTPOINT,FSTYPE'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                self.logger.warning("lsblk command failed during compatibility check")
                return compatibility_info
            
            # Parse JSON output
            data = json.loads(result.stdout)
            
            for device in data.get('blockdevices', []):
                # Check if it's a USB device
                if device.get('tran') == 'usb' and device.get('type') == 'disk':
                    compatibility_info['no_usb_devices'] = False
                    
                    # Check for partitions
                    children = device.get('children', [])
                    if children:
                        for child in children:
                            device_path = f"/dev/{child['name']}"
                            fstype = child.get('fstype', '').lower()
                            
                            if fstype == 'vfat':
                                compatibility_info['compatible_devices'].append(device_path)
                            elif fstype:
                                compatibility_info['incompatible_devices'].append({
                                    'device': device_path,
                                    'filesystem': fstype.upper(),
                                    'name': child['name']
                                })
                    else:
                        # No partitions, check the device itself
                        device_path = f"/dev/{device['name']}"
                        fstype = device.get('fstype', '').lower()
                        
                        if fstype == 'vfat':
                            compatibility_info['compatible_devices'].append(device_path)
                        elif fstype:
                            compatibility_info['incompatible_devices'].append({
                                'device': device_path,
                                'filesystem': fstype.upper(),
                                'name': device['name']
                            })
            
            self.logger.info(f"USB compatibility check: {len(compatibility_info['compatible_devices'])} compatible, "
                           f"{len(compatibility_info['incompatible_devices'])} incompatible")
            
        except Exception as e:
            self.logger.error(f"Error checking USB filesystem compatibility: {e}")
        
        return compatibility_info