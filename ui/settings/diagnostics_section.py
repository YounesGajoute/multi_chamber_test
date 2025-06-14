#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UPDATED Diagnostics Section module for the Multi-Chamber Test application.

This module provides the DiagnosticsSection class with:
- Removed hardware unavailable indicators system
- Standardized all indicators to size 24
- Simplified UI building without pre-validation
- Clean error handling through status messages
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading
import time
import platform
from typing import Dict, Any, List, Optional, Callable, Union, Tuple

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, GPIO_PINS
from multi_chamber_test.ui.settings.base_section import BaseSection


class DiagnosticsSection(BaseSection):
    """
    UPDATED Diagnostics section with simplified design and standardized indicators.
    
    This class provides hardware testing functionality with clean interface design,
    standardized size 24 indicators, and direct error handling.
    """
    
    def __init__(self, parent, test_manager):
        """
        Initialize with simplified parameters.
        
        Args:
            parent: Parent widget (content frame from settings tab)
            test_manager: TestManager instance for accessing hardware
        """
        # Call base class constructor
        super().__init__(parent)
        
        self.test_manager = test_manager
        
        # Get hardware components from main window via proper traversal
        self.main_window = self._find_main_window()
        
        # Initialize hardware component references
        self._initialize_hardware_references()
        
        # Status variables for UI updates
        self._initialize_status_variables()
        
        # Thread management flags
        self._initialize_thread_flags()
        
        # UI component references
        self._initialize_ui_references()
        
        # Build the interface
        self._build_interface()
        
        # Perform initial operations
        self._perform_initial_setup()
    
    def _find_main_window(self):
        """
        Find the main window instance with error handling.
        
        Returns:
            MainWindow instance or None if not found
        """
        widget = self.parent
        max_traversal = 10  # Prevent infinite loops
        traversal_count = 0
        
        while widget and traversal_count < max_traversal:
            # Look for MainWindow class or specific attributes
            if hasattr(widget, '_safe_gpio_command') and hasattr(widget, 'gpio_worker_running'):
                self.logger.info("Found main window via direct attributes")
                return widget
            
            # Check if this widget has a main_window attribute
            if hasattr(widget, 'main_window'):
                self.logger.info("Found main window via main_window attribute")
                return widget.main_window
            
            # Check class name
            if widget.__class__.__name__ == 'MainWindow':
                self.logger.info("Found main window via class name")
                return widget
            
            # Navigate up the widget hierarchy
            try:
                widget = widget.master
                traversal_count += 1
            except AttributeError:
                break
        
        self.logger.warning("Could not find main window for GPIO worker access")
        return None
    
    def _initialize_hardware_references(self):
        """Initialize hardware component references."""
        if self.main_window:
            self.valve_controller = getattr(self.main_window, 'valve_controller', None)
            self.physical_controls = getattr(self.main_window, 'physical_controls', None)
            self.gpio_manager = getattr(self.main_window, 'gpio_manager', None)
            self.pressure_sensor = getattr(self.main_window, 'pressure_sensor', None)
            self.printer_manager = getattr(self.main_window, 'printer_manager', None)
        else:
            # Fallback to test_manager if available
            self.valve_controller = getattr(self.test_manager, 'valve_controller', None) if self.test_manager else None
            self.physical_controls = None
            self.gpio_manager = None
            self.pressure_sensor = getattr(self.test_manager, 'pressure_sensor', None) if self.test_manager else None
            self.printer_manager = getattr(self.test_manager, 'printer_manager', None) if self.test_manager else None
    
    def _initialize_status_variables(self):
        """Initialize status variables for UI updates."""
        self.valve_status = tk.StringVar(value="Ready")
        self.led_status = tk.StringVar(value="Ready")
        self.pressure_status = tk.StringVar(value="Ready")
        self.printer_status = tk.StringVar(value="Ready")
        self.start_stop_status = tk.StringVar(value="Ready")
        
        # Pressure display variables
        self.pressure_values = [
            tk.StringVar(value="--"),
            tk.StringVar(value="--"),
            tk.StringVar(value="--")
        ]
    
    def _initialize_thread_flags(self):
        """Initialize thread management flags."""
        self._valve_operations = set()
        self._led_test_active = False
        self._printer_monitoring_active = False
        self._button_monitoring_active = False
        self._shutdown_requested = False
    
    def _initialize_ui_references(self):
        """Initialize UI component references."""
        self.valve_indicators = {}
        self.start_led_indicator = None
        self.stop_led_indicator = None
        self.printer_indicator = None
        self.start_indicator = None
        self.stop_indicator = None
    
    def _build_interface(self):
        """Build the diagnostics interface."""
        try:
            # Create main title
            title_label = ttk.Label(
                self.content_frame,
                text="Hardware Diagnostics",
                style='ContentTitle.TLabel'
            )
            title_label.pack(anchor=tk.W, pady=(0, 20))
            
            # Build interface sections - ALWAYS CREATE ALL SECTIONS
            self._build_valve_control_section()
            self._build_led_test_section()
            self._build_pressure_display_section()
            self._build_printer_test_section()
            self._build_start_stop_section()
            
            self.logger.info("Diagnostics interface built successfully")
            
        except Exception as e:
            self.logger.error(f"Error building diagnostics interface: {e}")
            self._build_error_interface(str(e))
    
    def _build_error_interface(self, error_message: str):
        """Build a simple error interface when main interface fails."""
        error_frame = ttk.Frame(self.content_frame)
        error_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(
            error_frame,
            text="⚠️ Diagnostics Interface Error",
            font=("TkDefaultFont", 14, "bold"),
            foreground="red"
        ).pack(pady=10)
        
        ttk.Label(
            error_frame,
            text=f"Error: {error_message}",
            wraplength=600,
            justify=tk.LEFT
        ).pack(pady=10)
        
        ttk.Label(
            error_frame,
            text="Please check the application logs for more details.",
            style='CardText.TLabel'
        ).pack(pady=10)
    
    def _build_valve_control_section(self):
        """Build valve control section - SIMPLIFIED VERSION."""
        card_frame, content_frame = self.create_card(
            "Valve Control",
            "Test inlet and outlet valves with 50ms pulses"
        )
        
        # Status display - ALWAYS SHOW
        status_frame = ttk.Frame(content_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(status_frame, text="Status:", style='CardText.TLabel').pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.valve_status, style='Value.TLabel').pack(side=tk.LEFT, padx=(10, 0))
        
        # Valve control grid - ALWAYS CREATE
        valve_grid = ttk.Frame(content_frame)
        valve_grid.pack(fill=tk.X, pady=10)
        
        # Headers
        ttk.Label(valve_grid, text="Chamber", style='CardTitle.TLabel').grid(row=0, column=0, padx=10, pady=5)
        ttk.Label(valve_grid, text="Inlet", style='CardTitle.TLabel').grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(valve_grid, text="Outlet", style='CardTitle.TLabel').grid(row=0, column=2, padx=10, pady=5)
        
        # Create valve buttons for each chamber
        for chamber in range(3):
            self.valve_indicators[chamber] = {}
            
            # Chamber label
            ttk.Label(
                valve_grid,
                text=f"Chamber {chamber + 1}",
                style='CardText.TLabel'
            ).grid(row=chamber + 1, column=0, padx=10, pady=5)
            
            # Inlet valve controls - SIZE 24 INDICATOR
            inlet_frame = ttk.Frame(valve_grid)
            inlet_frame.grid(row=chamber + 1, column=1, padx=5, pady=5)
            
            inlet_indicator = tk.Label(inlet_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
            inlet_indicator.pack()
            
            inlet_btn = ttk.Button(
                inlet_frame,
                text="Test Inlet",
                command=lambda c=chamber: self._pulse_valve(c, "inlet"),
                width=10
            )
            inlet_btn.pack()
            
            self.valve_indicators[chamber]['inlet'] = (inlet_btn, inlet_indicator)
            
            # Outlet valve controls - SIZE 24 INDICATOR
            outlet_frame = ttk.Frame(valve_grid)
            outlet_frame.grid(row=chamber + 1, column=2, padx=5, pady=5)
            
            outlet_indicator = tk.Label(outlet_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
            outlet_indicator.pack()
            
            outlet_btn = ttk.Button(
                outlet_frame,
                text="Test Outlet",
                command=lambda c=chamber: self._pulse_valve(c, "outlet"),
                width=10
            )
            outlet_btn.pack()
            
            self.valve_indicators[chamber]['outlet'] = (outlet_btn, outlet_indicator)
    
    def _build_led_test_section(self):
        """Build LED test section - SIMPLIFIED VERSION."""
        card_frame, content_frame = self.create_card(
            "LED Test",
            "Test start and stop button LEDs"
        )
        
        # Status display - ALWAYS SHOW
        status_frame = ttk.Frame(content_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(status_frame, text="Status:", style='CardText.TLabel').pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.led_status, style='Value.TLabel').pack(side=tk.LEFT, padx=(10, 0))
        
        # LED test controls - ALWAYS CREATE
        led_controls = ttk.Frame(content_frame)
        led_controls.pack(fill=tk.X, pady=10)
        
        # Start LED test - SIZE 24 INDICATOR
        start_led_frame = ttk.Frame(led_controls)
        start_led_frame.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        
        ttk.Label(start_led_frame, text="Start LED", style='CardTitle.TLabel').pack()
        self.start_led_indicator = tk.Label(start_led_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
        self.start_led_indicator.pack()
        
        ttk.Button(
            start_led_frame,
            text="Test Start LED",
            command=self._test_start_led
        ).pack(pady=5)
        
        # Stop LED test - SIZE 24 INDICATOR
        stop_led_frame = ttk.Frame(led_controls)
        stop_led_frame.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        
        ttk.Label(stop_led_frame, text="Stop LED", style='CardTitle.TLabel').pack()
        self.stop_led_indicator = tk.Label(stop_led_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
        self.stop_led_indicator.pack()
        
        ttk.Button(
            stop_led_frame,
            text="Test Stop LED",
            command=self._test_stop_led
        ).pack(pady=5)
    
    def _build_pressure_display_section(self):
        """Build pressure display section - SIMPLIFIED VERSION."""
        card_frame, content_frame = self.create_card(
            "Pressure Readings",
            "Current pressure values from all chambers"
        )
        
        # Status display - ALWAYS SHOW
        status_frame = ttk.Frame(content_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(status_frame, text="Status:", style='CardText.TLabel').pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.pressure_status, style='Value.TLabel').pack(side=tk.LEFT, padx=(10, 0))
        
        # Pressure readings display - ALWAYS CREATE
        readings_frame = ttk.Frame(content_frame)
        readings_frame.pack(fill=tk.X, pady=10)
        
        for i in range(3):
            chamber_frame = ttk.Frame(readings_frame)
            chamber_frame.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
            
            ttk.Label(
                chamber_frame,
                text=f"Chamber {i + 1}",
                style='CardTitle.TLabel'
            ).pack()
            
            value_label = ttk.Label(
                chamber_frame,
                textvariable=self.pressure_values[i],
                font=("TkDefaultFont", 14, "bold")
            )
            value_label.pack()
            
            ttk.Label(chamber_frame, text="mbar", style='CardText.TLabel').pack()
        
        # Refresh button - ALWAYS SHOW
        ttk.Button(
            content_frame,
            text="Refresh Readings",
            command=self._refresh_pressure_readings
        ).pack(pady=10)
    
    def _build_printer_test_section(self):
        """Build printer test section - SIMPLIFIED VERSION."""
        card_frame, content_frame = self.create_card(
            "Printer Test",
            "Test printer connectivity and functionality"
        )
        
        # Status display - ALWAYS SHOW
        status_frame = ttk.Frame(content_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(status_frame, text="Status:", style='CardText.TLabel').pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.printer_status, style='Value.TLabel').pack(side=tk.LEFT, padx=(10, 0))
        
        # Printer controls - ALWAYS CREATE
        printer_controls = ttk.Frame(content_frame)
        printer_controls.pack(fill=tk.X, pady=10)
        
        # Status indicator - SIZE 24 INDICATOR
        indicator_frame = ttk.Frame(printer_controls)
        indicator_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(indicator_frame, text="Connection", style='CardTitle.TLabel').pack()
        self.printer_indicator = tk.Label(indicator_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
        self.printer_indicator.pack()
        
        # Test button - ALWAYS SHOW
        button_frame = ttk.Frame(printer_controls)
        button_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Button(
            button_frame,
            text="Test Printer",
            command=self._test_printer
        ).pack(pady=10)
    
    def _build_start_stop_section(self):
        """Build start/stop button monitoring section - SIMPLIFIED VERSION."""
        card_frame, content_frame = self.create_card(
            "Physical Button Monitor",
            "Monitor physical start and stop button states"
        )
        
        # Status display - ALWAYS SHOW
        status_frame = ttk.Frame(content_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(status_frame, text="Status:", style='CardText.TLabel').pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.start_stop_status, style='Value.TLabel').pack(side=tk.LEFT, padx=(10, 0))
        
        # Button indicators - ALWAYS CREATE
        buttons_frame = ttk.Frame(content_frame)
        buttons_frame.pack(fill=tk.X, pady=10)
        
        # Start button indicator - SIZE 24
        start_frame = ttk.Frame(buttons_frame)
        start_frame.pack(side=tk.LEFT, padx=40, fill=tk.X, expand=True)
        
        ttk.Label(start_frame, text="Start Button", style='CardTitle.TLabel').pack()
        self.start_indicator = tk.Label(start_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
        self.start_indicator.pack()
        
        # Stop button indicator - SIZE 24
        stop_frame = ttk.Frame(buttons_frame)
        stop_frame.pack(side=tk.LEFT, padx=40, fill=tk.X, expand=True)
        
        ttk.Label(stop_frame, text="Stop Button", style='CardTitle.TLabel').pack()
        self.stop_indicator = tk.Label(stop_frame, text="●", fg="gray", font=("TkDefaultFont", 24))
        self.stop_indicator.pack()
    
    def _perform_initial_setup(self):
        """Perform initial setup and start monitoring."""
        # Start monitoring threads for available hardware
        self._start_printer_monitoring()
        self._start_button_monitoring()
        
        # Perform initial status checks
        self._schedule_ui_update(self._refresh_pressure_readings)
        self._schedule_ui_update(self._check_printer_status)
    
    # ===== VALVE CONTROL METHODS =====
    
    def _pulse_valve(self, chamber: int, valve_type: str):
        """Pulse a specific valve for 50ms with simplified error handling."""
        if valve_type not in ['inlet', 'outlet']:
            self.valve_status.set(f"Invalid valve type: {valve_type}")
            return
        
        valve_key = f"{chamber}_{valve_type}"
        if valve_key in self._valve_operations:
            self.valve_status.set(f"Valve {valve_type} in chamber {chamber + 1} is already active")
            return
        
        # Get button and indicator - direct access
        try:
            button, indicator = self.valve_indicators[chamber][valve_type]
        except KeyError:
            self.valve_status.set(f"UI components not found for {valve_type} valve")
            return
        
        # Disable button and set indicator to green
        button.config(state='disabled')
        indicator.config(fg="green")
        
        # Add to active operations
        self._valve_operations.add(valve_key)
        
        # Start valve operation in background thread
        threading.Thread(
            target=self._valve_pulse_worker,
            args=(chamber, valve_type, valve_key, button, indicator),
            daemon=True,
            name=f"ValvePulse_{chamber}_{valve_type}"
        ).start()
    
    def _valve_pulse_worker(self, chamber: int, valve_type: str, valve_key: str, button, indicator):
        """Worker thread for valve pulse operation with error handling."""
        try:
            self._update_ui(lambda: self.valve_status.set(f"Pulsing {valve_type} valve in chamber {chamber + 1}..."))
            
            # Check if valve controller is available
            if not self.valve_controller:
                self._update_ui(lambda: self.valve_status.set("Valve controller not available"))
                return
            
            # Activate valve
            success = False
            try:
                if valve_type == "inlet":
                    success = self.valve_controller.set_inlet_valve(chamber, True)
                elif valve_type == "outlet":
                    success = self.valve_controller.set_outlet_valve(chamber, True)
                
                if not success:
                    self._update_ui(lambda: self.valve_status.set(f"Failed to activate {valve_type} valve"))
                    return
                
                # Wait 50ms
                time.sleep(0.05)
                
                # Deactivate valve
                if valve_type == "inlet":
                    deactivate_success = self.valve_controller.set_inlet_valve(chamber, False)
                elif valve_type == "outlet":
                    deactivate_success = self.valve_controller.set_outlet_valve(chamber, False)
                
                if deactivate_success:
                    self._update_ui(lambda: self.valve_status.set(f"Valve {valve_type} chamber {chamber + 1} pulsed successfully"))
                else:
                    self._update_ui(lambda: self.valve_status.set(f"Warning: Failed to deactivate {valve_type} valve"))
                
            except Exception as valve_error:
                self._update_ui(lambda: self.valve_status.set(f"Valve operation error: {str(valve_error)}"))
                self.logger.error(f"Valve operation error: {valve_error}")
                
                # Try to ensure valve is closed on error
                try:
                    if valve_type == "inlet":
                        self.valve_controller.set_inlet_valve(chamber, False)
                    elif valve_type == "outlet":
                        self.valve_controller.set_outlet_valve(chamber, False)
                except:
                    pass  # Best effort cleanup
                
        except Exception as e:
            self._update_ui(lambda: self.valve_status.set(f"Critical valve error: {str(e)}"))
            self.logger.error(f"Critical valve error: {e}")
        finally:
            # Reset button and indicator
            def cleanup():
                if not self._shutdown_requested:
                    try:
                        button.config(state='normal')
                        indicator.config(fg="gray")
                    except tk.TclError:
                        pass  # Widget was destroyed
                self._valve_operations.discard(valve_key)
            
            self._update_ui(cleanup)
    
    # ===== LED CONTROL METHODS =====
    
    def _safe_gpio_command(self, command_type: str, *args, callback=None, **kwargs):
        """Send thread-safe GPIO command via main window's GPIO worker."""
        if not self.main_window or not hasattr(self.main_window, '_safe_gpio_command'):
            error_msg = "Main window GPIO worker not available"
            self.logger.error(error_msg)
            if callback:
                self._schedule_ui_update(lambda: callback(False, error_msg))
            return None
        
        try:
            return self.main_window._safe_gpio_command(command_type, *args, callback=callback, **kwargs)
        except Exception as e:
            error_msg = f"GPIO command error: {e}"
            self.logger.error(error_msg)
            if callback:
                self._schedule_ui_update(lambda: callback(False, error_msg))
            return None
    
    def _test_start_led(self):
        """Test STATUS_LED_GREEN (Start LED)."""
        if self._led_test_active:
            self.led_status.set("LED test already running")
            return
        
        self._led_test_active = True
        if self.start_led_indicator:
            self.start_led_indicator.config(fg="green")
        
        def on_start_led_test(success, result):
            try:
                if success:
                    self.led_status.set("Start LED test completed successfully")
                else:
                    self.led_status.set(f"Start LED test failed: {result}")
                
                # Reset indicator and flag
                if self.start_led_indicator and not self._shutdown_requested:
                    self.start_led_indicator.config(fg="gray")
                self._led_test_active = False
                
                # Turn off LED after test
                self._safe_gpio_command("set_start_button_enabled", False)
                
            except Exception as e:
                self.logger.error(f"Error in start LED test callback: {e}")
                self._led_test_active = False
        
        self.led_status.set("Testing Start LED...")
        self._safe_gpio_command("set_start_button_enabled", True, callback=on_start_led_test)
    
    def _test_stop_led(self):
        """Test STATUS_LED_RED (Stop LED)."""
        if self._led_test_active:
            self.led_status.set("LED test already running")
            return
        
        self._led_test_active = True
        if self.stop_led_indicator:
            self.stop_led_indicator.config(fg="green")
        
        def on_stop_led_test(success, result):
            try:
                if success:
                    self.led_status.set("Stop LED test completed successfully")
                else:
                    self.led_status.set(f"Stop LED test failed: {result}")
                
                # Reset indicator and flag
                if self.stop_led_indicator and not self._shutdown_requested:
                    self.stop_led_indicator.config(fg="gray")
                self._led_test_active = False
                
                # Turn off LED after test
                self._safe_gpio_command("set_stop_button_enabled", False)
                
            except Exception as e:
                self.logger.error(f"Error in stop LED test callback: {e}")
                self._led_test_active = False
        
        self.led_status.set("Testing Stop LED...")
        self._safe_gpio_command("set_stop_button_enabled", True, callback=on_stop_led_test)
    
    # ===== PRESSURE SENSOR METHODS =====
    
    def _refresh_pressure_readings(self):
        """Refresh pressure readings from all chambers."""
        if self._shutdown_requested:
            return
        
        threading.Thread(
            target=self._pressure_reading_worker,
            daemon=True,
            name="PressureReader"
        ).start()
    
    def _pressure_reading_worker(self):
        """Worker thread for pressure readings."""
        try:
            self._update_ui(lambda: self.pressure_status.set("Reading pressures..."))
            
            # Check if pressure sensor is available
            if not self.pressure_sensor:
                self._update_ui(lambda: self.pressure_status.set("Pressure sensor not available"))
                return
            
            # Read pressures with timeout
            pressures = None
            try:
                pressures = self.pressure_sensor.read_all_pressures()
            except Exception as sensor_error:
                self.logger.error(f"Pressure sensor read error: {sensor_error}")
                self._update_ui(lambda: self.pressure_status.set(f"Sensor error: {str(sensor_error)}"))
                return
            
            if pressures is None:
                self._update_ui(lambda: self.pressure_status.set("Failed to read pressures"))
                return
            
            # Update pressure displays
            valid_readings = 0
            for i, pressure in enumerate(pressures):
                if i < len(self.pressure_values):
                    if pressure is not None and not self._shutdown_requested:
                        pressure_text = f"{pressure:.1f}"
                        valid_readings += 1
                    else:
                        pressure_text = "Error"
                    
                    def update_pressure(index=i, text=pressure_text):
                        try:
                            self.pressure_values[index].set(text)
                        except tk.TclError:
                            pass  # Widget was destroyed
                    
                    self._update_ui(update_pressure)
            
            # Update status based on results
            if valid_readings == len(pressures):
                self._update_ui(lambda: self.pressure_status.set("All pressure readings updated"))
            elif valid_readings > 0:
                self._update_ui(lambda: self.pressure_status.set(f"{valid_readings}/{len(pressures)} readings successful"))
            else:
                self._update_ui(lambda: self.pressure_status.set("No valid pressure readings"))
            
        except Exception as e:
            self.logger.error(f"Pressure reading worker error: {e}")
            self._update_ui(lambda: self.pressure_status.set(f"Pressure reading error: {str(e)}"))
    
    # ===== PRINTER METHODS =====
    
    def _test_printer(self):
        """Test printer connection and functionality."""
        if self._shutdown_requested:
            return
        
        threading.Thread(
            target=self._printer_test_worker,
            daemon=True,
            name="PrinterTester"
        ).start()
    
    def _printer_test_worker(self):
        """Worker thread for printer testing."""
        try:
            self._update_ui(lambda: self.printer_status.set("Testing printer..."))
            
            # Check if printer manager is available
            if not self.printer_manager:
                self._update_ui(lambda: self.printer_status.set("Printer manager not available"))
                return
            
            # Test printer connection
            success = False
            try:
                success = self.printer_manager.test_connection()
            except Exception as printer_error:
                self.logger.error(f"Printer test error: {printer_error}")
                self._update_ui(lambda: self.printer_status.set(f"Printer error: {str(printer_error)}"))
                return
            
            if success:
                self._update_ui(lambda: self.printer_status.set("Printer test successful"))
            else:
                self._update_ui(lambda: self.printer_status.set("Printer test failed - check connection"))
            
        except Exception as e:
            self.logger.error(f"Printer test worker error: {e}")
            self._update_ui(lambda: self.printer_status.set(f"Printer test error: {str(e)}"))
    
    def _start_printer_monitoring(self):
        """Start real-time printer status monitoring."""
        if self.printer_manager and not self._shutdown_requested:
            self._printer_monitoring_active = True
            threading.Thread(
                target=self._printer_monitoring_worker,
                daemon=True,
                name="PrinterMonitor"
            ).start()
    
    def _printer_monitoring_worker(self):
        """Worker thread for real-time printer status monitoring."""
        while (getattr(self, '_printer_monitoring_active', False) and 
               not self._shutdown_requested):
            try:
                status = self.printer_manager.get_printer_status()
                
                if status.get('available', False) and status.get('accessible', False):
                    # Printer is connected and accessible
                    self._update_ui(lambda: self.printer_indicator and self.printer_indicator.config(fg="green"))
                else:
                    # Printer is disconnected or not accessible
                    self._update_ui(lambda: self.printer_indicator and self.printer_indicator.config(fg="gray"))
                
                time.sleep(2.0)  # Check every 2 seconds
                
            except Exception as e:
                if not self._shutdown_requested:
                    self.logger.debug(f"Printer monitoring error: {e}")
                    self._update_ui(lambda: self.printer_indicator and self.printer_indicator.config(fg="gray"))
                time.sleep(5.0)  # Longer delay on error
    
    def _check_printer_status(self):
        """Check initial printer status (called once on startup)."""
        if self.printer_manager and not self._shutdown_requested:
            threading.Thread(
                target=self._printer_status_worker,
                daemon=True,
                name="PrinterStatusChecker"
            ).start()
    
    def _printer_status_worker(self):
        """Worker thread for checking initial printer status."""
        try:
            status = self.printer_manager.get_printer_status()
            
            if status.get('available', False) and status.get('accessible', False):
                self._update_ui(lambda: self.printer_status.set("Printer connected and ready"))
            else:
                self._update_ui(lambda: self.printer_status.set("Printer disconnected or not accessible"))
                
        except Exception as e:
            self.logger.error(f"Printer status check error: {e}")
            self._update_ui(lambda: self.printer_status.set(f"Printer status error: {str(e)}"))
    
    # ===== PHYSICAL BUTTON MONITORING =====
    
    def _start_button_monitoring(self):
        """Start monitoring physical button states."""
        if not self.physical_controls or self._shutdown_requested:
            return
        
        self._button_monitoring_active = True
        self.start_stop_status.set("Monitoring physical buttons...")
        
        # Register callbacks to monitor actual button presses if available
        try:
            if hasattr(self.physical_controls, 'register_start_callback'):
                self.physical_controls.register_start_callback(self._on_physical_start_pressed)
            if hasattr(self.physical_controls, 'register_stop_callback'):
                self.physical_controls.register_stop_callback(self._on_physical_stop_pressed)
        except Exception as e:
            self.logger.warning(f"Could not register button callbacks: {e}")
        
        # Start background monitoring of button states
        threading.Thread(
            target=self._button_state_monitoring_worker,
            daemon=True,
            name="ButtonMonitor"
        ).start()
    
    def _button_state_monitoring_worker(self):
        """Worker thread for monitoring physical button states."""
        while (getattr(self, '_button_monitoring_active', False) and 
               not self._shutdown_requested):
            try:
                # Monitor button states if GPIO manager is available
                if (self.gpio_manager and 
                    hasattr(self.gpio_manager, 'read_input') and
                    'START_BTN' in GPIO_PINS and 
                    'STOP_BTN' in GPIO_PINS):
                    
                    # Read start button state
                    try:
                        start_state = self.gpio_manager.read_input(GPIO_PINS['START_BTN'])
                        if start_state is not None:
                            color = "green" if start_state else "gray"
                            self._update_ui(lambda c=color: self.start_indicator and self.start_indicator.config(fg=c))
                    except Exception as e:
                        self.logger.debug(f"Start button read error: {e}")
                    
                    # Read stop button state
                    try:
                        stop_state = self.gpio_manager.read_input(GPIO_PINS['STOP_BTN'])
                        if stop_state is not None:
                            color = "green" if stop_state else "gray"
                            self._update_ui(lambda c=color: self.stop_indicator and self.stop_indicator.config(fg=c))
                    except Exception as e:
                        self.logger.debug(f"Stop button read error: {e}")
                
                time.sleep(0.1)  # Check every 100ms for responsive feedback
                
            except Exception as e:
                if not self._shutdown_requested:
                    self.logger.debug(f"Button monitoring error: {e}")
                time.sleep(1.0)  # Longer delay on error
    
    def _on_physical_start_pressed(self):
        """Callback for when physical start button is pressed."""
        if self._shutdown_requested:
            return
        
        def update_ui():
            if self.start_indicator:
                self.start_indicator.config(fg="green")
            self.start_stop_status.set("Start button pressed")
        
        self._update_ui(update_ui)
        
        # Reset status message after 2 seconds
        def reset_status():
            if not self._shutdown_requested:
                self.start_stop_status.set("Monitoring physical buttons...")
        
        self.parent.after(2000, reset_status)
    
    def _on_physical_stop_pressed(self):
        """Callback for when physical stop button is pressed."""
        if self._shutdown_requested:
            return
        
        def update_ui():
            if self.stop_indicator:
                self.stop_indicator.config(fg="green")
            self.start_stop_status.set("Stop button pressed")
        
        self._update_ui(update_ui)
        
        # Reset status message after 2 seconds
        def reset_status():
            if not self._shutdown_requested:
                self.start_stop_status.set("Monitoring physical buttons...")
        
        self.parent.after(2000, reset_status)
    
    # ===== UTILITY METHODS =====
    
    def _update_ui(self, update_func: Callable):
        """Thread-safe UI update method."""
        if self._shutdown_requested:
            return
        
        if threading.current_thread() != threading.main_thread():
            try:
                self.parent.after_idle(update_func)
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
            except Exception as e:
                self.logger.error(f"Error scheduling UI update: {e}")
        else:
            try:
                update_func()
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
            except Exception as e:
                self.logger.error(f"Error in UI update: {e}")
    
    # ===== LIFECYCLE METHODS =====
    
    def on_selected(self):
        """Called when this section is selected."""
        super().on_selected()
        
        # Refresh data when section becomes visible
        self._schedule_ui_update(self._refresh_pressure_readings)
        self._schedule_ui_update(self._check_printer_status)
        
        self.logger.info("Diagnostics section selected and refreshed")
    
    def on_deselected(self):
        """Called when this section is deselected."""
        # No need to stop monitoring threads here as they should continue
        # running in the background for real-time updates
        return super().on_deselected()
    
    def cleanup(self):
        """Cleanup when section is destroyed with comprehensive resource management."""
        self.logger.info("Starting diagnostics section cleanup...")
        
        try:
            # Set shutdown flag to stop all background operations
            self._shutdown_requested = True
            
            # Stop all background monitoring
            self._valve_operations.clear()
            self._led_test_active = False
            self._printer_monitoring_active = False
            self._button_monitoring_active = False
            
            # Clear UI references to prevent access to destroyed widgets
            self.valve_indicators.clear()
            self.start_led_indicator = None
            self.stop_led_indicator = None
            self.printer_indicator = None
            self.start_indicator = None
            self.stop_indicator = None
            
            # Unregister button callbacks if they were registered
            if (self.physical_controls and 
                hasattr(self.physical_controls, 'register_start_callback')):
                try:
                    # Note: Most callback systems don't have unregister methods,
                    # so we just clear our references
                    pass
                except Exception as e:
                    self.logger.debug(f"Error unregistering callbacks: {e}")
            
            self.logger.info("Diagnostics section cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during diagnostics cleanup: {e}")
        
        # Call base cleanup
        super().cleanup()