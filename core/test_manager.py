#!/usr/bin/env python
# -*- coding: utf-8 -*-


import logging
import threading
import time
import numpy as np
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from multi_chamber_test.config.constants import TIME_DEFAULTS, PRESSURE_DEFAULTS, TEST_STATES
from multi_chamber_test.hardware.valve_controller import ValveController
from multi_chamber_test.hardware.pressure_sensor import PressureSensor
from multi_chamber_test.hardware.printer import PrinterManager
from multi_chamber_test.database.reference_db import ReferenceDatabase
from multi_chamber_test.database.test_result_db import TestResultDatabase
from multi_chamber_test.core.logger import TestLogger


class ChamberPhase(Enum):
    """Enum representing chamber test phases"""
    IDLE = 0
    FILLING = 1
    REGULATING = 2
    STABILIZING = 3
    TESTING = 4
    EMPTYING = 5
    COMPLETE = 6


class ChamberTestState:
    """
    State container for an individual chamber during testing.
    """
    
    def __init__(self, chamber_index: int):
        """
        Initialize the chamber state.
        
        Args:
            chamber_index: Index of the chamber (0-2)
        """
        self.chamber_index = chamber_index  # 0-based index
        
        # Chamber parameters
        self.enabled = True
        self.pressure_target = PRESSURE_DEFAULTS['TARGET']
        self.pressure_threshold = PRESSURE_DEFAULTS['THRESHOLD']
        self.pressure_tolerance = PRESSURE_DEFAULTS['TOLERANCE']
        
        # Test state
        self.current_pressure = 0.0
        self.start_pressure = 0.0
        self.final_pressure = 0.0
        self.mean_pressure = 0.0
        self.pressure_std = 0.0
        self.result = None
        
        # Phase tracking
        self.phase = ChamberPhase.IDLE
        self.test_complete = False
        
        # State tracking for concurrent execution
        self.regulation_state = 'idle'  # 'filling', 'venting', 'stable'
        self.last_pressure = None
        self.pressure_rates = []
        self.consecutive_stable = 0
        self.pressure_readings = []
        
        # Timing
        self.fill_start_time = None
        self.stability_achieved = False

    def reset(self):
        """Reset the chamber state for a new test."""
        self.current_pressure = 0.0
        self.start_pressure = 0.0
        self.final_pressure = 0.0
        self.mean_pressure = 0.0
        self.pressure_std = 0.0
        self.result = None
        self.pressure_readings = []
        
        self.phase = ChamberPhase.IDLE
        self.test_complete = False
        self.stability_achieved = False
        
        # Reset concurrent execution state
        self.regulation_state = 'idle'
        self.last_pressure = None
        self.pressure_rates = []
        self.consecutive_stable = 0
        
        # Reset timing
        self.fill_start_time = None


