#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced General Settings Section for the Multi-Chamber Test application.

This module provides an improved GeneralSection class for configuring global
test settings such as test duration, mode selection, and login requirements.
Implements the observer pattern for settings synchronization.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import time
import datetime
import subprocess
import os
import platform
from typing import Callable, Optional, Dict, Any

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, TIME_DEFAULTS
from multi_chamber_test.config.settings import SettingsManager
from multi_chamber_test.core.test_manager import TestManager
from multi_chamber_test.ui.keypad import show_numeric_keypad
from multi_chamber_test.ui.settings.base_section import BaseSection


class GeneralSection(BaseSection):
    """
    General settings section for global application settings.
    
    This section allows configuration of:
    - Test mode (Reference/Manual)
    - Test duration
    - System date and time
    - Login requirements
    
    Implements efficient UI updating and settings synchronization.
    """
    
    def __init__(self, parent, settings_manager: SettingsManager, test_manager: TestManager):
        """
        Initialize the GeneralSection.

        Args:
            parent: Parent widget
            settings_manager: Manages persistent settings
            test_manager: Manages test state and operations
        """
        # Store manager references
        self.settings_manager = settings_manager
        self.test_manager = test_manager
        self.settings_manager.register_observer(self.on_setting_changed)

        # State variables
        self.duration_var = tk.IntVar(value=settings_manager.get_test_duration())
        self.current_time_var = tk.StringVar()
        self.require_login_var = tk.BooleanVar(value=settings_manager.get_setting('require_login', False))
        self.session_timeout_var = tk.IntVar(value=settings_manager.get_setting('session_timeout', 600))
        self.test_mode_var = tk.StringVar(value=settings_manager.get_setting('test_mode', "reference"))
        self.unsaved_changes = {}

        # Initialize hours and minutes variables
        total_seconds = self.session_timeout_var.get()
        self.timeout_hours = tk.IntVar(value=total_seconds // 3600)
        self.timeout_minutes = tk.IntVar(value=(total_seconds % 3600) // 60)

        # Call base class initialization
        super().__init__(parent)
    
    def on_setting_changed(self, key: str, value: Any):
        """
        Handle settings changes from other components.
        
        Args:
            key: Setting key that changed
            value: New value
        """
        if key == 'test_duration':
            self.duration_var.set(value)
        elif key == 'test_mode':
            self.test_mode_var.set(value)
        elif key == 'require_login':
            self.require_login_var.set(value)
            # Show/hide timeout settings based on new value
            if hasattr(self, 'timeout_frame'):
                if value:
                    self.timeout_frame.pack(fill=tk.X, pady=10)
                else:
                    self.timeout_frame.pack_forget()
        elif key == 'session_timeout':
            self.session_timeout_var.set(value)
            self._update_hours_minutes_from_seconds()
        elif key == 'settings_reset':
            self.refresh_all()
    
    def create_widgets(self):
        """Create UI widgets for the general settings section."""
        
        # Section title with icon
        title_frame = ttk.Frame(self.content_frame, style='Content.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(
            title_frame,
            text="General Settings",
            style='ContentTitle.TLabel'
        ).pack(anchor=tk.W)
        
        # Create each settings card
        self.create_test_mode_card()
        self.create_test_duration_card()
        self.create_datetime_card()
        self.create_login_requirements_card()
        
        # Save/Reset buttons at bottom
        self.create_action_buttons()
        
        # Start time display updater
        self._update_time_display()
    
    def create_test_mode_card(self):
        """Create the test mode selection card."""
        # Create a styled card
        card, content = self.create_card(
            "Test Mode",
            "Configure how test parameters are determined."
        )
        
        # Test mode selection
        mode_frame = ttk.Frame(content, style='Card.TFrame')
        mode_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            mode_frame,
            text="Test Mode:",
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        # Test mode radio buttons
        test_modes_frame = ttk.Frame(mode_frame, style='Card.TFrame')
        test_modes_frame.pack(side=tk.LEFT, padx=15)
        
        ttk.Radiobutton(
            test_modes_frame,
            text="Manual Test",
            variable=self.test_mode_var,
            value="manual",
            command=self._on_test_mode_changed
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Radiobutton(
            test_modes_frame,
            text="Reference Test",
            variable=self.test_mode_var,
            value="reference",
            command=self._on_test_mode_changed
        ).pack(side=tk.LEFT)
        
        # Description for each mode
        description_frame = ttk.Frame(content, style='Card.TFrame')
        description_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.mode_description = ttk.Label(
            description_frame,
            text="In Reference mode, a barcode must be scanned to load test parameters.",
            font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray'),
            wraplength=600
        )
        self.mode_description.pack(anchor=tk.W, padx=15)
        
        # Update description based on initial mode
        self._update_mode_description()
    
    def _on_test_mode_changed(self):
        """
        Handle test mode change with UI updates.
        Tracks changes and updates the mode description.
        """
        # Update the description
        self._update_mode_description()
        
        # Track as an unsaved change if different from saved value
        saved_value = self.settings_manager.get_setting('test_mode', "reference")
        current_value = self.test_mode_var.get()
        
        if saved_value != current_value:
            self.unsaved_changes['test_mode'] = current_value
        elif 'test_mode' in self.unsaved_changes:
            del self.unsaved_changes['test_mode']
            
        # Update save button state
        self._update_save_button()
    
    def _update_mode_description(self):
        """Update the mode description based on the selected mode."""
        mode = self.test_mode_var.get()
        
        if mode == "reference":
            self.mode_description.config(
                text="In Reference mode, a barcode must be scanned to load test parameters."
            )
        else:  # manual mode
            self.mode_description.config(
                text="In Manual mode, test parameters are set directly in chamber settings."
            )
    
    def create_test_duration_card(self):
        """Create the test duration settings card."""
        # Create a styled card
        card, content = self.create_card(
            "Test Duration",
            "Set the duration for running a test."
        )
        
        # Test duration setting
        self.create_editor_row(
            content,
            "Test Duration:",
            self.duration_var,
            self._edit_test_duration,
            "seconds"
        )
        
        # Track variable changes to detect unsaved changes
        self.duration_var.trace_add("write", self._on_duration_changed)
    
    def _on_duration_changed(self, *args):
        """
        Handle changes to the duration value.
        Tracks unsaved changes.
        """
        # Track as an unsaved change if different from saved value
        saved_value = self.settings_manager.get_test_duration()
        current_value = self.duration_var.get()
        
        if saved_value != current_value:
            self.unsaved_changes['test_duration'] = current_value
        elif 'test_duration' in self.unsaved_changes:
            del self.unsaved_changes['test_duration']
            
        # Update save button state
        self._update_save_button()
    
    def _edit_test_duration(self):
        """Show keypad for editing test duration."""
        def on_duration_set(value):
            # Update variable - trace will handle UI updates
            try:
                self.duration_var.set(int(value))
            except (ValueError, TypeError):
                pass
        
        # Show numeric keypad with appropriate limits
        show_numeric_keypad(
            self.parent,
            self.duration_var,
            "Test Duration",
            min_value=1,
            max_value=600,  # 10 minutes max
            decimal_places=0,
            callback=on_duration_set
        )
    
    def create_datetime_card(self):
        """Create the date & time settings card."""
        # Create a styled card
        card, content = self.create_card(
            "System Date & Time",
            "View and set the system date and time."
        )
        
        # Current date & time display
        time_frame = ttk.Frame(content, style='Card.TFrame')
        time_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            time_frame,
            text="Current System Time:",
            font=UI_FONTS['LABEL'],
            background='#FFFFFF'
        ).pack(side=tk.LEFT)
        
        # Current time display
        self.time_display = ttk.Label(
            time_frame,
            textvariable=self.current_time_var,
            font=UI_FONTS['VALUE'],
            foreground=UI_COLORS['PRIMARY'],
            background='#FFFFFF'
        )
        self.time_display.pack(side=tk.LEFT, padx=15)
        
        # Set date & time button
        set_time_button = ttk.Button(
            time_frame,
            text="Set Date & Time",
            command=self._show_datetime_dialog,
            style='Settings.TButton'
        )
        set_time_button.pack(side=tk.RIGHT)
    
    def _update_time_display(self):
        """
        Update the time display with efficient refresh to minimize UI updates.
        """
        try:
            # Get current time
            now = datetime.datetime.now()
            formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
            
            # Only update if it's changed (seconds changed)
            if self.current_time_var.get() != formatted_time:
                self.current_time_var.set(formatted_time)
            
            # Schedule next update at next whole second
            next_second = 1000 - (now.microsecond // 1000)
            timer_id = self.parent.after(next_second, self._update_time_display)
            self._register_timer(timer_id)
            
        except Exception as e:
            # Log error and try again later
            self.logger.error(f"Error updating time display: {e}")
            timer_id = self.parent.after(1000, self._update_time_display)
            self._register_timer(timer_id)
    
    def _show_datetime_dialog(self):
        """Show a dialog to set the system date and time."""
        # Create a top-level dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title("Set System Date & Time")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Make dialog modal
        dialog.focus_set()
        
        # Center the dialog
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - 400) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - 300) // 2
        dialog.geometry(f"400x300+{x}+{y}")
        
        # Get current date and time
        now = datetime.datetime.now()
        
        # Create variables for the date and time parts
        year_var = tk.IntVar(value=now.year)
        month_var = tk.IntVar(value=now.month)
        day_var = tk.IntVar(value=now.day)
        hour_var = tk.IntVar(value=now.hour)
        minute_var = tk.IntVar(value=now.minute)
        second_var = tk.IntVar(value=now.second)
        
        # Create the form inside the dialog
        content_frame = ttk.Frame(dialog, style='Card.TFrame', padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(
            content_frame,
            text="Set System Date & Time",
            font=UI_FONTS['SUBHEADER'],
            background='#FFFFFF'
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Date controls
        date_frame = ttk.Frame(content_frame, style='Card.TFrame')
        date_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            date_frame,
            text="Date:",
            font=UI_FONTS['LABEL'],
            background='#FFFFFF'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Year spinner
        ttk.Spinbox(
            date_frame,
            from_=2000,
            to=2100,
            textvariable=year_var,
            width=6
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(
            date_frame,
            text="-",
            background='#FFFFFF'
        ).pack(side=tk.LEFT)
        
        # Month spinner
        ttk.Spinbox(
            date_frame,
            from_=1,
            to=12,
            textvariable=month_var,
            width=4
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(
            date_frame,
            text="-",
            background='#FFFFFF'
        ).pack(side=tk.LEFT)
        
        # Day spinner
        ttk.Spinbox(
            date_frame,
            from_=1,
            to=31,
            textvariable=day_var,
            width=4
        ).pack(side=tk.LEFT, padx=2)
        
        # Time controls
        time_frame = ttk.Frame(content_frame, style='Card.TFrame')
        time_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            time_frame,
            text="Time:",
            font=UI_FONTS['LABEL'],
            background='#FFFFFF'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Hour spinner
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=23,
            textvariable=hour_var,
            width=4
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(
            time_frame,
            text=":",
            background='#FFFFFF'
        ).pack(side=tk.LEFT)
        
        # Minute spinner
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=59,
            textvariable=minute_var,
            width=4
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(
            time_frame,
            text=":",
            background='#FFFFFF'
        ).pack(side=tk.LEFT)
        
        # Second spinner
        ttk.Spinbox(
            time_frame,
            from_=0,
            to=59,
            textvariable=second_var,
            width=4
        ).pack(side=tk.LEFT, padx=2)
        
        # Warning message
        warning_label = ttk.Label(
            content_frame,
            text="Note: Setting system time requires administrator privileges and may require a password.",
            wraplength=350,
            foreground="#721C24",
            background="#F8D7DA",
            padding=10
        )
        warning_label.pack(fill=tk.X, pady=20)
        
        # Button frame
        button_frame = ttk.Frame(content_frame, style='Card.TFrame')
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        # Cancel button
        ttk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            width=10
        ).pack(side=tk.LEFT)
        
        # Set time button
        ttk.Button(
            button_frame,
            text="Set Time",
            command=lambda: self._set_system_time(
                year_var.get(),
                month_var.get(),
                day_var.get(),
                hour_var.get(),
                minute_var.get(),
                second_var.get(),
                dialog
            ),
            style='Settings.TButton',
            width=10
        ).pack(side=tk.RIGHT)
    
    def _set_system_time(self, year, month, day, hour, minute, second, dialog):
        """
        Attempt to set the system time with appropriate error handling.
        
        Args:
            year, month, day, hour, minute, second: Date and time components
            dialog: Dialog to close when done
        """
        # Format date and time for system command
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        time_str = f"{hour:02d}:{minute:02d}:{second:02d}"
        
        try:
            # Different commands based on platform
            system = platform.system().lower()
            
            if system == 'linux' or system == 'darwin':  # Linux or macOS
                cmd = f"sudo date -s '{date_str} {time_str}'"
                exit_code = os.system(cmd)  # Will prompt for password
                success = exit_code == 0
            elif system == 'windows':
                # Windows needs separate date and time commands
                date_cmd = f"date {month:02d}-{day:02d}-{year:04d}"
                time_cmd = f"time {hour:02d}:{minute:02d}:{second:02d}"
                exit_code1 = os.system(date_cmd)
                exit_code2 = os.system(time_cmd)
                success = exit_code1 == 0 and exit_code2 == 0
            else:
                success = False
                messagebox.showerror("Error", f"Unsupported platform: {system}")
                return
                
            # Close dialog and show result
            dialog.destroy()
            
            if success:
                messagebox.showinfo("Success", "System date and time updated successfully.")
            else:
                messagebox.showerror("Error", "Failed to update system date and time. Check permissions.")
        
        except Exception as e:
            self.logger.error(f"Error setting system time: {e}")
            dialog.destroy()
            messagebox.showerror("Error", f"Failed to set system time: {e}")
    
    def create_login_requirements_card(self):
        """Create the login requirements settings card with hours and minutes display."""
        # Enlarge the checkbox via its style
        style = ttk.Style()
        style.configure(
            'Card.TCheckbutton',
            indicatorpadding=20,   # much larger check-square region
            padding=(20, 10)       # extra space around text & indicator
        )
    
        # Create a styled card
        card, content = self.create_card(
            "Login Policy",
            "Configure login requirements and session timeout."
        )
    
        # Require login checkbox
        login_frame = ttk.Frame(content, style='Card.TFrame')
        login_frame.pack(fill=tk.X, pady=10)
    
        require_login_cb = ttk.Checkbutton(
            login_frame,
            text="Require Login on Application Start",
            variable=self.require_login_var,
            command=self._on_require_login_changed,
            style='Card.TCheckbutton'
        )
        require_login_cb.pack(anchor=tk.W)
    
        # Session timeout in hours and minutes
        self.timeout_frame = ttk.Frame(content, style='Card.TFrame')
        self.timeout_frame.pack(fill=tk.X, pady=10)
    
        ttk.Label(
            self.timeout_frame,
            text="Session Timeout:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(side=tk.LEFT)
    
        # Hours and minutes display
        time_display_frame = ttk.Frame(self.timeout_frame)
        time_display_frame.pack(side=tk.LEFT, padx=(10, 0))
    
        # Hours display
        hours_frame = ttk.Frame(time_display_frame)
        hours_frame.pack(side=tk.LEFT)
    
        hours_value = ttk.Label(
            hours_frame,
            textvariable=self.timeout_hours,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12, 'bold')),
            foreground=UI_COLORS.get('PRIMARY', 'blue')
        )
        hours_value.pack(side=tk.LEFT)
    
        ttk.Label(
            hours_frame,
            text=" hours",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(side=tk.LEFT)
    
        # Minutes display
        minutes_frame = ttk.Frame(time_display_frame)
        minutes_frame.pack(side=tk.LEFT, padx=(10, 0))
    
        minutes_value = ttk.Label(
            minutes_frame,
            textvariable=self.timeout_minutes,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12, 'bold')),
            foreground=UI_COLORS.get('PRIMARY', 'blue')
        )
        minutes_value.pack(side=tk.LEFT)
    
        ttk.Label(
            minutes_frame,
            text=" minutes",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(side=tk.LEFT)
    
        # Edit hours and minutes buttons
        edit_frame = ttk.Frame(self.timeout_frame)
        edit_frame.pack(side=tk.LEFT, padx=(20, 0))
    
        ttk.Button(
            edit_frame,
            text="Edit Hours",
            command=self._edit_timeout_hours,
            padding=5
        ).pack(side=tk.LEFT)
    
        ttk.Button(
            edit_frame,
            text="Edit Minutes",
            command=self._edit_timeout_minutes,
            padding=5
        ).pack(side=tk.LEFT, padx=(5, 0))
    
        # Only show the timeout controls if login is required
        if not self.require_login_var.get():
            self.timeout_frame.pack_forget()
    
    def _on_require_login_changed(self):
        """
        Handle change to the require login checkbox.
        Shows/hides the session timeout and tracks the change.
        """
        # Show/hide timeout setting based on checkbox state
        if self.require_login_var.get():
            self.timeout_frame.pack(fill=tk.X, pady=10)
        else:
            self.timeout_frame.pack_forget()
        
        # Track as an unsaved change
        saved_value = self.settings_manager.get_setting('require_login', False)
        current_value = self.require_login_var.get()
        
        if saved_value != current_value:
            self.unsaved_changes['require_login'] = current_value
        elif 'require_login' in self.unsaved_changes:
            del self.unsaved_changes['require_login']
            
        # Update save button state
        self._update_save_button()
    
    def _update_hours_minutes_from_seconds(self):
        """Update the hours and minutes variables from session_timeout seconds."""
        total_seconds = self.session_timeout_var.get()
        self.timeout_hours.set(total_seconds // 3600)
        self.timeout_minutes.set((total_seconds % 3600) // 60)
    
    def _update_seconds_from_hours_minutes(self):
        """Update session_timeout seconds from hours and minutes variables."""
        hours = self.timeout_hours.get()
        minutes = self.timeout_minutes.get()
        
        total_seconds = (hours * 3600) + (minutes * 60)
        self.session_timeout_var.set(total_seconds)
        
        # Track as an unsaved change
        saved_value = self.settings_manager.get_setting('session_timeout', 600)
        if saved_value != total_seconds:
            self.unsaved_changes['session_timeout'] = total_seconds
        elif 'session_timeout' in self.unsaved_changes:
            del self.unsaved_changes['session_timeout']
            
        # Update save button state
        self._update_save_button()
    
    def _edit_timeout_hours(self):
        """Show keypad to edit timeout hours."""
        def on_hours_set(value):
            try:
                hours = int(value)
                if hours >= 0:
                    self.timeout_hours.set(hours)
                    self._update_seconds_from_hours_minutes()
            except (ValueError, TypeError):
                pass
        
        # Show numeric keypad for hours
        show_numeric_keypad(
            self.parent,
            self.timeout_hours,
            "Session Timeout Hours",
            min_value=0,
            max_value=24,  # Max 24 hours
            decimal_places=0,
            callback=on_hours_set
        )
    
    def _edit_timeout_minutes(self):
        """Show keypad to edit timeout minutes."""
        def on_minutes_set(value):
            try:
                minutes = int(value)
                if 0 <= minutes < 60:
                    self.timeout_minutes.set(minutes)
                    self._update_seconds_from_hours_minutes()
            except (ValueError, TypeError):
                pass
        
        # Show numeric keypad for minutes
        show_numeric_keypad(
            self.parent,
            self.timeout_minutes,
            "Session Timeout Minutes",
            min_value=0,
            max_value=59,  # 0-59 minutes
            decimal_places=0,
            callback=on_minutes_set
        )
    
    def create_action_buttons(self):
        """Create save and reset buttons at the bottom of the section."""
        # Button container
        button_frame = ttk.Frame(self.content_frame, style='Content.TFrame')
        button_frame.pack(fill=tk.X, pady=20)
        
        # Save button - initially disabled until changes are made
        self.save_button = ttk.Button(
            button_frame,
            text="Save Changes",
            command=self._save_changes,
            style='Settings.TButton',
            state='disabled',
            width=15
        )
        self.save_button.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Reset button - initially disabled until changes are made
        self.reset_button = ttk.Button(
            button_frame,
            text="Reset",
            command=self._reset_changes,
            state='disabled',
            width=10
        )
        self.reset_button.pack(side=tk.RIGHT)
    
    def _update_save_button(self):
        """Update the state of save/reset buttons based on whether there are unsaved changes."""
        if self.unsaved_changes:
            self.save_button.config(state='normal')
            self.reset_button.config(state='normal')
        else:
            self.save_button.config(state='disabled')
            self.reset_button.config(state='disabled')
    
    def _save_changes(self):
        """Save all changes to settings."""
        try:
            # Handle each type of setting
            for key, value in self.unsaved_changes.items():
                if key == 'test_duration':
                    self.settings_manager.set_test_duration(value)
                    # Also update test manager
                    self.test_manager.set_test_duration(value)
                elif key == 'test_mode':
                    # Save test mode setting
                    self.settings_manager.set_setting(key, value)
                    # Update the test manager with the new mode
                    # Note: this will just set the mode without a reference barcode
                    # The reference barcode will need to be set in the Main tab
                    self.test_manager.set_test_mode(value)
                else:
                    # For other generic settings
                    self.settings_manager.set_setting(key, value)
            
            # Save settings to disk
            self.settings_manager.save_settings()
            
            # Clear unsaved changes list
            self.unsaved_changes.clear()
            
            # Update button states
            self._update_save_button()
            
            # Show success message
            self.show_feedback("Settings saved successfully", duration=3000)
            
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
            self.show_feedback(f"Failed to save settings: {e}", is_error=True)
    
    def _reset_changes(self):
        """Reset all changes to last saved values."""
        if not self.unsaved_changes:
            return
            
        # Ask for confirmation
        if not self.show_confirmation("Confirm Reset", "Discard all unsaved changes?"):
            return
            
        # Reset each changed setting
        try:
            # Reset test mode
            if 'test_mode' in self.unsaved_changes:
                self.test_mode_var.set(self.settings_manager.get_setting('test_mode', "reference"))
                self._update_mode_description()
            
            # Reset test duration
            if 'test_duration' in self.unsaved_changes:
                self.duration_var.set(self.settings_manager.get_test_duration())
            
            # Reset login requirement
            if 'require_login' in self.unsaved_changes:
                self.require_login_var.set(self.settings_manager.get_setting('require_login', False))
                
                # Update UI to reflect login state
                if self.require_login_var.get():
                    self.timeout_frame.pack(fill=tk.X, pady=10)
                else:
                    self.timeout_frame.pack_forget()
            
            # Reset session timeout
            if 'session_timeout' in self.unsaved_changes:
                self.session_timeout_var.set(self.settings_manager.get_setting('session_timeout', 600))
                self._update_hours_minutes_from_seconds()
            
            # Clear unsaved changes
            self.unsaved_changes.clear()
            
            # Update button states
            self._update_save_button()
            
            # Show success message
            self.show_feedback("Changes reset successfully", duration=3000)
        
        except Exception as e:
            self.logger.error(f"Error resetting settings: {e}")
            self.show_feedback(f"Failed to reset settings: {e}", is_error=True)
    
    def refresh_all(self):
        """
        Refresh all UI components to reflect current settings.
        Called when the section is shown or needs full refresh.
        """
        # Update test mode
        self.test_mode_var.set(self.settings_manager.get_setting('test_mode', "reference"))
        self._update_mode_description()
        
        # Update test duration
        self.duration_var.set(self.settings_manager.get_test_duration())
        
        # Update login requirements
        self.require_login_var.set(self.settings_manager.get_setting('require_login', False))
        self.session_timeout_var.set(self.settings_manager.get_setting('session_timeout', 600))
        self._update_hours_minutes_from_seconds()
        
        # Show/hide timeout setting based on require login state
        if self.require_login_var.get():
            self.timeout_frame.pack(fill=tk.X, pady=10)
        else:
            self.timeout_frame.pack_forget()
        
        # Clear unsaved changes
        self.unsaved_changes.clear()
        
        # Update button states
        self._update_save_button()
    
    def on_selected(self):
        """Called when this section is selected or settings tab is selected."""
        # Call base class implementation first for common handling
        super().on_selected()
        
        # Ensure time display is active
        self._update_time_display()
    
    def on_deselected(self):
        """Called when this section is deselected or settings tab is deselected."""
        # Check for unsaved changes
        if self.unsaved_changes:
            response = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before leaving?",
                icon=messagebox.WARNING
            )
            
            if response is None:  # Cancel
                return False  # Prevent navigation
            elif response:  # Yes
                self._save_changes()
            # else: No - discard changes
        
        return super().on_deselected()
    
    def cleanup(self):
        """Perform any cleanup operations before app shutdown."""
        # Unregister observer
        try:
            self.settings_manager.unregister_observer(self.on_setting_changed)
        except Exception:
            pass
        
        # Cancel time display timer
        for timer_id in list(self._timer_ids):
            try:
                self.parent.after_cancel(timer_id)
            except:
                pass
        
        # Call base class cleanup
        super().cleanup()