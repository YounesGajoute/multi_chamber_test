#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main Window module for the Multi-Chamber Test application.

This module provides the MainWindow class that initializes and manages
the application's main window, including tab switching, authentication,
and hardware component initialization.

FIXED: Thread-safe GPIO integration with PhysicalControls module
- Added GPIO worker thread for thread safety
- Implemented automatic state synchronization
- Enhanced error handling and recovery
- Proper cleanup with thread management
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
import os
import time
import threading
import queue
from typing import Dict, Any, Optional, List, Callable, Tuple, Union
import atexit
import functools

# Fix PIL import
try:
    from PIL import Image, ImageTk
except ImportError:
    # Provide fallback for systems without PIL
    Image = None
    ImageTk = None

# Import configuration
from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, UI_DIMENSIONS, LOGO_PATH
from multi_chamber_test.config.settings import SettingsManager

# Import hardware components
from multi_chamber_test.hardware.gpio_manager import GPIOManager
from multi_chamber_test.hardware.valve_controller import ValveController
from multi_chamber_test.hardware.pressure_sensor import PressureSensor
from multi_chamber_test.hardware.printer import PrinterManager

# Try to import physical controls (may not be available on all systems)
try:
    from multi_chamber_test.hardware.physical_controls import PhysicalControls
    PHYSICAL_CONTROLS_AVAILABLE = True
except ImportError:
    PHYSICAL_CONTROLS_AVAILABLE = False

# Import core components
from multi_chamber_test.core.test_manager import TestManager
from multi_chamber_test.core.calibration_manager import CalibrationManager
from multi_chamber_test.core.logger import TestLogger
from multi_chamber_test.core.roles import get_role_manager, has_access, get_current_role

# Import database components
from multi_chamber_test.database.reference_db import ReferenceDatabase
from multi_chamber_test.database.calibration_db import CalibrationDatabase

# Import observer pattern utilities
from multi_chamber_test.utils.observers import enhance_test_manager, enhance_role_manager

# Import UI tabs
from multi_chamber_test.ui.tab_main import MainTab
from multi_chamber_test.ui.tab_settings import SettingsTab
from multi_chamber_test.ui.tab_calibration import CalibrationTab
from multi_chamber_test.ui.tab_reference import ReferenceTab
from multi_chamber_test.ui.password_dialog import PasswordDialog
from multi_chamber_test.ui.login_tab import LoginTab