class TestManager:

    
    def __init__(self, 
                 valve_controller: ValveController,
                 pressure_sensor: PressureSensor,
                 printer_manager: Optional[PrinterManager] = None,
                 reference_db: Optional[ReferenceDatabase] = None,
                 test_logger: Optional[TestLogger] = None):

        self.logger = logging.getLogger('TestManager')
        self._setup_logger()
        
        self.valve_controller = valve_controller
        self.pressure_sensor = pressure_sensor
        self.printer_manager = printer_manager
        self.reference_db = reference_db
        self.test_logger = test_logger or TestLogger()
        
        # Direct TestResultDatabase usage
        self.test_result_db = TestResultDatabase()
        
        # ADDED: Thread safety locks
        self._valve_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._database_lock = threading.Lock()
        self._stop_lock = threading.Lock()
        
        # Callbacks
        self.on_test_started: Callable[[], None] = lambda: None
        self.on_test_finished: Callable[[], None] = lambda: None
        
        # Test parameters
        self.test_mode = "manual"  # "manual" or "reference"
        self.current_reference = None
        self.test_duration = TIME_DEFAULTS['TEST_DURATION']
        self.require_login = False
        
        # Adaptive control parameters
        self.FAST_MODE = {
            'threshold': 10.0,  # mbar from target for fast mode
            'pulse_on': 0.1,    # seconds
            'pulse_off': 0.05   # seconds
        }
        
        self.MEDIUM_MODE = {
            'threshold': 5.0,   # mbar from target for medium mode
            'pulse_on': 0.05,   # seconds
            'pulse_off': 0.1    # seconds
        }
        
        self.FINE_MODE = {
            'threshold': 1.0,   # mbar from target for fine mode
            'pulse_on': 0.02,   # seconds
            'pulse_off': 0.2    # seconds
        }
        
        self.base_tolerance = 0.1  # Base tolerance for pressure regulation
        
        # Timing parameters
        self.fill_timeout = 60
        self.stability_duration = 25
        self.regulation_timeout = 60
        self.emptying_duration = 10
        
        # Test state - protected by _state_lock
        self.chamber_states = [ChamberTestState(i) for i in range(3)]
        self.test_state = "IDLE"
        self.test_phase = None
        self.elapsed_time = 0.0
        self.running_test = False
        self._stop_requested = False
        self._emptying_in_progress = False
        
        # User information for current test
        self.current_user = None
        self.current_user_id = None
        
        # Monitoring thread
        self.monitoring_thread = None
        self._monitoring_running = False
        
        # Test execution thread
        self.test_thread = None
        
        # Callbacks for UI updates
        self.status_callback = None
        self.progress_callback = None
        self.result_callback = None
                
        # Database save tracking
        self._database_save_completed = False
        
        # Error tracking
        self._consecutive_sensor_errors = 0
        self._max_consecutive_errors = 5
    
    def _setup_logger(self):
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def set_callbacks(self, status_callback: Optional[Callable] = None,
                     progress_callback: Optional[Callable] = None,
                     result_callback: Optional[Callable] = None):
        with self._state_lock:
            self.status_callback = status_callback
            self.progress_callback = progress_callback
            self.result_callback = result_callback
    
    def set_test_mode(self, mode: str, reference: Optional[str] = None) -> bool:
        with self._state_lock:
            if self.running_test:
                self.logger.error("Cannot change mode during active test")
                return False
                
            if mode not in ["manual", "reference"]:
                self.logger.error(f"Invalid test mode: {mode}")
                return False
                
            self.test_mode = mode
            
            if mode == "reference":
                if not reference:
                    self.logger.error("Reference barcode required for reference mode")
                    return False
                    
                if self.reference_db:
                    # Load reference from database
                    ref_data = self.reference_db.load_reference(reference)
                    if not ref_data:
                        self.logger.error(f"Reference not found: {reference}")
                        return False
                        
                    # Apply reference parameters
                    self.current_reference = reference
                    self.test_duration = ref_data.get('test_duration', TIME_DEFAULTS['TEST_DURATION'])
                    
                    # Apply chamber-specific parameters
                    chamber_data = ref_data.get('chambers', [])
                    for i, chamber in enumerate(chamber_data):
                        if i < len(self.chamber_states):
                            self.chamber_states[i].enabled = chamber.get('enabled', True)
                            self.chamber_states[i].pressure_target = chamber.get('pressure_target', PRESSURE_DEFAULTS['TARGET'])
                            self.chamber_states[i].pressure_threshold = chamber.get('pressure_threshold', PRESSURE_DEFAULTS['THRESHOLD'])
                            self.chamber_states[i].pressure_tolerance = chamber.get('pressure_tolerance', PRESSURE_DEFAULTS['TOLERANCE'])
                else:
                    self.logger.warning("Reference database not available")
                    return False
                    
            else:  # manual mode
                self.current_reference = None
            
            self.logger.info(f"Test mode set to {mode}" + (f" with reference {reference}" if reference else ""))
            return True
    
    def set_chamber_parameters(self, chamber_index: int, params: Dict[str, Any]) -> bool:
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}")
            return False
            
        with self._state_lock:
            if self.running_test:
                self.logger.error("Cannot change parameters during active test")
                return False
                
            chamber = self.chamber_states[chamber_index]
            
            if 'enabled' in params:
                chamber.enabled = bool(params['enabled'])
                
            if 'pressure_target' in params:
                target = float(params['pressure_target'])
                if 0 <= target <= PRESSURE_DEFAULTS['MAX_PRESSURE']:
                    chamber.pressure_target = target
                else:
                    self.logger.error(f"Invalid target pressure: {target}")
                    return False
                    
            if 'pressure_threshold' in params:
                threshold = float(params['pressure_threshold'])
                if threshold >= 0:
                    chamber.pressure_threshold = threshold
                else:
                    self.logger.error(f"Invalid threshold pressure: {threshold}")
                    return False
                    
            if 'pressure_tolerance' in params:
                tolerance = float(params['pressure_tolerance'])
                if tolerance >= 0:
                    chamber.pressure_tolerance = tolerance
                else:
                    self.logger.error(f"Invalid pressure tolerance: {tolerance}")
                    return False
        
        self.logger.info(f"Updated parameters for chamber {chamber_index + 1}")
        return True
    
    def get_test_status(self) -> Dict[str, Any]:
        with self._state_lock:
            chamber_info = []
            for chamber in self.chamber_states:
                chamber_info.append({
                    'index': chamber.chamber_index,
                    'enabled': chamber.enabled,
                    'pressure_target': chamber.pressure_target,
                    'pressure_threshold': chamber.pressure_threshold,
                    'pressure_tolerance': chamber.pressure_tolerance,
                    'current_pressure': chamber.current_pressure,
                    'phase': chamber.phase.name if hasattr(chamber, 'phase') else 'UNKNOWN',
                    'stability_achieved': chamber.stability_achieved,
                    'result': chamber.result if self.test_state == 'COMPLETE' else None
                })
                
            return {
                'test_mode': self.test_mode,
                'reference': self.current_reference,
                'test_state': self.test_state,
                'test_phase': self.test_phase,
                'elapsed_time': self.elapsed_time,
                'total_duration': self.test_duration,
                'running': self.running_test,
                'chambers': chamber_info
            }
    
    def _validate_hardware_connections(self) -> bool:
        errors = []
        
        # Test valve controller
        try:
            for i in range(3):
                with self._valve_lock:
                    self.valve_controller.set_chamber_valves(i, False, False)
                    time.sleep(0.01)  # Small delay for hardware response
        except Exception as e:
            errors.append(f"Valve controller error: {e}")
        
        # Test pressure sensor
        try:
            pressures = self._read_pressures_with_retry(max_retries=2)
            if not pressures:
                errors.append("Pressure sensor not responding")
        except Exception as e:
            errors.append(f"Pressure sensor error: {e}")
        
        # Test database connection (if method exists)
        try:
            if hasattr(self.test_result_db, '_test_connection'):
                self.test_result_db._test_connection()
        except Exception as e:
            errors.append(f"Database connection error: {e}")
        
        if errors:
            for error in errors:
                self.logger.error(f"Hardware validation: {error}")
            return False
        
        self.logger.info("Hardware validation successful")
        return True
    
    def _read_pressures_with_retry(self, max_retries: int = 3) -> Optional[List[float]]:
        for attempt in range(max_retries):
            try:
                pressures = self.pressure_sensor.read_all_pressures()
                if pressures and len(pressures) >= 3:
                    # Validate pressure values
                    valid_pressures = []
                    for p in pressures[:3]:  # Only take first 3
                        if p is not None and 0 <= p <= 2000:  # Reasonable pressure range
                            valid_pressures.append(p)
                        else:
                            valid_pressures.append(0.0)  # Default to 0 for invalid readings
                    
                    self._consecutive_sensor_errors = 0  # Reset error counter
                    return valid_pressures
                    
                self.logger.warning(f"Invalid pressure reading attempt {attempt + 1}: {pressures}")
                
            except Exception as e:
                self.logger.error(f"Pressure read error attempt {attempt + 1}: {e}")
                
            if attempt < max_retries - 1:
                time.sleep(0.1)
        
        self._consecutive_sensor_errors += 1
        self.logger.error(f"All pressure reading attempts failed (consecutive errors: {self._consecutive_sensor_errors})")
        return None
    
    def start_test(self) -> bool:
        with self._state_lock:
            if self.running_test:
                self.logger.error("Test already in progress")
                return False
                
            if self.test_mode == "reference" and not self.current_reference:
                self.logger.error("No reference loaded for reference mode")
                return False
                
            # Check if any chambers are enabled
            enabled_chambers = [ch for ch in self.chamber_states if ch.enabled]
            if not enabled_chambers:
                self.logger.error("No chambers enabled for testing")
                return False
        
        # Validate hardware before starting
        if not self._validate_hardware_connections():
            self.logger.error("Hardware validation failed - cannot start test")
            return False
        
        # Get current user info if available
        try:
            from multi_chamber_test.core.roles import get_role_manager
            role_manager = get_role_manager()
            if role_manager.is_authenticated():
                user_info = role_manager.get_current_user_info()
                if user_info:
                    self.current_user = user_info.get('username')
                    self.current_user_id = user_info.get('id_number')
        except ImportError:
            self.logger.warning("Role manager not available")
        
        # Validate test configuration
        try:
            self._validate_test_configuration()
        except ValueError as e:
            self.logger.error(f"Test configuration invalid: {e}")
            return False
        
        # Initialize test state
        with self._state_lock:
            self._stop_requested = False
            self._emptying_in_progress = False
            self.running_test = True
            self.test_state = "IDLE"
            self.test_phase = None
            self.elapsed_time = 0.0
            self._database_save_completed = False
            self._consecutive_sensor_errors = 0
            
            for chamber in self.chamber_states:
                chamber.reset()
        
        # Close all solenoids initially
        try:
            with self._valve_lock:
                for i in range(3):
                    self.valve_controller.set_chamber_valves(i, False, False)
        except Exception as e:
            self.logger.error(f"Failed to initialize valves: {e}")
            with self._state_lock:
                self.running_test = False
            return False
        
        # Call the test started callback
        try:
            self.on_test_started()
        except Exception as e:
            self.logger.error(f"Error in test started callback: {e}")
        
        # Start test in a separate thread
        self.test_thread = threading.Thread(target=self._run_concurrent_test, daemon=True)
        self.test_thread.start()
        
        self.logger.info("Test started successfully")
        return True
    
    def _validate_test_configuration(self):
        with self._state_lock:
            active_chambers = [i for i in range(3) if self.chamber_states[i].enabled]
            if not active_chambers:
                raise ValueError("No chambers enabled for testing")
                
            if self.test_mode == "reference" and not self.current_reference:
                raise ValueError("Reference required for reference mode")
                
            # Validate pressure parameters
            for chamber in self.chamber_states:
                if chamber.enabled:
                    if chamber.pressure_target <= 0:
                        raise ValueError(f"Invalid target pressure for chamber {chamber.chamber_index + 1}")
                    if chamber.pressure_threshold < 0:
                        raise ValueError(f"Invalid threshold pressure for chamber {chamber.chamber_index + 1}")
                    if chamber.pressure_tolerance <= 0:
                        raise ValueError(f"Invalid tolerance for chamber {chamber.chamber_index + 1}")
    
    def stop_test(self) -> bool:
        """Stop test with proper chamber emptying sequence using normal completion emptying"""
        
        with self._stop_lock:
            # Check if there's anything to stop
            with self._state_lock:
                if not self.running_test and not self._emptying_in_progress:
                    self.logger.info("No test running and no emptying in progress")
                    return True
                
                if self._stop_requested:
                    self.logger.info("Stop already requested")
                    return True
            
            self.logger.info("STOP TEST REQUESTED - Beginning controlled stop procedure")
            
            # STEP 1: Set stop flags immediately
            with self._state_lock:
                self._stop_requested = True
                if self.running_test:
                    self.test_state = "STOPPING"
                    self._update_status("Stopping test - preparing for controlled emptying...")
            
            # STEP 2: Wait briefly for test thread to recognize stop and complete current operations
            if self.test_thread and self.test_thread.is_alive():
                self.test_thread.join(timeout=2.0)
                if self.test_thread.is_alive():
                    self.logger.warning("Test thread still running after stop request")
            
            # STEP 3: Perform controlled emptying using the same method as normal completion
            try:
                self.logger.info("Starting controlled emptying procedure (same as normal completion)")
                
                # Use the same controlled emptying method that's used for normal test completion
                self._perform_normal_completion_emptying()
                
                self.logger.info("Controlled emptying completed successfully")
                
            except Exception as e:
                self.logger.error(f"Error during controlled emptying: {e}")
                # Fallback to emergency emptying if controlled emptying fails
                try:
                    self.logger.warning("Falling back to emergency emptying procedure")
                    self._start_immediate_emptying()
                    
                    # Wait for emergency emptying to complete
                    timeout = 0
                    while self._emptying_in_progress and timeout < 30:
                        time.sleep(0.5)
                        timeout += 0.5
                        
                except Exception as emergency_error:
                    self.logger.critical(f"Emergency emptying also failed: {emergency_error}")
                    # Final safety: force close all valves
                    self._force_close_all_valves()
            
            # STEP 4: Ensure final state cleanup
            with self._state_lock:
                self.running_test = False
                self._emptying_in_progress = False
                if self.test_state == "STOPPING":
                    self.test_state = "IDLE"
            
            # STEP 5: Stop monitoring
            self._stop_monitoring()
            
            # STEP 6: Final valve safety check
            self._force_close_all_valves()
            
            self._update_status("Test stopped - chambers emptied safely")
            self.logger.info("Stop test procedure completed successfully")
            
            # Call the test finished callback
            try:
                self.on_test_finished()
            except Exception as e:
                self.logger.error(f"Error in test finished callback during stop: {e}")
            
            return True
    
    def _start_immediate_emptying(self):

        try:
            self.logger.info("Starting immediate chamber emptying procedure")
            
            with self._state_lock:
                if self._emptying_in_progress:
                    self.logger.info("Emptying already in progress")
                    return
                    
                self._emptying_in_progress = True
                self.test_phase = 'immediate_emptying'
            
            # IMMEDIATELY open outlet valves and close inlet valves for all enabled chambers
            enabled_chambers = []
            with self._state_lock:
                enabled_chambers = [i for i in range(3) if self.chamber_states[i].enabled]
            
            with self._valve_lock:
                for chamber_index in enabled_chambers:
                    try:
                        # Safety: close inlet, open outlet IMMEDIATELY
                        self.valve_controller.set_chamber_valves(chamber_index, False, True)
                        
                        with self._state_lock:
                            self.chamber_states[chamber_index].phase = ChamberPhase.EMPTYING
                            
                        self.logger.info(f"IMMEDIATE emptying started for chamber {chamber_index + 1}")
                        
                    except Exception as e:
                        self.logger.error(f"Error starting immediate emptying for chamber {chamber_index + 1}: {e}")
            
            # Start monitoring emptying progress in background thread
            emptying_monitor_thread = threading.Thread(
                target=self._monitor_emptying_progress, 
                daemon=True,
                name="EmptyingMonitor"
            )
            emptying_monitor_thread.start()
            
            self.logger.info("Immediate emptying valves opened, monitoring started")
            
        except Exception as e:
            self.logger.critical(f"CRITICAL: Error in immediate emptying start: {e}")
            # Emergency fallback
            self._force_close_all_valves()
            raise
    
    def _monitor_emptying_progress(self):

        try:
            self.logger.info("Monitoring emptying progress...")
            empty_start = time.time()
            max_empty_time = self.emptying_duration
            
            while time.time() - empty_start < max_empty_time:
                try:
                    pressures = self._read_pressures_with_retry(max_retries=2)
                    if pressures and len(pressures) >= 3:
                        all_empty = True
                        
                        with self._state_lock:
                            enabled_chambers = [i for i in range(3) if self.chamber_states[i].enabled]
                        
                        for chamber_index in enabled_chambers:
                            current_pressure = pressures[chamber_index] if chamber_index < len(pressures) else 0.0
                            
                            with self._state_lock:
                                self.chamber_states[chamber_index].current_pressure = current_pressure
                            
                            # Check if chamber is empty (5 mbar threshold)
                            if current_pressure > 5.0:
                                all_empty = False
                                
                            self.logger.debug(f"Chamber {chamber_index + 1} pressure during emptying: {current_pressure:.1f} mbar")
                        
                        # Exit early if all chambers are empty
                        if all_empty:
                            elapsed = time.time() - empty_start
                            self.logger.info(f"All chambers emptied successfully in {elapsed:.1f}s")
                            break
                            
                except Exception as e:
                    self.logger.error(f"Error reading pressures during emptying: {e}")
                
                time.sleep(0.2)  # Check every 200ms
            
            # Always close all valves after emptying timeout or completion
            self._force_close_all_valves()
            
            # Update final status
            elapsed_total = time.time() - empty_start
            if elapsed_total >= max_empty_time:
                self.logger.warning(f"Emptying completed with timeout after {elapsed_total:.1f}s")
            else:
                self.logger.info(f"Emptying monitoring completed in {elapsed_total:.1f}s")
                
        except Exception as e:
            self.logger.critical(f"Critical error in emptying monitoring: {e}")
            
        finally:
            # Ensure cleanup happens
            self._force_close_all_valves()
            
            with self._state_lock:
                self._emptying_in_progress = False
                if not self.running_test:
                    self.test_state = "IDLE"
                    
            self._update_status("Test stopped - chambers emptied")
            self.logger.info("Emptying monitoring completed")
    
    def _force_close_all_valves(self):

        try:
            self.logger.info("Force closing all valves for safety")
            
            with self._valve_lock:
                for chamber_index in range(3):
                    try:
                        self.valve_controller.set_chamber_valves(chamber_index, False, False)
                        
                        # Update chamber state
                        with self._state_lock:
                            if chamber_index < len(self.chamber_states):
                                if self.chamber_states[chamber_index].phase == ChamberPhase.EMPTYING:
                                    self.chamber_states[chamber_index].phase = ChamberPhase.IDLE
                        
                        self.logger.debug(f"Valves closed for chamber {chamber_index + 1}")
                        
                    except Exception as e:
                        self.logger.critical(f"CRITICAL: Failed to close valves for chamber {chamber_index + 1}: {e}")
                        
            self.logger.info("All valves force-closed")
            
        except Exception as e:
            self.logger.critical(f"CRITICAL: Error in force close all valves: {e}")
    
    def _check_stop_requested(self) -> bool:

        with self._state_lock:
            if self._stop_requested:
                if self.test_state not in ("STOPPING", "EMPTYING", "IDLE"):
                    self.test_state = "STOPPING"
                    self._update_status("Test stop detected - initiating emptying")
                
                # Start immediate emptying if not already started
                if not self._emptying_in_progress:
                    try:
                        self._start_immediate_emptying()
                    except Exception as e:
                        self.logger.error(f"Error starting emptying on stop check: {e}")
                        self._force_close_all_valves()
                        
                return True
                
            return False
    
    def _control_chamber_valves_safe(self, chamber_index: int, inlet_state: bool, outlet_state: bool):

        try:
            # Check for stop request first
            if self._stop_requested or not self.running_test:
                # Force close all solenoids on stop
                with self._valve_lock:
                    self.valve_controller.set_chamber_valves(chamber_index, False, False)
                return
            
            with self._valve_lock:
                # Safety: if opening inlet, ensure outlet is closed first
                if inlet_state and outlet_state:
                    self.logger.warning(f"Safety violation: Attempted to open both valves for chamber {chamber_index + 1}")
                    inlet_state = False  # Prioritize safety
                
                # Add safety delay when switching from outlet to inlet
                if inlet_state:
                    self.valve_controller.set_chamber_valves(chamber_index, False, False)
                    time.sleep(0.05)  # Small delay to ensure outlet closes first
                    
                self.valve_controller.set_chamber_valves(chamber_index, inlet_state, outlet_state)
                
        except Exception as e:
            self.logger.error(f"Valve control error for chamber {chamber_index + 1}: {e}")
            # Safety: ensure valves are closed on error
            try:
                with self._valve_lock:
                    self.valve_controller.set_chamber_valves(chamber_index, False, False)
            except Exception as safety_error:
                self.logger.critical(f"CRITICAL: Safety valve closure failed for chamber {chamber_index + 1}: {safety_error}")
    
    def _apply_adaptive_control(self, chamber_index: int, error: float, pressure_rates: List[float], 
                              regulation_states: Dict[int, str], tolerance: float):

        abs_error = abs(error)
        
        # Determine control mode based on error magnitude
        if abs_error > self.FAST_MODE['threshold']:
            control_mode = self.FAST_MODE
            mode_name = 'FAST'
        elif abs_error > self.MEDIUM_MODE['threshold']:
            control_mode = self.MEDIUM_MODE
            mode_name = 'MEDIUM'
        else:
            control_mode = self.FINE_MODE
            mode_name = 'FINE'
        
        # Calculate average rate of change if available
        avg_rate = 0
        if pressure_rates:
            avg_rate = sum(pressure_rates) / len(pressure_rates)
        
        # Predictive adjustment - reduce action if pressure is changing
        # in the desired direction
        predicted_pressure = self.chamber_states[chamber_index].current_pressure + (avg_rate * 0.5)
        predicted_error = self.chamber_states[chamber_index].pressure_target - predicted_pressure
        
        # If pressure is moving in the right direction, reduce control action
        if abs(predicted_error) < abs_error:
            rate_factor = 0.5  # Reduce action by 50%
        else:
            rate_factor = min(1.0, abs(avg_rate) / 10.0)
        
        # Adaptive pulse timing based on rate of change
        adjusted_pulse_on = control_mode['pulse_on'] * (1 - rate_factor * 0.3)
        adjusted_pulse_off = control_mode['pulse_off'] * (1 + rate_factor * 0.5)
        
        # Apply control action
        if error > tolerance:  # Need to increase pressure
            if regulation_states[chamber_index] != 'filling':
                self.logger.debug(f"Chamber {chamber_index + 1} - {mode_name} increase: "
                                f"{self.chamber_states[chamber_index].current_pressure:.1f}/"
                                f"{self.chamber_states[chamber_index].pressure_target:.1f} mbar "
                                f"(rate: {avg_rate:.2f} mbar/s)")
                regulation_states[chamber_index] = 'filling'
            
            self._control_chamber_valves_safe(chamber_index, True, False)
            time.sleep(adjusted_pulse_on)
            self._control_chamber_valves_safe(chamber_index, False, False)
            time.sleep(adjusted_pulse_off)
            
        elif error < -tolerance:  # Need to decrease pressure
            if regulation_states[chamber_index] != 'venting':
                self.logger.debug(f"Chamber {chamber_index + 1} - {mode_name} decrease: "
                                f"{self.chamber_states[chamber_index].current_pressure:.1f}/"
                                f"{self.chamber_states[chamber_index].pressure_target:.1f} mbar "
                                f"(rate: {avg_rate:.2f} mbar/s)")
                regulation_states[chamber_index] = 'venting'
            
            self._control_chamber_valves_safe(chamber_index, False, True)
            time.sleep(adjusted_pulse_on * 1.5)  # Longer pulse for venting
            self._control_chamber_valves_safe(chamber_index, False, False)
            time.sleep(adjusted_pulse_off)
        else:
            regulation_states[chamber_index] = 'stable'
            self._control_chamber_valves_safe(chamber_index, False, False)
    
    def _run_concurrent_test(self):

        try:
            # Start pressure monitoring
            self._start_monitoring()
            
            # Get active chambers
            with self._state_lock:
                active_chambers = [i for i in range(3) if self.chamber_states[i].enabled]
            
            test_results = {i: True for i in active_chambers}
            
            self.logger.info(f"Starting test for chambers: {[i+1 for i in active_chambers]}")
            
            if not active_chambers:
                raise Exception("No chambers enabled for testing")
            
            # Reset displays and states
            with self._state_lock:
                for chamber in self.chamber_states:
                    chamber.current_pressure = 0.0
                    chamber.phase = ChamberPhase.IDLE
                
                self.elapsed_time = 0.0
                self.test_phase = None
                self.test_state = 'IDLE'
            
            # Initialize test variables
            target_pressures = {}
            with self._state_lock:
                target_pressures = {ch: self.chamber_states[ch].pressure_target for ch in active_chambers}
            
            stabilization_readings = {i: [] for i in active_chambers}
            test_pressures = {i: [] for i in active_chambers}
            
            # ========================================================================================
            # PHASE 1: FILLING
            # ========================================================================================
            if self._check_stop_requested():
                return False
            
            with self._state_lock:
                self.test_phase = 'filling'
                self.test_state = 'FILLING'
            self._update_status("Filling chambers...", True)
            
            self.logger.info("Phase 1: Filling all chambers...")
            chambers_filling = set(active_chambers)
            fill_start_time = time.time()
            
            while chambers_filling and not self._check_stop_requested():
                # Check for fill timeout
                if time.time() - fill_start_time > self.fill_timeout:
                    raise Exception(f"Fill timeout exceeded ({self.fill_timeout}s)")
                
                pressures = self._read_pressures_with_retry()
                if not pressures:
                    # Handle sensor failure
                    if self._consecutive_sensor_errors >= self._max_consecutive_errors:
                        raise Exception("Too many consecutive sensor reading failures")
                    continue
                
                for chamber_index in list(chambers_filling):
                    current_pressure = pressures[chamber_index] if chamber_index < len(pressures) else 0.0
                    target_pressure = target_pressures[chamber_index]
                    
                    # Update current pressure
                    with self._state_lock:
                        self.chamber_states[chamber_index].current_pressure = current_pressure
                    
                    if current_pressure < target_pressure:
                        self._control_chamber_valves_safe(chamber_index, True, False)
                    else:
                        self._control_chamber_valves_safe(chamber_index, False, False)
                        chambers_filling.remove(chamber_index)
                        
                        with self._state_lock:
                            self.chamber_states[chamber_index].phase = ChamberPhase.REGULATING
                            
                        self.logger.info(f"Chamber {chamber_index + 1} filled to {current_pressure:.1f} mbar")
                
                # Update progress
                filled_count = len(active_chambers) - len(chambers_filling)
                progress = filled_count / len(active_chambers)
                self._update_progress(time.time() - fill_start_time, self.fill_timeout, 
                                    {'phase': 'filling', 'progress': progress})
                
                time.sleep(0.1)
            
            if self._check_stop_requested():
                return False
                
            self.logger.info("All chambers filled successfully")
            
            # ========================================================================================
            # PHASE 2: REGULATION
            # ========================================================================================
            with self._state_lock:
                self.test_phase = 'regulating'
                self.test_state = 'REGULATING'
            self._update_status("Regulating pressures to target...", True)
            
            self.logger.info("Phase 2: Pressure Regulation...")
            
            chambers_regulating = set(active_chambers)
            regulation_states = {i: 'fast' for i in active_chambers}
            last_pressures = {i: None for i in active_chambers}
            pressure_rates = {i: [] for i in active_chambers}
            consecutive_stable = {i: 0 for i in active_chambers}
            regulation_start_time = time.time()
            
            while (self.running_test and chambers_regulating and 
                   not self._check_stop_requested() and
                   time.time() - regulation_start_time < self.regulation_timeout):
                
                pressures = self._read_pressures_with_retry()
                if not pressures:
                    continue
                
                for chamber_index in list(chambers_regulating):
                    current_pressure = pressures[chamber_index] if chamber_index < len(pressures) else 0.0
                    target_pressure = target_pressures[chamber_index]
                    
                    with self._state_lock:
                        chamber = self.chamber_states[chamber_index]
                        chamber.current_pressure = current_pressure
                        chamber_tolerance = chamber.pressure_tolerance
                    
                    # Calculate pressure change rate
                    if last_pressures[chamber_index] is not None:
                        rate = (current_pressure - last_pressures[chamber_index]) / 0.1
                        pressure_rates[chamber_index].append(rate)
                        if len(pressure_rates[chamber_index]) > 10:
                            pressure_rates[chamber_index].pop(0)
                    last_pressures[chamber_index] = current_pressure
                    
                    # Calculate error and check stability
                    error = target_pressure - current_pressure
                    abs_error = abs(error)
                    
                    # Check if within chamber's pressure tolerance
                    if abs_error <= chamber_tolerance:
                        consecutive_stable[chamber_index] += 1
                        if consecutive_stable[chamber_index] >= 5:  # Stable for 0.5 seconds
                            self._control_chamber_valves_safe(chamber_index, False, False)
                            chambers_regulating.remove(chamber_index)
                            
                            with self._state_lock:
                                self.chamber_states[chamber_index].phase = ChamberPhase.STABILIZING
                                
                            self.logger.info(f"Chamber {chamber_index + 1} reached target: {current_pressure:.1f} mbar")
                            continue
                    else:
                        consecutive_stable[chamber_index] = 0
                    
                    # Apply adaptive control
                    self._apply_adaptive_control(chamber_index, error, pressure_rates[chamber_index], 
                                               regulation_states, chamber_tolerance)
                
                time.sleep(0.1)
            
            # Check for regulation timeout
            if time.time() - regulation_start_time >= self.regulation_timeout and chambers_regulating:
                self.logger.warning(f"Regulation timeout exceeded for chambers: {list(chambers_regulating)}")
            
            if not chambers_regulating:
                self.logger.info("All chambers have reached their target pressures")
            
            # Reset all solenoids after regulation
            with self._valve_lock:
                for chamber_index in active_chambers:
                    self.valve_controller.set_chamber_valves(chamber_index, False, False)
            
            if self._check_stop_requested():
                return False
            
            # ========================================================================================
            # PHASE 3: STABILIZATION
            # ========================================================================================
            with self._state_lock:
                self.test_phase = 'stabilizing'
                self.test_state = 'STABILIZING'
            self._update_status("Stabilizing pressure...", True)
            
            self.logger.info("Phase 3: Verifying pressure stability...")
            stability_start = time.time()
            all_stable = False
            
            while (self.running_test and not self._check_stop_requested() and
                   time.time() - stability_start < self.stability_duration):
                
                pressures = self._read_pressures_with_retry()
                if not pressures:
                    continue
                    
                all_stable = True
                
                for chamber_index in active_chambers:
                    current_pressure = pressures[chamber_index] if chamber_index < len(pressures) else 0.0
                    
                    with self._state_lock:
                        self.chamber_states[chamber_index].current_pressure = current_pressure
                        chamber_tolerance = self.chamber_states[chamber_index].pressure_tolerance
                    
                    readings = stabilization_readings[chamber_index]
                    readings.append(current_pressure)
                    if len(readings) > 50:
                        readings.pop(0)
                    
                    if len(readings) >= 20:
                        mean_pressure = sum(readings[-20:]) / 20
                        max_deviation = max(abs(p - mean_pressure) for p in readings[-20:])
                        if max_deviation > chamber_tolerance:
                            all_stable = False
                            break
                
                if all_stable:
                    break
                
                # Update progress
                elapsed = time.time() - stability_start
                progress = min(elapsed / self.stability_duration, 1.0)
                self._update_progress(elapsed, self.stability_duration, 
                                    {'phase': 'stabilization', 'progress': progress})
                
                time.sleep(0.1)
            
            if self._check_stop_requested():
                return False
                
            if not all_stable:
                self.logger.warning("Stabilization timeout - proceeding with test")
                
            # Mark all chambers as stabilized
            with self._state_lock:
                for chamber_index in active_chambers:
                    self.chamber_states[chamber_index].stability_achieved = all_stable
                    self.chamber_states[chamber_index].phase = ChamberPhase.TESTING
                    
            self.logger.info("Stabilization phase completed")
            
            # ========================================================================================
            # PHASE 4: TEST EXECUTION
            # ========================================================================================
            with self._state_lock:
                self.test_phase = 'testing'
                self.test_state = 'TESTING'
            self._update_status("Testing in progress...", True)
            
            test_start_time = time.time()
            
            # Record start pressures
            with self._state_lock:
                for chamber_index in active_chambers:
                    chamber = self.chamber_states[chamber_index]
                    chamber.start_pressure = chamber.current_pressure
                    chamber.pressure_readings = [chamber.current_pressure]
                    
                test_duration = self.test_duration
            
            while (self.running_test and not self._check_stop_requested() and
                   time.time() - test_start_time < test_duration):
                
                pressures = self._read_pressures_with_retry()
                elapsed_time = time.time() - test_start_time
                
                with self._state_lock:
                    self.elapsed_time = elapsed_time
                
                if not pressures:
                    continue
                
                for chamber_index in active_chambers:
                    current_pressure = pressures[chamber_index] if chamber_index < len(pressures) else 0.0
                    
                    with self._state_lock:
                        chamber = self.chamber_states[chamber_index]
                        chamber.current_pressure = current_pressure
                        chamber.pressure_readings.append(current_pressure)
                        
                        # Keep reasonable number of readings
                        if len(chamber.pressure_readings) > 1000:
                            chamber.pressure_readings.pop(0)
                        
                        # Check threshold violation
                        if current_pressure < chamber.pressure_threshold:
                            test_results[chamber_index] = False
                            chamber.result = False
                            self.logger.error(f"Chamber {chamber_index + 1} failed: "
                                            f"Pressure {current_pressure:.1f} mbar below threshold "
                                            f"{chamber.pressure_threshold:.1f} mbar")
                        
                        # Update final pressure
                        chamber.final_pressure = current_pressure
                    
                    test_pressures[chamber_index].append(current_pressure)
                    if len(test_pressures[chamber_index]) > 50:
                        test_pressures[chamber_index].pop(0)
                
                # Update progress
                progress = elapsed_time / test_duration
                self._update_progress(elapsed_time, test_duration, 
                                    {'phase': 'testing', 'chambers_status': test_results})
                
                time.sleep(0.1)
            
            if self._check_stop_requested():
                self.logger.warning("Test stopped during execution")
                return False
            
            self.logger.info("Test phase completed successfully")
            
            # ========================================================================================
            # PHASE 5: COMPLETION AND RESULTS
            # ========================================================================================
            self.logger.info("Starting test completion phase")
            
            # Calculate overall result
            overall_result = all(test_results[chamber] for chamber in active_chambers)
            
            # Process completion concurrently
            completion_result = self._run_concurrent_completion(test_results, active_chambers, overall_result)
            
            self.logger.info(f"Test completed with overall result: {'PASS' if overall_result else 'FAIL'}")
            return overall_result
            
        except Exception as e:
            self.logger.error(f"Test execution error: {e}")
            with self._state_lock:
                self.test_state = "ERROR"
            self._update_status(f"Test error: {e}")
            return False
            
        finally:
            # Comprehensive cleanup
            self._cleanup_test_execution()
    
    def _cleanup_test_execution(self):

        try:
            # Stop monitoring
            self._stop_monitoring()
            
            # Update running state
            with self._state_lock:
                self.running_test = False
            
            # Perform final emptying only if stop wasn't requested (normal completion)
            if not self._stop_requested and not self._emptying_in_progress:
                try:
                    self.logger.info("Normal test completion - performing final emptying")
                    self._perform_normal_completion_emptying()
                except Exception as e:
                    self.logger.error(f"Error in final emptying: {e}")
            else:
                self.logger.info("Skipping final emptying - already handled by stop procedure")
            
            # Final safety check - ensure all valves are closed
            self._force_close_all_valves()
            
            # Update final state
            with self._state_lock:
                if self.test_state not in ("COMPLETE", "ERROR", "STOPPING", "IDLE"):
                    self.test_state = "IDLE"
                    self._update_status("Test completed")
            
            # Call completion callback
            try:
                self.on_test_finished()
            except Exception as e:
                self.logger.error(f"Error in test finished callback: {e}")
                
            self.logger.info("Test execution cleanup completed")
            
        except Exception as e:
            self.logger.critical(f"Critical error in test cleanup: {e}")
    
    def _perform_normal_completion_emptying(self):
        """
        Normal completion emptying - used for both normal completion AND manual stop.
        Keeps the original implementation without parallel/sequential choice.
        """
        try:
            self.logger.info("Starting normal completion emptying")
            
            with self._state_lock:
                self.test_phase = 'emptying'
                self.test_state = 'EMPTYING'
                self._emptying_in_progress = True
                enabled_chambers = [i for i in range(3) if self.chamber_states[i].enabled]
                    
            self._update_status("Emptying chambers...")
            
            # Open outlet valves for enabled chambers
            with self._valve_lock:
                for chamber_index in enabled_chambers:
                    try:
                        self.valve_controller.set_chamber_valves(chamber_index, False, True)
                        
                        with self._state_lock:
                            self.chamber_states[chamber_index].phase = ChamberPhase.EMPTYING
                            
                        self.logger.debug(f"Started normal emptying for chamber {chamber_index + 1}")
                        
                    except Exception as e:
                        self.logger.error(f"Error starting normal emptying for chamber {chamber_index + 1}: {e}")
            
            # Monitor emptying progress (blocking call for normal completion)
            empty_start = time.time()
            max_empty_time = self.emptying_duration
            
            while time.time() - empty_start < max_empty_time:
                # Check for stop request even during normal emptying
                if self._stop_requested and not self._emptying_in_progress:
                    self.logger.info("Stop requested during normal emptying - switching to stop mode")
                    return  # Let the stop procedure handle it
                    
                try:
                    pressures = self._read_pressures_with_retry(max_retries=2)
                    if pressures and len(pressures) >= 3:
                        all_empty = True
                        
                        for chamber_index in enabled_chambers:
                            current_pressure = pressures[chamber_index] if chamber_index < len(pressures) else 0.0
                            
                            with self._state_lock:
                                self.chamber_states[chamber_index].current_pressure = current_pressure
                            
                            # Check if chamber is empty (5 mbar threshold)
                            if current_pressure > 5.0:
                                all_empty = False
                        
                        # Exit early if all chambers are empty
                        if all_empty:
                            elapsed = time.time() - empty_start
                            self.logger.info(f"Normal emptying completed in {elapsed:.1f}s")
                            break
                            
                except Exception as e:
                    self.logger.error(f"Error during normal emptying: {e}")
                
                time.sleep(0.2)
            
            # Close all valves after emptying
            with self._valve_lock:
                for chamber_index in range(3):
                    try:
                        self.valve_controller.set_chamber_valves(chamber_index, False, False)
                        
                        with self._state_lock:
                            if chamber_index < len(self.chamber_states):
                                self.chamber_states[chamber_index].phase = ChamberPhase.COMPLETE
                                
                    except Exception as e:
                        self.logger.error(f"Error closing valves for chamber {chamber_index + 1}: {e}")
            
            self.logger.info("Normal completion emptying finished")
            
        except Exception as e:
            self.logger.error(f"Error in normal completion emptying: {e}")
            # Even on error, try to close valves
            self._force_close_all_valves()
            raise
        finally:
            with self._state_lock:
                self._emptying_in_progress = False
    
    def _run_concurrent_completion(self, test_results: Dict[int, bool], 
                                 active_chambers: List[int], overall_result: bool) -> bool:

        self.logger.info("Starting concurrent completion processing")
        
        # Prepare result data
        self._prepare_result_data(test_results, active_chambers, overall_result)
        
        # Use ThreadPoolExecutor for controlled concurrent execution
        completion_success = True
        
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="TestCompletion") as executor:
                
                # Submit both tasks concurrently
                emptying_future = executor.submit(self._perform_normal_completion_emptying)
                results_future = executor.submit(self._process_test_results, 
                                               test_results, active_chambers, overall_result)
                
                # Wait for both tasks with timeout
                try:
                    for future in as_completed([emptying_future, results_future], timeout=60):
                        if future == emptying_future:
                            future.result()  # May raise exception
                            self.logger.info("Concurrent emptying completed")
                            
                        elif future == results_future:
                            future.result()  # May raise exception
                            self.logger.info("Concurrent result processing completed")
                            
                except Exception as e:
                    self.logger.error(f"Error in concurrent completion task: {e}")
                    completion_success = False
                    
        except Exception as e:
            self.logger.error(f"Error in concurrent completion setup: {e}")
            completion_success = False
        
        # Final status update
        with self._state_lock:
            self.test_state = "COMPLETE"
        self._update_status(f"Test completed: {'PASS' if overall_result else 'FAIL'}")
        
        return completion_success and overall_result
    
    def _prepare_result_data(self, test_results: Dict[int, bool], 
                           active_chambers: List[int], overall_result: bool):

        with self._state_lock:
            # Calculate final results and statistics for all chambers
            for chamber_index in active_chambers:
                chamber = self.chamber_states[chamber_index]
                chamber.result = test_results.get(chamber_index, False)
                chamber.test_complete = True
                chamber.phase = ChamberPhase.COMPLETE
                
                # Calculate statistics if we have readings
                if chamber.pressure_readings:
                    chamber.mean_pressure = sum(chamber.pressure_readings) / len(chamber.pressure_readings)
                    chamber.pressure_std = np.std(chamber.pressure_readings) if len(chamber.pressure_readings) > 1 else 0.0
                
                # Log final results
                pressure_drop = chamber.start_pressure - chamber.final_pressure
                self.logger.info(f"Chamber {chamber_index + 1}: Start={chamber.start_pressure:.1f} mbar, "
                               f"Final={chamber.final_pressure:.1f} mbar, "
                               f"Drop={pressure_drop:.1f} mbar, "
                               f"Result={'PASS' if chamber.result else 'FAIL'}")
    
    def _process_test_results(self, test_results: Dict[int, bool], 
                            active_chambers: List[int], overall_result: bool) -> bool:

        try:
            self.logger.info("Starting concurrent result processing")
            
            processing_success = True
            
            # STEP 1: Save to database
            try:
                self._save_test_to_database_safe(overall_result, active_chambers)
                self.logger.info("Database save completed")
            except Exception as e:
                self.logger.error(f"Database save failed: {e}")
                processing_success = False
            
            # STEP 2: Print results (only on PASS)
            if self.printer_manager and overall_result:
                try:
                    self._print_results_safe(active_chambers, overall_result)
                    self.logger.info("Printing completed")
                except Exception as e:
                    self.logger.error(f"Printing failed: {e}")
                    # Don't mark as failure - printing is not critical
            
            # STEP 3: Execute callbacks
            try:
                self._execute_result_callbacks_safe(overall_result, active_chambers)
                self.logger.info("Callbacks completed")
            except Exception as e:
                self.logger.error(f"Callbacks failed: {e}")
                # Don't mark as failure - callbacks are not critical
            
            return processing_success
            
        except Exception as e:
            self.logger.error(f"Critical error in result processing: {e}")
            return False
    
    def _save_test_to_database_safe(self, overall_result: bool, active_chambers: List[int]):

        with self._database_lock:
            if self._database_save_completed:
                self.logger.info("Database save already completed")
                return
            
            try:
                # Validate data before save
                if not self._validate_test_data_for_save(overall_result, active_chambers):
                    raise ValueError("Invalid test data for database save")
                
                # Prepare test record
                test_record = self._prepare_database_record(overall_result, active_chambers)
                
                # Save with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        self.test_result_db.save_test_result(test_record)
                        self._database_save_completed = True
                        self.logger.info(f"Database save successful (attempt {attempt + 1})")
                        return
                        
                    except Exception as e:
                        self.logger.warning(f"Database save attempt {attempt + 1} failed: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(1.0)  # Wait before retry
                
                raise Exception("All database save attempts failed")
                
            except Exception as e:
                self.logger.error(f"Database save failed: {e}")
                raise
    
    def _validate_test_data_for_save(self, overall_result: bool, active_chambers: List[int]) -> bool:

        try:
            # Check basic parameters
            if not isinstance(overall_result, bool):
                return False
                
            if not active_chambers or not isinstance(active_chambers, list):
                return False
            
            # Check chamber data
            with self._state_lock:
                for chamber_index in active_chambers:
                    if chamber_index < 0 or chamber_index >= len(self.chamber_states):
                        return False
                        
                    chamber = self.chamber_states[chamber_index]
                    if not hasattr(chamber, 'final_pressure') or chamber.final_pressure is None:
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating test data: {e}")
            return False
    
    def _prepare_database_record(self, overall_result: bool, active_chambers: List[int]) -> Dict[str, Any]:

        operator_name = self.current_user or "N/A"
        operator_id = self.current_user_id or "N/A"
        
        test_record = {
            'timestamp': datetime.now().isoformat(),
            'operator_id': operator_id,
            'operator_name': operator_name,
            'reference': self.current_reference or "N/A",
            'test_mode': self.test_mode,
            'test_duration': int(self.test_duration),
            'overall_result': overall_result,
            'chambers': []
        }
        
        # Add chamber data for ALL chambers (database expects 3 chambers)
        with self._state_lock:
            for chamber_idx in range(3):
                chamber = self.chamber_states[chamber_idx]
                
                chamber_data = {
                    'chamber_id': chamber_idx,
                    'enabled': chamber.enabled,
                    'pressure_target': float(chamber.pressure_target),
                    'pressure_threshold': float(chamber.pressure_threshold),
                    'pressure_tolerance': float(chamber.pressure_tolerance),
                    'start_pressure': float(getattr(chamber, 'start_pressure', 0.0)),
                    'final_pressure': float(getattr(chamber, 'final_pressure', 0.0)),
                    'mean_pressure': float(getattr(chamber, 'mean_pressure', 0.0)),
                    'pressure_std': float(getattr(chamber, 'pressure_std', 0.0)),
                    'result': chamber.result if chamber_idx in active_chambers else False
                }
                test_record['chambers'].append(chamber_data)
        
        return test_record
    
    def _print_results_safe(self, active_chambers: List[int], overall_result: bool):

        try:
            # Only print if all chambers passed
            if not overall_result:
                self.logger.info("Not printing - test failed")
                return
            
            # Get current timestamp
            now = datetime.now()
            date_str = now.strftime("%d/%m/%Y")
            time_str = now.strftime("%H:%M:%S")
            
            # Get reference and operator data
            reference = self.current_reference or ""
            operator_id = self.current_user_id or ""
            
            # Prepare stripped values as specified
            if reference and len(reference) > 3:
                stripped_model = reference[3:]  # Remove first 3 characters
            else:
                stripped_model = reference
            
            if reference and len(reference) > 7:
                stripped_barcode = reference[7:]  # Remove first 7 characters  
            else:
                stripped_barcode = reference
            
            # Build ZPL exactly as specified
            zpl = (
                "^XA\n"
                "^PW799^LH70,10\n"
                "^A0N,25,25^FO70,15^FDLEAR - KENITRA^FS\n"
                "^A0N,25,25^FO70,50^FDGROMET EB V216^FS\n"
                f"^A0N,25,25^FO70,85^FDOp.Nr.{operator_id}^FS\n"
                f"^A0N,40,40^FO70,140^FD{stripped_model}^FS\n"
                f"^A0N,25,25^FO70,190^FDDATE:{date_str}^FS\n"
                f"^A0N,25,25^FO70,220^FDTIME:{time_str}^FS\n"
                "^A0N,40,40^FO70,250^FDGROMMET TEST PASS^FS\n"
                # Right vertical barcode
                "^FT570,75\n"
                f"^BY2^BCR,50,Y,N,N^FD{stripped_barcode}^FS\n"
                # Bottom horizontal barcode
                "^FT0,240\n"
                f"^BY2^BCB,50,Y,N,N^FD{stripped_barcode}^FS\n"
                "^XZ"
            )
            
            # Send ZPL directly to printer
            success = self.printer_manager._send_zpl(zpl)
            if success:
                self.logger.info(f"Test results printed successfully for reference: {reference}")
            else:
                self.logger.error("Failed to send ZPL to printer")
            
        except Exception as e:
            self.logger.error(f"Printing error: {e}")
    
    def _execute_result_callbacks_safe(self, overall_result: bool, active_chambers: List[int]):

        if not self.result_callback:
            return
        
        try:
            # Prepare detailed results for UI
            chamber_results = []
            
            with self._state_lock:
                for chamber_idx in active_chambers:
                    chamber = self.chamber_states[chamber_idx]
                    
                    result_info = {
                        "chamber_index": chamber_idx,
                        "target_pressure": chamber.pressure_target,
                        "start_pressure": getattr(chamber, 'start_pressure', 0.0),
                        "final_pressure": getattr(chamber, 'final_pressure', 0.0),
                        "mean_pressure": getattr(chamber, 'mean_pressure', 0.0),
                        "pressure_drop": getattr(chamber, 'start_pressure', 0.0) - getattr(chamber, 'final_pressure', 0.0),
                        "pressure_std": getattr(chamber, 'pressure_std', 0.0),
                        "threshold": chamber.pressure_threshold,
                        "result": chamber.result,
                        "stability_achieved": getattr(chamber, 'stability_achieved', False),
                        "enabled": chamber.enabled
                    }
                    chamber_results.append(result_info)
            
            # Execute callback safely
            self.result_callback(overall_result, chamber_results)
            self.logger.debug("Result callback executed successfully")
            
        except Exception as e:
            self.logger.error(f"Error in result callback: {e}")
    
    def _start_monitoring(self):

        self.logger.info("Starting pressure monitoring")
        
        with self._state_lock:
            self._monitoring_running = True
        
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop_enhanced,
            daemon=True,
            name="PressureMonitor"
        )
        self.monitoring_thread.start()
    
    def _stop_monitoring(self):
        self.logger.info("Stopping pressure monitoring")
        
        with self._state_lock:
            self._monitoring_running = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=3.0)
            if self.monitoring_thread.is_alive():
                self.logger.warning("Monitoring thread did not terminate gracefully")
                # Note: In Python, we can't force kill threads, but we ensure cleanup
    
    def _monitoring_loop_enhanced(self):

        try:
            self.logger.info("Enhanced monitoring loop started")
            consecutive_errors = 0
            
            while True:
                with self._state_lock:
                    if not self._monitoring_running or self._stop_requested:
                        break
                
                try:
                    pressures = self._read_pressures_with_retry(max_retries=2)
                    
                    if pressures:
                        consecutive_errors = 0  # Reset error counter
                        
                        with self._state_lock:
                            for chamber_index, chamber in enumerate(self.chamber_states):
                                if chamber.enabled and chamber_index < len(pressures):
                                    chamber.current_pressure = pressures[chamber_index]
                    else:
                        consecutive_errors += 1
                        if consecutive_errors >= self._max_consecutive_errors:
                            self.logger.error("Too many consecutive sensor errors - requesting emergency stop")
                            with self._state_lock:
                                self._stop_requested = True
                            break
                            
                except Exception as e:
                    consecutive_errors += 1
                    self.logger.error(f"Monitoring error {consecutive_errors}: {e}")
                    
                    if consecutive_errors >= self._max_consecutive_errors:
                        self.logger.critical("Critical monitoring failure - requesting emergency stop")
                        with self._state_lock:
                            self._stop_requested = True
                        break
                
                time.sleep(0.05)  # 20Hz monitoring
        
        except Exception as e:
            self.logger.error(f"Critical error in monitoring thread: {e}")
        
        finally:
            self.logger.info("Pressure monitoring stopped")
    
    def handle_physical_start(self):

        with self._state_lock:
            if not self.running_test and not self._emptying_in_progress:
                started = self.start_test()
                if not started:
                    self.logger.warning("Physical start press: start_test() returned False")
            else:
                self.logger.info("Physical start press ignored: test already running or emptying in progress")
    
    def handle_physical_stop(self):

        with self._state_lock:
            should_stop = self.running_test or self._emptying_in_progress
        
        if should_stop:
            self.logger.info("Physical stop button pressed - initiating immediate stop")
            
            stopped = self.stop_test()
            
            if not stopped:
                self.logger.warning("Physical stop press: stop_test() returned False")
                # Emergency fallback
                try:
                    self.logger.warning("Attempting emergency valve closure due to stop_test failure")
                    self._force_close_all_valves()
                    with self._state_lock:
                        self._stop_requested = True
                        self.running_test = False
                        self._emptying_in_progress = False
                        self.test_state = "IDLE"
                except Exception as e:
                    self.logger.critical(f"CRITICAL: Emergency valve closure failed: {e}")
            else:
                self.logger.info("Physical stop successful")
        else:
            self.logger.info("Physical stop press ignored: no test running and no emptying in progress")
    
    
    def _update_status(self, message: str, update_ui: bool = True):

        self.logger.info(message)
        
        if update_ui and self.status_callback:
            try:
                with self._state_lock:
                    test_state = self.test_state
                self.status_callback(test_state, message)
            except Exception as e:
                self.logger.error(f"Error in status callback: {e}")
    
    def _update_progress(self, current_time: float, total_time: float, progress_info: Dict[str, Any] = None):

        if self.progress_callback:
            try:
                self.progress_callback(current_time, total_time, progress_info or {})
            except Exception as e:
                self.logger.error(f"Error in progress callback: {e}")
    
    def set_login_requirement(self, require_login: bool) -> None:

        with self._state_lock:
            self.require_login = require_login
        self.logger.info(f"Login requirement set to: {'required' if require_login else 'not required'}")
    