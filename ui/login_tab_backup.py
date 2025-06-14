#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- coding: cp1252 -*-

"""
Modern Login Tab module for the Multi-Chamber Test application.

This module provides a streamlined LoginTab class that implements a secure user login
interface with an integrated alphanumeric keyboard in a modern, card-based layout
optimized for touchscreens with professional styling and enhanced user experience.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
import time
from typing import Callable, Optional, Dict, Any, List, Tuple
import threading

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS
from multi_chamber_test.core.roles import get_role_manager


class IntegratedKeyboard(ttk.Frame):
    """
    An integrated alphanumeric keyboard that can be embedded directly in UI layouts.
    
    This keyboard provides lowercase, uppercase, and numeric layouts with proper
    styling and visual feedback for touch interfaces, optimized for efficiency.
    """
    
    def __init__(self, parent, entry_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize the integrated keyboard.
        
        Args:
            parent: Parent widget
            entry_callback: Function to call with typed characters
        """
        super().__init__(parent)
        self.entry_callback = entry_callback
        
        # Keyboard state
        self.shift_active = False
        self.caps_lock = False
        
        # Get colors from parent or use defaults
        self.colors = getattr(parent, 'colors', UI_COLORS)
        
        # Configure keyboard layouts with improved organization
        self.lowercase_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'Backspace'],
            ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
            ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
            ['Shift', 'z', 'x', 'c', 'v', 'b', 'n', 'm', '.', 'Enter']
        ]
        
        self.uppercase_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'Backspace'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Shift', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', '.', 'Enter']
        ]
        
        # Improved symbols layout with more useful characters
        self.symbols_layout = [
            ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', 'Backspace'],
            ['-', '_', '=', '+', '[', ']', '{', '}', '\\', '|'],
            [';', ':', "'", '"', ',', '.', '<', '>', '/', '?'],
            ['Shift', 'Space', 'Clear', 'Enter']
        ]
        
        # Create the keyboard UI with responsive sizing
        self._create_keyboard()
    
    def _create_keyboard(self):
        """Create the keyboard layout and buttons with improved spacing and styling."""
        # Configure frame to expand properly
        self.columnconfigure(0, weight=1)
        
        # Clear any existing widgets
        for widget in self.winfo_children():
            widget.destroy()
        
        self.key_buttons = {}
        
        # Determine which layout to use
        if self.shift_active:
            layout = self.symbols_layout if self.caps_lock else self.uppercase_layout
        else:
            layout = self.uppercase_layout if self.caps_lock else self.lowercase_layout
        
        # Button sizing based on keyboard frame width
        self.update_idletasks()  # Ensure geometry is up to date
        
        # Create keyboard with consistent sizing
        for row_index, row in enumerate(layout):
            row_frame = ttk.Frame(self)
            row_frame.grid(row=row_index, column=0, sticky="ew", pady=2)
            row_frame.columnconfigure(tuple(range(len(row))), weight=1)
            
            # Determine the number of units in this row for relative sizing
            total_units = sum(self._get_key_width_units(key) for key in row)
            
            # Create buttons with proportional widths
            col_index = 0
            for key in row:
                # Determine styling based on key type
                width_units = self._get_key_width_units(key)
                style = self._get_key_style(key)
                
                # Create the button with proper styling
                btn = ttk.Button(
                    row_frame,
                    text=key if key != 'Space' else ' ',
                    style=style,
                    command=lambda k=key: self._key_pressed(k)
                )
                btn.grid(row=0, column=col_index, sticky="ew", padx=2, 
                         columnspan=width_units)
                
                # Add hover effect using bindings
                btn.bind("<Enter>", lambda e, b=btn: self._on_key_hover(b, True))
                btn.bind("<Leave>", lambda e, b=btn: self._on_key_hover(b, False))
                
                # Store button reference
                if key in self.key_buttons:
                    self.key_buttons[key].append(btn)
                else:
                    self.key_buttons[key] = [btn]
                
                col_index += width_units
    
    def _get_key_width_units(self, key: str) -> int:
        """
        Get the relative width units for a key.
        
        Args:
            key: The key text
            
        Returns:
            Width in relative units
        """
        if key == 'Backspace':
            return 2
        elif key == 'Enter':
            return 2
        elif key == 'Shift':
            return 2
        elif key == 'Space':
            return 6  # Spacebar takes up more space
        elif key == 'Clear':
            return 2
        else:
            return 1
    
    def _get_key_style(self, key: str) -> str:
        """
        Get the appropriate style for a key.
        
        Args:
            key: The key text
            
        Returns:
            Style name to use
        """
        if key == 'Enter':
            return 'Keyboard.Enter.TButton'
        elif key in ('Shift', 'Backspace', 'Clear'):
            return 'Keyboard.Special.TButton' if key != 'Shift' or not self.shift_active else 'Keyboard.Active.TButton'
        elif key == 'Space':
            return 'Keyboard.Space.TButton'
        else:
            return 'Keyboard.Key.TButton'
    
    def _on_key_hover(self, button: ttk.Button, is_hovering: bool):
            """
            Toggle the built-in ttk 'active' state on hover instead of touching
            the unsupported 'relief' option.
            """
            if is_hovering:
                button.state(['active'])     # hover on
            else:
                button.state(['!active'])    # hover off
    
    def _key_pressed(self, key: str):
        """
        Handle key press events with improved feedback and new functions.
        
        Args:
            key: The key that was pressed
        """
        # Provide visual feedback
        self._provide_key_feedback()
        
        if key == 'Backspace':
            # Send backspace character
            if self.entry_callback:
                self.entry_callback('\b')
        elif key == 'Enter':
            # Send enter/return
            if self.entry_callback:
                self.entry_callback('\n')
        elif key == 'Shift':
            # Toggle shift state
            self.shift_active = not self.shift_active
            self._update_layout()
        elif key == 'Caps':
            # Toggle caps lock
            self.caps_lock = not self.caps_lock
            self.shift_active = False
            self._update_layout()
        elif key == 'Space':
            # Send space character
            if self.entry_callback:
                self.entry_callback(' ')
        elif key == 'Clear':
            # Send special clear command
            if self.entry_callback:
                self.entry_callback('\x7F')  # Special code for clear
        else:
            # Send the character
            if self.entry_callback:
                self.entry_callback(key)
                
            # If shift is active, toggle it off (unless caps lock is on)
            if self.shift_active and not self.caps_lock:
                self.shift_active = False
                self._update_layout()
    
    def _provide_key_feedback(self):
        """Provide visual feedback when a key is pressed."""
        # We'll use a simple flash effect on the button itself
        # rather than changing the frame background
        pass
    
    def _update_layout(self):
        """Update the keyboard layout based on shift/caps state - reuses existing method."""
        self._create_keyboard()


