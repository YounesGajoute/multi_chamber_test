#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Observer utilities for the Multi-Chamber Test application.

This module provides helper functions and mixins to add observer pattern
capabilities to existing components in the system.
"""

import logging
from typing import Dict, Any, Optional

class TestManagerObserver:
    """
    Mixin that adds observer pattern compatibility to TestManager.
    
    This class can be integrated with the existing TestManager to add
    support for receiving settings updates through the observer pattern.
    """
    
    def register_with_settings_manager(self, settings_manager):
        """
        Register this TestManager as an observer of the SettingsManager.
        
        Args:
            settings_manager: The SettingsManager instance to observe
        """
        if hasattr(settings_manager, 'register_observer'):
            settings_manager.register_observer(self.on_setting_changed)
            self.logger.info("TestManager registered as observer of SettingsManager")
        else:
            self.logger.warning("SettingsManager doesn't support observer registration")
    
    def on_setting_changed(self, key: str, value: Any):
        """
        Handle settings changes from SettingsManager.
        
        Args:
            key: The setting key that changed
            value: The new value
        """
        if self.running_test:
            self.logger.debug(f"Ignoring setting change during active test: {key}")
            return
            
        # Handle test duration changes
        if key == 'test_duration':
            self.logger.info(f"Updating test duration to {value}")
            self.test_duration = int(value)
            
        # Handle test mode changes
        elif key == 'test_mode':
            self.logger.info(f"Updating test mode to {value}")
            # Only update mode, don't try to load reference
            if value in ["manual", "reference"]:
                self.test_mode = value
                
        # Handle chamber settings changes
        elif key.startswith('chamber') and '_' in key:
            # Extract chamber index and setting name
            try:
                parts = key.split('_', 1)
                chamber_str = parts[0]
                setting_name = parts[1]
                
                # Convert from 1-based to 0-based index
                chamber_idx = int(chamber_str[7:]) - 1  # Extract number after "chamber"
                
                if 0 <= chamber_idx < len(self.chamber_states):
                    chamber_state = self.chamber_states[chamber_idx]
                    
                    if setting_name == 'pressure_target':
                        chamber_state.pressure_target = float(value)
                        self.logger.debug(f"Updated chamber {chamber_idx+1} target to {value}")
                        
                    elif setting_name == 'pressure_threshold':
                        chamber_state.pressure_threshold = float(value)
                        self.logger.debug(f"Updated chamber {chamber_idx+1} threshold to {value}")
                        
                    elif setting_name == 'pressure_tolerance':
                        chamber_state.pressure_tolerance = float(value)
                        self.logger.debug(f"Updated chamber {chamber_idx+1} tolerance to {value}")
                        
                    elif setting_name == 'enabled':
                        chamber_state.enabled = bool(value)
                        self.logger.debug(f"Updated chamber {chamber_idx+1} enabled state to {value}")
                        
                    elif setting_name == 'offset':
                        # Handle offset changes if applicable
                        if hasattr(chamber_state, 'offset'):
                            chamber_state.offset = float(value)
                            self.logger.debug(f"Updated chamber {chamber_idx+1} offset to {value}")
            except (ValueError, IndexError) as e:
                self.logger.error(f"Error processing chamber setting {key}: {e}")
        
        # Handle bulk chamber updates
        elif key.startswith('chamber') and not '_' in key:
            try:
                # Check if it's a single chamber update
                chamber_idx = int(key[7:]) - 1  # Convert from 1-based to 0-based
                
                if isinstance(value, dict) and 0 <= chamber_idx < len(self.chamber_states):
                    chamber = self.chamber_states[chamber_idx]
                    
                    if 'enabled' in value:
                        chamber.enabled = bool(value['enabled'])
                    
                    if 'pressure_target' in value:
                        chamber.pressure_target = float(value['pressure_target'])
                    
                    if 'pressure_threshold' in value:
                        chamber.pressure_threshold = float(value['pressure_threshold'])
                    
                    if 'pressure_tolerance' in value:
                        chamber.pressure_tolerance = float(value['pressure_tolerance'])
                    
                    self.logger.info(f"Bulk update of chamber {chamber_idx+1} settings")
            except (ValueError, IndexError):
                pass
        
        # Handle global reset
        elif key == 'settings_reset':
            self.logger.info("Resetting all test settings to defaults")
            # Reset test duration
            from multi_chamber_test.config.constants import TIME_DEFAULTS, PRESSURE_DEFAULTS
            self.test_duration = TIME_DEFAULTS['TEST_DURATION']
            
            # Reset chamber settings
            for i in range(len(self.chamber_states)):
                self.chamber_states[i].enabled = True
                self.chamber_states[i].pressure_target = PRESSURE_DEFAULTS['TARGET']
                self.chamber_states[i].pressure_threshold = PRESSURE_DEFAULTS['THRESHOLD']
                self.chamber_states[i].pressure_tolerance = PRESSURE_DEFAULTS['TOLERANCE']
            

class RoleManagerObserver:
    """
    Mixin that adds observer pattern compatibility to RoleManager.
    
    This class can be integrated with the existing RoleManager to add
    support for receiving settings updates through the observer pattern.
    """
    
    def register_with_settings_manager(self, settings_manager):
        """
        Register this RoleManager as an observer of the SettingsManager.
        
        Args:
            settings_manager: The SettingsManager instance to observe
        """
        if hasattr(settings_manager, 'register_observer'):
            settings_manager.register_observer(self.on_setting_changed)
            self.logger.info("RoleManager registered as observer of SettingsManager")
        else:
            self.logger.warning("SettingsManager doesn't support observer registration")
    
    def on_setting_changed(self, key: str, value: Any):
        """
        Handle settings changes from SettingsManager.
        
        Args:
            key: The setting key that changed
            value: The new value
        """
        # Handle login requirement changes
        if key == 'require_login':
            self.logger.info(f"Updating require_login to {value}")
            self.set_require_login(bool(value))
            
        # Handle session timeout changes
        elif key == 'session_timeout':
            self.logger.info(f"Updating session_timeout to {value}")
            self.set_session_timeout(int(value))


def enhance_test_manager(test_manager, settings_manager=None):
    """
    Enhance an existing TestManager instance with observer capabilities.
    
    Args:
        test_manager: The TestManager instance to enhance
        settings_manager: Optional settings manager to register with
        
    Returns:
        The enhanced TestManager instance
    """
    # Add the observer methods to the test manager instance
    test_manager.register_with_settings_manager = TestManagerObserver.register_with_settings_manager.__get__(test_manager)
    test_manager.on_setting_changed = TestManagerObserver.on_setting_changed.__get__(test_manager)
    
    # Store settings manager reference if needed
    if not hasattr(test_manager, 'settings_manager') and settings_manager is not None:
        test_manager.settings_manager = settings_manager
    
    # Register with settings manager if provided
    if settings_manager is not None:
        test_manager.register_with_settings_manager(settings_manager)
    
    return test_manager


def enhance_role_manager(role_manager, settings_manager=None):
    """
    Enhance an existing RoleManager instance with observer capabilities.
    
    Args:
        role_manager: The RoleManager instance to enhance
        settings_manager: Optional settings manager to register with
        
    Returns:
        The enhanced RoleManager instance
    """
    # Add the observer methods to the role manager instance
    role_manager.register_with_settings_manager = RoleManagerObserver.register_with_settings_manager.__get__(role_manager)
    role_manager.on_setting_changed = RoleManagerObserver.on_setting_changed.__get__(role_manager)
    
    # Register with settings manager if provided
    if settings_manager is not None:
        role_manager.register_with_settings_manager(settings_manager)
    
    return role_manager