def profile(func):
    """Decorator to profile function execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        # Log slow operations
        if execution_time > 0.1:  # 100ms threshold
            logger = logging.getLogger('Profiler')
            logger.warning(f"Slow operation: {func.__name__} took {execution_time:.3f}s")
        
        return result
    return wrapper


class MainWindow:

    
    def __init__(self, start_with_login=None):

        self.logger = logging.getLogger('MainWindow')
        self._setup_logger()
        
        # Handle deprecated parameter
        if start_with_login is not None:
            self.logger.warning(
                f"Parameter 'start_with_login={start_with_login}' is deprecated. "
                "Login requirement is now determined from settings."
            )
        
        # PHASE 1: Settings-First Initialization
        # =====================================
        
        # Initialize settings manager FIRST to establish authoritative configuration source
        self.logger.info("Initializing settings manager...")
        self.settings_manager = SettingsManager()
        
        # Validate settings load and apply fallbacks if needed
        if not self._validate_settings_load():
            self.logger.warning("Settings validation failed, applying fallbacks")
            self._apply_fallback_settings()
        
        # Determine login requirement from settings (authoritative source)
        self.require_login_from_settings = self.settings_manager.get_setting('require_login', False)
        self.logger.info(f"Login requirement from settings: {self.require_login_from_settings}")
        
        # PHASE 2: UI Foundation Setup
        # ============================
        
        # Set up the main window
        self.root = tk.Tk()
        self.root.title("Multi-Chamber Test")
    
        # Configure for touchscreen/fullscreen use
        self.root.attributes('-fullscreen', True)
        self.root.geometry(f"{UI_DIMENSIONS['WINDOW_WIDTH']}x{UI_DIMENSIONS['WINDOW_HEIGHT']}+0+0")
        self.root.resizable(False, False)
        self.root.config(cursor="none")  # Hide cursor for touchscreen operation
    
        # Load and configure application style
        self._setup_application_style()
    
        # PHASE 3: Component Initialization with Settings Sync
        # ====================================================
        
        # Initialize managers and hardware with explicit settings synchronization
        init_success = self.init_application_components()
        if not init_success:
            self.logger.critical("Application initialization failed. Exiting.")
            self.root.destroy()
            return
    
        # Validate that all components are synchronized with settings
        if not self._validate_component_synchronization():
            self.logger.error("Component synchronization validation failed")
            # Continue but log the issue for debugging
    
        # PHASE 4: UI Layout and Event Handling
        # =====================================
        
        # Create the UI layout
        self.create_ui_layout()
    
        # Configure exit handling
        atexit.register(self.cleanup)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
    
        # Bind global key events
        self.bind_key_events()
    
        # Custom events for tab switching
        self._setup_custom_events()
    
        # PHASE 5: Hardware Integration
        # =============================
        
        # Set up hardware buffer
        self._setup_hardware_buffer()
        
        # Thread-safe GPIO management
        self._setup_gpio_worker()
        
        # Physical state synchronization
        self._setup_physical_state_sync()
        
        # PHASE 6: UI State Management
        # ============================
        
        # Initialize UI state tracking
        self.preloaded_tabs = set()
        self.preloading_active = False
        self.current_tab = None
        self.hardware_callbacks = {}
        self.login_redirect_tab = None
    
        # Update role display with current authentication state
        self.update_role_display()
        
        # PHASE 7: Initial Tab Selection (Settings-Based)
        # ===============================================
        
        # Initialize starting tab based on validated settings
        self._initialize_starting_tab_from_settings()
            
        # Start background tab preloading after UI is settled
        self.root.after(3000, self.preload_tabs_in_background)
        
        # Log final initialization state for debugging
        self._log_initialization_completion()
    
    def _setup_logger(self):
        """Configure logging for the main window."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _setup_gpio_worker(self):
        """Set up thread-safe GPIO operation system."""
        # GPIO command queue for thread safety
        self.gpio_command_queue = queue.Queue()
        self.gpio_result_queue = queue.Queue()
        self.gpio_callbacks: Dict[str, Callable] = {}
        
        # Start GPIO worker thread
        self.gpio_worker_running = True
        self.gpio_worker_thread = threading.Thread(
            target=self._gpio_worker_loop,
            daemon=True,
            name="GPIOWorker"
        )
        self.gpio_worker_thread.start()
        
        # Start result processing on GUI thread
        self._process_gpio_results()
        
        self.logger.info("GPIO worker system initialized")
    
    def _gpio_worker_loop(self):
        """Thread-safe GPIO operations worker."""
        self.logger.debug("GPIO worker thread started")
        
        while self.gpio_worker_running:
            try:
                # Get command with timeout
                cmd_id, cmd_type, args, kwargs = self.gpio_command_queue.get(timeout=0.1)
                
                # Handle stop signal
                if cmd_type == "STOP":
                    break
                
                result = None
                success = True
                error_msg = None
                
                try:
                    if not self.physical_controls:
                        success = False
                        error_msg = "Physical controls not available"
                    elif cmd_type == "set_status_led":
                        result = self.physical_controls.set_status_led(*args, **kwargs)
                    elif cmd_type == "set_start_button_enabled":
                        result = self.physical_controls.set_start_button_enabled(*args, **kwargs)
                    elif cmd_type == "set_stop_button_enabled":
                        result = self.physical_controls.set_stop_button_enabled(*args, **kwargs)
                    elif cmd_type == "sync_led_states":
                        result = self.physical_controls.sync_led_states()
                    else:
                        success = False
                        error_msg = f"Unknown GPIO command: {cmd_type}"
                
                except Exception as e:
                    success = False
                    error_msg = str(e)
                    self.logger.error(f"GPIO operation failed: {cmd_type} - {e}")
                
                # Queue result for GUI thread
                self.gpio_result_queue.put((cmd_id, success, result, error_msg))
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Critical error in GPIO worker: {e}")
                break
        
        self.logger.debug("GPIO worker thread ended")
    
    def _process_gpio_results(self):
        """Process GPIO results on GUI thread."""
        try:
            # Process all available results
            processed_count = 0
            while processed_count < 10:  # Limit to prevent GUI blocking
                try:
                    cmd_id, success, result, error_msg = self.gpio_result_queue.get_nowait()
                    processed_count += 1
                    
                    # Call callback if exists
                    if cmd_id in self.gpio_callbacks:
                        callback = self.gpio_callbacks[cmd_id]
                        try:
                            if success:
                                callback(True, result)
                            else:
                                callback(False, error_msg or "Unknown error")
                        except Exception as e:
                            self.logger.error(f"GPIO callback error: {e}")
                        
                        # Remove processed callback
                        del self.gpio_callbacks[cmd_id]
                    
                    # Update status for failed operations
                    if not success:
                        self.logger.warning(f"GPIO operation failed: {error_msg}")
                        
                except queue.Empty:
                    break
                    
        except Exception as e:
            self.logger.error(f"Error processing GPIO results: {e}")
        
        finally:
            # Schedule next processing
            self.root.after(50, self._process_gpio_results)
    
    def _safe_gpio_command(self, cmd_type: str, *args, callback: Optional[Callable] = None, **kwargs) -> str:
        """
        Queue a GPIO command for safe execution.
        
        Args:
            cmd_type: Type of GPIO command
            *args: Command arguments
            callback: Optional callback function(success: bool, result: Any)
            **kwargs: Command keyword arguments
            
        Returns:
            Command ID for tracking
        """
        cmd_id = f"{cmd_type}_{time.time():.6f}"
        
        # Store callback if provided
        if callback:
            self.gpio_callbacks[cmd_id] = callback
        
        # Queue command (non-blocking)
        try:
            self.gpio_command_queue.put_nowait((cmd_id, cmd_type, args, kwargs))
        except queue.Full:
            self.logger.warning(f"GPIO command queue full, dropping command: {cmd_type}")
            if callback:
                # Remove callback since command won't execute
                del self.gpio_callbacks[cmd_id]
                # Call callback with error
                self.root.after_idle(lambda: callback(False, "Command queue full"))
        
        return cmd_id
    
    def _validate_settings_load(self) -> bool:
        """
        ENHANCED: Validate settings load with comprehensive diagnostics.
        
        Returns:
            bool: True if settings were loaded and validated successfully
        """
        try:
            # Get detailed diagnostics from settings manager
            diagnostics = self.settings_manager.validate_settings_integrity()
            
            # Log comprehensive diagnostics for debugging
            self.logger.info("=== Settings Validation Diagnostics ===")
            self.logger.info(f"File exists: {diagnostics['file_exists']}")
            self.logger.info(f"File readable: {diagnostics['file_readable']}")
            self.logger.info(f"File size: {diagnostics['file_size']} bytes")
            self.logger.info(f"Critical settings present: {diagnostics['critical_settings_present']}")
            self.logger.info(f"Type validation passed: {diagnostics['type_validation_passed']}")
            self.logger.info(f"require_login: {diagnostics['require_login_value']} ({diagnostics['require_login_type']})")
            self.logger.info(f"session_timeout: {diagnostics['session_timeout_value']} ({diagnostics['session_timeout_type']})")
            self.logger.info(f"Total settings: {diagnostics['total_settings']}")
            
            # Log any issues or warnings
            if diagnostics['issues']:
                self.logger.warning(f"Validation issues: {diagnostics['issues']}")
            if diagnostics['warnings']:
                self.logger.info(f"Validation warnings: {diagnostics['warnings']}")
            
            # Determine if validation passed
            validation_passed = (
                diagnostics['critical_settings_present'] and
                diagnostics['type_validation_passed'] and
                len(diagnostics['issues']) == 0
            )
            
            # Even if file doesn't exist, we can proceed with defaults
            if not diagnostics['file_exists']:
                self.logger.info("Settings file not found, but defaults are valid")
                validation_passed = True
            
            self.logger.info(f"Settings validation result: {'PASSED' if validation_passed else 'FAILED'}")
            self.logger.info("==========================================")
            
            return validation_passed
            
        except Exception as e:
            self.logger.error(f"Error during settings validation: {e}")
            return False
    
    def _apply_fallback_settings(self):
        """
        ENHANCED: Apply comprehensive fallback settings with validation.
        """
        self.logger.warning("Applying enhanced fallback settings")
        
        # Define comprehensive fallback settings
        fallback_settings = {
            'require_login': False,  # Safe default for new installations
            'session_timeout': 600,  # 10 minutes
            'test_mode': 'reference',
            'test_duration': 90,
            'calibration_method': 'offset_only'
        }
        
        # Apply fallback settings with proper notification
        for setting, value in fallback_settings.items():
            self.settings_manager.set_setting(setting, value, notify=False)
            self.logger.info(f"Fallback setting applied: {setting} = {value}")
        
        # Validate that fallback settings are correct
        diagnostics = self.settings_manager.validate_settings_integrity()
        if not diagnostics['type_validation_passed']:
            self.logger.error(f"Fallback settings validation failed: {diagnostics['issues']}")
            # Force safe values
            self.settings_manager.settings['require_login'] = False
            self.settings_manager.settings['session_timeout'] = 600
            self.logger.warning("Forced safe login settings after fallback validation failure")
        
        # Try to save fallback settings for future use
        try:
            save_success = self.settings_manager.save_settings()
            if save_success:
                self.logger.info("Fallback settings saved successfully")
            else:
                self.logger.warning("Failed to save fallback settings")
        except Exception as e:
            self.logger.error(f"Exception saving fallback settings: {e}")
    
    def _validate_component_synchronization(self) -> bool:
        """
        ENHANCED: Validate that all components are properly synchronized.
        
        Returns:
            bool: True if all components are synchronized correctly
        """
        try:
            validation_results = {}
            
            # 1. Settings Manager validation
            settings_require_login = self.settings_manager.get_setting('require_login', False)
            settings_session_timeout = self.settings_manager.get_setting('session_timeout', 600)
            
            validation_results['settings_manager'] = {
                'require_login': settings_require_login,
                'require_login_type': type(settings_require_login).__name__,
                'session_timeout': settings_session_timeout,
                'session_timeout_type': type(settings_session_timeout).__name__,
                'valid_types': isinstance(settings_require_login, bool) and isinstance(settings_session_timeout, (int, float))
            }
            
            # 2. Role Manager validation
            role_manager_require_login = None
            role_manager_session_timeout = None
            
            if hasattr(self.role_manager, 'get_require_login'):
                try:
                    role_manager_require_login = self.role_manager.get_require_login()
                except Exception as e:
                    self.logger.warning(f"Could not get require_login from role manager: {e}")
            
            if hasattr(self.role_manager, 'get_session_timeout'):
                try:
                    role_manager_session_timeout = self.role_manager.get_session_timeout()
                except Exception as e:
                    self.logger.warning(f"Could not get session_timeout from role manager: {e}")
            elif hasattr(self.role_manager, 'session_timeout'):
                role_manager_session_timeout = getattr(self.role_manager, 'session_timeout', None)
            elif hasattr(self.role_manager, '_session_timeout'):
                role_manager_session_timeout = getattr(self.role_manager, '_session_timeout', None)
            
            validation_results['role_manager'] = {
                'require_login': role_manager_require_login,
                'session_timeout': role_manager_session_timeout,
                'has_get_require_login': hasattr(self.role_manager, 'get_require_login'),
                'has_session_timeout_attr': hasattr(self.role_manager, 'session_timeout') or hasattr(self.role_manager, '_session_timeout')
            }
            
            # 3. Synchronization validation
            sync_issues = []
            
            # Check require_login synchronization
            if role_manager_require_login is not None:
                if settings_require_login != role_manager_require_login:
                    sync_issues.append(f"require_login mismatch: settings={settings_require_login}, role_manager={role_manager_require_login}")
            else:
                sync_issues.append("Could not validate require_login synchronization (role manager value unavailable)")
            
            # Check session_timeout synchronization
            if role_manager_session_timeout is not None:
                if settings_session_timeout != role_manager_session_timeout:
                    sync_issues.append(f"session_timeout mismatch: settings={settings_session_timeout}, role_manager={role_manager_session_timeout}")
            else:
                self.logger.info("session_timeout synchronization not validated (role manager value unavailable)")
            
            # Log validation results
            self.logger.info("=== Component Synchronization Validation ===")
            self.logger.info(f"Settings Manager: {validation_results['settings_manager']}")
            self.logger.info(f"Role Manager: {validation_results['role_manager']}")
            
            if sync_issues:
                self.logger.error(f"Synchronization issues: {sync_issues}")
                
                # Attempt to fix synchronization issues
                self.logger.info("Attempting to fix synchronization issues...")
                fix_success = self._sync_role_manager_with_settings()
                
                if fix_success:
                    # Re-validate after fix
                    post_fix_require_login = None
                    if hasattr(self.role_manager, 'get_require_login'):
                        try:
                            post_fix_require_login = self.role_manager.get_require_login()
                        except:
                            pass
                    
                    if post_fix_require_login == settings_require_login:
                        self.logger.info("Synchronization fix successful")
                        sync_issues = []  # Clear issues
                    else:
                        self.logger.error(f"Synchronization fix failed: still have mismatch")
                else:
                    self.logger.error("Synchronization fix failed")
            else:
                self.logger.info("All components are synchronized correctly")
            
            self.logger.info("=============================================")
            
            return len(sync_issues) == 0
            
        except Exception as e:
            self.logger.error(f"Error during component synchronization validation: {e}")
            return False
    
    def _sync_role_manager_with_settings(self):
        """
        ENHANCED: Synchronize role manager with settings using multiple strategies.
        
        Returns:
            bool: True if synchronization was successful
        """
        try:
            # Get current settings values with validation
            require_login = self.settings_manager.get_setting('require_login', False)
            session_timeout = self.settings_manager.get_setting('session_timeout', 600)
            
            # Validate settings types
            if not isinstance(require_login, bool):
                self.logger.warning(f"require_login has invalid type {type(require_login)}, converting")
                require_login = bool(require_login)
                self.settings_manager.set_setting('require_login', require_login, notify=False)
            
            if not isinstance(session_timeout, (int, float)) or session_timeout < 0:
                self.logger.warning(f"session_timeout has invalid value {session_timeout}, using 600")
                session_timeout = 600
                self.settings_manager.set_setting('session_timeout', session_timeout, notify=False)
            
            self.logger.info(f"Syncing role manager: require_login={require_login}, session_timeout={session_timeout}")
            
            # Strategy 1: Direct attribute setting (if available)
            sync_success = False
            
            if hasattr(self.role_manager, '_require_login'):
                old_value = getattr(self.role_manager, '_require_login', None)
                self.role_manager._require_login = require_login
                self.logger.info(f"Direct sync: require_login {old_value} -> {require_login}")
                sync_success = True
            
            if hasattr(self.role_manager, '_session_timeout'):
                self.role_manager._session_timeout = session_timeout
                self.logger.info(f"Direct sync: session_timeout -> {session_timeout}")
            
            # Strategy 2: Setter methods (if available)
            if hasattr(self.role_manager, 'set_require_login'):
                try:
                    self.role_manager.set_require_login(require_login)
                    self.logger.info(f"Setter sync: require_login -> {require_login}")
                    sync_success = True
                except Exception as e:
                    self.logger.warning(f"Setter sync failed for require_login: {e}")
            
            if hasattr(self.role_manager, 'set_session_timeout'):
                try:
                    self.role_manager.set_session_timeout(session_timeout)
                    self.logger.info(f"Setter sync: session_timeout -> {session_timeout}")
                except Exception as e:
                    self.logger.warning(f"Setter sync failed for session_timeout: {e}")
            
            # Strategy 3: Reload method (if available)
            if hasattr(self.role_manager, 'reload_from_settings'):
                try:
                    self.role_manager.reload_from_settings(self.settings_manager)
                    self.logger.info("Reload sync: role manager reloaded from settings")
                    sync_success = True
                except Exception as e:
                    self.logger.warning(f"Reload sync failed: {e}")
            
            # Validate synchronization worked
            if hasattr(self.role_manager, 'get_require_login'):
                try:
                    synced_value = self.role_manager.get_require_login()
                    if synced_value == require_login:
                        self.logger.info(f"Sync validation PASSED: {synced_value} == {require_login}")
                        sync_success = True
                    else:
                        self.logger.error(f"Sync validation FAILED: expected {require_login}, got {synced_value}")
                        sync_success = False
                except Exception as e:
                    self.logger.warning(f"Sync validation error: {e}")
            else:
                self.logger.warning("Role manager doesn't have get_require_login method for validation")
            
            return sync_success
            
        except Exception as e:
            self.logger.error(f"Error synchronizing role manager with settings: {e}")
            return False
    
    def _initialize_starting_tab_from_settings(self):
        """
        Initialize starting tab based on settings-derived login requirements.
        
        This method uses settings as the authoritative source for determining
        whether login is required, ensuring consistent behavior regardless of
        how the application was started.
        """
        try:
            # Get login requirement from settings (authoritative source)
            require_login = self.settings_manager.get_setting('require_login', False)
            
            # Log the decision basis
            self.logger.info(f"Determining starting tab - require_login from settings: {require_login}")
            
            # Check current authentication state
            is_authenticated = self.role_manager.is_authenticated()
            has_main_access = self.role_manager.has_tab_access("main")
            
            # Decision logic based on settings
            if require_login:
                if not is_authenticated:
                    self.logger.info("Login required and not authenticated - starting with login tab")
                    target_tab = "login"
                elif has_main_access:
                    self.logger.info("Login required, authenticated with main access - starting with main tab")
                    target_tab = "main"
                else:
                    self.logger.info("Login required, authenticated but no main access - re-authenticate")
                    target_tab = "login"
            else:
                # Login not required
                if has_main_access:
                    self.logger.info("Login not required and main accessible - starting with main tab")
                    target_tab = "main"
                else:
                    self.logger.info("Login not required but main not accessible - starting with login tab")
                    target_tab = "login"
            
            # Switch to determined tab
            self.switch_tab(target_tab)
            
            # Log final decision
            self.logger.info(f"Started with tab: {target_tab}")
            
        except Exception as e:
            self.logger.error(f"Error determining starting tab: {e}")
            # Safe fallback to login tab
            self.logger.info("Falling back to login tab due to error")
            self.switch_tab("login")
    
    def _log_initialization_completion(self):
        """
        Log detailed initialization state for debugging and monitoring.
        """
        try:
            state = {
                'settings_file_exists': os.path.exists(self.settings_manager.settings_file),
                'require_login_setting': self.settings_manager.get_setting('require_login'),
                'role_manager_require_login': self.role_manager.get_require_login(),
                'current_role': get_current_role() if hasattr(self, 'role_manager') else 'unknown',
                'is_authenticated': self.role_manager.is_authenticated() if hasattr(self, 'role_manager') else False,
                'has_main_access': self.role_manager.has_tab_access("main") if hasattr(self, 'role_manager') else False,
                'starting_tab': getattr(self, 'current_tab', 'not_set'),
                'physical_controls_available': hasattr(self, 'physical_controls') and self.physical_controls is not None,
                'gpio_worker_running': getattr(self, 'gpio_worker_running', False)
            }
            
            self.logger.info(f"MainWindow initialization completed successfully")
            self.logger.debug(f"Initialization state: {state}")
            
            # Validate consistency
            settings_login = state['require_login_setting']
            role_login = state['role_manager_require_login']
            
            if settings_login != role_login:
                self.logger.warning(f"Initialization completed with settings/role manager mismatch: {settings_login} vs {role_login}")
            else:
                self.logger.info("Settings and role manager are synchronized")
            
        except Exception as e:
            self.logger.error(f"Error logging initialization completion: {e}")
    
    def _setup_physical_state_sync(self):
        """Set up physical state synchronization."""
        # Current physical state tracking
        self.physical_state = {
            'test_running': False,
            'current_tab': None,
            'user_authenticated': False,
            'start_button_enabled': True,
            'stop_button_enabled': False,
            'status_led_mode': None
        }
        
        # State sync timer
        self.sync_timer_active = True
        self._schedule_state_sync()
        
        self.logger.info("Physical state synchronization initialized")
    
    def _schedule_state_sync(self):
        """Schedule periodic state synchronization."""
        if self.sync_timer_active:
            self._sync_physical_state()
            # Sync every 500ms
            self.root.after(500, self._schedule_state_sync)
    
    def _sync_physical_state(self):
        """Synchronize physical controls with current GUI state."""
        try:
            # Get current GUI state
            current_state = self._get_current_gui_state()
            
            # Check if sync is needed
            if self._state_needs_sync(current_state):
                self._apply_physical_state_changes(current_state)
                
        except Exception as e:
            self.logger.error(f"Error in state sync: {e}")
    
    
    def debug_physical_controls_state(self):
        """
        Debug method to check physical controls state and permissions.
        Call this method to diagnose physical control issues.
        """
        debug_info = {
            "require_login_setting": self.settings_manager.get_setting('require_login', False),
            "role_manager_require_login": self.role_manager.get_require_login() if hasattr(self, 'role_manager') else None,
            "is_authenticated": self.role_manager.is_authenticated() if hasattr(self, 'role_manager') else False,
            "has_main_access": self.role_manager.has_tab_access("main") if hasattr(self, 'role_manager') else False,
            "current_role": get_current_role() if hasattr(self, 'role_manager') else 'unknown',
            "current_tab": getattr(self, 'current_tab', None),
            "physical_controls_available": hasattr(self, 'physical_controls') and self.physical_controls is not None,
            "gpio_worker_running": getattr(self, 'gpio_worker_running', False),
            "physical_state": getattr(self, 'physical_state', {}),
            "current_gui_state": self._get_current_gui_state() if hasattr(self, '_get_current_gui_state') else {}
        }
        
        self.logger.info(f"Physical Controls Debug State: {debug_info}")
        
        # Check for common issues
        issues = []
        
        if not debug_info["physical_controls_available"]:
            issues.append("Physical controls not available or not initialized")
        
        if not debug_info["gpio_worker_running"]:
            issues.append("GPIO worker thread not running")
        
        if debug_info["require_login_setting"] != debug_info["role_manager_require_login"]:
            issues.append(f"Settings/RoleManager mismatch: {debug_info['require_login_setting']} vs {debug_info['role_manager_require_login']}")
        
        if not debug_info["has_main_access"]:
            issues.append("User does not have main tab access")
        
        gui_state = debug_info["current_gui_state"]
        if not gui_state.get("start_button_enabled", False) and not gui_state.get("stop_button_enabled", False):
            issues.append("Both physical buttons disabled - check authorization logic")
        
        if issues:
            self.logger.warning(f"Physical controls issues detected: {issues}")
        else:
            self.logger.info("No obvious physical controls issues detected")
        
        return debug_info
    
    
    def _get_current_gui_state(self) -> Dict[str, Any]:
        """
        Get current GUI state for synchronization.
        
        FIXED: Use authorization checks instead of authentication checks
        to support both require_login = True and require_login = False modes.
        """
        # Get test running state
        test_running = False
        if hasattr(self, 'current_tab') and self.current_tab == "main":
            tab_instance = self.tab_instances.get("main")
            if tab_instance and hasattr(tab_instance, 'test_running'):
                test_running = tab_instance.test_running
        
        # FIXED: Check authorization only, not authentication
        # This works correctly for both require_login = True and False
        user_has_main_access = (
            hasattr(self, 'role_manager') and 
            self.role_manager.has_tab_access("main")
        )
        
        # Get authentication state for status display (not for control access)
        is_authenticated = (
            hasattr(self, 'role_manager') and 
            self.role_manager.is_authenticated()
        )
        
        # Get test state if available
        test_state = "IDLE"
        if hasattr(self, 'current_tab') and self.current_tab == "main":
            tab_instance = self.tab_instances.get("main")
            if tab_instance and hasattr(tab_instance, 'get_test_state'):
                try:
                    test_state = tab_instance.get_test_state()
                except:
                    test_state = "IDLE"
        
        # Debug logging to help track issues
        self.logger.debug(f"Physical state check: has_main_access={user_has_main_access}, "
                         f"is_authenticated={is_authenticated}, test_running={test_running}, "
                         f"test_state={test_state}")
        
        return {
            'test_running': test_running,
            'current_tab': getattr(self, 'current_tab', None),
            'user_has_main_access': user_has_main_access,  # Use this for control access
            'is_authenticated': is_authenticated,  # Keep for status display
            'start_button_enabled': user_has_main_access and not test_running,
            'stop_button_enabled': user_has_main_access and test_running,
            'status_led_mode': self._get_status_led_mode_for_state(test_state)
        }
    
    def _get_status_led_mode_for_state(self, test_state: str) -> Optional[str]:
        """Get appropriate status LED mode for test state."""
        if test_state == "IDLE":
            return None
        elif test_state in ["FILLING", "REGULATING", "STABILIZING", "TESTING"]:
            return "blink-slow"
        elif test_state == "EMPTYING":
            return "blink-fast"
        elif test_state == "COMPLETE":
            return "solid"
        elif test_state == "ERROR":
            return "blink-fast"
        else:
            return None
    
    def _state_needs_sync(self, new_state: Dict[str, Any]) -> bool:
        """Check if physical state needs synchronization."""
        # Compare relevant fields
        for key in ['start_button_enabled', 'stop_button_enabled', 'status_led_mode']:
            if self.physical_state.get(key) != new_state.get(key):
                return True
        return False
    
    def _apply_physical_state_changes(self, new_state: Dict[str, Any]):
        """
        Apply changes to physical controls.
        
        FIXED: Updated to use the corrected state keys.
        """
        # Update start button if changed
        if self.physical_state.get('start_button_enabled') != new_state.get('start_button_enabled'):
            self._safe_gpio_command(
                "set_start_button_enabled", 
                new_state['start_button_enabled'],
                callback=lambda success, result: self.logger.debug(
                    f"Start button {'enabled' if new_state['start_button_enabled'] else 'disabled'}: {success}"
                )
            )
        
        # Update stop button if changed
        if self.physical_state.get('stop_button_enabled') != new_state.get('stop_button_enabled'):
            self._safe_gpio_command(
                "set_stop_button_enabled", 
                new_state['stop_button_enabled'],
                callback=lambda success, result: self.logger.debug(
                    f"Stop button {'enabled' if new_state['stop_button_enabled'] else 'disabled'}: {success}"
                )
            )
        
        # Update status LED if changed
        if self.physical_state.get('status_led_mode') != new_state.get('status_led_mode'):
            self._safe_gpio_command(
                "set_status_led", 
                new_state['status_led_mode'],
                callback=lambda success, result: self.logger.debug(
                    f"Status LED mode {new_state['status_led_mode']}: {success}"
                )
            )
        
        # Update stored state
        self.physical_state.update(new_state)
        
        # Log the state change for debugging
        self.logger.debug(f"Physical state updated: start_enabled={new_state.get('start_button_enabled')}, "
                         f"stop_enabled={new_state.get('stop_button_enabled')}, "
                         f"led_mode={new_state.get('status_led_mode')}")
    
    def _initialize_starting_tab(self):
        """
        DEPRECATED: Replaced by _initialize_starting_tab_from_settings.
        
        This method is kept for backward compatibility but just delegates
        to the new settings-based initialization.
        """
        self.logger.warning("_initialize_starting_tab called - delegating to _initialize_starting_tab_from_settings")
        self._initialize_starting_tab_from_settings()
    
    def _setup_application_style(self):
        """Set up application-wide styles and theme."""
        style = ttk.Style()
        
        # Use a cleaner theme as a base
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')
        
        # Configure common styles
        style.configure(
            'TFrame',
            background=UI_COLORS['BACKGROUND']
        )
        
        style.configure(
            'TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY'],
            font=UI_FONTS['LABEL']
        )
        
        style.configure(
            'TButton',
            background=UI_COLORS['PRIMARY'],
            foreground=UI_COLORS['SECONDARY'],
            font=UI_FONTS['BUTTON']
        )
        
        style.map(
            'TButton',
            background=[('active', UI_COLORS['PRIMARY'])]
        )
        
        style.configure(
            'TCheckbutton',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY'],
            font=UI_FONTS['LABEL']
        )
        
        style.configure(
            'TRadiobutton',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY'],
            font=UI_FONTS['LABEL']
        )
        
        # Add styles for settings sections
        style.configure(
            'Card.TFrame',
            background=UI_COLORS['BACKGROUND'],
            relief='solid',
            borderwidth=1
        )
        
        style.configure(
            'ContentTitle.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY'],
            font=UI_FONTS['HEADER']
        )
        
        # Loading styles
        style.configure(
            'Loading.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY'],
            font=UI_FONTS['HEADER']
        )
        
        style.configure(
            'LoadingFrame.TFrame',
            background=UI_COLORS['BACKGROUND'],
            relief='raised',
            borderwidth=2
        )
        
        # Tab button styles
        style.configure(
            'Nav.TButton',
            font=UI_FONTS['BUTTON'],
            padding=(15, 8)
        )
        
        style.configure(
            'Selected.Nav.TButton',
            font=UI_FONTS['BUTTON'],
            padding=(15, 8),
            background=UI_COLORS['PRIMARY'],
            foreground=UI_COLORS['SECONDARY']
        )
    
    def _setup_custom_events(self):
        """Set up custom events for tab switching."""
        # Define custom events
        custom_events = [
            "<<SwitchToLoginTab>>",
            "<<SwitchToMainTab>>",
            "<<SwitchToSettingsTab>>",
            "<<SwitchToCalibrationTab>>",
            "<<SwitchToReferenceTab>>"
        ]
        
        # Create events
        for event in custom_events:
            self.root.event_add(event, "None")
        
        # Bind event handlers
        self.root.bind("<<SwitchToLoginTab>>", lambda e: self.switch_tab("login"))
        self.root.bind("<<SwitchToMainTab>>", lambda e: self.switch_tab("main"))
        self.root.bind("<<SwitchToSettingsTab>>", lambda e: self.switch_tab("settings"))
        self.root.bind("<<SwitchToCalibrationTab>>", lambda e: self.switch_tab("calibration"))
        self.root.bind("<<SwitchToReferenceTab>>", lambda e: self.switch_tab("reference"))
    
    def _setup_hardware_buffer(self):
        """Create a buffer between hardware and UI to prevent blocking."""
        self.hardware_queue = queue.Queue()
        self.hardware_results = {}
        
        # Start worker thread
        self.hardware_thread = threading.Thread(
            target=self._hardware_worker,
            daemon=True,
            name="HardwareWorker"
        )
        self.hardware_thread.start()
        
        # Start processing results on UI thread
        self._process_hardware_results()
    
    def _hardware_worker(self):
        """Background thread to handle hardware interactions with retry logic."""
        retry_counts = {}  # Track retry attempts by task ID
        
        while True:
            try:
                # Get task from queue with timeout
                task_id, component, method, args, kwargs = self.hardware_queue.get(timeout=0.1)
                
                # Track retries
                retry_count = retry_counts.get(task_id, 0)
                
                # Execute task with retry logic
                try:
                    if hasattr(component, method):
                        result = getattr(component, method)(*args, **kwargs)
                        self.hardware_results[task_id] = (True, result)
                        # Clear retry count on success
                        if task_id in retry_counts:
                            del retry_counts[task_id]
                    else:
                        self.hardware_results[task_id] = (False, f"Method {method} not found")
                except Exception as e:
                    # Check if this is a retryable error (I/O errors often are)
                    if isinstance(e, (IOError, OSError)) and retry_count < 3:
                        # Requeue the task for retry
                        retry_counts[task_id] = retry_count + 1
                        self.logger.warning(f"Retrying hardware operation ({retry_count+1}/3): {e}")
                        self.hardware_queue.put((task_id, component, method, args, kwargs))
                    else:
                        # Max retries reached or non-retryable error
                        self.hardware_results[task_id] = (False, str(e))
                        if task_id in retry_counts:
                            del retry_counts[task_id]
                
                # Mark task as done
                self.hardware_queue.task_done()
                
            except queue.Empty:
                # No tasks in queue, just continue
                pass
            
            except Exception as e:
                self.logger.error(f"Error in hardware worker: {e}")
                time.sleep(0.1)
    
    def _process_hardware_results(self):
        """Process hardware results on the UI thread."""
        try:
            # Check if we have callbacks to process
            processed = []
            for task_id in list(self.hardware_results.keys()):
                success, result = self.hardware_results[task_id]
                
                # Call appropriate callback
                if task_id in self.hardware_callbacks:
                    callback = self.hardware_callbacks[task_id]
                    try:
                        callback(success, result)
                    except Exception as e:
                        self.logger.error(f"Error in hardware callback: {e}")
                    
                    # Remove processed callback
                    del self.hardware_callbacks[task_id]
                    processed.append(task_id)
            
            # Remove processed results
            for task_id in processed:
                del self.hardware_results[task_id]
        
        except Exception as e:
            self.logger.error(f"Error processing hardware results: {e}")
            
        finally:
            # Schedule next processing
            self.root.after(50, self._process_hardware_results)
    
    def call_hardware(self, component, method, *args, callback=None, **kwargs):
        """
        Queue a hardware call to be executed in the background.
        
        Args:
            component: Hardware component to call
            method: Method name to call
            *args: Positional arguments for the method
            callback: Optional callback to be called with result
            **kwargs: Keyword arguments for the method
            
        Returns:
            Task ID for tracking the request
        """
        # Generate unique task ID
        task_id = id(callback) if callback else time.time()
        
        # Store callback
        if callback:
            self.hardware_callbacks[task_id] = callback
            
        # Queue task
        self.hardware_queue.put((task_id, component, method, args, kwargs))
        
        return task_id

    @profile
    def init_application_components(self):
        """
        ENHANCED: Initialize application components with proper synchronization order.
        
        Returns:
            bool: True if initialization was successful
        """
        try:
            self.logger.info("=== Enhanced Application Component Initialization ===")
            
            # NOTE: SettingsManager already initialized in __init__ with validation
            
            # Log current settings state
            self.logger.info("Current settings state:")
            diagnostics = self.settings_manager.validate_settings_integrity()
            self.logger.info(f"  require_login: {diagnostics['require_login_value']} ({diagnostics['require_login_type']})")
            self.logger.info(f"  session_timeout: {diagnostics['session_timeout_value']} ({diagnostics['session_timeout_type']})")
            
            # Initialize hardware components (unchanged)
            self.logger.info("Initializing hardware components...")
            try:
                self.gpio_manager = GPIOManager()
                self.gpio_manager.initialize()
            except Exception as e:
                self.logger.warning(f"GPIO initialization failed: {e}. Using MockGPIOManager instead.")
                from multi_chamber_test.hardware.mock_gpio_manager import MockGPIOManager
                self.gpio_manager = MockGPIOManager()
                self.gpio_manager.initialize()
    
            # Initialize other hardware components
            self.pressure_sensor = PressureSensor()
            self.valve_controller = ValveController(self.gpio_manager)
            self.printer_manager = PrinterManager()
    
            # Initialize physical controls (unchanged)
            if PHYSICAL_CONTROLS_AVAILABLE:
                try:
                    self.physical_controls = PhysicalControls(self.gpio_manager)
                    if self.physical_controls.setup():
                        self.logger.info("Physical controls initialized successfully")
                        self.physical_controls.register_start_callback(self.on_physical_start)
                        self.physical_controls.register_stop_callback(self.on_physical_stop)
                    else:
                        self.logger.warning("Failed to set up physical controls")
                        self.physical_controls = None
                except Exception as e:
                    self.logger.warning(f"Physical controls initialization failed: {e}")
                    self.physical_controls = None
            else:
                self.logger.info("Physical controls not available on this system")
                self.physical_controls = None
    
            # Initialize databases (unchanged)
            self.reference_db = ReferenceDatabase()
            self.calibration_db = CalibrationDatabase()
    
            # Initialize core components (unchanged)
            self.test_logger = TestLogger()
    
            # Create TestManager
            self.test_manager = TestManager(
                self.valve_controller,
                self.pressure_sensor,
                self.printer_manager,
                self.reference_db,
                self.test_logger
            )
    
            # Create CalibrationManager
            self.calibration_manager = CalibrationManager(
                self.pressure_sensor,
                self.calibration_db,
                self.printer_manager
            )
    
            # CRITICAL SECTION: Role Manager Initialization and Synchronization
            self.logger.info("Initializing role manager with enhanced synchronization...")
            
            # Step 1: Get role manager instance
            self.role_manager = get_role_manager()
            self.logger.info("Role manager instance obtained")
            
            # Step 2: Pre-enhancement synchronization (critical timing)
            self.logger.info("Performing pre-enhancement synchronization...")
            pre_sync_success = self._sync_role_manager_with_settings()
            if not pre_sync_success:
                self.logger.warning("Pre-enhancement synchronization failed, continuing anyway")
            
            # Step 3: Enhance with observer pattern
            self.logger.info("Enhancing role manager with observer pattern...")
            enhance_role_manager(self.role_manager, self.settings_manager)
            
            # Step 4: Post-enhancement validation
            self.logger.info("Validating post-enhancement synchronization...")
            post_sync_success = self._validate_component_synchronization()
            if not post_sync_success:
                self.logger.error("Post-enhancement synchronization validation failed")
                
                # Final attempt at synchronization
                self.logger.info("Attempting final synchronization...")
                final_sync_success = self._sync_role_manager_with_settings()
                if final_sync_success:
                    # Final validation
                    final_validation = self._validate_component_synchronization()
                    if final_validation:
                        self.logger.info("Final synchronization successful")
                    else:
                        self.logger.error("Final synchronization still failed")
                else:
                    self.logger.error("Final synchronization attempt failed")
            
            # Set up observer pattern for test manager
            self.logger.info("Setting up test manager observer pattern...")
            enhance_test_manager(self.test_manager, self.settings_manager)
    
            # Final state logging
            self.logger.info("=== Final Component State ===")
            final_diagnostics = self.settings_manager.validate_settings_integrity()
            self.logger.info(f"Settings require_login: {final_diagnostics['require_login_value']}")
            
            if hasattr(self.role_manager, 'get_require_login'):
                try:
                    role_require_login = self.role_manager.get_require_login()
                    self.logger.info(f"Role manager require_login: {role_require_login}")
                    
                    if role_require_login == final_diagnostics['require_login_value']:
                        self.logger.info("? Settings and role manager are synchronized")
                    else:
                        self.logger.error("? Settings and role manager are NOT synchronized")
                except Exception as e:
                    self.logger.warning(f"Could not verify final role manager state: {e}")
            
            self.logger.info("Observer pattern connections established")
            self.logger.info("Application components initialized successfully")
            self.logger.info("================================================")
            
            return True
    
        except Exception as e:
            self.logger.error(f"Failed to initialize application components: {e}")
            messagebox.showerror(
                "Initialization Error",
                f"Failed to initialize application components: {e}\n\nThe application may not function correctly."
            )
            return False
    
    def create_ui_layout(self):
        """Create the main UI layout."""
        # Main content frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top bar with logo and title
        self.create_top_bar()
        
        # Navigation bar
        self.create_nav_bar()
        
        # Tab container frame
        self.tab_container = ttk.Frame(self.main_frame)
        self.tab_container.pack(fill=tk.BOTH, expand=True)
        
        # Initialize tabs
        self.tabs = {}
        self.tab_instances = {}
        
        # Create tab frames
        self.create_tabs()
        
        # Status bar
        self.create_status_bar()
    
    def create_top_bar(self):
        """Create the top bar with logo and title."""
        top_bar = ttk.Frame(self.main_frame)
        top_bar.pack(fill=tk.X, padx=10, pady=(10, 0))
        
        # Load logo if available
        try:
            if Image is not None:
                logo_image = Image.open(LOGO_PATH)
                # Resize image if needed
                max_height = 120
                width, height = logo_image.size
                if height > max_height:
                    ratio = max_height / height
                    new_width = int(width * ratio)
                    logo_image = logo_image.resize((new_width, max_height), Image.LANCZOS)
                
                logo_photo = ImageTk.PhotoImage(logo_image)
                logo_label = ttk.Label(top_bar, image=logo_photo, background=UI_COLORS['BACKGROUND'])
                logo_label.image = logo_photo  # Keep a reference to prevent garbage collection
                logo_label.pack(side=tk.LEFT)
            else:
                raise ImportError("PIL not available")
        except Exception as e:
            self.logger.warning(f"Could not load logo: {e}")
            # Fallback to text if logo can't be loaded
            ttk.Label(
                top_bar,
                text="Multi-Chamber Test",
                font=UI_FONTS['HEADER'],
                foreground=UI_COLORS['PRIMARY']
            ).pack(side=tk.LEFT)
        
        # Current time display (right-aligned)
        self.time_label = ttk.Label(
            top_bar,
            text="",
            font=UI_FONTS['SUBHEADER']
        )
        self.time_label.pack(side=tk.RIGHT)
        
        # Start clock update
        self.update_clock()
    
    def create_nav_bar(self):
        """Create navigation bar with tab buttons and proper permission checking."""
        nav_frame = ttk.Frame(self.main_frame)
        nav_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        
        # Define tab buttons - remove hardcoded access requirements
        self.tab_buttons = {}
        tabs_info = [
            {"name": "login", "label": "Login"},
            {"name": "main", "label": "Main"},
            {"name": "settings", "label": "Settings"},
            {"name": "calibration", "label": "Calibration"},
            {"name": "reference", "label": "Reference"}
        ]
        
        # Create buttons for each tab
        for tab in tabs_info:
            button = ttk.Button(
                nav_frame,
                text=tab["label"],
                style='Nav.TButton',
                command=lambda t=tab["name"]: self._safe_switch_tab(t)
            )
            button.pack(side=tk.LEFT, padx=(0, 10))
            self.tab_buttons[tab["name"]] = button
        
        # Update tab visibility based on current permissions
        self._update_tab_visibility()
    
    def create_tabs(self):
        """Create empty placeholders for tabs, but don't initialize them yet."""
        self.tabs = {}
        self.tab_instances = {}
        
        # Create tab frames only
        for tab_name in ["login", "main", "settings", "calibration", "reference"]:
            tab_frame = ttk.Frame(self.tab_container)
            self.tabs[tab_name] = tab_frame
    
    @profile
    def initialize_tab(self, tab_name):
        """Initialize a tab only when needed."""
        if tab_name not in self.tab_instances:
            self.logger.info(f"Initializing tab: {tab_name}")
            
            if tab_name == "login":
                self.tab_instances[tab_name] = LoginTab(
                    self.tabs[tab_name],
                    on_login_success=self.handle_login_success
                )
            elif tab_name == "main":
                self.tab_instances[tab_name] = MainTab(
                    self.tabs[tab_name],
                    self.test_manager,
                    self.settings_manager
                )
            elif tab_name == "settings":
                self.tab_instances[tab_name] = SettingsTab(
                    self.tabs[tab_name], 
                    self.test_manager,
                    self.settings_manager
                )
            elif tab_name == "calibration":
                # CORRECTED: Made initialization match CalibrationTab's expected parameters
                self.tab_instances[tab_name] = CalibrationTab(
                    self.tabs[tab_name],
                    self.calibration_manager,
                    self.pressure_sensor
                )
            elif tab_name == "reference":
                self.tab_instances[tab_name] = ReferenceTab(
                    self.tabs[tab_name],
                    self.reference_db,
                    self.test_manager
                )
                
            # Mark this tab as preloaded
            self.preloaded_tabs.add(tab_name)
            
        return self.tab_instances.get(tab_name)
    
    def create_status_bar(self):
        """Create status bar at the bottom of the window."""
        status_frame = ttk.Frame(self.main_frame, relief=tk.SUNKEN)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Left-aligned status message
        self.status_message = ttk.Label(
            status_frame,
            text="System Ready",
            padding=(10, 2)
        )
        self.status_message.pack(side=tk.LEFT)
        
        # Right-aligned user role display
        self.role_label = ttk.Label(
            status_frame,
            text="Role: Operator",
            padding=(10, 2)
        )
        self.role_label.pack(side=tk.RIGHT)
        
        # Logout button (if not in Operator role)
        self.logout_button = ttk.Button(
            status_frame,
            text="Logout",
            command=self.logout,
            width=10
        )
        # Only show logout button when authenticated
        # (will be updated by update_role_display)
        
        # Update role display initially
        self.update_role_display()
    
    def update_clock(self):
        """Update the clock display."""
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%Y-%m-%d")
        self.time_label.config(text=f"{current_date} {current_time}")
        
        # Schedule next update in 1 second
        self.root.after(1000, self.update_clock)
    
    def _safe_switch_tab(self, tab_name: str):
        """Safely switch tabs with permission checking."""
        try:
            # Check if user has access to the tab
            if not self.role_manager.has_tab_access(tab_name):
                messagebox.showwarning(
                    "Access Denied", 
                    f"You don't have permission to access the {tab_name.title()} tab."
                )
                return
            
            # Proceed with tab switch
            self.switch_tab(tab_name)
            
        except Exception as e:
            self.logger.error(f"Error in safe tab switch: {e}")
            self.update_status_message("Error switching tabs")
    
    def _update_tab_visibility(self):
        """Update tab button visibility based on current permissions."""
        try:
            for tab_name, button in self.tab_buttons.items():
                # Check if user has access to this tab
                if self.role_manager.has_tab_access(tab_name):
                    button.config(state='normal')
                    # Update button style if this is the current tab
                    if hasattr(self, 'current_tab') and self.current_tab == tab_name:
                        button.configure(style='Selected.Nav.TButton')
                    else:
                        button.configure(style='Nav.TButton')
                else:
                    button.config(state='disabled')
                    
        except Exception as e:
            self.logger.error(f"Error updating tab visibility: {e}")
    
    def update_role_display(self):
        """Update the current role display in the status bar with user info."""
        try:
            current_role = get_current_role()
            current_user = self.role_manager.get_current_username()
            
            # Build display text with user information
            if current_user:
                display_text = f"User: {current_user} ({current_role.title()})"
            else:
                display_text = f"Role: {current_role.title()}"
            
            self.role_label.config(text=display_text)
            
            # FIXED: Better logout button management
            # Show logout button if user is authenticated (not just checking role)
            if self.role_manager.is_authenticated():
                self.logout_button.pack(side=tk.RIGHT, padx=10)
            else:
                self.logout_button.pack_forget()
            
            # FIXED: Ensure tab visibility is updated when role changes
            self._update_tab_visibility()
            
            self.logger.debug(f"Role display updated: {display_text}, authenticated: {self.role_manager.is_authenticated()}")
            
        except Exception as e:
            self.logger.error(f"Error updating role display: {e}")
    
    def update_status_message(self, message: str):
        """Update the status bar message."""
        self.status_message.config(text=message)
    
    @profile
    def switch_tab(self, tab_name: str):
        """
        Enhanced tab switching with permission checking.
        
        Args:
            tab_name: Name of the tab to switch to
        """
        # Show immediate feedback for user experience
        self.update_status_message(f"Loading {tab_name.title()} tab...")
        
        # Check if user has access to the tab (except for login tab)
        if tab_name != "login" and not self.role_manager.has_tab_access(tab_name):
            # FIXED: Store original tab name BEFORE modifying it
            original_tab_name = tab_name
            
            # Special handling for restricted tabs
            if tab_name in ["calibration", "reference"]:
                messagebox.showwarning(
                    "Access Denied",
                    f"You don't have permission to access the {tab_name.title()} tab.\n\n"
                    f"Please contact an administrator for access."
                )
                # Stay on current tab
                if hasattr(self, 'current_tab') and self.current_tab:
                    self.update_status_message(f"Tab: {self.current_tab.title()}")
                return
            else:
                # For other tabs, redirect to login if required
                if self.role_manager.get_require_login():
                    self.update_status_message(f"Authentication required for {tab_name.title()}")
                    # FIXED: Store the ORIGINAL requested tab for after login
                    self.login_redirect_tab = original_tab_name
                    tab_name = "login"  # Now change to login tab
                else:
                    # Login not required but access denied - stay on current tab
                    if hasattr(self, 'current_tab') and self.current_tab:
                        self.update_status_message(f"Tab: {self.current_tab.title()}")
                    return

        # Check if tab exists
        if tab_name not in self.tabs:
            self.logger.error(f"Tab '{tab_name}' not found")
            return
        
        # Continue with existing tab switch logic...
        def execute_tab_switch():
            self.show_loading_screen(f"Loading {tab_name.title()} tab...")
            
            # Hide current tab first
            if hasattr(self, 'current_tab') and self.current_tab:
                current_tab_instance = self.tab_instances.get(self.current_tab)
                if current_tab_instance and hasattr(current_tab_instance, 'on_tab_deselected'):
                    try:
                        result = current_tab_instance.on_tab_deselected()
                        if result is False:
                            self.hide_loading_screen()
                            self.update_status_message(f"Tab: {self.current_tab.title()}")
                            return
                    except Exception as e:
                        self.logger.error(f"Error in on_tab_deselected: {e}")
                
                self.tabs[self.current_tab].pack_forget()
            
            # Initialize tab if needed
            if tab_name not in self.tab_instances:
                def complete_initialization():
                    self.initialize_tab(tab_name)
                    self._finish_tab_switch(tab_name)
                
                self.root.after(10, complete_initialization)
            else:
                self._finish_tab_switch(tab_name)
        
        self.root.after(10, execute_tab_switch)
    
    def _finish_tab_switch(self, tab_name):
        """Complete the tab switch process."""
        try:
            # Show the new tab
            self.tabs[tab_name].pack(fill=tk.BOTH, expand=True)
            self.current_tab = tab_name
            
            # Hide loading screen
            self.hide_loading_screen()
            
            # Call on_tab_selected in a separate event to avoid blocking
            def delayed_selection():
                tab_instance = self.tab_instances.get(tab_name)
                if tab_instance and hasattr(tab_instance, 'on_tab_selected'):
                    try:
                        tab_instance.on_tab_selected()
                    except Exception as e:
                        self.logger.error(f"Error in on_tab_selected: {e}")
            
            # Update UI state for the new tab
            self.update_tab_button_states()
            self.update_status_message(f"Tab: {tab_name.title()}")
            
            # Use a slight delay for tab selection to let the UI render first
            self.root.after(50, delayed_selection)
            
            # Force immediate state sync after tab switch
            self.root.after(100, self._sync_physical_state)
            
            # Start preloading other tabs if not already preloading
            if not self.preloading_active:
                self.root.after(1000, self.preload_tabs_in_background)
                
            self.logger.info(f"Successfully switched to tab {tab_name}")
            
        except Exception as e:
            self.logger.error(f"Error finishing tab switch to {tab_name}: {e}")
            self.hide_loading_screen()
            self.update_status_message("Error switching tabs")
    
    def update_tab_button_states(self):
        """Update the visual state of tab buttons based on current tab."""
        for name, button in self.tab_buttons.items():
            if name == self.current_tab:
                button.configure(style='Selected.Nav.TButton')
            else:
                button.configure(style='Nav.TButton')
    
    def preload_tabs_in_background(self):
        """Pre-initialize tabs in the background to improve switching performance."""
        if self.preloading_active:
            return  # Already preloading
            
        self.preloading_active = True
        tab_names = ["main", "settings", "calibration", "reference"]
        self.logger.info("Starting background tab initialization")
        
        def initialize_next_tab(index=0):
            try:
                if index >= len(tab_names):
                    self.logger.info("All tabs preloaded in background")
                    self.preloading_active = False
                    return
                
                tab_name = tab_names[index]
                if tab_name not in self.tab_instances and tab_name != self.current_tab:
                    self.logger.info(f"Background initializing: {tab_name}")
                    
                    # Create a separate function for initialization to avoid
                    # blocking the UI thread for too long
                    
                    # First, show a "preloading" indicator in the hidden tab
                    preload_frame = ttk.Frame(self.tabs[tab_name])
                    preload_frame.pack(fill=tk.BOTH, expand=True)
                    
                    preload_label = ttk.Label(
                        preload_frame,
                        text=f"Preloading {tab_name.title()} tab...",
                        style='Loading.TLabel'
                    )
                    preload_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
                    
                    # Define actual initialization function
                    def do_initialize():
                        try:
                            # Initialize the tab
                            self.initialize_tab(tab_name)
                            # Destroy preload indicator
                            preload_frame.destroy()
                            self.logger.info(f"Background initialization of {tab_name} complete")
                        except Exception as e:
                            self.logger.error(f"Error initializing tab {tab_name} in background: {e}")
                            
                        # Schedule next tab initialization
                        self.root.after(500, lambda: initialize_next_tab(index + 1))
                    
                    # Schedule initialization after a delay
                    self.root.after(100, do_initialize)
                else:
                    # Skip to next tab
                    self.root.after(100, lambda: initialize_next_tab(index + 1))
            except Exception as e:
                    self.logger.error(f"Error preloading tab {tab_names[index]}: {e}")
                    # Continue with next tab rather than stopping the entire process
                    self.root.after(100, lambda: initialize_next_tab(index + 1))
        
        # Start preloading
        initialize_next_tab()
    
    def show_loading_screen(self, message="Loading..."):
        """
        Show a loading screen overlay while switching tabs.
        
        Args:
            message: Message to display on the loading screen
        """
        # If loading frame already exists, just update message
        if hasattr(self, 'loading_toplevel') and self.loading_toplevel.winfo_exists():
            if hasattr(self, 'loading_message'):
                self.loading_message.config(text=message)
            return
        
        # Create a toplevel window for the loading screen
        self.loading_toplevel = tk.Toplevel(self.root)
        self.loading_toplevel.withdraw()  # Hide initially
        
        # Make it cover the main window
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        
        # Position the toplevel
        self.loading_toplevel.geometry(f"{width}x{height}+{x}+{y}")
        
        # Remove window decorations and make it semi-transparent
        self.loading_toplevel.overrideredirect(True)
        self.loading_toplevel.attributes('-alpha', 0.7)
        
        # Set background color
        self.loading_toplevel.configure(background='#333333')
        
        # Create the loading message container
        loading_container = tk.Frame(
            self.loading_toplevel,
            background=UI_COLORS['BACKGROUND'],
            borderwidth=2,
            relief=tk.RAISED
        )
        loading_container.place(
            relx=0.5, rely=0.5,
            anchor=tk.CENTER,
            width=400, height=150
        )
        
        # Add spinner animation
        self.spinner_text = tk.StringVar(value="?")
        spinner_label = tk.Label(
            loading_container,
            textvariable=self.spinner_text,
            font=('Helvetica', 24),
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY']
        )
        spinner_label.pack(pady=(20, 10))
        
        # Add message
        self.loading_message = tk.Label(
            loading_container,
            text=message,
            font=UI_FONTS['LABEL'],
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY']
        )
        self.loading_message.pack(pady=(10, 20))
        
        # Start spinner animation
        self._animate_spinner()
        
        # Show the loading overlay
        self.loading_toplevel.deiconify()
        self.loading_toplevel.lift()
        self.loading_toplevel.update()
    
    def _animate_spinner(self):
        """Animate the loading spinner."""
        if not hasattr(self, 'loading_toplevel') or not self.loading_toplevel.winfo_exists():
            return
            
        if not hasattr(self, 'spinner_text'):
            return
            
        # Spinner animation frames - braille pattern animation
        frames = ["?", "?", "?", "?", "?", "?", "?", "?"]
        
        # Get current frame index
        current_text = self.spinner_text.get()
        current_idx = frames.index(current_text) if current_text in frames else 0
        next_idx = (current_idx + 1) % len(frames)
        
        # Update spinner
        self.spinner_text.set(frames[next_idx])
        
        # Schedule next frame
        self.root.after(100, self._animate_spinner)
    
    def hide_loading_screen(self):
        """Hide the loading screen."""
        if hasattr(self, 'loading_toplevel') and self.loading_toplevel.winfo_exists():
            self.loading_toplevel.destroy()
            delattr(self, 'loading_toplevel')
    
    def handle_login_success(self, role=None):
        """Handle successful login with permission updates."""
        try:
            # Get updated user information
            current_user = self.role_manager.get_current_username()
            current_role = self.role_manager.get_current_role()
            
            # Log the login
            self.logger.info(f"Login success: {current_user} as {current_role}")
            
            # FIXED: Update UI components in correct order with delays
            def update_ui_after_login():
                # Update role display
                self.update_role_display()
                
                # Update tab visibility
                self._update_tab_visibility()
                
                # Display success message with user info
                if current_user:
                    self.update_status_message(f"Welcome {current_user} ({current_role})")
                else:
                    self.update_status_message(f"Logged in as {current_role}")
                
                # Force physical state sync after login
                self.root.after_idle(self._sync_physical_state)
            
            # Schedule UI update after a brief delay to ensure role manager is fully updated
            self.root.after(50, update_ui_after_login)
            
            # FIXED: Better redirect logic with delay
            def handle_tab_redirect():
                target_tab = None
                
                # Check if there's a redirect tab and it's accessible
                if hasattr(self, "login_redirect_tab") and self.login_redirect_tab:
                    if self.role_manager.has_tab_access(self.login_redirect_tab):
                        target_tab = self.login_redirect_tab
                        self.logger.info(f"Redirecting to requested tab: {target_tab}")
                    else:
                        self.logger.warning(f"Redirect tab {self.login_redirect_tab} not accessible after login")
                    # Clear the redirect tab
                    self.login_redirect_tab = None
                
                # If no valid redirect tab, go to main if accessible
                if not target_tab:
                    if self.role_manager.has_tab_access("main"):
                        target_tab = "main"
                    else:
                        # Find first accessible tab
                        for tab_name in ["settings", "calibration", "reference"]:
                            if self.role_manager.has_tab_access(tab_name):
                                target_tab = tab_name
                                break
                
                # Switch to the target tab
                if target_tab:
                    self.logger.info(f"Switching to tab after login: {target_tab}")
                    self.switch_tab(target_tab)
                else:
                    # Shouldn't happen, but stay on login if no accessible tabs
                    self.logger.warning("No accessible tabs found after login")
            
            # Schedule tab redirect after UI updates
            self.root.after(100, handle_tab_redirect)
                
        except Exception as e:
            self.logger.error(f"Error in login success handler: {e}")
            # Fallback: try to go to main tab after a delay
            def fallback_switch():
                try:
                    if self.role_manager.has_tab_access("main"):
                        self.switch_tab("main")
                    else:
                        self.logger.error("Cannot access main tab even after login")
                except Exception as fallback_error:
                    self.logger.error(f"Fallback tab switch also failed: {fallback_error}")
            
            self.root.after(200, fallback_switch)
    
    def logout(self):
        """Log out the current user with proper cleanup."""
        try:
            current_user = self.role_manager.get_current_username()
            
            # Confirm logout if user is authenticated
            if self.role_manager.is_authenticated():
                if not messagebox.askyesno("Logout", f"Are you sure you want to log out?"):
                    return
            
            # Perform logout
            self.role_manager.logout()
            
            # Update role display
            self.update_role_display()
            
            # Force physical state sync after logout
            self.root.after_idle(self._sync_physical_state)
            
            # Log the logout
            if current_user:
                self.logger.info(f"User logout: {current_user}")
                self.update_status_message(f"Logged out {current_user}")
            else:
                self.update_status_message("Logged out successfully")
            
            # Switch to appropriate tab after logout
            if self.role_manager.get_require_login():
                self.switch_tab("login")
            else:
                # Go to main tab if accessible with default role
                if self.role_manager.has_tab_access("main"):
                    self.switch_tab("main")
                else:
                    self.switch_tab("login")
                    
        except Exception as e:
            self.logger.error(f"Error in logout: {e}")
    
    def show_auth_dialog(self, min_role: str, on_success: Optional[Callable] = None):
        """
        Show authentication dialog for access to protected features.
        
        Args:
            min_role: Minimum role required
            on_success: Function to call on successful authentication
        """
        def auth_success():
            # Refresh the authentication session
            self.role_manager.refresh_session()
            
            # Update role display
            self.update_role_display()
            
            # Force physical state sync after authentication
            self.root.after_idle(self._sync_physical_state)
            
            # Call success callback if provided
            if on_success:
                on_success()
        
        # Show password dialog
        PasswordDialog(
            self.root,
            min_role,
            on_success=auth_success
        )
    
    # FIXED: Thread-safe button handlers
    def on_physical_start(self):
        """
        Thread-safe physical start button handler.
        
        FIXED: Consistent authorization check (no authentication requirement).
        """
        self.logger.info("Physical start button pressed")
        
        def handle_start_button():
            """Handle start button press on GUI thread."""
            try:
                # FIXED: Use consistent authorization check
                if not (hasattr(self, 'role_manager') and 
                       self.role_manager.has_tab_access("main")):
                    self.logger.warning("Physical start button denied - insufficient permissions")
                    
                    # Flash LED to indicate denied access
                    def on_deny_led_set(success, result):
                        if success:
                            # Turn off LED after 2 seconds
                            self.root.after(2000, lambda: self._safe_gpio_command("set_status_led", None))
                    
                    self._safe_gpio_command("set_status_led", "blink-fast", callback=on_deny_led_set)
                    return
                
                # Handle based on current tab
                if hasattr(self, 'current_tab') and self.current_tab == "main":
                    tab_instance = self.tab_instances.get("main")
                    if tab_instance and hasattr(tab_instance, 'start_test'):
                        try:
                            # Start test
                            tab_instance.start_test()
                            self.logger.info("Test started via physical button")
                            
                            # Force immediate state sync
                            self.root.after_idle(self._sync_physical_state)
                            
                        except Exception as e:
                            self.logger.error(f"Error starting test via physical button: {e}")
                            
                            # Flash LED to indicate error
                            def on_error_led_set(success, result):
                                if success:
                                    self.root.after(3000, lambda: self._safe_gpio_command("set_status_led", None))
                            
                            self._safe_gpio_command("set_status_led", "blink-fast", callback=on_error_led_set)
                else:
                    # Switch to main tab if accessible
                    if (hasattr(self, 'role_manager') and 
                        self.role_manager.has_tab_access("main")):
                        self.switch_tab("main")
                        # Sync state after tab switch
                        self.root.after(100, self._sync_physical_state)
                        
            except Exception as e:
                self.logger.error(f"Error handling physical start button: {e}")
        
        # Schedule on GUI thread to avoid race conditions
        self.root.after_idle(handle_start_button)
    
    def on_physical_stop(self):
        """
        Thread-safe physical stop button handler.
        
        FIXED: Consistent authorization check (no authentication requirement).
        """
        self.logger.info("Physical stop button pressed")
        
        def handle_stop_button():
            """Handle stop button press on GUI thread."""
            try:
                # FIXED: Use consistent authorization check
                if not (hasattr(self, 'role_manager') and 
                       self.role_manager.has_tab_access("main")):
                    self.logger.warning("Physical stop button denied - insufficient permissions")
                    
                    # Flash LED to indicate denied access
                    def on_deny_led_set(success, result):
                        if success:
                            self.root.after(2000, lambda: self._safe_gpio_command("set_status_led", None))
                    
                    self._safe_gpio_command("set_status_led", "blink-fast", callback=on_deny_led_set)
                    return
                
                # Get main tab instance
                tab_instance = self.tab_instances.get("main")
                if tab_instance and hasattr(tab_instance, 'stop_test'):
                    try:
                        tab_instance.stop_test()
                        self.logger.info("Test stopped via physical button")
                        
                        # Force immediate state sync
                        self.root.after_idle(self._sync_physical_state)
                        
                        # Switch to main tab if not already there
                        if (hasattr(self, 'current_tab') and self.current_tab != "main" and
                            hasattr(self, 'role_manager') and self.role_manager.has_tab_access("main")):
                            self.switch_tab("main")
                            
                    except Exception as e:
                        self.logger.error(f"Error stopping test via physical button: {e}")
                        
                        # Flash LED to indicate error
                        def on_error_led_set(success, result):
                            if success:
                                self.root.after(3000, lambda: self._safe_gpio_command("set_status_led", None))
                        
                        self._safe_gpio_command("set_status_led", "blink-fast", callback=on_error_led_set)
                else:
                    self.logger.debug("Physical stop button pressed but main tab not available")
                    
            except Exception as e:
                self.logger.error(f"Error handling physical stop button: {e}")
        
        # Schedule on GUI thread
        self.root.after_idle(handle_stop_button)
    
    # DEPRECATED: These methods are replaced by automatic state sync
    def _update_physical_button_states(self):
        """DEPRECATED: Use automatic state sync instead."""
        self.logger.debug("_update_physical_button_states called - using automatic sync")
        # Force a sync cycle
        if hasattr(self, '_sync_physical_state'):
            self.root.after_idle(self._sync_physical_state)
    
    def update_physical_controls_from_test_state(self, test_state: str, test_running: bool):
        """DEPRECATED: Use automatic state sync instead."""
        self.logger.debug("update_physical_controls_from_test_state called - using automatic sync")
        # Force a sync cycle
        if hasattr(self, '_sync_physical_state'):
            self.root.after_idle(self._sync_physical_state)
    
    def _safe_set_status_led(self, mode):
        """DEPRECATED: Use _safe_gpio_command instead."""
        self.logger.debug(f"_safe_set_status_led called with mode: {mode} - using _safe_gpio_command")
        self._safe_gpio_command("set_status_led", mode)
    
    def bind_key_events(self):
        """Bind global key events with permission checks."""
        # Escape key to exit fullscreen
        self.root.bind('<Escape>', self.toggle_fullscreen)
        
        # Function keys for tab switching (with permission checks)
        self.root.bind('<F1>', lambda e: self._safe_switch_tab("main"))
        self.root.bind('<F2>', lambda e: self._safe_switch_tab("settings"))
        self.root.bind('<F3>', lambda e: self._safe_switch_tab("calibration"))
        self.root.bind('<F4>', lambda e: self._safe_switch_tab("reference"))
        self.root.bind('<F9>', lambda e: self._safe_switch_tab("login"))
        
        # F10 to logout
        self.root.bind('<F10>', lambda e: self.logout())
        
        # Home key to return to main tab
        self.root.bind('<Home>', lambda e: self._safe_switch_tab("main"))
    
    def test_physical_controls(self):
        """Test physical controls functionality with thread-safe operations."""
        if not self.physical_controls:
            self.logger.warning("Cannot test physical controls - not available")
            return False
        
        try:
            self.logger.info("Testing physical controls...")
            
            # Test LEDs with safe GPIO commands
            test_sequence = [
                ("solid", 1000),     # 1 second
                ("blink-slow", 2000), # 2 seconds
                ("blink-fast", 2000), # 2 seconds
                (None, 1000)         # 1 second off
            ]
            
            def run_test_sequence(index=0):
                if index >= len(test_sequence):
                    # Test complete, test button LEDs
                    self._test_button_leds()
                    return
                
                mode, duration = test_sequence[index]
                
                def on_led_set(success, result):
                    if success:
                        # Schedule next test after duration
                        self.root.after(duration, lambda: run_test_sequence(index + 1))
                    else:
                        self.logger.error(f"Failed to set LED mode {mode}")
                        run_test_sequence(index + 1)
                
                self._safe_gpio_command("set_status_led", mode, callback=on_led_set)
            
            # Start test sequence
            run_test_sequence()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error testing physical controls: {e}")
            return False
    
    def _test_button_leds(self):
        """Test button LEDs as part of physical controls test."""
        def test_start_button():
            def on_start_enabled(success, result):
                if success:
                    # Enable stop button after 1 second
                    self.root.after(1000, test_stop_button)
                else:
                    test_stop_button()
            
            self._safe_gpio_command("set_start_button_enabled", True, callback=on_start_enabled)
        
        def test_stop_button():
            def on_stop_enabled(success, result):
                if success:
                    # Reset to normal state after 1 second
                    self.root.after(1000, reset_to_normal)
                else:
                    reset_to_normal()
            
            self._safe_gpio_command("set_stop_button_enabled", True, callback=on_stop_enabled)
        
        def reset_to_normal():
            # Reset both buttons to disabled
            self._safe_gpio_command("set_start_button_enabled", False)
            self._safe_gpio_command("set_stop_button_enabled", False)
            
            # Force state sync after test
            self.root.after(1000, self._sync_physical_state)
            
            self.logger.info("Physical controls test completed")
        
        # Start button LED test
        test_start_button()
    
    def get_physical_controls_status(self) -> dict:
        """Get status of physical controls for debugging."""
        if not self.physical_controls:
            return {'available': False, 'reason': 'Physical controls not initialized'}
        
        try:
            status = self.physical_controls.get_status()
            status['available'] = True
            
            # Add GPIO worker status
            status['gpio_worker'] = {
                'running': getattr(self, 'gpio_worker_running', False),
                'queue_size': self.gpio_command_queue.qsize() if hasattr(self, 'gpio_command_queue') else 0,
                'callbacks_pending': len(self.gpio_callbacks) if hasattr(self, 'gpio_callbacks') else 0
            }
            
            # Add physical state
            status['physical_state'] = getattr(self, 'physical_state', {})
            
            return status
        except Exception as e:
            return {'available': False, 'error': str(e)}
    
    def debug_login_state(self):
        """Debug method to check login and tab access state."""
        debug_info = {
            "is_authenticated": self.role_manager.is_authenticated(),
            "current_role": get_current_role(),
            "current_user": self.role_manager.get_current_username(),
            "require_login": self.role_manager.get_require_login(),
            "current_tab": getattr(self, 'current_tab', None),
            "login_redirect_tab": getattr(self, 'login_redirect_tab', None),
            "tab_access": {},
            "physical_controls_status": self.get_physical_controls_status()
        }
        
        # Check access to each tab
        for tab_name in ["login", "main", "settings", "calibration", "reference"]:
            try:
                debug_info["tab_access"][tab_name] = self.role_manager.has_tab_access(tab_name)
            except Exception as e:
                debug_info["tab_access"][tab_name] = f"Error: {e}"
        
        self.logger.info(f"Debug State: {debug_info}")
        return debug_info
    
    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode."""
        is_fullscreen = bool(self.root.attributes('-fullscreen'))
        self.root.attributes('-fullscreen', not is_fullscreen)
        
        # Show cursor if exiting fullscreen
        if is_fullscreen:
            self.root.config(cursor="")
        else:
            self.root.config(cursor="none")
    
    def on_exit(self):
        """Handle application exit."""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.cleanup()
            self.root.destroy()
    
    def cleanup(self):
        """Enhanced cleanup with proper thread management."""
        self.logger.info("Cleaning up resources...")
        
        try:
            # Stop state synchronization
            self.sync_timer_active = False
            
            # Stop GPIO worker thread
            if hasattr(self, 'gpio_worker_running'):
                self.gpio_worker_running = False
                
                # Signal worker to stop
                try:
                    self.gpio_command_queue.put_nowait((None, "STOP", (), {}))
                except queue.Full:
                    pass
                
                # Wait for worker to finish
                if hasattr(self, 'gpio_worker_thread'):
                    self.gpio_worker_thread.join(timeout=2.0)
                    if self.gpio_worker_thread.is_alive():
                        self.logger.warning("GPIO worker thread did not terminate gracefully")
            
            # Stop background loading
            self.preloading_active = False
            
            # Clean up tabs
            for tab_name, tab_instance in self.tab_instances.items():
                if hasattr(tab_instance, 'cleanup'):
                    try:
                        tab_instance.cleanup()
                    except Exception as e:
                        self.logger.error(f"Error cleaning up {tab_name} tab: {e}")
            
            # Clean up hardware buffer
            if hasattr(self, 'hardware_queue'):
                try:
                    # Clear queue
                    while not self.hardware_queue.empty():
                        try:
                            self.hardware_queue.get_nowait()
                            self.hardware_queue.task_done()
                        except:
                            break
                except:
                    pass
            
            # Clean up hardware
            try:
                if hasattr(self, 'valve_controller'):
                    # Close all valves
                    for i in range(3):
                        self.valve_controller.stop_chamber(i)
                        
                # Clean up physical controls (this will stop its own threads)
                if hasattr(self, 'physical_controls') and self.physical_controls:
                    self.physical_controls.cleanup()
                    
                # Final GPIO cleanup
                if hasattr(self, 'gpio_manager'):
                    self.gpio_manager.cleanup()
                    
            except Exception as e:
                self.logger.error(f"Error during hardware cleanup: {e}")
            
            # Save settings before exit
            if hasattr(self, 'settings_manager'):
                self.settings_manager.save_settings()
                
            self.logger.info("Cleanup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Run the application main loop."""
        self.logger.info("Starting application main loop")
        self.root.mainloop()


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to log unhandled exceptions."""
    logger = logging.getLogger('ExceptionHandler')
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Show error message to user
    error_message = f"An unhandled error occurred: {exc_type.__name__}: {exc_value}"
    try:
        messagebox.showerror("Application Error", error_message)
    except:
        # If even showing a messagebox fails, print to console
        print(f"CRITICAL ERROR: {error_message}")