class EnhancedEntry(ttk.Frame):
    """
    Enhanced entry field with clear visual styling and direct keyboard interaction.
    
    Provides password masking, visibility toggle, and visual focus indicators.
    """
    
    def __init__(self, parent, label_text: str, variable: tk.StringVar, is_password: bool = False, 
                 on_focus: Optional[Callable] = None, on_enter: Optional[Callable] = None):
        """
        Initialize enhanced entry field.
        
        Args:
            parent: Parent widget
            label_text: Label text for the field
            variable: StringVar to bind to the entry
            is_password: Whether to mask input as password
            on_focus: Callback when entry receives focus
            on_enter: Callback when Enter is pressed in this entry
        """
        super().__init__(parent)
        self.variable = variable
        self.on_focus_callback = on_focus
        self.on_enter_callback = on_enter
        self.is_password = is_password
        self.show_password = False
        
        # Colors for styling
        self.colors = getattr(parent, 'colors', UI_COLORS)
        
        # Create the enhanced entry UI
        self._create_ui(label_text)
    
    def _create_ui(self, label_text: str):
        """Create the enhanced entry UI with modern styling."""
        # Make the frame expand properly
        self.columnconfigure(0, weight=1)
        
        # Label
        self.label = ttk.Label(
            self,
            text=label_text,
            style='EntryLabel.TLabel'
        )
        self.label.grid(row=0, column=0, sticky="w", pady=(0, 5), columnspan=2)
        
        # Entry field
        self.entry = ttk.Entry(
            self,
            textvariable=self.variable,
            style='Enhanced.TEntry',
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            show="*" if self.is_password and not self.show_password else ""
        )
        self.entry.grid(row=1, column=0, sticky="ew")
        
        # Add password visibility toggle if this is a password field
        if self.is_password:
            self.toggle_btn = ttk.Button(
                self,
                text="??",  # Eye symbol
                style='PasswordToggle.TButton',
                width=3,
                command=self._toggle_password_visibility
            )
            self.toggle_btn.grid(row=1, column=1, padx=(2, 0))
        
        # Add focus highlight frame
        self.highlight_frame = ttk.Frame(
            self,
            style='Entry.Highlight.TFrame',
            height=2
        )
        self.highlight_frame.grid(row=2, column=0, sticky="ew", columnspan=2 if self.is_password else 1)
        self.highlight_frame.lower()  # Start as invisible
        
        # Bind focus events
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", self._on_enter)
    
    def _on_focus_in(self, event):
        """Handle entry receiving focus with visual indication."""
        # Show the highlight
        self.highlight_frame.configure(style='Entry.HighlightActive.TFrame')
        
        if self.on_focus_callback:
            self.on_focus_callback(self)
    
    def _on_focus_out(self, event):
        """Handle entry losing focus."""
        # Hide the highlight
        self.highlight_frame.configure(style='Entry.Highlight.TFrame')
    
    def _on_enter(self, event):
        """Handle Enter key press in entry."""
        if self.on_enter_callback:
            self.on_enter_callback()
    
    def _toggle_password_visibility(self):
        """Toggle password visibility."""
        self.show_password = not self.show_password
        self.entry.configure(show="" if self.show_password else "*")
        
        # Update button text to indicate state
        self.toggle_btn.configure(text="??" if not self.show_password else "??")
    
    def set_focus(self):
        """Set focus to this entry field."""
        self.entry.focus_set()
    
    def clear(self):
        """Clear the entry field."""
        self.variable.set("")


