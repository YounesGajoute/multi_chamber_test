#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FIXED: Enhanced Settings manager for the Multi-Chamber Test application.

This module provides a robust SettingsManager class with comprehensive
login requirements handling, proper type conversion, and validation.

KEY FIXES:
- Robust boolean setting loading (especially require_login)
- Enhanced type conversion with fallbacks
- Settings integrity validation
- Detailed logging for debugging
- Proper error handling and recovery
"""

import csv
import os
import logging
from typing import Callable, Any, Dict, List, Optional, Union, Tuple
from .constants import SETTINGS_FILE, PRESSURE_DEFAULTS, TIME_DEFAULTS, CALIBRATION_CONFIG

class SettingsManager:
    """
    FIXED: Manager for application settings with robust login requirements handling.
    
    The SettingsManager maintains settings for the application, including:
    - Global test parameters (test duration)
    - Per-chamber settings (pressure target, threshold, tolerance, enabled state)
    - Login requirements (with enhanced validation)
    - Calibration offsets (main calibration method)
    
    FIXES:
    - Robust type conversion for boolean settings
    - Enhanced validation and error recovery
    - Detailed logging for debugging
    - Settings integrity checks
    """
    
    def __init__(self, settings_file: str = SETTINGS_FILE):
        """
        Initialize the SettingsManager with enhanced validation.
        
        Args:
            settings_file: Path to the settings CSV file. Defaults to the value in constants.
        """
        self.settings_file = settings_file
        self.logger = logging.getLogger('SettingsManager')
        self._setup_logger()
        
        # Initialize with default settings FIRST
        self.settings = {}
        self._init_default_settings()
        self._observers = []
        
        # Attempt to load settings with validation
        load_success = self.load_settings()
        
        # CRITICAL: Validate login requirements were loaded correctly
        self._validate_critical_settings(load_success)
        
        # Log final state for debugging
        self._log_initialization_state()
    
    def _setup_logger(self):
        """Configure logging for the settings manager."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _init_default_settings(self):
        """Initialize settings with default values."""
        # Global test settings
        self.settings['test_duration'] = TIME_DEFAULTS['TEST_DURATION']
        self.settings['test_mode'] = "reference"  # Default to reference mode
        
        # CRITICAL: Login settings with explicit defaults
        self.settings['require_login'] = False  # Conservative default for new installations
        self.settings['session_timeout'] = 600  # 10 minutes default
        
        # Per-chamber settings
        for i in range(1, 4):  # Chambers 1-3
            prefix = f'chamber{i}_'
            self.settings[f'{prefix}pressure_target'] = PRESSURE_DEFAULTS['TARGET']
            self.settings[f'{prefix}pressure_threshold'] = PRESSURE_DEFAULTS['THRESHOLD']
            self.settings[f'{prefix}pressure_tolerance'] = PRESSURE_DEFAULTS['TOLERANCE']
            self.settings[f'{prefix}enabled'] = 1  # Enabled by default
            self.settings[f'{prefix}offset'] = CALIBRATION_CONFIG['DEFAULT_OFFSET']  # Main calibration method
        
        # Calibration settings
        self.settings['calibration_method'] = CALIBRATION_CONFIG['METHOD']
        
        self.logger.debug("Default settings initialized")
    
    def load_settings(self) -> bool:
        """
        FIXED: Load settings from the settings file with robust type conversion.
        
        Returns:
            bool: True if settings were loaded successfully, False otherwise.
        """
        try:
            if not os.path.exists(self.settings_file):
                self.logger.info("Settings file not found. Using default settings.")
                return False
            
            # Check if file is readable and not empty
            try:
                file_size = os.path.getsize(self.settings_file)
                if file_size == 0:
                    self.logger.warning("Settings file is empty. Using default settings.")
                    return False
            except OSError as e:
                self.logger.warning(f"Cannot access settings file: {e}. Using default settings.")
                return False
            
            loaded_settings = {}
            settings_count = 0
            
            with open(self.settings_file, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Validate CSV format
                if not reader.fieldnames or 'setting' not in reader.fieldnames or 'value' not in reader.fieldnames:
                    self.logger.error("Invalid settings file format. Missing required columns.")
                    return False
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 to account for header
                    setting = row.get('setting', '').strip()
                    value = row.get('value', '').strip()
                    
                    if not setting:
                        self.logger.debug(f"Row {row_num}: Empty setting name, skipping")
                        continue
                    
                    if value == '':
                        self.logger.debug(f"Row {row_num}: Empty value for {setting}, skipping")
                        continue
                    
                    # ENHANCED: Robust type conversion with explicit handling
                    try:
                        converted_value = self._convert_setting_value(setting, value)
                        loaded_settings[setting] = converted_value
                        settings_count += 1
                        
                        # Special logging for critical settings
                        if setting in ['require_login', 'session_timeout']:
                            self.logger.info(f"Loaded critical setting: {setting} = {converted_value} (type: {type(converted_value).__name__})")
                        else:
                            self.logger.debug(f"Loaded setting: {setting} = {converted_value}")
                            
                    except ValueError as e:
                        self.logger.warning(f"Row {row_num}: Invalid value for {setting}: {value} - {e}")
                        continue
                    except Exception as e:
                        self.logger.error(f"Row {row_num}: Unexpected error processing {setting}: {e}")
                        continue
            
            if settings_count == 0:
                self.logger.warning("No valid settings found in file")
                return False
            
            # Apply loaded settings to current settings
            self.settings.update(loaded_settings)
            
            self.logger.info(f"Settings loaded successfully: {settings_count} settings from {self.settings_file}")
            return True
                
        except Exception as e:
            self.logger.error(f"Error loading settings file: {e}")
            return False
    
    def _convert_setting_value(self, setting: str, value: str) -> Any:
        """
        ENHANCED: Convert setting value to appropriate type with robust error handling.
        
        Args:
            setting: Setting name
            value: String value from CSV
            
        Returns:
            Converted value of appropriate type
            
        Raises:
            ValueError: If conversion fails
        """
        # Handle boolean settings with multiple accepted formats
        if setting in ['require_login']:
            # Accept multiple boolean representations
            if isinstance(value, str):
                lower_value = value.lower().strip()
                if lower_value in ('true', '1', 'yes', 'on', 'enabled'):
                    return True
                elif lower_value in ('false', '0', 'no', 'off', 'disabled'):
                    return False
                else:
                    # Try to parse as integer for backwards compatibility
                    try:
                        return bool(int(float(value)))
                    except (ValueError, TypeError):
                        raise ValueError(f"Invalid boolean value: {value}")
            else:
                return bool(int(float(value)))
        
        # Handle chamber enabled settings (backward compatibility)
        elif 'enabled' in setting:
            return bool(int(float(value)))
        
        # Handle integer settings
        elif setting in ['session_timeout', 'test_duration'] or any(keyword in setting for keyword in ['target', 'threshold', 'tolerance']):
            return int(float(value))  # Parse as float first to handle "150.0" -> 150
        
        # Handle float settings
        elif 'offset' in setting:
            return float(value)
        
        # Handle string settings
        else:
            return str(value)
    
    def _validate_critical_settings(self, load_success: bool):
        """
        ADDED: Validate that critical settings were loaded correctly.
        
        Args:
            load_success: Whether the initial load was successful
        """
        # Check critical settings
        require_login = self.get_setting('require_login')
        session_timeout = self.get_setting('session_timeout')
        
        issues = []
        
        # Validate require_login
        if require_login is None:
            issues.append("require_login is None")
        elif not isinstance(require_login, bool):
            issues.append(f"require_login has wrong type: {type(require_login)} (value: {require_login})")
            # Try to fix it
            try:
                self.settings['require_login'] = bool(require_login)
                self.logger.warning(f"Fixed require_login type: {require_login} -> {bool(require_login)}")
            except:
                self.settings['require_login'] = False
                self.logger.error("Could not fix require_login, set to False")
        
        # Validate session_timeout
        if session_timeout is None:
            issues.append("session_timeout is None")
        elif not isinstance(session_timeout, (int, float)):
            issues.append(f"session_timeout has wrong type: {type(session_timeout)} (value: {session_timeout})")
            # Try to fix it
            try:
                self.settings['session_timeout'] = int(float(session_timeout))
                self.logger.warning(f"Fixed session_timeout type: {session_timeout} -> {int(float(session_timeout))}")
            except:
                self.settings['session_timeout'] = 600
                self.logger.error("Could not fix session_timeout, set to 600")
        elif session_timeout < 0:
            self.settings['session_timeout'] = 600
            self.logger.warning("session_timeout was negative, set to 600")
        
        if issues:
            self.logger.warning(f"Critical settings validation issues: {issues}")
            
            # If load failed and we have issues, ensure we have valid defaults
            if not load_success:
                self.logger.warning("Load failed and validation issues found, ensuring safe defaults")
                self.settings['require_login'] = False
                self.settings['session_timeout'] = 600
    
    def _log_initialization_state(self):
        """ADDED: Log final initialization state for debugging."""
        require_login = self.get_setting('require_login')
        session_timeout = self.get_setting('session_timeout')
        
        self.logger.info(f"SettingsManager initialized:")
        self.logger.info(f"  Settings file: {self.settings_file}")
        self.logger.info(f"  File exists: {os.path.exists(self.settings_file)}")
        self.logger.info(f"  require_login: {require_login} (type: {type(require_login).__name__})")
        self.logger.info(f"  session_timeout: {session_timeout} (type: {type(session_timeout).__name__})")
        self.logger.info(f"  Total settings: {len(self.settings)}")
    
    def save_settings(self) -> bool:
        """
        Save current settings to the settings file.
        
        Returns:
            bool: True if settings were saved successfully, False otherwise.
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            
            with open(self.settings_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['setting', 'value'])
                
                for setting, value in sorted(self.settings.items()):  # Sort for consistent output
                    # Convert boolean to string representation
                    if isinstance(value, bool):
                        str_value = 'true' if value else 'false'
                    else:
                        str_value = str(value)
                    
                    writer.writerow([setting, str_value])
            
            # Verify the save by checking file size
            file_size = os.path.getsize(self.settings_file)
            if file_size == 0:
                self.logger.error("Settings file is empty after save")
                return False
            
            self.logger.info(f"Settings saved successfully to {self.settings_file} ({file_size} bytes)")
            
            # Log critical settings for verification
            require_login = self.get_setting('require_login')
            session_timeout = self.get_setting('session_timeout')
            self.logger.info(f"Saved critical settings: require_login={require_login}, session_timeout={session_timeout}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
            return False
    
    def validate_settings_integrity(self) -> Dict[str, Any]:
        """
        ADDED: Validate settings integrity and return detailed diagnostics.
        
        Returns:
            Dictionary with validation results and diagnostics
        """
        diagnostics = {
            'file_exists': False,
            'file_readable': False,
            'file_size': 0,
            'critical_settings_present': False,
            'type_validation_passed': False,
            'require_login_value': None,
            'require_login_type': None,
            'session_timeout_value': None,
            'session_timeout_type': None,
            'total_settings': len(self.settings),
            'issues': [],
            'warnings': []
        }
        
        try:
            # Check file existence and readability
            if os.path.exists(self.settings_file):
                diagnostics['file_exists'] = True
                try:
                    diagnostics['file_size'] = os.path.getsize(self.settings_file)
                    if diagnostics['file_size'] > 0:
                        with open(self.settings_file, 'r') as f:
                            content = f.read(100)  # Read first 100 chars
                            diagnostics['file_readable'] = len(content) > 0
                except Exception as e:
                    diagnostics['issues'].append(f"File read error: {e}")
            else:
                diagnostics['warnings'].append("Settings file does not exist")
            
            # Check critical settings
            require_login = self.get_setting('require_login')
            session_timeout = self.get_setting('session_timeout')
            
            diagnostics['require_login_value'] = require_login
            diagnostics['require_login_type'] = type(require_login).__name__
            diagnostics['session_timeout_value'] = session_timeout
            diagnostics['session_timeout_type'] = type(session_timeout).__name__
            
            if require_login is not None and session_timeout is not None:
                diagnostics['critical_settings_present'] = True
            else:
                diagnostics['issues'].append("Critical settings missing or None")
            
            # Type validation
            type_issues = []
            if not isinstance(require_login, bool):
                type_issues.append(f"require_login should be bool, got {type(require_login).__name__}")
            
            if not isinstance(session_timeout, (int, float)):
                type_issues.append(f"session_timeout should be int/float, got {type(session_timeout).__name__}")
            elif session_timeout < 0:
                type_issues.append("session_timeout is negative")
            
            if not type_issues:
                diagnostics['type_validation_passed'] = True
            else:
                diagnostics['issues'].extend(type_issues)
            
        except Exception as e:
            diagnostics['issues'].append(f"Validation error: {e}")
        
        return diagnostics
    
    def register_observer(self, callback: Callable[[str, Any], None]):
        """
        Register a callback to be called when settings are changed.
        The callback should accept (key, value) as arguments.
        """
        if callback not in self._observers:
            self._observers.append(callback)
            self.logger.debug(f"Registered observer {callback.__qualname__}")
    
    def unregister_observer(self, callback: Callable[[str, Any], None]):
        """
        Unregister a previously registered callback.
        
        Args:
            callback: The callback function to unregister
        """
        if callback in self._observers:
            self._observers.remove(callback)
            self.logger.debug(f"Unregistered observer {callback.__qualname__}")
    
    def _notify_observers(self, key: str, value: Any):
        """
        Notify all observers of a setting change.
        
        Args:
            key: The setting key that changed
            value: The new value of the setting
        """
        self.logger.debug(f"Notifying observers of change to {key}")
        for callback in self._observers:
            try:
                callback(key, value)
            except Exception as e:
                self.logger.error(f"Error in observer callback {callback.__qualname__}: {e}")
    
    def set_setting(self, key: str, value: Any, notify: bool = True):
        """
        Set a setting and optionally notify observers.
        
        Args:
            key: Setting key to update
            value: New value to set
            notify: Whether to notify observers (default: True)
        """
        old_value = self.settings.get(key)
        
        # Type validation for critical settings
        if key == 'require_login' and not isinstance(value, bool):
            self.logger.warning(f"Converting require_login from {type(value)} to bool: {value}")
            value = bool(value)
        elif key == 'session_timeout' and not isinstance(value, (int, float)):
            self.logger.warning(f"Converting session_timeout from {type(value)} to int: {value}")
            try:
                value = int(float(value))
            except (ValueError, TypeError):
                self.logger.error(f"Could not convert session_timeout: {value}, using 600")
                value = 600
        
        self.settings[key] = value
        
        # Log critical setting changes
        if key in ['require_login', 'session_timeout']:
            self.logger.info(f"Setting {key}: {old_value} -> {value}")
        
        # Only notify if the value actually changed
        if notify and old_value != value:
            self._notify_observers(key, value)
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting by key.
        
        Args:
            key: Setting key to retrieve
            default: Default value if setting doesn't exist
            
        Returns:
            The setting value or default if not found
        """
        return self.settings.get(key, default)
    
    def get_test_duration(self) -> int:
        """Get the current test duration setting in seconds."""
        return int(self.settings.get('test_duration', TIME_DEFAULTS['TEST_DURATION']))
    
    def set_test_duration(self, duration: int, notify: bool = True) -> None:
        """
        Set the test duration with observer notification.
        
        Args:
            duration: Test duration in seconds
            notify: Whether to notify observers (default: True)
        """
        # Ensure positive value
        duration = max(1, int(duration)) 
        
        # Only update if changed
        if self.settings.get('test_duration') != duration:
            self.settings['test_duration'] = duration
            
            if notify:
                self._notify_observers('test_duration', duration)
    
    def get_chamber_settings(self, chamber_index: int) -> Dict[str, Any]:
        """
        Get all settings for a specific chamber.
        
        Args:
            chamber_index: Index of the chamber (1-3)
            
        Returns:
            Dict containing chamber settings: target, threshold, tolerance, enabled, offset
        """
        if not 1 <= chamber_index <= 3:
            raise ValueError(f"Invalid chamber index: {chamber_index}. Must be 1-3.")
            
        prefix = f'chamber{chamber_index}_'
        return {
            'pressure_target': int(self.settings.get(f'{prefix}pressure_target', PRESSURE_DEFAULTS['TARGET'])),
            'pressure_threshold': int(self.settings.get(f'{prefix}pressure_threshold', PRESSURE_DEFAULTS['THRESHOLD'])),
            'pressure_tolerance': int(self.settings.get(f'{prefix}pressure_tolerance', PRESSURE_DEFAULTS['TOLERANCE'])),
            'enabled': bool(self.settings.get(f'{prefix}enabled', True)),
            'offset': float(self.settings.get(f'{prefix}offset', CALIBRATION_CONFIG['DEFAULT_OFFSET']))
        }
    
    def set_chamber_settings(self, chamber_index: int, settings: Dict[str, Any], notify: bool = True) -> None:
        """
        Update settings for a specific chamber with observer notifications.
        
        Args:
            chamber_index: Index of the chamber (1-3)
            settings: Dictionary of settings to update
            notify: Whether to notify observers (default: True)
        """
        if not 1 <= chamber_index <= 3:
            raise ValueError(f"Invalid chamber index: {chamber_index}. Must be 1-3.")
            
        prefix = f'chamber{chamber_index}_'
        changes = {}  # Track changes for notification
        
        if 'pressure_target' in settings:
            target = max(0, min(PRESSURE_DEFAULTS['MAX_PRESSURE'], int(settings['pressure_target'])))
            if self.settings.get(f'{prefix}pressure_target') != target:
                self.settings[f'{prefix}pressure_target'] = target
                changes[f'{prefix}pressure_target'] = target
            
        if 'pressure_threshold' in settings:
            threshold = max(0, int(settings['pressure_threshold']))
            if self.settings.get(f'{prefix}pressure_threshold') != threshold:
                self.settings[f'{prefix}pressure_threshold'] = threshold
                changes[f'{prefix}pressure_threshold'] = threshold
            
        if 'pressure_tolerance' in settings:
            tolerance = max(0, int(settings['pressure_tolerance']))
            if self.settings.get(f'{prefix}pressure_tolerance') != tolerance:
                self.settings[f'{prefix}pressure_tolerance'] = tolerance
                changes[f'{prefix}pressure_tolerance'] = tolerance
            
        if 'enabled' in settings:
            enabled = bool(settings['enabled'])
            if self.settings.get(f'{prefix}enabled') != enabled:
                self.settings[f'{prefix}enabled'] = enabled
                changes[f'{prefix}enabled'] = enabled
            
        if 'offset' in settings:
            offset = max(CALIBRATION_CONFIG['MIN_OFFSET'], 
                        min(CALIBRATION_CONFIG['MAX_OFFSET'], float(settings['offset'])))
            if abs(self.settings.get(f'{prefix}offset', 0.0) - offset) > 0.01:  # Account for float precision
                self.settings[f'{prefix}offset'] = offset
                changes[f'{prefix}offset'] = offset
        
        # Notify about all changes
        if notify and changes:
            # First send the individual setting changes
            for key, value in changes.items():
                self._notify_observers(key, value)
            
            # Then send a notification that the entire chamber was updated
            # This allows components to perform bulk updates if needed
            chamber_key = f'chamber{chamber_index}'
            self._notify_observers(chamber_key, settings)
    
    def set_chamber_offset(self, chamber_index: int, offset: float, notify: bool = True) -> None:
        """
        Set the calibration offset for a specific chamber with optional notification.
        
        Args:
            chamber_index: Index of the chamber (1-3)
            offset: Pressure offset value in mbar
            notify: Whether to notify observers (default: True)
        """
        if not 1 <= chamber_index <= 3:
            raise ValueError(f"Invalid chamber index: {chamber_index}. Must be 1-3.")
        
        # Clamp offset to valid range
        offset = max(CALIBRATION_CONFIG['MIN_OFFSET'], 
                    min(CALIBRATION_CONFIG['MAX_OFFSET'], float(offset)))
        
        key = f'chamber{chamber_index}_offset'    
        old_value = self.settings.get(key, CALIBRATION_CONFIG['DEFAULT_OFFSET'])
        
        # Only update if changed (account for float precision)
        if abs(old_value - offset) > 0.01:
            self.settings[key] = offset
            
            if notify:
                self._notify_observers(key, offset)
    
    def get_chamber_offset(self, chamber_index: int) -> float:
        """
        Get the calibration offset for a specific chamber.
        
        Args:
            chamber_index: Index of the chamber (1-3)
            
        Returns:
            float: The offset value in mbar
        """
        if not 1 <= chamber_index <= 3:
            raise ValueError(f"Invalid chamber index: {chamber_index}. Must be 1-3.")
            
        return float(self.settings.get(f'chamber{chamber_index}_offset', CALIBRATION_CONFIG['DEFAULT_OFFSET']))
    
    def get_all_chamber_offsets(self) -> List[float]:
        """
        Get offsets for all chambers.
        
        Returns:
            List of offset values for chambers 1-3
        """
        return [self.get_chamber_offset(i) for i in range(1, 4)]
    
    def set_all_chamber_offsets(self, offsets: List[float], notify: bool = True) -> None:
        """
        Set offsets for all chambers at once.
        
        Args:
            offsets: List of offset values for chambers 1-3
            notify: Whether to notify observers (default: True)
        """
        if len(offsets) != 3:
            raise ValueError(f"Expected 3 offsets, got {len(offsets)}")
        
        changes = {}
        
        for i, offset in enumerate(offsets, 1):
            # Clamp offset to valid range
            offset = max(CALIBRATION_CONFIG['MIN_OFFSET'], 
                        min(CALIBRATION_CONFIG['MAX_OFFSET'], float(offset)))
            
            key = f'chamber{i}_offset'
            old_value = self.settings.get(key, CALIBRATION_CONFIG['DEFAULT_OFFSET'])
            
            # Only update if changed (account for float precision)
            if abs(old_value - offset) > 0.01:
                self.settings[key] = offset
                changes[key] = offset
        
        # Notify about changes
        if notify and changes:
            for key, value in changes.items():
                self._notify_observers(key, value)
            
            # Send bulk notification
            self._notify_observers('all_chamber_offsets', offsets)
    
    def reset_chamber_offsets(self, notify: bool = True) -> None:
        """
        Reset all chamber offsets to default values.
        
        Args:
            notify: Whether to notify observers (default: True)
        """
        default_offsets = [CALIBRATION_CONFIG['DEFAULT_OFFSET']] * 3
        self.set_all_chamber_offsets(default_offsets, notify)
    
    def get_all_chamber_settings(self) -> List[Dict[str, Any]]:
        """
        Get settings for all chambers.
        
        Returns:
            List of dictionaries containing settings for each chamber.
        """
        return [self.get_chamber_settings(i) for i in range(1, 4)]
    
    def set_all_chamber_settings(self, settings_list: List[Dict[str, Any]], notify: bool = True) -> None:
        """
        Update settings for all chambers at once with notifications.
        
        Args:
            settings_list: List of dictionaries with settings for each chamber.
                         The list should have 3 elements (one per chamber).
            notify: Whether to notify observers (default: True)
        """
        if len(settings_list) != 3:
            raise ValueError(f"Expected 3 chamber settings, got {len(settings_list)}")
            
        for i, chamber_settings in enumerate(settings_list, 1):
            self.set_chamber_settings(i, chamber_settings, notify=False)
            
        # Send a single notification for all chambers if needed
        if notify:
            self._notify_observers('all_chambers', settings_list)
    
    def reset_to_defaults(self, notify: bool = True) -> None:
        """
        Reset all settings to their default values with notification.
        
        Args:
            notify: Whether to notify observers (default: True)
        """
        # Store old settings for comparison
        old_settings = self.settings.copy()
        
        # Reset to defaults
        self._init_default_settings()
        self.logger.info("Settings reset to defaults.")
        
        # Notify about changes
        if notify:
            # Identify changed settings
            for key, value in self.settings.items():
                if key not in old_settings or old_settings[key] != value:
                    self._notify_observers(key, value)
            
            # Finally send a global reset notification
            self._notify_observers('settings_reset', None)
    
    def validate_chamber_offset(self, offset: float) -> Tuple[bool, str]:
        """
        Validate a chamber offset value.
        
        Args:
            offset: Offset value to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            offset = float(offset)
            
            if offset < CALIBRATION_CONFIG['MIN_OFFSET']:
                return False, f"Offset cannot be less than {CALIBRATION_CONFIG['MIN_OFFSET']} mbar"
            
            if offset > CALIBRATION_CONFIG['MAX_OFFSET']:
                return False, f"Offset cannot be greater than {CALIBRATION_CONFIG['MAX_OFFSET']} mbar"
            
            return True, "Valid offset"
            
        except ValueError:
            return False, "Offset must be a valid number"
    
    def get_calibration_config(self) -> Dict[str, Any]:
        """
        Get the current calibration configuration.
        
        Returns:
            Dictionary with calibration configuration
        """
        return {
            'method': self.settings.get('calibration_method', CALIBRATION_CONFIG['METHOD']),
            'max_offset': CALIBRATION_CONFIG['MAX_OFFSET'],
            'min_offset': CALIBRATION_CONFIG['MIN_OFFSET'],
            'default_offset': CALIBRATION_CONFIG['DEFAULT_OFFSET'],
            'precision': CALIBRATION_CONFIG['OFFSET_PRECISION']
        }