#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FIXED: Enhanced Main Tab module for the Multi-Chamber Test application.

This module provides the MainTab class with improved pressure gauges,
simplified timeline, and enhanced status display.

FIXED: Manual mode support - properly handles test mode switching
- Always initializes core variables regardless of mode
- Implements proper manual mode UI with chamber parameter display
- Fixes start_test() logic to handle both reference and manual modes
- Robust error handling and logging

Key fixes:
- Core variables always initialized in __init__
- Manual mode UI implementation with chamber settings display
- Mode-specific start_test() logic
- Proper variable lifecycle management
- FIXED: Syntax error in show_test_results method
"""

import tkinter as tk
from tkinter import ttk
import logging
import math
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, UI_DIMENSIONS, TEST_STATES, PRESSURE_DEFAULTS
from multi_chamber_test.core.test_manager import TestManager
from multi_chamber_test.config.settings import SettingsManager


class MainTab:
    """
    Enhanced main testing interface tab with FIXED manual mode support.
    
    This class implements the main testing screen with enhanced pressure gauges,
    simplified timeline, improved status display, and FIXED frame positioning.
    FIXED: Proper support for both reference and manual test modes.
    """
    
    def __init__(self, parent, test_manager: TestManager, settings_manager: SettingsManager):
        """
        Initialize the MainTab with the parent widget and TestManager.
        
        Args:
            parent: Parent widget (typically a Frame in main_window.py)
            test_manager: TestManager instance for test control
            settings_manager: SettingsManager instance for configuration
        """
        self.logger = logging.getLogger('MainTab')
        self._setup_logger()
       
        self.parent = parent
        self.test_manager = test_manager
        self.settings_manager = settings_manager
        
        # Register as observer for settings changes
        self.settings_manager.register_observer(self.on_setting_changed)

        # Store colors for easy access
        self.colors = UI_COLORS

        # Set up internal state variables
        self.test_running = False
        self.test_state = tk.StringVar(value="IDLE")
        
        # FIXED: Always initialize core variables regardless of test mode
        # These variables are needed by various methods regardless of the current mode
        self.current_reference = tk.StringVar(value="")
        self.barcode_var = tk.StringVar()
        
        # Track current test mode for proper UI management
        self.current_test_mode = self.settings_manager.get_setting('test_mode', "reference")
        
        # Set up variable traces
        self.test_state.trace_add('write', self._handle_state_change)
        
        # Setup TTK styles
        self._setup_styles()
        
        # Main container frame
        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Create UI components
        self.create_status_section()
        self.create_reference_section()
        self.create_chamber_gauges()
        self.create_timeline()
        self.create_control_buttons()
        
        # Register callbacks with test manager
        self.test_manager.set_callbacks(
            status_callback=self.update_status,
            progress_callback=self.update_progress,
            result_callback=self.show_test_results
        )
        
        # Initialize the UI with current test state
        self.update_all()
        
        # Schedule regular UI updates
        self._start_ui_updates()
    
    def _setup_logger(self):
        """Configure logging for the main tab."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _setup_styles(self):
        """Setup TTK styles for the interface."""
        style = ttk.Style()
        
        # Card frame style
        style.configure(
            'Card.TFrame',
            background=UI_COLORS['BACKGROUND'],
            relief='solid',
            borderwidth=1,
            bordercolor=UI_COLORS['BORDER']
        )
        
        # Status background styles
        style.configure(
            'StatusBg.TFrame',
            background=UI_COLORS['STATUS_BG']
        )
        style.configure(
            'StatusRunning.TFrame',
            background=UI_COLORS['PRIMARY']
        )
        style.configure(
            'StatusWarning.TFrame',
            background=UI_COLORS['WARNING']
        )
        style.configure(
            'StatusSuccess.TFrame',
            background=UI_COLORS['SUCCESS']
        )
        style.configure(
            'StatusError.TFrame',
            background=UI_COLORS['ERROR']
        )
        
        # Text styles
        style.configure(
            'CardTitle.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY'],
            font=UI_FONTS['HEADER']
        )
        style.configure(
            'CardText.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY'],
            font=UI_FONTS['LABEL']
        )
        style.configure(
            'Status.TLabel',
            background=UI_COLORS['STATUS_BG'],
            foreground=UI_COLORS['TEXT_PRIMARY'],
            font=UI_FONTS['SUBHEADER']
        )
        style.configure(
            'StatusRunning.TLabel',
            background=UI_COLORS['PRIMARY'],
            foreground=UI_COLORS['SECONDARY'],
            font=UI_FONTS['SUBHEADER']
        )
        style.configure(
            'StatusWarning.TLabel',
            background=UI_COLORS['WARNING'],
            foreground=UI_COLORS['SECONDARY'],
            font=UI_FONTS['SUBHEADER']
        )
        style.configure(
            'StatusSuccess.TLabel',
            background=UI_COLORS['SUCCESS'],
            foreground=UI_COLORS['SECONDARY'],
            font=UI_FONTS['SUBHEADER']
        )
        style.configure(
            'StatusError.TLabel',
            background=UI_COLORS['ERROR'],
            foreground=UI_COLORS['SECONDARY'],
            font=UI_FONTS['SUBHEADER']
        )
        style.configure(
            'GaugeTitle.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY'],
            font=UI_FONTS['SUBHEADER'],
            anchor='center'
        )
        style.configure(
            'Value.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY'],
            font=UI_FONTS['VALUE']
        )
        
        # Button styles
        style.configure(
            'Action.TButton',
            font=UI_FONTS['BUTTON'],
            background=UI_COLORS['PRIMARY'],
            foreground=UI_COLORS['SECONDARY']
        )
        style.map(
            'Action.TButton',
            background=[('active', UI_COLORS['PRIMARY'])]
        )
        
        style.configure(
            'Warning.TButton',
            font=UI_FONTS['BUTTON'],
            background=UI_COLORS['ERROR'],
            foreground=UI_COLORS['SECONDARY']
        )
        style.map(
            'Warning.TButton',
            background=[('active', UI_COLORS['ERROR'])]
        )
    
    def create_status_section(self):
        """Create the status display section."""
        status_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Status message with colored background
        status_container = ttk.Frame(status_frame, padding=15)
        status_container.pack(fill=tk.X, pady=(0, 10))
        
        # Status message with dynamic background
        self.status_bg_frame = ttk.Frame(
            status_container,
            style='StatusBg.TFrame',
            padding=10
        )
        self.status_bg_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(
            self.status_bg_frame,
            text=TEST_STATES["IDLE"],
            style='Status.TLabel',
            anchor=tk.CENTER
        )
        self.status_label.pack(fill=tk.X)
    
    def create_reference_section(self):
        """Create the reference selection and barcode scanning section."""
        self.ref_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        self.ref_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Get the current test mode from settings
        test_mode = self.settings_manager.get_setting('test_mode', "reference")
        
        # Build content based on mode
        self._build_reference_content(test_mode)
    
    def _build_reference_content(self, test_mode, current_ref=""):
        """FIXED: Build reference section content based on test mode with proper support for manual mode."""
        # Clear existing content
        for widget in self.ref_frame.winfo_children():
            widget.destroy()
        
        # Title
        title_text = "Test Reference" if test_mode == "reference" else "Test Configuration"
        ttk.Label(
            self.ref_frame,
            text=title_text,
            style='CardTitle.TLabel'
        ).pack(anchor=tk.W, padx=15, pady=(10, 0))
        
        # Description text about the current mode
        description_frame = ttk.Frame(self.ref_frame, padding=(15, 10))
        description_frame.pack(fill=tk.X)
        
        if test_mode == "reference":
            description_text = "Scan a barcode to load test parameters."
        else:  # manual mode
            description_text = "Using chamber parameters from settings."
        
        ttk.Label(
            description_frame,
            text=description_text,
            style='CardText.TLabel'
        ).pack(anchor=tk.W, pady=(5, 0))
        
        # Mode-specific content
        if test_mode == "reference":
            self._create_reference_mode_content(current_ref)
        else:  # manual mode
            self._create_manual_mode_content()

    def _create_reference_mode_content(self, current_ref=""):
        """Create content for reference mode with barcode scanner input and current reference display."""
        # Create container for reference mode content
        reference_frame = ttk.Frame(self.ref_frame, padding=(15, 5, 15, 10))
        reference_frame.pack(fill=tk.X)
        
        # Barcode scanner input row
        scanner_row = ttk.Frame(reference_frame)
        scanner_row.pack(fill=tk.X, pady=(0, 5))
        
        # Barcode scanner label and entry
        ttk.Label(
            scanner_row,
            text="Scan Barcode:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Barcode entry field (hidden but functional for scanner input)
        self.barcode_entry = ttk.Entry(
            scanner_row,
            textvariable=self.barcode_var,
            width=30,
            font=UI_FONTS['VALUE']
        )
        self.barcode_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.barcode_entry.bind('<Return>', self.handle_barcode_scan)
        self.barcode_entry.bind('<KeyRelease>', self._on_barcode_input)
        
        # Set focus on the barcode entry
        self.barcode_entry.focus_set()
        
        # Current reference display row
        reference_row = ttk.Frame(reference_frame)
        reference_row.pack(fill=tk.X)
        
        # Current reference label and value on the same line
        ttk.Label(
            reference_row,
            text="Current Reference:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Reference value display
        self.ref_value_label = ttk.Label(
            reference_row,
            textvariable=self.current_reference,
            style='Value.TLabel'
        )
        self.ref_value_label.pack(side=tk.LEFT)
        
        # Set current reference if provided
        if current_ref:
            self.current_reference.set(current_ref)
        elif not self.current_reference.get():
            # Show placeholder if no reference loaded
            self.current_reference.set("No reference loaded")
        
        # Schedule focus maintenance
        self._maintain_barcode_focus()

    def _create_manual_mode_content(self):
        """Create simplified content for manual mode (description text only)."""
        # Create container for manual mode content
        manual_frame = ttk.Frame(self.ref_frame, padding=(15, 5, 15, 10))
        manual_frame.pack(fill=tk.X)
        
        # Simple description text only
        ttk.Label(
            manual_frame,
            text="Using chamber parameters from settings.",
            style='CardText.TLabel'
        ).pack(anchor=tk.W)

    def _get_chamber_configurations(self):
        """Get current chamber configurations from test manager or settings."""
        configurations = []
        
        try:
            # Try to get from test manager first
            if hasattr(self.test_manager, 'chamber_states') and self.test_manager.chamber_states:
                for i, chamber_state in enumerate(self.test_manager.chamber_states):
                    if i < 3:  # Only first 3 chambers
                        config = {
                            'enabled': getattr(chamber_state, 'enabled', True),
                            'target': getattr(chamber_state, 'pressure_target', 'N/A'),
                            'threshold': getattr(chamber_state, 'pressure_threshold', 'N/A')
                        }
                        configurations.append(config)
                        
            # If we don't have enough configurations, pad with defaults
            while len(configurations) < 3:
                config = {
                    'enabled': self.settings_manager.get_setting(f'chamber_{len(configurations)+1}_enabled', True),
                    'target': self.settings_manager.get_setting(f'chamber_{len(configurations)+1}_target', 300),
                    'threshold': self.settings_manager.get_setting(f'chamber_{len(configurations)+1}_threshold', 280)
                }
                configurations.append(config)
                
        except Exception as e:
            self.logger.error(f"Error getting chamber configurations: {e}")
            # Fallback to default configurations
            for i in range(3):
                config = {
                    'enabled': True,
                    'target': 300,
                    'threshold': 280
                }
                configurations.append(config)
        
        return configurations[:3]  # Only return first 3

    def _create_standard_barcode_interface(self, current_ref=""):
        """Create standard barcode interface layout."""
        self.barcode_frame = ttk.Frame(self.ref_frame, padding=(15, 5, 15, 10))
        self.barcode_frame.pack(fill=tk.X)
        
        # Barcode label and entry
        input_row = ttk.Frame(self.barcode_frame)
        input_row.pack(fill=tk.X)
        
        self.ref_label = ttk.Label(
            input_row,
            text="Scan Reference Barcode:",
            style='CardText.TLabel'
        )
        self.ref_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Barcode entry field
        self.barcode_entry = ttk.Entry(
            input_row,
            textvariable=self.barcode_var,
            width=30,
            font=UI_FONTS['VALUE']
        )
        self.barcode_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.barcode_entry.bind('<Return>', self.handle_barcode_scan)
        self.barcode_entry.focus_set()
        
        # Current reference display
        if current_ref or (hasattr(self, 'current_reference') and self.current_reference.get()):
            self._create_current_reference_display(current_ref)

    def _create_compact_barcode_interface(self, current_ref=""):
        """Create compact barcode interface for limited screen space."""
        self.barcode_frame = ttk.Frame(self.ref_frame, padding=(10, 3, 10, 8))
        self.barcode_frame.pack(fill=tk.X)
        
        # Everything on one line for compact layout
        main_row = ttk.Frame(self.barcode_frame)
        main_row.pack(fill=tk.X)
        
        # Shorter label
        ttk.Label(
            main_row,
            text="Barcode:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        # Compact entry
        self.barcode_entry = ttk.Entry(
            main_row,
            textvariable=self.barcode_var,
            width=20,  # Reduced width
            font=UI_FONTS['VALUE']
        )
        self.barcode_entry.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        self.barcode_entry.bind('<Return>', self.handle_barcode_scan)
        self.barcode_entry.focus_set()
        
        # Current reference inline if exists
        if current_ref or (hasattr(self, 'current_reference') and self.current_reference.get()):
            ref_text = current_ref or self.current_reference.get()
            ttk.Label(
                main_row,
                text="Current:",
                style='CardText.TLabel'
            ).pack(side=tk.LEFT, padx=(10, 5))
            
            ttk.Label(
                main_row,
                text=ref_text,
                style='Value.TLabel'
            ).pack(side=tk.LEFT)

    def _create_current_reference_display(self, current_ref):
        """Create current reference display section."""
        # Current Reference display (initially hidden, shown when reference is loaded)
        self.ref_display_frame = ttk.Frame(self.ref_frame, padding=(15, 5, 15, 10))
        
        ttk.Label(
            self.ref_display_frame,
            text="Current Reference:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Restore current reference or use provided value
        if current_ref:
            self.current_reference.set(current_ref)
        
        self.ref_value_label = ttk.Label(
            self.ref_display_frame,
            textvariable=self.current_reference,
            style='Value.TLabel'
        )
        self.ref_value_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Show current reference if available
        if self.current_reference.get():
            self.ref_display_frame.pack(fill=tk.X)

    def _calculate_available_height(self):
        """Calculate available screen height for content."""
        try:
            # Get screen dimensions
            screen_height = self.parent.winfo_screenheight()
            
            # Account for title bar, status bar, etc.
            reserved_height = 150
            
            # Calculate current content height
            self.main_frame.update_idletasks()
            current_height = sum(child.winfo_reqheight() for child in self.main_frame.winfo_children())
            
            # Return available height
            return screen_height - reserved_height - current_height
        except Exception as e:
            self.logger.error(f"Error calculating available height: {e}")
            return 300  # Safe fallback

    def _ensure_reference_frame_visibility(self):
        """Ensure reference frame and all other frames remain visible."""
        try:
            # Force geometry update
            self.main_frame.update_idletasks()
            
            # Check total height
            total_height = sum(child.winfo_reqheight() for child in self.main_frame.winfo_children())
            screen_height = self.parent.winfo_screenheight()
            available_height = screen_height - 150  # Account for window decorations
            
            if total_height > available_height:
                self.logger.warning(f"Content height ({total_height}) exceeds screen space ({available_height})")
                self._apply_space_optimization()
            
        except Exception as e:
            self.logger.error(f"Error ensuring frame visibility: {e}")

    def _apply_space_optimization(self):
        """Apply space optimizations when content exceeds screen height."""
        # Reduce padding on reference frame if it exists
        if hasattr(self, 'barcode_frame'):
            # Reduce padding
            self.barcode_frame.configure(padding=(10, 2, 10, 5))
        
        # Slightly reduce gauge sizes
        if hasattr(self, 'pressure_gauges'):
            for canvas in self.pressure_gauges:
                current_size = canvas.winfo_reqwidth()
                if current_size > 120:  # Only reduce if reasonably large
                    new_size = max(100, int(current_size * 0.9))
                    canvas.configure(width=new_size, height=new_size)
        
        # Reduce timeline height
        if hasattr(self, 'timeline_canvas'):
            current_height = self.timeline_canvas.winfo_reqheight()
            if current_height > 40:
                new_height = max(30, int(current_height * 0.8))
                self.timeline_canvas.configure(height=new_height)
    
    def create_chamber_gauges(self):
        """Create the enhanced pressure gauges for all chambers."""
        # Main container for all gauges
        gauges_container = ttk.Frame(self.main_frame, style='Card.TFrame')
        gauges_container.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Title
        ttk.Label(
            gauges_container,
            text="Chamber Pressure Monitoring",
            style='CardTitle.TLabel'
        ).pack(anchor=tk.W, padx=15, pady=(10, 0))
        
        # Gauge content frame
        self.gauges_frame = ttk.Frame(gauges_container, padding=15)
        self.gauges_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid columns to be equal width
        self.gauges_frame.columnconfigure(0, weight=1)
        self.gauges_frame.columnconfigure(1, weight=1)
        self.gauges_frame.columnconfigure(2, weight=1)
        
        # Create enhanced gauges for each chamber
        self.chamber_frames = []
        self.pressure_gauges = []
        
        for i in range(3):
            # Gauge frame
            chamber_frame = ttk.Frame(self.gauges_frame)
            chamber_frame.grid(row=0, column=i, sticky='nsew', padx=10)
            
            # Chamber title
            ttk.Label(
                chamber_frame,
                text=f"Chamber {i+1}",
                style='GaugeTitle.TLabel'
            ).pack(pady=(0, 5))
            
            # Pressure gauge (Canvas)
            gauge_canvas = tk.Canvas(
                chamber_frame,
                width=UI_DIMENSIONS['GAUGE_SIZE'],
                height=UI_DIMENSIONS['GAUGE_SIZE'],
                bg=UI_COLORS['BACKGROUND'],
                highlightthickness=0
            )
            gauge_canvas.pack(pady=5)
            
            # Store references
            self.chamber_frames.append(chamber_frame)
            self.pressure_gauges.append(gauge_canvas)
            
            # Initial draw - initialize the enhanced gauge
            self.initialize_enhanced_pressure_gauge(i, enabled=True)
    
    def create_timeline(self):
        """Create the simplified test timeline visualization."""
        timeline_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        timeline_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        ttk.Label(
            timeline_frame,
            text="Leak Test Progress",
            style='CardTitle.TLabel'
        ).pack(anchor=tk.W, padx=15, pady=(10, 0))
        
        # Timeline content
        timeline_content = ttk.Frame(timeline_frame, padding=15)
        timeline_content.pack(fill=tk.X)
        
        # Timeline canvas
        self.timeline_canvas = tk.Canvas(
            timeline_content,
            height=UI_DIMENSIONS['TIMELINE_HEIGHT'],
            bg=UI_COLORS['BACKGROUND'],
            highlightthickness=0
        )
        self.timeline_canvas.pack(fill=tk.X, expand=True)
        
        # Initial draw
        self.draw_simplified_timeline(0, 0)
    
    def create_control_buttons(self):
        """Create the test control buttons."""
        buttons_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        buttons_frame.pack(fill=tk.X)
        
        # Button container with padding
        button_container = ttk.Frame(buttons_frame, padding=15)
        button_container.pack(fill=tk.X)
        
        # Start Test button
        self.start_button = ttk.Button(
            button_container,
            text="Start Test",
            command=self.start_test,
            style='Action.TButton',
            width=UI_DIMENSIONS['BUTTON_WIDTH']
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Stop Test button (initially disabled)
        self.stop_button = ttk.Button(
            button_container,
            text="Stop Test",
            command=self.stop_test,
            style='Warning.TButton',
            width=UI_DIMENSIONS['BUTTON_WIDTH'],
            state='disabled'
        )
        self.stop_button.pack(side=tk.LEFT)
    
    def _handle_state_change(self, *args):
        """Handle changes in test state with proper UI updates."""
        state = self.test_state.get()
        
        # Update status label based on state
        if state in TEST_STATES:
            self.status_label.config(text=TEST_STATES[state])
        
        # Update status colors based on state
        if state == "IDLE":
            self.status_bg_frame.configure(style='StatusBg.TFrame')
            self.status_label.configure(style='Status.TLabel')
        elif state in ["FILLING", "REGULATING", "STABILIZING", "TESTING"]:
            self.status_bg_frame.configure(style='StatusRunning.TFrame')
            self.status_label.configure(style='StatusRunning.TLabel')
        elif state == "EMPTYING":
            self.status_bg_frame.configure(style='StatusWarning.TFrame')
            self.status_label.configure(style='StatusWarning.TLabel')
        elif state == "COMPLETE":
            self.status_bg_frame.configure(style='StatusSuccess.TFrame')
            self.status_label.configure(style='StatusSuccess.TLabel')
        elif state == "ERROR":
            self.status_bg_frame.configure(style='StatusError.TFrame')
            self.status_label.configure(style='StatusError.TLabel')
        
        # Update button states based on test state
        if state in ["IDLE", "COMPLETE", "ERROR"]:
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            self.test_running = False
        else:
            self.start_button.config(state='disabled')
            self.stop_button.config(state='normal')
            self.test_running = True
    
    def handle_barcode_scan(self, event=None):
        """Handle barcode scanner input."""
        barcode = self.barcode_var.get().strip()
        if not barcode:
            self.logger.warning("Empty barcode scanned")
            return
        
        # Try to load the reference
        success = self.test_manager.set_test_mode("reference", barcode)
        
        if success:
            # Update the StringVar; the label on the same line will update automatically.
            self.current_reference.set(f"Current: {barcode}")
            
            # Clear barcode field for next scan
            self.barcode_var.set("")
            
            # Show success message
            self.update_status("IDLE", f"Reference {barcode} loaded successfully")
            for chamber_index in range(len(self.test_manager.chamber_states)):
                self.update_chamber_display(chamber_index)
        else:
            # Show error and clear field
            self.barcode_var.set("")
            self.update_status("ERROR", f"Reference {barcode} not found or invalid")
    
    def initialize_enhanced_pressure_gauge(self, chamber_index: int, target: float = None, 
                                         threshold: float = None, tolerance: float = None, 
                                         enabled: bool = True, failed: bool = False):
        """Initialize the enhanced pressure gauge with target and threshold indicators and failure highlighting."""
        canvas = self.pressure_gauges[chamber_index]
        canvas.delete("all")  # Clear the canvas completely for initialization
        
        # Get chamber state from test manager for default values if needed
        chamber_state = self.test_manager.chamber_states[chamber_index]
        chamber_target = target if target is not None else chamber_state.pressure_target
        chamber_threshold = threshold if threshold is not None else chamber_state.pressure_threshold
        chamber_tolerance = tolerance if tolerance is not None else chamber_state.pressure_tolerance
        chamber_enabled = enabled if enabled is not None else chamber_state.enabled
        
        # Constants for gauge dimensions
        GAUGE_SIZE = UI_DIMENSIONS['GAUGE_SIZE']
        CENTER_X, CENTER_Y = GAUGE_SIZE // 2, GAUGE_SIZE // 2
        RADIUS = (GAUGE_SIZE // 2) - 15
        INNER_RADIUS = RADIUS - 25
        MAX_PRESSURE = PRESSURE_DEFAULTS['MAX_PRESSURE']
        
        # Determine background color based on failure state
        if failed:
            background_color = '#FFEBEE'  # Light red background for failed chambers
            border_color = UI_COLORS['ERROR']
            border_width = 3
        elif not chamber_enabled:
            background_color = '#F5F5F5'  # Gray background for disabled chambers
            border_color = UI_COLORS['BORDER']
            border_width = 2
        else:
            background_color = UI_COLORS['BACKGROUND']
            border_color = UI_COLORS['BORDER']
            border_width = 2
        
        # Draw gauge background with failure highlighting
        canvas.create_oval(
            CENTER_X - RADIUS,
            CENTER_Y - RADIUS,
            CENTER_X + RADIUS,
            CENTER_Y + RADIUS,
            fill=background_color,
            outline=border_color,
            width=border_width,
            tags=("static", "background")
        )
        
        # Skip the rest if chamber is disabled
        if not chamber_enabled:
            canvas.create_text(
                CENTER_X,
                CENTER_Y - 10,
                text="Disabled",
                font=UI_FONTS['SUBHEADER'],
                fill=UI_COLORS['TEXT_SECONDARY'],
                tags=("static", "disabled_text")
            )
            return
        
        # Show failure indicator for failed chambers
        if failed:
            canvas.create_text(
                CENTER_X,
                CENTER_Y - 50,
                text="FAILED",
                font=UI_FONTS['SUBHEADER'],
                fill=UI_COLORS['ERROR'],
                tags=("static", "failure_text")
            )
        
        # Draw tolerance zone background (skip if failed to avoid visual confusion)
        if not failed:
            tolerance_start = chamber_target - chamber_tolerance
            tolerance_end = chamber_target + chamber_tolerance
            tolerance_start_angle = 150 - (tolerance_start * 300 / MAX_PRESSURE)
            tolerance_end_angle = 150 - (tolerance_end * 300 / MAX_PRESSURE)
            
            canvas.create_arc(
                CENTER_X - RADIUS,
                CENTER_Y - RADIUS,
                CENTER_X + RADIUS,
                CENTER_Y + RADIUS,
                start=tolerance_start_angle,
                extent=tolerance_end_angle - tolerance_start_angle,
                fill='#E8F5E9',  # Light green background for tolerance zone
                outline='',
                tags=("static", "tolerance_zone")
            )
        
        # Draw main scale arc with failure coloring
        scale_color = UI_COLORS['ERROR'] if failed else UI_COLORS['BORDER']
        canvas.create_arc(
            CENTER_X - RADIUS,
            CENTER_Y - RADIUS,
            CENTER_X + RADIUS,
            CENTER_Y + RADIUS,
            start=150,
            extent=-300,
            style=tk.ARC,
            outline=scale_color,
            width=14,
            tags=("static", "scale_arc")
        )
        
        # Draw scale markers and labels
        for i in range(0, MAX_PRESSURE + 1, 100):
            angle = 150 - (i * 300 / MAX_PRESSURE)
            radian = math.radians(angle)
            
            # Draw major tick marks
            cos_val = math.cos(radian)
            sin_val = math.sin(radian)
            
            marker_color = UI_COLORS['ERROR'] if failed else UI_COLORS['TEXT_PRIMARY']
            canvas.create_line(
                CENTER_X + INNER_RADIUS * cos_val,
                CENTER_Y - INNER_RADIUS * sin_val,
                CENTER_X + RADIUS * cos_val,
                CENTER_Y - RADIUS * sin_val,
                fill=marker_color,
                width=3,
                tags=("static", "scale_marker")
            )
            
            # Draw label
            label_radius = INNER_RADIUS - 22
            label_color = UI_COLORS['ERROR'] if failed else UI_COLORS['TEXT_PRIMARY']
            canvas.create_text(
                CENTER_X + label_radius * cos_val,
                CENTER_Y - label_radius * sin_val,
                text=str(i),
                font=UI_FONTS['GAUGE_UNIT'],
                fill=label_color,
                tags=("static", "scale_label")
            )
        
        # Draw pointer pivot
        pivot_color = UI_COLORS['ERROR'] if failed else UI_COLORS['PRIMARY']
        canvas.create_oval(
            CENTER_X - 5,
            CENTER_Y - 5,
            CENTER_X + 5,
            CENTER_Y + 5,
            fill=pivot_color,
            outline="",
            tags=("static", "pivot")
        )
        
        # Add enhanced target marker (green triangle) - skip if failed
        if not failed:
            target_angle = 150 - (chamber_target * 300 / MAX_PRESSURE)
            target_radian = math.radians(target_angle)
            cos_val = math.cos(target_radian)
            sin_val = math.sin(target_radian)
            
            # Create triangle points for the target marker
            triangle_size = 12
            p1_x = CENTER_X + (RADIUS + 8) * cos_val
            p1_y = CENTER_Y - (RADIUS + 8) * sin_val
            p2_x = CENTER_X + (RADIUS - triangle_size) * cos_val - triangle_size * sin_val
            p2_y = CENTER_Y - (RADIUS - triangle_size) * sin_val - triangle_size * cos_val
            p3_x = CENTER_X + (RADIUS - triangle_size) * cos_val + triangle_size * sin_val
            p3_y = CENTER_Y - (RADIUS - triangle_size) * sin_val + triangle_size * cos_val
            
            canvas.create_polygon(
                p1_x, p1_y, p2_x, p2_y, p3_x, p3_y,
                fill=UI_COLORS['SUCCESS'],
                outline='darkgreen',
                width=2,
                tags=("static", "target_marker")
            )
            
            # Add enhanced threshold marker (red triangle)
            threshold_angle = 150 - (chamber_threshold * 300 / MAX_PRESSURE)
            threshold_radian = math.radians(threshold_angle)
            cos_val = math.cos(threshold_radian)
            sin_val = math.sin(threshold_radian)
            
            # Create triangle points for the threshold marker
            p1_x = CENTER_X + (RADIUS + 8) * cos_val
            p1_y = CENTER_Y - (RADIUS + 8) * sin_val
            p2_x = CENTER_X + (RADIUS - triangle_size) * cos_val - triangle_size * sin_val
            p2_y = CENTER_Y - (RADIUS - triangle_size) * sin_val - triangle_size * cos_val
            p3_x = CENTER_X + (RADIUS - triangle_size) * cos_val + triangle_size * sin_val
            p3_y = CENTER_Y - (RADIUS - triangle_size) * sin_val + triangle_size * cos_val
            
            canvas.create_polygon(
                p1_x, p1_y, p2_x, p2_y, p3_x, p3_y,
                fill=UI_COLORS['ERROR'],
                outline='darkred',
                width=2,
                tags=("static", "threshold_marker")
            )
        
        # Draw unit text
        unit_color = UI_COLORS['ERROR'] if failed else UI_COLORS['TEXT_SECONDARY']
        canvas.create_text(
            CENTER_X,
            CENTER_Y + 40,
            text="mbar",
            font=UI_FONTS['GAUGE_UNIT'],
            fill=unit_color,
            tags=("static", "unit_text")
        )
    
    def update_gauge_display(self, chamber_index: int, current_pressure: float = 0.0, failed: bool = False):
        """Update the dynamic parts of the enhanced pressure gauge display with failure highlighting."""
        try:
            canvas = self.pressure_gauges[chamber_index]
            
            # Get chamber state for enabled status
            chamber_state = self.test_manager.chamber_states[chamber_index]
            chamber_enabled = chamber_state.enabled
            
            # Skip update if chamber is disabled
            if not chamber_enabled:
                return
                
            # Get dimensions
            GAUGE_SIZE = UI_DIMENSIONS['GAUGE_SIZE']
            CENTER_X, CENTER_Y = GAUGE_SIZE // 2, GAUGE_SIZE // 2
            RADIUS = (GAUGE_SIZE // 2) - 15
            MAX_PRESSURE = PRESSURE_DEFAULTS['MAX_PRESSURE']
            
            # Constrain pressure value to valid range for display
            display_pressure = max(0, min(current_pressure, MAX_PRESSURE))
            
            # Calculate pointer angle from pressure value
            angle = 150 - (display_pressure * 300 / MAX_PRESSURE)
            radian = math.radians(angle)
            cos_val = math.cos(radian)
            sin_val = math.sin(radian)
            
            # Remove previous dynamic elements
            canvas.delete("dynamic")
            
            # Draw pointer line with failure coloring
            pointer_length = RADIUS - 20
            pointer_color = UI_COLORS['ERROR'] if failed else UI_COLORS['PRIMARY']
            canvas.create_line(
                CENTER_X, CENTER_Y,
                CENTER_X + pointer_length * cos_val,
                CENTER_Y - pointer_length * sin_val,
                fill=pointer_color,
                width=4,
                tags=("dynamic", "pointer")
            )
            
            # Draw digital value display as integer with failure coloring
            display_value = int(round(current_pressure))
            value_color = UI_COLORS['ERROR'] if failed else UI_COLORS['PRIMARY']
            canvas.create_text(
                CENTER_X,
                CENTER_Y + 20,
                text=f"{display_value}",
                font=UI_FONTS['VALUE'],
                fill=value_color,
                tags=("dynamic", "pressure_value")
            )
            
        except Exception as e:
            self.logger.error(f"Error updating gauge display: {e}")
    
    def draw_simplified_timeline(self, current_time: float, total_time: float):
        """Draw the simplified test timeline visualization without current time display."""
        canvas = self.timeline_canvas
        canvas.delete("all")  # Clear previous drawing
        
        # Get canvas dimensions
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        
        # Use default width if not yet packed
        if width < 10:
            width = 600
        
        # Timeline constants
        padding = 20
        bar_height = height // 2
        
        # Draw timeline background
        canvas.create_rectangle(
            padding, height // 2 - bar_height // 2,
            width - padding, height // 2 + bar_height // 2,
            fill=UI_COLORS['BACKGROUND_ALT'],
            outline=UI_COLORS['BORDER'],
            width=1
        )
        
        # Calculate progress proportion
        if total_time > 0:
            progress = min(1.0, current_time / total_time)
        else:
            progress = 0
            
        # Draw progress fill
        progress_width = (width - 2 * padding) * progress
        if progress_width > 0:
            canvas.create_rectangle(
                padding, height // 2 - bar_height // 2,
                padding + progress_width, height // 2 + bar_height // 2,
                fill=UI_COLORS['PRIMARY'],
                outline="",
            )
        
        # Draw labels - only start and end times (no current time)
        # Start time
        canvas.create_text(
            padding, height // 2 + bar_height // 2 + 15,
            text="0:00",
            font=UI_FONTS['LABEL'],
            fill=UI_COLORS['TEXT_PRIMARY'],
            anchor='w'
        )
        
        # End time (test duration)
        if total_time > 0:
            minutes, seconds = divmod(int(total_time), 60)
            time_text = f"{minutes}:{seconds:02d}"
        else:
            # Use configured test duration
            test_duration = getattr(self.test_manager, 'test_duration', 300)
            minutes, seconds = divmod(int(test_duration), 60)
            time_text = f"{minutes}:{seconds:02d}"
            
        canvas.create_text(
            width - padding, height // 2 + bar_height // 2 + 15,
            text=time_text,
            font=UI_FONTS['LABEL'],
            fill=UI_COLORS['TEXT_PRIMARY'],
            anchor='e'
        )
    
    def update_progress(self, current_time: float, total_time: float, progress_info: Dict = None):
        """Update the test progress display - only for leak test phase."""
        # Only update timeline during the actual leak test phase
        if progress_info and progress_info.get('phase') == 'testing':
            # Update timeline with leak test progress
            test_duration = getattr(self.test_manager, 'test_duration', total_time)
            self.draw_simplified_timeline(current_time, test_duration)
        else:
            # Clear timeline for non-testing phases
            self.draw_simplified_timeline(0, 0)
    
    def update_status(self, state: str, message: str = None):
        """Update the test status display with direct test manager messages."""
        # Update state variable (will trigger _handle_state_change)
        self.test_state.set(state)
        
        # Update status message directly from test manager if provided
        if message and hasattr(self, 'status_label'):
            self.status_label.config(text=message)
    
    def start_test(self):
        """FIXED: Start the test with proper mode-specific validation."""
        # Get current test mode
        test_mode = self.settings_manager.get_setting('test_mode', "reference")
        
        # Mode-specific validation
        if test_mode == "reference":
            # Reference mode requires a valid reference to be loaded
            if not hasattr(self, 'current_reference') or not self.current_reference.get():
                self.update_status("ERROR", "Please scan a reference barcode before starting the test")
                return
        else:  # manual mode
            # Manual mode can start without reference - parameters come from settings
            self.logger.info("Starting test in manual mode using settings parameters")
        
        # Call the test manager to start the test
        success = self.test_manager.start_test()
        
        if success:
            # Update UI for test running state
            self.test_running = True
            mode_text = "reference" if test_mode == "reference" else "manual"
            self.update_status("FILLING", f"Test started in {mode_text} mode - filling chambers")
        else:
            self.update_status("ERROR", "Failed to start test - check connections")
    
    def stop_test(self):
        """Stop the test."""
        # Call test manager to stop the test
        self.test_manager.stop_test()
        
        # Update UI
        self.update_status("IDLE", "Test stopped by user")
    
    def show_test_results(self, overall_result: bool, chamber_results: List[Dict[str, Any]]):
        """Display test results after completion with chamber failure highlighting."""
        # Update status with result
        result_text = "PASS" if overall_result else "FAIL"
        self.update_status(
            "COMPLETE" if overall_result else "ERROR",
            f"Test Complete - {result_text}"
        )
        
        # Update chamber displays to show failures
        for i, result in enumerate(chamber_results):
            if i < 3 and result.get('enabled', True):  # Only for first 3 enabled chambers
                chamber_failed = not result.get('result', False)
                self.update_chamber_display(i, failed=chamber_failed)
        
        # Create a results frame if it doesn't exist
        if not hasattr(self, 'results_frame'):
            self.results_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
            self.results_frame.pack(fill=tk.X, pady=(0, 10))
        else:
            # Clear previous results
            for widget in self.results_frame.winfo_children():
                widget.destroy()
        
        # Add overall result at the top
        result_bg_color = UI_COLORS['SUCCESS'] if overall_result else UI_COLORS['ERROR']
        result_text_color = UI_COLORS['SECONDARY']
        
        result_frame = ttk.Frame(self.results_frame)
        result_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Add colored background for overall result
        canvas = tk.Canvas(
            result_frame,
            height=60,
            background=result_bg_color,
            highlightthickness=0
        )
        canvas.pack(fill=tk.X)
        
        # Add result text
        result_label = ttk.Label(
            canvas,
            text=f"TEST {result_text}",
            foreground=result_text_color,
            background=result_bg_color,
            font=('Helvetica', 24, 'bold')
        )
        result_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Add chamber results
        content_frame = ttk.Frame(self.results_frame, padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        for i, result in enumerate(chamber_results):
            # Skip disabled chambers
            if not result.get('enabled', True):
                continue
                
            # Create a frame for this chamber's results
            chamber_frame = ttk.Frame(content_frame)
            chamber_frame.pack(fill=tk.X, pady=(0, 10))
            
            # Chamber title
            ttk.Label(
                chamber_frame,
                text=f"Chamber {i+1}",
                font=UI_FONTS['SUBHEADER']
            ).pack(anchor=tk.W)
            
            # Chamber result details
            details_frame = ttk.Frame(chamber_frame)
            details_frame.pack(fill=tk.X, padx=20)
            
            # Chamber target and actual pressure
            ttk.Label(
                details_frame,
                text="Target Pressure:",
                font=UI_FONTS['LABEL']
            ).grid(row=0, column=0, sticky=tk.W, pady=2)
            
            ttk.Label(
                details_frame,
                text=f"{int(round(result.get('target_pressure', 0)))} mbar",
                font=UI_FONTS['VALUE']
            ).grid(row=0, column=1, sticky=tk.W, padx=10, pady=2)
            
            ttk.Label(
                details_frame,
                text="Actual Pressure:",
                font=UI_FONTS['LABEL']
            ).grid(row=1, column=0, sticky=tk.W, pady=2)
            
            ttk.Label(
                details_frame,
                text=f"{int(round(result.get('actual_pressure', 0)))} mbar",
                font=UI_FONTS['VALUE']
            ).grid(row=1, column=1, sticky=tk.W, padx=10, pady=2)
            
            # Chamber result
            chamber_result = result.get('result', False)
            result_color = UI_COLORS['SUCCESS'] if chamber_result else UI_COLORS['ERROR']
            
            ttk.Label(
                details_frame,
                text="Result:",
                font=UI_FONTS['LABEL']
            ).grid(row=2, column=0, sticky=tk.W, pady=2)
            
            ttk.Label(
                details_frame,
                text="PASS" if chamber_result else "FAIL",
                foreground=result_color,
                font=UI_FONTS['VALUE']
            ).grid(row=2, column=1, sticky=tk.W, padx=10, pady=2)
    
    def _on_barcode_input(self, event=None):
        """Handle barcode input as user types or scanner inputs data."""
        # Auto-process when barcode looks complete (common barcode lengths: 8, 12, 13 digits)
        barcode = self.barcode_var.get().strip()
        
        # Check if this looks like a complete barcode (adjust length as needed)
        if len(barcode) >= 8 and (len(barcode) in [8, 12, 13] or barcode.endswith('\n')):
            # Remove any trailing newline from scanner
            clean_barcode = barcode.rstrip('\n\r')
            self.barcode_var.set(clean_barcode)
            
            # Process the barcode
            self.handle_barcode_scan()

    def _maintain_barcode_focus(self):
        """Maintain focus on barcode scanner input field."""
        if hasattr(self, 'barcode_entry') and self.barcode_entry.winfo_exists():
            try:
                # Only set focus if no other widget has focus or if focus is lost
                current_focus = self.barcode_entry.focus_get()
                if current_focus != self.barcode_entry:
                    self.barcode_entry.focus_set()
            except tk.TclError:
                # Widget might be destroyed, stop trying to focus
                return
            
            # Schedule next focus check (every 500ms)
            self.parent.after(500, self._maintain_barcode_focus)
    
    
    
    def update_all(self):
        """Update all UI elements with current data."""
        # Update chamber displays
        for i in range(3):
            self.update_chamber_display(i)
            
        # Check if we have any existing test state to display
        if hasattr(self.test_manager, 'state'):
            current_state = self.test_manager.state
            self.update_status(current_state)
            
        # Check if we have a loaded reference (safely)
        if (hasattr(self.test_manager, 'reference') and 
            self.test_manager.reference and 
            hasattr(self, 'current_reference')):
            self.current_reference.set(self.test_manager.reference)
            if hasattr(self, 'ref_display_frame'):
                self.ref_display_frame.pack(fill=tk.X)
    
    def update_chamber_display(self, chamber_index: int, failed: bool = False):
        """Update a specific chamber's display with current data and failure state."""
        # Get chamber state
        if chamber_index < len(self.test_manager.chamber_states):
            chamber_state = self.test_manager.chamber_states[chamber_index]
            
            # Re-initialize enhanced gauge with chamber state values and failure state
            self.initialize_enhanced_pressure_gauge(
                chamber_index,
                target=chamber_state.pressure_target,
                threshold=chamber_state.pressure_threshold,
                tolerance=chamber_state.pressure_tolerance,
                enabled=chamber_state.enabled,
                failed=failed
            )
            
            # Update pressure value if enabled
            if chamber_state.enabled and hasattr(chamber_state, 'current_pressure'):
                self.update_gauge_display(chamber_index, chamber_state.current_pressure, failed)
    
    def _start_ui_updates(self):
        """Start regular UI updates for pressure gauges."""
        self.update_pressure_gauges()
        
    def update_pressure_gauges(self):
        """Update pressure displays with current readings."""
        try:
            # Update each chamber's pressure display
            for i in range(3):
                if i < len(self.test_manager.chamber_states):
                    chamber_state = self.test_manager.chamber_states[i]
                    if hasattr(chamber_state, 'enabled') and chamber_state.enabled:
                        if hasattr(chamber_state, 'current_pressure'):
                            self.update_gauge_display(i, chamber_state.current_pressure)
        except Exception as e:
            self.logger.error(f"Error updating pressure gauges: {e}")
        
        # Schedule next update (100ms interval is good for responsive gauges)
        self.parent.after(100, self.update_pressure_gauges)
    
    def _rebuild_reference_section(self):
        """FIXED: Recreate the reference section based on current test mode with focus restoration."""
        if not hasattr(self, 'ref_frame'):
            self.logger.debug("No reference frame to rebuild")
            return
            
        # Get the current mode
        test_mode = self.settings_manager.get_setting('test_mode', "reference")
        self.logger.info(f"Rebuilding reference section for mode: {test_mode}")
        
        # Store any current reference value (safely)
        current_ref = ""
        if hasattr(self, 'current_reference'):
            try:
                current_ref = self.current_reference.get()
            except Exception as e:
                self.logger.warning(f"Error getting current reference: {e}")
                current_ref = ""
        
        # Update current test mode tracking
        self.current_test_mode = test_mode
        
        try:
            # Store current packed state of main_frame children
            self.main_frame.update_idletasks()  # Ensure geometry is updated
            
            # Destroy existing frame
            self.ref_frame.destroy()
            
            # Create new frame
            self.ref_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
            
            # STABLE POSITIONING: Always pack after the first child (status section)
            if self.main_frame.winfo_children():
                # Pack after the first child (status section)
                self.ref_frame.pack(after=self.main_frame.winfo_children()[0], fill=tk.X, pady=(0, 10))
            else:
                # Fallback: pack at the beginning with proper fill and padding
                self.ref_frame.pack(fill=tk.X, pady=(0, 10))
            
            # Build content based on mode
            self._build_reference_content(test_mode, current_ref)
            
            # Ensure frame visibility and proper layout
            self._ensure_reference_frame_visibility()
            
            # Restore focus if in reference mode
            if (test_mode == "reference" and 
                hasattr(self, 'barcode_entry') and 
                self.barcode_entry.winfo_exists()):
                # Schedule focus after UI update
                self.parent.after(100, lambda: self.barcode_entry.focus_set())
            
            self.logger.info("Reference section rebuilt successfully")
            
        except Exception as e:
            self.logger.error(f"Error rebuilding reference section: {e}")
            # Try to recover with a minimal reference frame
            try:
                self.ref_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
                self.ref_frame.pack(fill=tk.X, pady=(0, 10))
                
                # Add minimal content
                ttk.Label(
                    self.ref_frame,
                    text=f"Test Mode: {test_mode}",
                    style='CardTitle.TLabel'
                ).pack(anchor=tk.W, padx=15, pady=10)
                
                self.logger.info("Recovery reference section created")
            except Exception as recovery_error:
                self.logger.error(f"Failed to create recovery reference section: {recovery_error}")
    
    def on_setting_changed(self, setting_name: str, new_value):
        """FIXED: Handle settings changes that affect the main tab with improved error handling."""
        # Handle test mode changes
        if setting_name == 'test_mode':
            self.logger.info(f"Test mode changing from {getattr(self, 'current_test_mode', 'unknown')} to: {new_value}")
            
            try:
                # Rebuild reference section with improved positioning
                self._rebuild_reference_section()
                
                # Update all displays to reflect new mode
                self.update_all()
                
                # Log successful mode change
                self.logger.info(f"Successfully switched to {new_value} mode")
                
            except Exception as e:
                self.logger.error(f"Error during test mode change: {e}")
                # Show error to user
                if hasattr(self, 'update_status'):
                    self.update_status("ERROR", f"Mode change failed: {str(e)}")
                
                # Try to restore previous mode
                try:
                    if hasattr(self, 'current_test_mode') and self.current_test_mode != new_value:
                        self.logger.info(f"Attempting to restore previous mode: {self.current_test_mode}")
                        self._rebuild_reference_section()
                except Exception as restore_error:
                    self.logger.error(f"Failed to restore previous mode: {restore_error}")
        
        # Handle other settings that might affect chamber configuration
        elif setting_name.startswith('chamber_') or setting_name == 'test_duration':
            try:
                # Update chamber displays if in manual mode
                if getattr(self, 'current_test_mode', 'reference') == 'manual':
                    self._rebuild_reference_section()
                
                # Update chamber gauges
                self.update_all()
                
            except Exception as e:
                self.logger.error(f"Error updating chamber settings: {e}")
    
    def get_test_state(self):
        """Get current test state for external access (e.g., physical controls)."""
        try:
            return self.test_state.get()
        except Exception as e:
            self.logger.error(f"Error getting test state: {e}")
            return "IDLE"
    
    def on_tab_selected(self):
        """Called when tab is selected - ensure barcode focus is restored."""
        try:
            # Update all displays
            self.update_all()
            
            # Ensure current test mode is correctly displayed
            current_mode = self.settings_manager.get_setting('test_mode', "reference")
            if getattr(self, 'current_test_mode', None) != current_mode:
                self.logger.info(f"Test mode sync needed: {getattr(self, 'current_test_mode', 'None')} -> {current_mode}")
                self._rebuild_reference_section()
            
            # Restore focus to barcode entry if in reference mode
            if (current_mode == "reference" and 
                hasattr(self, 'barcode_entry') and 
                self.barcode_entry.winfo_exists()):
                self.barcode_entry.focus_set()
                
        except Exception as e:
            self.logger.error(f"Error in on_tab_selected: {e}")
        
    
    
    def on_tab_deselected(self):
        """Called when tab is about to be hidden."""
        try:
            # Check if we can safely leave the tab (e.g. no test running)
            if self.test_running:
                # Return False to prevent tab change
                return False
            
            # Allow tab change
            return True
            
        except Exception as e:
            self.logger.error(f"Error in on_tab_deselected: {e}")
            # Allow tab change on error to prevent getting stuck
            return True
    
    def cleanup(self):
        """Perform cleanup when tab is destroyed."""
        try:
            # Stop any scheduled UI updates
            if hasattr(self, 'parent') and self.parent:
                try:
                    # Cancel the after callbacks if possible
                    self.parent.after_cancel(self.update_pressure_gauges)
                except:
                    pass
                    
            # Unregister from settings observer
            if hasattr(self, 'settings_manager'):
                try:
                    self.settings_manager.unregister_observer(self.on_setting_changed)
                except:
                    pass
                    
            self.logger.info("MainTab cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during MainTab cleanup: {e}")