class LoadingIndicator(ttk.Frame):
    """
    A simple loading spinner for visual feedback during operations.
    """
    
    def __init__(self, parent, size: int = 20, thickness: int = 4):
        """
        Initialize loading indicator.
        
        Args:
            parent: Parent widget
            size: Size of the indicator in pixels
            thickness: Thickness of the spinner arc
        """
        super().__init__(parent)
        self.size = size
        self.thickness = thickness
        self.angle = 0
        self.colors = getattr(parent, 'colors', UI_COLORS)
        self.is_running = False
        self._animation_after_id = None
        
        # Create canvas for drawing
        self.canvas = tk.Canvas(
            self,
            width=size,
            height=size,
            bg=self.colors.get('BACKGROUND', '#FFFFFF'),
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Initial draw
        self._draw_spinner()
    
    def _draw_spinner(self):
        """Draw the spinner at the current angle."""
        # Clear canvas
        self.canvas.delete("all")
        
        # Calculate coordinates
        x1 = y1 = self.thickness / 2
        x2 = y2 = self.size - self.thickness / 2
        
        # Draw arc segment that appears to rotate
        start_angle = self.angle
        extent = 120  # degrees of the arc
        
        self.canvas.create_arc(
            x1, y1, x2, y2,
            start=start_angle,
            extent=extent,
            style=tk.ARC,
            outline=self.colors.get('PRIMARY', '#00A7E1'),
            width=self.thickness
        )
    
    def start(self):
        """Start the loading animation."""
        if not self.is_running:
            self.is_running = True
            self._animate()
    
    def stop(self):
        """Stop the loading animation."""
        self.is_running = False
        if self._animation_after_id:
            self.after_cancel(self._animation_after_id)
            self._animation_after_id = None
    
    def _animate(self):
        """Animate the spinner by updating the angle."""
        if not self.is_running:
            return
            
        # Update angle and redraw
        self.angle = (self.angle + 10) % 360
        self._draw_spinner()
        
        # Schedule next frame
        self._animation_after_id = self.after(50, self._animate)


class LoginCard(ttk.Frame):
    """
    A visually distinct card-like container for the login form.
    
    Provides elevation effect and rounded corners for a modern look.
    """
    
    def __init__(self, parent):
        """
        Initialize the login card.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.colors = getattr(parent, 'colors', UI_COLORS)
        
        # Create a canvas for custom drawing
        self.canvas = tk.Canvas(
            self,
            bg=self.colors.get('CARD_BACKGROUND', '#FFFFFF'),
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Inner frame for content
        self.inner_frame = ttk.Frame(
            self.canvas,
            style='Card.TFrame'
        )
        
        # Add inner frame to canvas with padding
        self.canvas_window = self.canvas.create_window(
            10, 10,  # Position with padding
            anchor=tk.NW,
            window=self.inner_frame
        )
        
        # Bind to resize events
        self.canvas.bind("<Configure>", self._on_configure)
        
        # Draw the shadow effect
        self._draw_shadow()
    
    def _on_configure(self, event):
        """Handle resize to update the card size."""
        # Update canvas window size, keeping the padding
        width = event.width - 20
        height = event.height - 20
        self.canvas.itemconfig(
            self.canvas_window,
            width=width,
            height=height
        )
        
        # Redraw the shadow effect
        self._draw_shadow()
    
    def _draw_shadow(self):
        """Draw a subtle shadow effect for depth."""
        # Clear existing shadows
        self.canvas.delete("shadow")
        
        # Get dimensions
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width <= 1 or height <= 1:  # Not yet properly initialized
            return
            
        # Draw subtle shadow rectangles
        shadow_color = self.colors.get('SHADOW', '#E0E0E0')
        
        # Bottom shadow
        self.canvas.create_rectangle(
            5, height - 5, width - 5, height,
            fill=shadow_color, outline="",
            tags="shadow"
        )
        
        # Right shadow
        self.canvas.create_rectangle(
            width - 5, 5, width, height - 5,
            fill=shadow_color, outline="",
            tags="shadow"
        )
        
        # Send shadows to back
        self.canvas.tag_lower("shadow")


class LoginTab:
    """
    Modern login interface tab with integrated keyboard in a professional card-based layout.
    
    This class implements a login screen with username/password authentication
    and an integrated alphanumeric keyboard for easy touch input, with enhanced
    visual styling and user experience improvements.
    """
    
    def __init__(self, parent, on_login_success: Optional[Callable] = None):
        """
        Initialize the LoginTab with the parent widget.
        
        Args:
            parent: Parent widget
            on_login_success: Callback function to call on successful login
        """
        self.logger = logging.getLogger('LoginTab')
        self._setup_logger()
        
        self.parent = parent
        self.on_login_success = on_login_success
        self.role_manager = get_role_manager()
        
        # Store colors for easy access
        self.colors = UI_COLORS
        
        # Login form state variables
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.login_error = tk.StringVar()
        self.remember_username = tk.BooleanVar(value=False)
        self.active_entry = None
        
        # Main container
        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Setup TTK styles with enhanced visuals
        self._setup_styles()
        
        # Create login UI with card-based layout
        self._create_modern_login_ui()
    
    def _setup_logger(self):
        """Configure logging for the login tab."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _setup_styles(self):
        """Set up custom styles for the professional login interface."""
        style = ttk.Style()
        
        # Container styles
        style.configure(
            'Login.Container.TFrame',
            background=self.colors.get('BACKGROUND', '#F5F7FA')
        )
        
        style.configure(
            'Card.TFrame',
            background=self.colors.get('CARD_BACKGROUND', '#FFFFFF')
        )
        
        # Card content container
        style.configure(
            'CardContent.TFrame',
            background=self.colors.get('CARD_BACKGROUND', '#FFFFFF'),
            padding=10
        )
        
        # Header styles
        style.configure(
            'Login.Header.TLabel',
            font=UI_FONTS.get('HEADER', ('Helvetica', 20, 'bold')),
            foreground=self.colors.get('PRIMARY', '#00A7E1'),
            background=self.colors.get('CARD_BACKGROUND', '#FFFFFF'),
            padding=(0, 10, 0, 15)
        )
        
        # Separator style
        style.configure(
            'Login.TSeparator',
            background=self.colors.get('BORDER', '#E0E0E0')
        )
        
        # Entry styles with focus states
        style.configure(
            'Enhanced.TEntry',
            padding=10,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12))
        )
        
        style.configure(
            'EntryLabel.TLabel',
            font=UI_FONTS.get('LABEL', ('Helvetica', 12, 'bold')),
            foreground=self.colors.get('TEXT_PRIMARY', '#1E293B'),
            background=self.colors.get('CARD_BACKGROUND', '#FFFFFF')
        )
        
        # Entry highlight frame styles
        style.configure(
            'Entry.Highlight.TFrame',
            background=self.colors.get('BORDER', '#E0E0E0')
        )
        
        style.configure(
            'Entry.HighlightActive.TFrame',
            background=self.colors.get('PRIMARY', '#00A7E1')
        )
        
        # Error message style
        style.configure(
            'Error.TLabel',
            font=UI_FONTS.get('LABEL', ('Helvetica', 11)),
            foreground=self.colors.get('ERROR', '#F44336'),
            background=self.colors.get('CARD_BACKGROUND', '#FFFFFF')
        )
        
        # Login button styles
        style.configure(
            'Login.TButton',
            font=UI_FONTS.get('BUTTON', ('Helvetica', 12, 'bold')),
            padding=10
        )
        
        style.map(
            'Login.TButton',
            background=[('!active', self.colors.get('PRIMARY', '#00A7E1')), 
                        ('active', self.colors.get('PRIMARY_DARK', '#0077A7'))],
            foreground=[('!active', 'white'), ('active', 'white')]
        )
        
        # Password toggle button
        style.configure(
            'PasswordToggle.TButton',
            font=('Helvetica', 12),
            padding=5
        )
        
        # Keyboard styles - all blue buttons as requested
        primary_color = self.colors.get('PRIMARY', '#00A7E1')
        primary_dark = self.colors.get('PRIMARY_DARK', '#0077A7')
        
        # Regular keys
        style.configure(
            'Keyboard.Key.TButton',
            font=('Helvetica', 16),
            padding=8
        )
        
        style.map(
            'Keyboard.Key.TButton',
            background=[('!active', primary_color), ('active', primary_dark)],
            foreground=[('!active', 'white'), ('active', 'white')],
            relief=[('!active', 'flat'), ('active', 'sunken')]
        )
        
        # Special keys - same blue but different font
        style.configure(
            'Keyboard.Special.TButton',
            font=('Helvetica', 14),
            padding=8
        )
        
        style.map(
            'Keyboard.Special.TButton',
            background=[('!active', primary_color), ('active', primary_dark)],
            foreground=[('!active', 'white'), ('active', 'white')],
            relief=[('!active', 'flat'), ('active', 'sunken')]
        )
        
        # Enter key - same blue but bold font
        style.configure(
            'Keyboard.Enter.TButton',
            font=('Helvetica', 14, 'bold'),
            padding=8
        )
        
        style.map(
            'Keyboard.Enter.TButton',
            background=[('!active', primary_color), ('active', primary_dark)],
            foreground=[('!active', 'white'), ('active', 'white')],
            relief=[('!active', 'flat'), ('active', 'sunken')]
        )
        
        # Active key styling (for shift)
        style.configure(
            'Keyboard.Active.TButton',
            font=('Helvetica', 14, 'bold'),
            padding=8,
            background=primary_dark,
            foreground='white'
        )
        
        # Space bar styling - same blue
        style.configure(
            'Keyboard.Space.TButton',
            font=('Helvetica', 14),
            padding=8
        )
        
        style.map(
            'Keyboard.Space.TButton',
            background=[('!active', primary_color), ('active', primary_dark)],
            foreground=[('!active', 'white'), ('active', 'white')],
            relief=[('!active', 'flat'), ('active', 'sunken')]
        )
    
    def _create_modern_login_ui(self):
        """Create a professional card-based login interface with improved layout."""
        # Configure container for responsive behavior
        container = ttk.Frame(self.main_frame, style='Login.Container.TFrame')
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Split the container vertically - top for login card, bottom for keyboard
        container.grid_rowconfigure(0, weight=2)  # Login card takes 2/5 of space
        container.grid_rowconfigure(1, weight=3)  # Keyboard takes 3/5 of space
        container.grid_columnconfigure(0, weight=1)
        
        # Create the login card with elevation effect
        self.login_card = LoginCard(container)
        self.login_card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        # Inside the card - create a nice content area
        card_content = ttk.Frame(self.login_card.inner_frame, style='CardContent.TFrame')
        card_content.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Brand header with cleaner styling
        header_frame = ttk.Frame(card_content, style='Card.TFrame')
        header_frame.pack(fill=tk.X)
        
        ttk.Label(
            header_frame,
            text="Authentication",
            style='Login.Header.TLabel'
        ).pack(anchor=tk.CENTER)
        
        # Separator for visual hierarchy
        ttk.Separator(card_content, style='Login.TSeparator').pack(fill=tk.X, pady=5)
        
        # Input fields in vertical stack for clarity
        fields_frame = ttk.Frame(card_content, style='Card.TFrame')
        fields_frame.pack(fill=tk.X, pady=15)
        
        # Enhanced username field with improved styling
        self.username_field = EnhancedEntry(
            fields_frame,
            label_text="Username",
            variable=self.username_var,
            on_focus=self._on_entry_focus,
            on_enter=self._focus_password
        )
        self.username_field.pack(fill=tk.X, pady=(0, 15))
        
        # Enhanced password field with visibility toggle
        self.password_field = EnhancedEntry(
            fields_frame,
            label_text="Password",
            variable=self.password_var,
            is_password=True,
            on_focus=self._on_entry_focus,
            on_enter=self._handle_login
        )
        self.password_field.pack(fill=tk.X)
        
        # Remember username option
        remember_frame = ttk.Frame(card_content, style='Card.TFrame')
        remember_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(
            remember_frame,
            text="Remember username",
            variable=self.remember_username,
            style='Login.TCheckbutton'
        ).pack(side=tk.LEFT)
        
        # Error message with better positioning
        error_frame = ttk.Frame(card_content, style='Card.TFrame')
        error_frame.pack(fill=tk.X, pady=5)
        
        self.error_label = ttk.Label(
            error_frame,
            textvariable=self.login_error,
            style='Error.TLabel'
        )
        self.error_label.pack(fill=tk.X)
        
        # Action buttons with loading indicator
        button_frame = ttk.Frame(card_content, style='Card.TFrame')
        button_frame.pack(fill=tk.X, pady=10)
        
        # Loading indicator (hidden initially)
        self.loading_indicator = LoadingIndicator(button_frame)
        self.loading_indicator.pack(side=tk.LEFT, padx=5)
        self.loading_indicator.pack_forget()  # Hide initially
        
        # Login button with improved styling
        self.login_button = ttk.Button(
            button_frame,
            text="Login",
            style='Login.TButton',
            command=self._handle_login
        )
        self.login_button.pack(side=tk.RIGHT, padx=5, fill=tk.X, expand=True)
        
        # Keyboard area
        keyboard_frame = ttk.Frame(container, style='Login.Container.TFrame')
        keyboard_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # Create the keyboard with improved styling
        self.keyboard = IntegratedKeyboard(
            keyboard_frame,
            entry_callback=self._handle_keyboard_input
        )
        self.keyboard.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Set initial focus to username field
        self.active_entry = self.username_field
        self.username_field.set_focus()
        
        # Attempt to load saved username if option was previously selected
        self._load_saved_username()
    
    def _on_entry_focus(self, entry):
        """
        Handle entry field focus with improved keyboard interaction.
        
        Args:
            entry: The entry field that received focus
        """
        self.active_entry = entry
        self.login_error.set("")  # Clear any error message
    
    def _focus_password(self):
        """Switch focus to password field."""
        self.active_entry = self.password_field
        self.password_field.set_focus()
    
    def _handle_keyboard_input(self, key):
        """
        Handle input from the integrated keyboard with enhanced functionality.
        
        Args:
            key: The key pressed on the keyboard
        """
        if not self.active_entry:
            # No active entry, focus on username
            self.active_entry = self.username_field
            self.username_field.set_focus()
        
        # Get the current entry widget
        current_entry = self.active_entry
        
        if key == '\b':
            # Backspace - remove last character
            current_value = current_entry.variable.get()
            if current_value:
                current_entry.variable.set(current_value[:-1])
        elif key == '\n':
            # Enter/Return
            if current_entry == self.username_field:
                # Move to password field
                self._focus_password()
            else:
                # Attempt login
                self._handle_login()
        elif key == '\x7F':  
            # Clear field (special clear key)
            current_entry.variable.set("")
        else:
            # Add the character
            current_value = current_entry.variable.get()
            current_entry.variable.set(current_value + key)
    
    def _show_loading(self, is_loading: bool):
        """
        Show or hide the loading indicator.
        
        Args:
            is_loading: Whether the operation is in progress
        """
        if is_loading:
            # Show loading indicator and disable button
            self.loading_indicator.pack(side=tk.LEFT, padx=5)
            self.loading_indicator.start()
            self.login_button.configure(state='disabled')
        else:
            # Hide loading indicator and enable button
            self.loading_indicator.stop()
            self.loading_indicator.pack_forget()
            self.login_button.configure(state='normal')
    
    def _save_username(self):
        """Save the username if remember option is selected."""
        # In a real application, this would store in a settings file,
        # but for simplicity we'll just log it
        if self.remember_username.get():
            username = self.username_var.get().strip()
            self.logger.info(f"Saving username preference: {username}")
            # Actual implementation would save to file or settings
    
    def _load_saved_username(self):
        """Load saved username if available."""
        # In a real implementation, this would load from settings
        # For demonstration, we'll just assume none is saved
        pass
    
    def _handle_login(self):
        """Process login authentication with improved user feedback."""
        # Get input values
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        
        # Input validation with helpful messages
        if not username:
            self.login_error.set("Please enter your username")
            self.username_field.set_focus()
            return
        
        if not password:
            self.login_error.set("Please enter your password")
            self.password_field.set_focus()
            return
        
        # Show loading state
        self._show_loading(True)
        
        # Use threading to prevent UI freeze during authentication
        def perform_login():
            # Simulate network delay for authentication
            time.sleep(0.8)
            
            # Attempt authentication
            role = self.role_manager.authenticate_user(username, password)
            
            # Update UI in main thread
            self.parent.after(0, lambda: self._handle_auth_result(username, role))
        
        # Start authentication in background
        threading.Thread(target=perform_login, daemon=True).start()
    
    def _handle_auth_result(self, username: str, role: Optional[str]):
        """
        Handle authentication result with appropriate UI updates.
        
        Args:
            username: The username that was authenticated
            role: The role if authentication was successful, None otherwise
        """
        # Hide loading indicator
        self._show_loading(False)
        
        if role:
            # Successful login
            self.logger.info(f"Login successful: User '{username}' as {role}")
            self.login_error.set("")
            
            # Save username preference if option selected
            self._save_username()
            
            # Clear password for security
            self.password_var.set("")
            
            # Call the success callback
            if self.on_login_success:
                self.on_login_success(role)
        else:
            # Failed login with helpful message
            self.logger.warning(f"Login failed for user '{username}'")
            self.login_error.set("Invalid username or password. Please try again.")
            
            # Clear password field for security
            self.password_var.set("")
            self.password_field.set_focus()
    
    def on_tab_selected(self):
        """Called when this tab is selected."""
        # Only clear password, keep username if remember option is selected
        self.password_var.set("")
        self.login_error.set("")
        
        # Reset loading state
        self._show_loading(False)
        
        # Set focus to username entry if empty, otherwise password
        if not self.username_var.get():
            self.active_entry = self.username_field
            self.username_field.set_focus()
        else:
            self.active_entry = self.password_field
            self.password_field.set_focus()
    
    def on_tab_deselected(self):
        """Called when user switches away from this tab."""
        # Reset login form
        self.password_var.set("")
        self.login_error.set("")
        
        # Allow tab switching
        return True