#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Calibration Tab module for the Multi-Chamber Test application.

This module provides the CalibrationTab class that implements the calibration
interface, providing functionality to set pressure sensor offsets for accurate readings.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable, Union

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, UI_DIMENSIONS
from multi_chamber_test.core.calibration_manager import CalibrationManager
from multi_chamber_test.core.roles import has_access
from multi_chamber_test.hardware.pressure_sensor import PressureSensor
from multi_chamber_test.ui.password_dialog import PasswordDialog
from multi_chamber_test.ui.keypad import NumericKeypad


class CalibrationTab:
    """
    Calibration interface tab for pressure sensor offset adjustment.
    
    This class implements the calibration screen with chamber selection
    and offset adjustment controls. It provides a user-friendly interface
    to set the pressure sensor offsets for accurate measurements.
    """
    
    def __init__(self, parent, calibration_manager: CalibrationManager, 
                 pressure_sensor: PressureSensor):
        """
        Initialize the CalibrationTab with the required components.
        
        Args:
            parent: Parent widget (typically a Frame in main_window.py)
            calibration_manager: CalibrationManager for calibration control
            pressure_sensor: PressureSensor for offset management
        """
        self.logger = logging.getLogger('CalibrationTab')
        self._setup_logger()
        
        self.parent = parent
        self.calibration_manager = calibration_manager
        self.pressure_sensor = pressure_sensor
        
        # Store colors for easy access
        self.colors = UI_COLORS
        
        # Calibration state variables
        self.current_chamber = tk.IntVar(value=0)  # 0-2 for chamber selection
        self.chamber_offsets = [tk.DoubleVar(value=0.0) for _ in range(3)]  # Offset for each chamber
        
        # Setup TTK styles
        self._setup_styles()
        
        # Main container frame
        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Create UI components
        self.create_header_section()
        self.create_offset_adjustment_section()
        self.create_calibration_history_section()
        self.create_action_buttons()
        
        # Load current offsets
        self._load_current_offsets()
    
    def _setup_logger(self):
        """Configure logging for the calibration tab."""
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
        
        # Section styles
        style.configure(
            'Section.TFrame',
            background=UI_COLORS['BACKGROUND'],
            padding=15
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
            'Value.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY'],
            font=UI_FONTS['VALUE']
        )
        style.configure(
            'Success.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['SUCCESS'],
            font=UI_FONTS['LABEL']
        )
        style.configure(
            'Error.TLabel',
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['ERROR'],
            font=UI_FONTS['LABEL']
        )
        
        # Button styles
        style.configure(
            'Action.TButton',
            font=UI_FONTS['BUTTON'],
            padding=10
        )
        style.configure(
            'Secondary.TButton',
            font=UI_FONTS['BUTTON'],
            padding=10
        )
    
    def create_header_section(self):
        """Create the header section with title and chamber selection."""
        header_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title and description
        title_frame = ttk.Frame(header_frame, padding=15)
        title_frame.pack(fill=tk.X)
        
        ttk.Label(
            title_frame,
            text="Pressure Sensor Calibration (Offset Adjustment)",
            style='CardTitle.TLabel'
        ).pack(anchor=tk.W)
        
        ttk.Label(
            title_frame,
            text="Adjust pressure sensor offsets for accurate readings.",
            style='CardText.TLabel'
        ).pack(anchor=tk.W, pady=(5, 0))
        
        # Chamber selection frame
        chamber_frame = ttk.Frame(header_frame, padding=(15, 0, 15, 15))
        chamber_frame.pack(fill=tk.X)
        
        ttk.Label(
            chamber_frame,
            text="Select Chamber:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        # Chamber radio buttons
        for i in range(3):
            ttk.Radiobutton(
                chamber_frame,
                text=f"Chamber {i+1}",
                variable=self.current_chamber,
                value=i,
                command=self.on_chamber_changed
            ).pack(side=tk.LEFT, padx=(10, 0))
    
    def create_offset_adjustment_section(self):
        """Create the offset adjustment section."""
        offset_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        offset_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        ttk.Label(
            offset_frame,
            text="Offset Adjustment",
            style='CardTitle.TLabel'
        ).pack(anchor=tk.W, padx=15, pady=(10, 0))
        
        # Main content
        content_frame = ttk.Frame(offset_frame, padding=15)
        content_frame.pack(fill=tk.X)
        
        # Current offset display
        offset_display_frame = ttk.Frame(content_frame)
        offset_display_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(
            offset_display_frame,
            text="Current Offset:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        self.offset_display = ttk.Label(
            offset_display_frame,
            textvariable=self.chamber_offsets[0],
            style='Value.TLabel'
        )
        self.offset_display.pack(side=tk.LEFT, padx=(10, 5))
        
        ttk.Label(
            offset_display_frame,
            text="mbar",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        # Offset adjustment controls
        adjustment_frame = ttk.Frame(content_frame)
        adjustment_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(
            adjustment_frame,
            text="Adjust Offset:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        # Quick adjustment buttons
        ttk.Button(
            adjustment_frame,
            text="-10",
            style='Secondary.TButton',
            command=lambda: self.adjust_offset(-10),
            width=6
        ).pack(side=tk.LEFT, padx=(10, 2))
        
        ttk.Button(
            adjustment_frame,
            text="-5",
            style='Secondary.TButton',
            command=lambda: self.adjust_offset(-5),
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            adjustment_frame,
            text="-1",
            style='Secondary.TButton',
            command=lambda: self.adjust_offset(-1),
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            adjustment_frame,
            text="+1",
            style='Secondary.TButton',
            command=lambda: self.adjust_offset(1),
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            adjustment_frame,
            text="+5",
            style='Secondary.TButton',
            command=lambda: self.adjust_offset(5),
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            adjustment_frame,
            text="+10",
            style='Secondary.TButton',
            command=lambda: self.adjust_offset(10),
            width=6
        ).pack(side=tk.LEFT, padx=(2, 10))
        
        # Manual entry button
        ttk.Button(
            adjustment_frame,
            text="Set Manual",
            style='Action.TButton',
            command=self.set_manual_offset,
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        # Reset button
        ttk.Button(
            adjustment_frame,
            text="Reset to 0",
            style='Secondary.TButton',
            command=self.reset_offset,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        # Status message
        self.status_label = ttk.Label(
            content_frame,
            text="Select a chamber and adjust the offset as needed.",
            style='CardText.TLabel',
            wraplength=600
        )
        self.status_label.pack(anchor=tk.W)
    
    def create_calibration_history_section(self):
        """Create the calibration history section."""
        history_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        history_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        ttk.Label(
            history_frame,
            text="Calibration History",
            style='CardTitle.TLabel'
        ).pack(anchor=tk.W, padx=15, pady=(10, 0))
        
        # History content
        self.history_content = ttk.Frame(history_frame, padding=15)
        self.history_content.pack(fill=tk.X)
        
        # History will be populated when a chamber is selected
        ttk.Label(
            self.history_content,
            text="Select a chamber to view calibration history.",
            style='CardText.TLabel'
        ).pack(anchor=tk.W)
    
    def create_action_buttons(self):
        """Create the action buttons at the bottom of the tab."""
        buttons_frame = ttk.Frame(self.main_frame)
        buttons_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Apply Offset button
        self.apply_button = ttk.Button(
            buttons_frame,
            text="Apply Offset",
            style='Action.TButton',
            command=self.apply_offset,
            width=15
        )
        self.apply_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Save All Offsets button
        self.save_all_button = ttk.Button(
            buttons_frame,
            text="Save All Offsets",
            style='Action.TButton',
            command=self.save_all_offsets,
            width=15
        )
        self.save_all_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Load Offsets button
        self.load_button = ttk.Button(
            buttons_frame,
            text="Load Offsets",
            style='Secondary.TButton',
            command=self.load_offsets,
            width=12
        )
        self.load_button.pack(side=tk.LEFT)
    
    def _load_current_offsets(self):
        """Load current offsets from the pressure sensor."""
        for i in range(3):
            offset = self.pressure_sensor.get_chamber_offset(i)
            self.chamber_offsets[i].set(offset)
        
        # Update display for current chamber
        self.update_offset_display()
    
    def on_chamber_changed(self):
        """Handle chamber selection change."""
        chamber_index = self.current_chamber.get()
        self.logger.info(f"Selected chamber: {chamber_index + 1}")
        
        # Update offset display
        self.update_offset_display()
        
        # Update history display
        self.update_calibration_history(chamber_index)
    
    def update_offset_display(self):
        """Update the offset display for the current chamber."""
        chamber_index = self.current_chamber.get()
        self.offset_display.config(textvariable=self.chamber_offsets[chamber_index])
    
    def adjust_offset(self, amount: float):
        """
        Adjust the offset value by the specified amount.
        
        Args:
            amount: Amount to adjust by (mbar)
        """
        # Check for maintenance access
        if not has_access("MAINTENANCE"):
            self.show_auth_dialog("MAINTENANCE", on_success=lambda: self.adjust_offset(amount))
            return
        
        chamber_index = self.current_chamber.get()
        current_offset = self.chamber_offsets[chamber_index].get()
        new_offset = current_offset + amount
        
        # Update the offset variable
        self.chamber_offsets[chamber_index].set(new_offset)
        
        # Update status
        self.status_label.config(
            text=f"Offset for Chamber {chamber_index + 1} adjusted by {amount:+.1f} mbar. "
                 f"New offset: {new_offset:.1f} mbar. Click 'Apply Offset' to save.",
            style='CardText.TLabel'
        )
    
    def set_manual_offset(self):
        """Open a keypad to manually set the offset value."""
        # Check for maintenance access
        if not has_access("MAINTENANCE"):
            self.show_auth_dialog("MAINTENANCE", on_success=self.set_manual_offset)
            return
        
        chamber_index = self.current_chamber.get()
        
        def on_offset_set(value):
            self.chamber_offsets[chamber_index].set(value)
            self.status_label.config(
                text=f"Manual offset set for Chamber {chamber_index + 1}: {value:.1f} mbar. "
                     f"Click 'Apply Offset' to save.",
                style='CardText.TLabel'
            )
        
        # Show numeric keypad
        NumericKeypad(
            self.parent,
            self.chamber_offsets[chamber_index],
            title=f"Set Offset for Chamber {chamber_index + 1}",
            max_value=100.0,
            min_value=-100.0,
            decimal_places=1,
            callback=on_offset_set
        )
    
    def reset_offset(self):
        """Reset the offset to zero."""
        # Check for maintenance access
        if not has_access("MAINTENANCE"):
            self.show_auth_dialog("MAINTENANCE", on_success=self.reset_offset)
            return
        
        chamber_index = self.current_chamber.get()
        self.chamber_offsets[chamber_index].set(0.0)
        
        # Update status
        self.status_label.config(
            text=f"Offset for Chamber {chamber_index + 1} reset to 0.0 mbar. "
                 f"Click 'Apply Offset' to save.",
            style='CardText.TLabel'
        )
    
    def apply_offset(self):
        """Apply the current offset value to the selected chamber."""
        # Check for maintenance access
        if not has_access("MAINTENANCE"):
            self.show_auth_dialog("MAINTENANCE", on_success=self.apply_offset)
            return
        
        chamber_index = self.current_chamber.get()
        offset = self.chamber_offsets[chamber_index].get()
        
        try:
            # Apply offset through pressure sensor
            self.pressure_sensor.set_chamber_offset(chamber_index, offset)
            
            # Save offset using calibration manager
            success = self.calibration_manager.save_chamber_offset(chamber_index, offset)
            
            if success:
                self.status_label.config(
                    text=f"Offset of {offset:.1f} mbar applied and saved for Chamber {chamber_index + 1}.",
                    style='Success.TLabel'
                )
                
                # Update calibration history
                self.update_calibration_history(chamber_index)
                
                messagebox.showinfo(
                    "Offset Applied",
                    f"Offset of {offset:.1f} mbar applied to Chamber {chamber_index + 1}"
                )
            else:
                self.status_label.config(
                    text=f"Failed to save offset for Chamber {chamber_index + 1}.",
                    style='Error.TLabel'
                )
                messagebox.showerror("Error", "Failed to save offset")
                
        except Exception as e:
            self.logger.error(f"Error applying offset: {e}")
            self.status_label.config(
                text=f"Error applying offset: {str(e)}",
                style='Error.TLabel'
            )
            messagebox.showerror("Error", f"Failed to apply offset: {str(e)}")
    
    def save_all_offsets(self):
        """Save all chamber offsets at once."""
        # Check for maintenance access
        if not has_access("MAINTENANCE"):
            self.show_auth_dialog("MAINTENANCE", on_success=self.save_all_offsets)
            return
        
        try:
            success_count = 0
            
            for i in range(3):
                offset = self.chamber_offsets[i].get()
                
                # Apply to pressure sensor
                self.pressure_sensor.set_chamber_offset(i, offset)
                
                # Save using calibration manager
                if self.calibration_manager.save_chamber_offset(i, offset):
                    success_count += 1
                else:
                    self.logger.error(f"Failed to save offset for chamber {i + 1}")
            
            if success_count == 3:
                self.status_label.config(
                    text="All chamber offsets applied and saved successfully.",
                    style='Success.TLabel'
                )
                messagebox.showinfo(
                    "Offsets Saved",
                    "All chamber offsets have been applied and saved successfully."
                )
                
                # Update history for current chamber
                chamber_index = self.current_chamber.get()
                self.update_calibration_history(chamber_index)
                
            else:
                self.status_label.config(
                    text=f"Only {success_count}/3 chamber offsets saved successfully.",
                    style='Error.TLabel'
                )
                messagebox.showwarning(
                    "Partial Success",
                    f"Only {success_count} out of 3 chamber offsets were saved successfully."
                )
                
        except Exception as e:
            self.logger.error(f"Error saving all offsets: {e}")
            self.status_label.config(
                text=f"Error saving offsets: {str(e)}",
                style='Error.TLabel'
            )
            messagebox.showerror("Error", f"Failed to save offsets: {str(e)}")
    
    def load_offsets(self):
        """Load offsets from the calibration database."""
        try:
            # Load offsets from calibration manager
            offsets = self.calibration_manager.load_all_chamber_offsets()
            
            if offsets:
                for i, offset in enumerate(offsets):
                    if i < 3:  # Ensure we don't exceed chamber count
                        self.chamber_offsets[i].set(offset)
                        self.pressure_sensor.set_chamber_offset(i, offset)
                
                self.status_label.config(
                    text="Chamber offsets loaded successfully.",
                    style='Success.TLabel'
                )
                
                # Update display
                self.update_offset_display()
                
                # Update history for current chamber
                chamber_index = self.current_chamber.get()
                self.update_calibration_history(chamber_index)
                
                messagebox.showinfo(
                    "Offsets Loaded",
                    "Chamber offsets have been loaded successfully."
                )
            else:
                self.status_label.config(
                    text="No saved offsets found.",
                    style='Error.TLabel'
                )
                messagebox.showinfo(
                    "No Data",
                    "No saved calibration offsets were found."
                )
                
        except Exception as e:
            self.logger.error(f"Error loading offsets: {e}")
            self.status_label.config(
                text=f"Error loading offsets: {str(e)}",
                style='Error.TLabel'
            )
            messagebox.showerror("Error", f"Failed to load offsets: {str(e)}")
    
    def update_calibration_history(self, chamber_index: int):
        """
        Update the calibration history display for a chamber.
        
        Args:
            chamber_index: Index of the chamber (0-2)
        """
        # Clear existing history content
        for widget in self.history_content.winfo_children():
            widget.destroy()
        
        # Get calibration history from the manager
        history = self.calibration_manager.get_calibration_history(chamber_index)
        
        if not history:
            # No history available
            ttk.Label(
                self.history_content,
                text=f"No calibration history available for Chamber {chamber_index + 1}.",
                style='CardText.TLabel'
            ).pack(anchor=tk.W)
            return
        
        # Display most recent calibration first
        latest = history[0]
        
        # Latest calibration section
        latest_frame = ttk.Frame(self.history_content)
        latest_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            latest_frame,
            text="Current Calibration:",
            style='CardText.TLabel',
            font=UI_FONTS['SUBHEADER']
        ).pack(anchor=tk.W)
        
        # Format date for display
        date_str = latest.calibration_date.strftime("%Y-%m-%d %H:%M:%S")
        
        ttk.Label(
            latest_frame,
            text=f"Date: {date_str}",
            style='CardText.TLabel'
        ).pack(anchor=tk.W, padx=(20, 0))
        
        # Show offset instead of multiplier/offset
        ttk.Label(
            latest_frame,
            text=f"Offset: {latest.offset:.1f} mbar",
            style='CardText.TLabel'
        ).pack(anchor=tk.W, padx=(20, 0))
        
        # Additional calibration history if available
        if len(history) > 1:
            history_label = ttk.Label(
                self.history_content,
                text="Previous Calibrations:",
                style='CardText.TLabel',
                font=UI_FONTS['SUBHEADER']
            )
            history_label.pack(anchor=tk.W, pady=(10, 5))
            
            # Create a simple table for history
            for i, cal in enumerate(history[1:5]):  # Show up to 5 previous entries
                date_str = cal.calibration_date.strftime("%Y-%m-%d %H:%M:%S")
                ttk.Label(
                    self.history_content,
                    text=f"{date_str} - Offset: {cal.offset:.1f} mbar",
                    style='CardText.TLabel'
                ).pack(anchor=tk.W, padx=(20, 0))
    
    def show_auth_dialog(self, min_role: str, on_success: Optional[Callable] = None):
        """
        Show authentication dialog for access to protected features.
        
        Args:
            min_role: Minimum role required
            on_success: Function to call on successful authentication
        """
        def auth_success():
            # Call success callback if provided
            if on_success:
                on_success()
        
        # Show password dialog
        PasswordDialog(
            self.parent,
            min_role,
            on_success=auth_success
        )
    
    def on_tab_selected(self):
        """Called when this tab is selected."""
        # Load current offsets
        self._load_current_offsets()
        
        # Update the calibration history for the current chamber
        chamber_index = self.current_chamber.get()
        self.update_calibration_history(chamber_index)
    
    def on_tab_deselected(self):
        """Called when user switches away from this tab."""
        # No special handling needed for offset-only calibration
        return True
    
    def cleanup(self):
        """Clean up resources when closing the application."""
        # No cleanup needed for offset-only calibration
        pass