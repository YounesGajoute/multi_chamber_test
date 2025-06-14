#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Settings Tab module for the Multi-Chamber Test application.

This module provides the top-level SettingsTab class that serves as
a router to the modular settings sections in the new UI layout.
"""

import tkinter as tk
from tkinter import ttk
import logging
import importlib
from typing import Dict, Any, List, Optional, Callable

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS
from multi_chamber_test.config.settings import SettingsManager
from multi_chamber_test.core.test_manager import TestManager
from multi_chamber_test.core.roles import get_role_manager, has_access

# Import the new settings tab implementation
from multi_chamber_test.ui.settings.settings_tab import SettingsTab as ModularSettingsTab


class SettingsTab:
    """
    Settings Tab wrapper that implements the modular settings interface.
    
    This class serves as the entry point for the settings UI, maintaining
    compatibility with the original interface while using the new modular design.
    """
    
    def __init__(self, parent, test_manager: TestManager, settings_manager: SettingsManager):
        """
        Initialize the SettingsTab with the parent widget and required components.
        
        Args:
            parent: Parent widget (typically a Frame in main_window.py)
            test_manager: TestManager for applying settings
            settings_manager: SettingsManager for storing/retrieving settings
        """
        self.logger = logging.getLogger('SettingsTab')
        self._setup_logger()
        
        self.parent = parent
        self.test_manager = test_manager
        self.settings_manager = settings_manager
        
        # Create the modular settings tab implementation
        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Initialize the modular settings interface
        self.settings_tab = ModularSettingsTab(
            self.main_frame,
            test_manager,
            settings_manager
        )
    
    def _setup_logger(self):
        """Configure logging for the settings tab."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def on_tab_selected(self):
        """Called when this tab is selected."""
        # Delegate to modular implementation
        self.settings_tab.on_tab_selected()
    
    def on_tab_deselected(self):
        """Called when user switches away from this tab."""
        # Delegate to modular implementation
        return self.settings_tab.on_tab_deselected()
    
    def _go_back_to_main(self):
        """Navigate back to the main tab."""
        # Use event generation to switch tab
        self.parent.event_generate("<<SwitchToMainTab>>")