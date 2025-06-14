#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Chamber Configuration Section for the Settings Tab in Multi-Chamber Test application.

This module provides the ChamberSection class that implements a section for 
configuring chamber-specific parameters, including pressure targets, thresholds, 
and tolerances with an optimized UI update mechanism.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
from typing import Dict, Any

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, PRESSURE_DEFAULTS
from multi_chamber_test.ui.settings.base_section import BaseSection
from multi_chamber_test.ui.keypad import show_numeric_keypad


class ChamberSection(BaseSection):
    """
    Chamber configuration section for the Settings Tab.
    
    This class implements a UI section for configuring chamber-specific parameters,
    including pressure targets, thresholds, tolerances, and enabled state.
    """
    
    def __init__(self, parent, settings_manager, test_manager):
        """
        Initialize the Chamber Configuration section.
        
        Args:
            parent: Parent widget
            settings_manager: SettingsManager instance for handling settings
            test_manager: TestManager instance for applying settings
        """
        # Store managers
        self.settings_manager = settings_manager
        self.test_manager = test_manager
        
        # Chamber variables - using chamber 1-based indexing to match settings manager
        self.chamber_vars = {}
        self.chamber_panels = {}  # Initialize chamber_panels here
        
        # Initialize variables for each chamber
        for chamber_idx in range(1, 4):
            self._init_chamber_variables(chamber_idx)
        
        # Track expanded/collapsed state of chambers
        self.expanded_chambers = set([1])  # Start with chamber 1 expanded
        
        # Call base class constructor after initializing our variables
        super().__init__(parent)
    
    def _init_chamber_variables(self, chamber_idx: int):
        """
        Initialize variables for a chamber.
        
        Args:
            chamber_idx: Chamber index (1-3)
        """
        chamber_settings = self.settings_manager.get_chamber_settings(chamber_idx)
        
        # Create variables for this chamber
        self.chamber_vars[chamber_idx] = {
            'enabled': tk.BooleanVar(value=chamber_settings.get('enabled', True)),
            'pressure_target': tk.IntVar(value=chamber_settings.get('pressure_target', PRESSURE_DEFAULTS.get('TARGET', 150))),
            'pressure_threshold': tk.IntVar(value=chamber_settings.get('pressure_threshold', PRESSURE_DEFAULTS.get('THRESHOLD', 5))),
            'pressure_tolerance': tk.IntVar(value=chamber_settings.get('pressure_tolerance', PRESSURE_DEFAULTS.get('TOLERANCE', 2)))
        }
    
    def create_widgets(self):
        """Create the UI widgets for the Chamber Configuration section."""
        # Section title with icon
        title_frame = ttk.Frame(self.content_frame, style='Content.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(
            title_frame,
            text="Chamber Configuration",
            style='ContentTitle.TLabel'
        ).pack(anchor=tk.W)
        
        # Create chamber panels (initially all collapsed except chamber 1)
        for chamber_idx in range(1, 4):
            self._create_chamber_panel(chamber_idx)
        
        # Add controls section at the bottom with Apply button
        self._create_action_buttons()
    
    def _create_chamber_panel(self, chamber_idx: int):
        """
        Create a panel for a specific chamber.
        
        Args:
            chamber_idx: Chamber index (1-3)
        """
        # Chamber frame with border
        chamber_frame = ttk.Frame(self.content_frame, style='Card.TFrame')
        chamber_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Store the frame reference
        self.chamber_panels[chamber_idx] = chamber_frame
        
        # Header with expansion control and enable toggle
        header_frame = ttk.Frame(chamber_frame, padding=(10, 5))
        header_frame.pack(fill=tk.X)
        
        # Create toggle icon (down/right arrow)
        toggle_icon = "v" if chamber_idx in self.expanded_chambers else ">"
        toggle_btn = ttk.Label(
            header_frame,
            text=toggle_icon,
            font=("Helvetica", 12, "bold"),
            cursor="hand2"
        )
        toggle_btn.pack(side=tk.LEFT, padx=(0, 10))
        toggle_btn.bind("<Button-1>", lambda e, idx=chamber_idx: self._toggle_chamber(idx))
        
        # Chamber title
        title_label = ttk.Label(
            header_frame,
            text=f"Chamber {chamber_idx}",
            font=UI_FONTS.get('SUBHEADER', ('Helvetica', 14, 'bold'))
        )
        title_label.pack(side=tk.LEFT)
        title_label.bind("<Button-1>", lambda e, idx=chamber_idx: self._toggle_chamber(idx))
        
        # Enable/disable checkbox
        enabled_var = self.chamber_vars[chamber_idx]['enabled']
        enabled_check = ttk.Checkbutton(
            header_frame,
            text="Enabled",
            variable=enabled_var
        )
        enabled_check.pack(side=tk.RIGHT, padx=(0, 10))
        
        # Content panel (only created when expanded)
        if chamber_idx in self.expanded_chambers:
            self._create_chamber_content(chamber_idx)
    
    def _create_chamber_content(self, chamber_idx: int):
        """
        Create the content panel for a chamber.
        
        Args:
            chamber_idx: Chamber index (1-3)
        """
        chamber_frame = self.chamber_panels[chamber_idx]
        
        # Check if content already exists
        content_frame = next((w for w in chamber_frame.winfo_children() 
                             if getattr(w, 'content_panel', False)), None)
        
        if content_frame:
            # Content already exists
            return
        
        # Create content panel
        content_frame = ttk.Frame(chamber_frame, padding=(20, 5, 20, 15))
        content_frame.content_panel = True  # Add custom attribute to identify later
        content_frame.pack(fill=tk.X)
        
        # Parameter grid
        param_names = {
            'pressure_target': 'Target Pressure',
            'pressure_threshold': 'Threshold Pressure',
            'pressure_tolerance': 'Pressure Tolerance'
        }
        
        # Create parameter rows
        for i, (param_key, param_label) in enumerate(param_names.items()):
            row_frame = ttk.Frame(content_frame)
            row_frame.pack(fill=tk.X, pady=5)
            
            # Label
            ttk.Label(
                row_frame,
                text=f"{param_label}:",
                font=UI_FONTS.get('LABEL', ('Helvetica', 12)),
                width=20
            ).pack(side=tk.LEFT)
            
            # Value display
            value_var = self.chamber_vars[chamber_idx][param_key]
            value_frame = ttk.Frame(row_frame)
            value_frame.pack(side=tk.LEFT, padx=(10, 0))
            
            value_label = ttk.Label(
                value_frame,
                textvariable=value_var,
                font=UI_FONTS.get('VALUE', ('Helvetica', 12, 'bold')),
                foreground=UI_COLORS.get('PRIMARY', 'blue')
            )
            value_label.pack(side=tk.LEFT)
            
            ttk.Label(
                value_frame,
                text="mbar",
                font=UI_FONTS.get('LABEL', ('Helvetica', 12))
            ).pack(side=tk.LEFT, padx=(5, 0))
            
            # Edit button
            edit_btn = ttk.Button(
                row_frame,
                text="Edit",
                command=lambda k=param_key, idx=chamber_idx: self._edit_chamber_param(idx, k)
            )
            edit_btn.pack(side=tk.RIGHT)
            
            # Help text
            help_text = ""
            if param_key == 'pressure_target':
                help_text = "The target pressure to reach during testing."
            elif param_key == 'pressure_threshold':
                help_text = "Minimum pressure that must be maintained during test."
            elif param_key == 'pressure_tolerance':
                help_text = "Allowed pressure variation around target."
            
            if help_text:
                ttk.Label(
                    row_frame,
                    text=help_text,
                    font=('Helvetica', 10, 'italic'),
                    foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray'),
                    wraplength=400
                ).pack(anchor=tk.W, padx=(20, 0), pady=(2, 0))
    
    def _toggle_chamber(self, chamber_idx: int):
        """
        Toggle the expanded/collapsed state of a chamber panel.
        
        Args:
            chamber_idx: Chamber index (1-3)
        """
        chamber_frame = self.chamber_panels[chamber_idx]
        
        # Find the toggle icon in the header
        header_frame = chamber_frame.winfo_children()[0]
        toggle_btn = header_frame.winfo_children()[0]
        
        if chamber_idx in self.expanded_chambers:
            # Collapse the chamber
            for widget in chamber_frame.winfo_children():
                if getattr(widget, 'content_panel', False):
                    widget.destroy()
            
            # Update toggle icon
            toggle_btn.configure(text=">")
            
            self.expanded_chambers.remove(chamber_idx)
        else:
            # Expand the chamber
            self._create_chamber_content(chamber_idx)
            
            # Update toggle icon
            toggle_btn.configure(text="v")
            
            self.expanded_chambers.add(chamber_idx)
    
    def _edit_chamber_param(self, chamber_idx: int, param_key: str):
        """
        Edit a chamber parameter using the numeric keypad.
        
        Args:
            chamber_idx: Chamber index (1-3)
            param_key: Parameter key (pressure_target, etc.)
        """
        param_var = self.chamber_vars[chamber_idx][param_key]
        
        # Determine the parameter limits based on type
        limits = {}
        if param_key == 'pressure_target':
            max_pressure = PRESSURE_DEFAULTS.get('MAX_PRESSURE', 600)
            limits = {
                'max_value': max_pressure,
                'min_value': 0,
                'is_pressure_target': True
            }
        else:
            limits = {'min_value': 0}
        
        # Parameter titles for keypad
        param_titles = {
            'pressure_target': f"Chamber {chamber_idx} Target Pressure",
            'pressure_threshold': f"Chamber {chamber_idx} Threshold",
            'pressure_tolerance': f"Chamber {chamber_idx} Tolerance"
        }
        
        # Show numeric keypad with the appropriate limits
        show_numeric_keypad(
            self.parent,
            param_var,
            title=param_titles.get(param_key, param_key),
            decimal_places=0,
            **limits
        )
    
    def _create_action_buttons(self):
        """Create action buttons for applying settings."""
        # Button frame
        button_frame = ttk.Frame(self.content_frame, style='Card.TFrame')
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Apply button
        ttk.Button(
            button_frame,
            text="Apply Chamber Settings",
            command=self.apply_settings,
            padding=10
        ).pack(side=tk.RIGHT, padx=10, pady=10)
        
        # Reset button
        ttk.Button(
            button_frame,
            text="Reset to Defaults",
            command=self.reset_to_defaults,
            padding=10
        ).pack(side=tk.LEFT, padx=10, pady=10)
    
    def apply_settings(self):
        """Apply current settings to the settings manager and test manager."""
        self.logger.info("Applying chamber settings...")
        
        # Apply settings for each chamber
        for chamber_idx in range(1, 4):
            chamber_vars = self.chamber_vars[chamber_idx]
            
            # Prepare settings dict
            settings_dict = {
                'enabled': chamber_vars['enabled'].get(),
                'pressure_target': chamber_vars['pressure_target'].get(),
                'pressure_threshold': chamber_vars['pressure_threshold'].get(),
                'pressure_tolerance': chamber_vars['pressure_tolerance'].get()
            }
            
            # Update settings manager
            self.settings_manager.set_chamber_settings(chamber_idx, settings_dict)
            
            # Update test manager
            # Note: TestManager uses 0-based indexes, settings manager uses 1-based
            self.test_manager.set_chamber_parameters(chamber_idx - 1, settings_dict)
        
        # Save settings to file
        self.settings_manager.save_settings()
        
        # Show feedback
        self.show_feedback("Settings applied and saved successfully.")
    
    def reset_to_defaults(self):
        """Reset all chamber settings to default values."""
        if not self.show_confirmation(
            "Reset Chamber Settings",
            "Are you sure you want to reset all chamber settings to the default values?"
        ):
            return
        
        # Apply defaults for each chamber
        for chamber_idx in range(1, 4):
            # Use the defaults from PRESSURE_DEFAULTS
            defaults = {
                'enabled': True,
                'pressure_target': PRESSURE_DEFAULTS.get('TARGET', 150),
                'pressure_threshold': PRESSURE_DEFAULTS.get('THRESHOLD', 5),
                'pressure_tolerance': PRESSURE_DEFAULTS.get('TOLERANCE', 2)
            }
            
            # Update UI variables
            chamber_vars = self.chamber_vars[chamber_idx]
            chamber_vars['enabled'].set(defaults['enabled'])
            chamber_vars['pressure_target'].set(defaults['pressure_target'])
            chamber_vars['pressure_threshold'].set(defaults['pressure_threshold'])
            chamber_vars['pressure_tolerance'].set(defaults['pressure_tolerance'])
        
        # Show feedback
        self.show_feedback("Chamber settings reset to defaults. Click Apply to save changes.")
    
    def on_selected(self):
        """Called when this section is selected."""
        super().on_selected()
        # Refresh display
        self.refresh_all()
    
    def on_deselected(self):
        """Called when this section is deselected."""
        return super().on_deselected()
    
    def refresh_all(self):
        """Refresh all UI components to reflect current settings."""
        # Update chamber variables from settings
        for chamber_idx in range(1, 4):
            chamber_settings = self.settings_manager.get_chamber_settings(chamber_idx)
            chamber_vars = self.chamber_vars[chamber_idx]
            
            chamber_vars['enabled'].set(chamber_settings.get('enabled', True))
            chamber_vars['pressure_target'].set(chamber_settings.get('pressure_target', PRESSURE_DEFAULTS.get('TARGET', 150)))
            chamber_vars['pressure_threshold'].set(chamber_settings.get('pressure_threshold', PRESSURE_DEFAULTS.get('THRESHOLD', 5)))
            chamber_vars['pressure_tolerance'].set(chamber_settings.get('pressure_tolerance', PRESSURE_DEFAULTS.get('TOLERANCE', 2)))
    
    def cleanup(self):
        """Clean up resources when the section is destroyed."""
        # Call base class cleanup
        super().cleanup()