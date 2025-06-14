#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Keypad module for the Multi-Chamber Test application.

This module provides customizable keypad classes for numeric and alphanumeric input 
on touchscreen interfaces, optimized for 1920x1080 displays.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, Any, List, Tuple, Union

class NumericKeypad(tk.Toplevel):
    """
    Touchscreen-friendly numeric keypad for entering values.
    
    Provides a full-screen numeric keypad with large buttons suitable for
    touchscreen operation, with validation for different input types.
    """
    
    def __init__(self, parent, variable, title: str = "Enter Value", 
                 is_pressure_target: bool = False, max_value: Optional[float] = None,
                 min_value: Optional[float] = 0, decimal_places: int = 2,
                 callback: Optional[Callable] = None):
        """
        Initialize the NumericKeypad with the specified parameters.
        
        Args:
            parent: Parent widget
            variable: StringVar or IntVar to store the result
            title: Dialog title
            is_pressure_target: Whether this is for a pressure target (has specific validation)
            max_value: Maximum allowed value (None for no limit)
            min_value: Minimum allowed value (0 by default)
            decimal_places: Number of decimal places allowed
            callback: Optional callback function to call when OK is pressed
        """
        super().__init__(parent)
        
        self.variable = variable
        self.is_pressure_target = is_pressure_target
        self.result = ""
        self.max_value = max_value
        self.min_value = min_value
        self.decimal_places = decimal_places
        self.callback = callback
        
        # Set up window
        self.title(title)
        self.configure(bg="white")
        self.resizable(False, False)
        
        # Make this window modal
        self.transient(parent)
        self.after_idle(self._safe_grab)
        
        # Calculate an appropriate size based on screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Optimized for 1920x1080 displays - narrower and proportional
        width = int(screen_width * 0.6)  # Reduced from 0.5
        height = int(screen_height * 0.65)  # Reduced from 0.6
        
        # Position in center of screen
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Get colors from parent if available
        self.colors = getattr(parent, 'colors', {
            'primary': '#00A7E1',
            'secondary': '#FFFFFF',
            'background': '#FFFFFF',
            'text_primary': '#1E293B',
            'border': '#E2E8F0',
            'error': '#F44336'
        })
        
        # Setup styles
        self.setup_styles()
        
        # Create the UI elements
        self.create_ui()
        
        # Bind keyboard events
        self.bind("<Escape>", self.cancel_click)
        self.bind("<Return>", self.ok_click)
        
        # Focus on the entry field
        self.display.focus_set()
    
    def _safe_grab(self):
        """Safely set window grab after ensuring visibility and avoid errors if destroyed early."""
        if not self.winfo_exists():
            return  # Window is already destroyed
    
        try:
            self.lift()
            self.attributes('-topmost', True)
            self.update_idletasks()
            self.wait_visibility()  # Ensure window is visible before grabbing
    
            if not self.winfo_exists():
                return  # Window was destroyed while waiting
    
            self.grab_set()
    
            # Remove topmost after grab to avoid staying in front permanently
            self.after(100, lambda: self.attributes('-topmost', False))
    
            # Focus the entry field safely
            if hasattr(self, 'display') and self.display.winfo_exists():
                self.after(200, self.display.focus_set)
    
        except tk.TclError as e:
            print(f"Grab failed: {e}")
            # Only retry a few times to avoid infinite loop
            if self.winfo_exists():
                retry_count = getattr(self, '_grab_retry_count', 0)
                if retry_count < 5:
                    self._grab_retry_count = retry_count + 1
                    self.after(200, self._safe_grab)
    
    def setup_styles(self):
        """Set up custom styles for the keypad."""
        self.style = ttk.Style()
        
        # Keypad button style - larger for HD displays
        self.style.configure(
            'Keypad.TButton', 
            font=('Helvetica', 22),  # Increased from 16
            padding=15            # Increased from 10
        )
        
        # Action button style (OK, Cancel)
        self.style.configure(
            'Action.TButton',
            font=('Helvetica', 18),  # Increased from 14
            padding=15            # Increased from 10
        )
        
        # Secondary button style (Clear)
        self.style.configure(
            'Secondary.TButton',
            font=('Helvetica', 18),  # Increased from 14
            padding=15            # Increased from 10
        )
    
    def create_ui(self):
        """Create the user interface elements."""
        # Main container with padding
        main_frame = ttk.Frame(self, padding=30)
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        # Title label at top - larger for HD display
        ttk.Label(
            main_frame,
            text=self.title(),
            font=('Helvetica', 24, 'bold'),
            anchor='center'
        ).pack(fill=tk.X, pady=(0, 30))
    
        # Display frame
        display_frame = ttk.Frame(main_frame)
        display_frame.pack(fill=tk.X, pady=(0, 30))
    
        # Value label
        ttk.Label(
            display_frame,
            text="Value:",
            font=('Helvetica', 18)
        ).pack(side=tk.LEFT)
    
        # Display entry
        self.display = ttk.Entry(
            display_frame,
            textvariable=tk.StringVar(value=self.variable.get()),
            font=('Helvetica', 24),
            width=15,
            justify='right'
        )
        self.display.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(15, 0))
    
        # Error message label
        self.error_label = ttk.Label(
            main_frame,
            text="",
            font=('Helvetica', 16),
            foreground=self.colors.get('error', 'red')
        )
        self.error_label.pack(fill=tk.X, pady=(0, 20))
    
        # Keypad frame
        keypad_frame = ttk.Frame(main_frame)
        keypad_frame.pack(fill=tk.BOTH, expand=True)
    
        # Configure rows and columns
        for i in range(4):
            keypad_frame.rowconfigure(i, weight=1)
        for i in range(3):
            keypad_frame.columnconfigure(i, weight=1)
    
        # Button layout
        buttons = [
            '7', '8', '9',
            '4', '5', '6',
            '1', '2', '3',
            '.', '0', 'C'
        ]
    
        row, col = 0, 0
        for button in buttons:
            cmd = lambda x=button: self.click(x)
            btn = ttk.Button(
                keypad_frame,
                text=button,
                style='Keypad.TButton',
                command=cmd
            )
            btn.grid(row=row, column=col, sticky='nsew', padx=10, pady=10)
            col += 1
            if col > 2:
                col = 0
                row += 1
    
        # Action buttons frame
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(30, 0))
    
        # OK button
        self.ok_button = ttk.Button(
            action_frame,
            text="OK",
            style='Action.TButton',
            width=10,
            command=self.ok_click
        )
        self.ok_button.pack(side=tk.RIGHT, padx=10)
    
        # Cancel button
        self.cancel_button = ttk.Button(
            action_frame,
            text="Cancel",
            style='Secondary.TButton',
            width=10,
            command=self.cancel_click
        )
        self.cancel_button.pack(side=tk.RIGHT, padx=10)
    
        # Ensure focus lands on the entry field
        self.after(300, self.display.focus_set)
    
    def click(self, key):
        """
        Handle button clicks on the keypad.
        
        Args:
            key: The key that was clicked
        """
        current = self.display.get()
        
        if key == 'C':
            # Clear the display
            self.display.delete(0, tk.END)
        elif key == '.':
            # Only add decimal if not already present
            if '.' not in current:
                self.display.insert(tk.END, key)
        else:
            # Add number
            self.display.insert(tk.END, key)
        
        # Clear any error message
        self.error_label.config(text="")
    
    def validate_input(self) -> Tuple[bool, str]:
        """
        Validate the entered value.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            value = self.display.get().strip()
            
            # Check if empty
            if not value:
                return False, "Please enter a value"
            
            # Convert to appropriate type
            try:
                if '.' in value:
                    # Check decimal places
                    if len(value.split('.')[1]) > self.decimal_places:
                        return False, f"Maximum {self.decimal_places} decimal places allowed"
                    
                    # Convert to float
                    value_float = float(value)
                else:
                    # Convert to int if no decimal
                    value_float = int(value)
            except ValueError:
                return False, "Invalid number format"
            
            # Check min/max constraints
            if self.min_value is not None and value_float < self.min_value:
                return False, f"Value must be at least {self.min_value}"
                
            if self.max_value is not None and value_float > self.max_value:
                return False, f"Value cannot exceed {self.max_value}"
                
            # Additional validation for pressure target
            if self.is_pressure_target and value_float > 600:
                return False, "Target pressure cannot exceed 600 mbar"
            
            return True, ""
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def cancel_click(self, event=None):
        """Close the keypad dialog without saving."""
        self.destroy()
    
    def ok_click(self, event=None):
        """Validate and save the entered value."""
        is_valid, error_message = self.validate_input()
        
        if not is_valid:
            self.error_label.config(text=error_message)
            return
            
        # Set the value
        try:
            value = self.display.get().strip()
            
            # Convert to appropriate type for the variable
            if isinstance(self.variable, tk.IntVar):
                self.variable.set(int(float(value)))
            elif isinstance(self.variable, tk.DoubleVar):
                self.variable.set(float(value))
            else:
                self.variable.set(value)
            
            # Call callback if provided
            if self.callback:
                self.callback(self.variable.get())
            
            # Close the dialog
            self.destroy()
            
        except Exception as e:
            self.error_label.config(text=f"Error: {str(e)}")


class AlphanumericKeyboard(tk.Toplevel):
    """
    Touchscreen-friendly alphanumeric keyboard for text input.
    
    Provides a full-screen keyboard with large buttons suitable for
    touchscreen operation, supporting both lowercase and uppercase input.
    """
    
    def __init__(self, parent, variable, title: str = "Enter Text", 
                 max_length: Optional[int] = None,
                 password_mode: bool = False,
                 callback: Optional[Callable] = None):
        """
        Initialize the AlphanumericKeyboard with the specified parameters.
        
        Args:
            parent: Parent widget
            variable: StringVar to store the result
            title: Dialog title
            max_length: Maximum allowed length (None for no limit)
            password_mode: Whether to mask input as a password
            callback: Optional callback function to call when OK is pressed
        """
        super().__init__(parent)
        
        self.variable = variable
        self.max_length = max_length
        self.password_mode = password_mode
        self.callback = callback
        self.is_uppercase = False
        self.caps_lock = False
        self.shift_pressed = False
        
        # Set up window
        self.title(title)
        self.configure(bg="white")
        self.resizable(False, False)

        # Make this window modal and schedule safe grab
        self.transient(parent)
        self.after_idle(self._safe_grab)
        
        # Calculate and center the window
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = int(screen_width * 0.7)
        height = int(screen_height * 0.6)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Fallback color scheme
        self.colors = getattr(parent, 'colors', {
            'primary': '#00A7E1',
            'secondary': '#FFFFFF',
            'background': '#FFFFFF',
            'text_primary': '#1E293B',
            'border': '#E2E8F0',
            'error': '#F44336'
        })
        
        self.lowercase_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'BACK'],
            ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\\'],
            ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'", 'ENTER'],
            ['SHIFT', 'z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/', 'CAPS']
        ]
        
        self.uppercase_layout = [
            ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '_', '+', 'BACK'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '{', '}', '|'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ':', '"', 'ENTER'],
            ['SHIFT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', '<', '>', '?', 'CAPS']
        ]

        # Setup styles and interface
        self.setup_styles()
        self.create_ui()

        # Bindings
        self.bind("<Escape>", self.cancel_click)
        self.bind("<Return>", self.ok_click)
        self.display.focus_set()
    
    def _safe_grab(self):
        """Safely set window grab after ensuring visibility."""
        if not self.winfo_exists():
            return  # Skip if the window has been destroyed
    
        try:
            self.lift()
            self.attributes('-topmost', True)
            self.update_idletasks()
            self.wait_visibility()  # Ensure window is visible before grabbing
    
            if self.winfo_exists():  # Double-check after wait
                self.grab_set()
                self.after(100, lambda: self.attributes('-topmost', False))
    
                if hasattr(self, 'display') and self.display.winfo_exists():
                    self.after(200, self.display.focus_set)
    
        except tk.TclError as e:
            print(f"Grab failed: {e}")
            if self.winfo_exists():
                self.after(200, self._safe_grab)
    
    def setup_styles(self):
        """Set up custom styles for the keyboard."""
        self.style = ttk.Style()
        
        # Keyboard button style - larger for HD display
        self.style.configure(
            'Keyboard.TButton', 
            font=('Helvetica', 18),  # Increased from 14
            padding=8            # Increased from 5
        )
        
        # Special key style (Shift, Backspace, Enter)
        self.style.configure(
            'Special.TButton',
            font=('Helvetica', 16),  # Increased from 14
            padding=8            # Increased from 5
        )
        
        # Active special key (when CAPS or SHIFT is active)
        self.style.configure(
            'Active.Special.TButton',
            font=('Helvetica', 16),
            padding=8,
            background='#E2E8F0',
            foreground='#00A7E1'
        )
        
        # Action button style (OK, Cancel)
        self.style.configure(
            'Action.TButton',
            font=('Helvetica', 18),  # Increased from 14
            padding=15           # Increased from 10
        )
    
    def create_ui(self):
        """Create the user interface elements."""
        # Main container with padding
        main_frame = ttk.Frame(self, padding=30)  # Increased from 20
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title label at top - larger for HD display
        ttk.Label(
            main_frame, 
            text=self.title(),
            font=('Helvetica', 24, 'bold'),  # Increased from 18
            anchor='center'
        ).pack(fill=tk.X, pady=(0, 25))  # Increased padding
        
        # Display frame
        display_frame = ttk.Frame(main_frame)
        display_frame.pack(fill=tk.X, pady=(0, 25))  # Increased padding
        
        # Display entry with proper masking for password mode - larger for HD
        self.display = ttk.Entry(
            display_frame,
            textvariable=tk.StringVar(value=self.variable.get()),
            font=('Helvetica', 24),  # Increased from 18
            width=30,
            show='*' if self.password_mode else ''
        )
        self.display.pack(fill=tk.X, expand=True)
        
        # Error message label - larger text
        self.error_label = ttk.Label(
            main_frame,
            text="",
            font=('Helvetica', 16),  # Increased from 12
            foreground=self.colors.get('error', 'red')
        )
        self.error_label.pack(fill=tk.X, pady=(0, 15))  # Increased padding
        
        # Keyboard frame
        keyboard_frame = ttk.Frame(main_frame)
        keyboard_frame.pack(fill=tk.BOTH, expand=True)
        
        # Button rows with improved organization
        self.keyboard_buttons = []
        layout = self.uppercase_layout if self.is_uppercase else self.lowercase_layout
        
        for row_index, row in enumerate(layout):
            button_row = []
            row_frame = ttk.Frame(keyboard_frame)
            row_frame.pack(pady=5, fill=tk.X)  # Increased padding
            
            for key in row:
                # Determine button style and width
                if key in ['SHIFT', 'ENTER', 'BACK', 'CAPS']:
                    style = 'Special.TButton'
                    width = 8  # Fixed width for special keys
                    
                    # Map key text for display
                    display_key = key
                    if key == 'BACK':
                        display_key = "Backspace"
                    elif key == 'ENTER':
                        display_key = "Enter"
                    elif key == 'CAPS':
                        display_key = "Caps Lock"
                else:
                    style = 'Keyboard.TButton'
                    width = 4 if len(key) == 1 else len(key) * 2
                    display_key = key
                
                # Create button with correct command mapping
                if key == 'BACK':
                    btn = ttk.Button(
                        row_frame,
                        text=display_key,
                        width=width,
                        style=style,
                        command=lambda: self.handle_key_press('BACKSPACE')
                    )
                elif key == 'ENTER':
                    btn = ttk.Button(
                        row_frame,
                        text=display_key,
                        width=width,
                        style=style,
                        command=self.ok_click
                    )
                elif key == 'SHIFT':
                    btn = ttk.Button(
                        row_frame,
                        text=display_key,
                        width=width,
                        style=style,
                        command=lambda: self.handle_key_press('SHIFT')
                    )
                elif key == 'CAPS':
                    btn = ttk.Button(
                        row_frame,
                        text=display_key,
                        width=width,
                        style=style,
                        command=lambda: self.handle_key_press('CAPS')
                    )
                else:
                    btn = ttk.Button(
                        row_frame,
                        text=display_key,
                        width=width,
                        style=style,
                        command=lambda k=key: self.handle_key_press(k)
                    )
                
                # Pack button with proper spacing
                btn.pack(side=tk.LEFT, padx=3, pady=3, fill=tk.X,
                         expand=(key in ['SHIFT', 'ENTER', 'BACK', 'CAPS']))
                button_row.append(btn)
            
            self.keyboard_buttons.append(button_row)
        
        # Additional bottom row with space bar
        space_frame = ttk.Frame(keyboard_frame)
        space_frame.pack(pady=5, fill=tk.X)
        
        # Space key - larger and centered
        ttk.Button(
            space_frame,
            text="Space",
            width=25,  # Increased width
            style='Keyboard.TButton',
            command=lambda: self.handle_key_press(' ')
        ).pack(side=tk.LEFT, padx=3, pady=3, fill=tk.X, expand=True)
        
        # Action buttons frame
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(25, 0))  # Increased padding
        
        # Clear button - fixed width
        ttk.Button(
            action_frame, 
            text="Clear All", 
            width=12,  # Fixed width
            style='Secondary.TButton',
            command=self.clear_all
        ).pack(side=tk.LEFT, padx=10)  # Increased padding
        
        # OK and Cancel buttons - fixed width
        ttk.Button(
            action_frame, 
            text="OK", 
            width=10,  # Fixed width
            style='Action.TButton',
            command=self.ok_click
        ).pack(side=tk.RIGHT, padx=10)  # Increased padding
        
        ttk.Button(
            action_frame, 
            text="Cancel", 
            width=10,  # Fixed width
            style='Secondary.TButton',
            command=self.cancel_click
        ).pack(side=tk.RIGHT, padx=10)  # Increased padding
    
    def handle_key_press(self, key):
        """
        Handle key press on the keyboard with improved uppercase handling.
        
        Args:
            key: The key that was pressed
        """
        current = self.display.get()
        
        if key == 'CAPS':
            # Toggle caps lock mode
            self.caps_lock = not self.caps_lock
            self.is_uppercase = self.caps_lock  # Set layout based on caps state
            self.update_keyboard_layout()
            
            # Update CAPS button styling
            for row in self.keyboard_buttons:
                for btn in row:
                    if btn.cget('text') == "Caps Lock":
                        btn.config(style='Active.Special.TButton' if self.caps_lock else 'Special.TButton')
                        
        elif key == 'SHIFT':
            # Toggle shift for next character
            self.shift_pressed = not self.shift_pressed
            self.is_uppercase = self.shift_pressed  # Set layout temporarily
            self.update_keyboard_layout()
            
            # Update SHIFT button styling
            for row in self.keyboard_buttons:
                for btn in row:
                    if btn.cget('text') == "Shift":
                        btn.config(style='Active.Special.TButton' if self.shift_pressed else 'Special.TButton')
                
        elif key == 'BACKSPACE':
            # Remove the last character
            self.display.delete(len(current) - 1, tk.END)
            
        elif key == ' ':
            # Add space
            if self.max_length is None or len(current) < self.max_length:
                self.display.insert(tk.END, ' ')
                
        else:
            # Add the character if within length limit
            if self.max_length is None or len(current) < self.max_length:
                # Determine if we need uppercase or lowercase
                if self.is_uppercase and key.isalpha():
                    char = key.upper()
                else:
                    char = key
                    
                self.display.insert(tk.END, char)
                
                # Reset shift if it was temporary (caps lock stays on)
                if self.shift_pressed and not self.caps_lock:
                    self.shift_pressed = False
                    self.is_uppercase = self.caps_lock  # Return to caps lock state
                    self.update_keyboard_layout()
                    
                    # Update SHIFT button styling
                    for row in self.keyboard_buttons:
                        for btn in row:
                            if btn.cget('text') == "Shift":
                                btn.config(style='Special.TButton')
        
        # Clear any error message
        self.error_label.config(text="")
    
    def update_keyboard_layout(self):
        """Update the keyboard layout based on uppercase/lowercase state."""
        layout = self.uppercase_layout if self.is_uppercase else self.lowercase_layout
        
        for row_index, row in enumerate(layout):
            for key_index, key in enumerate(row):
                if row_index < len(self.keyboard_buttons) and key_index < len(self.keyboard_buttons[row_index]):
                    # Map special key names to their display text
                    display_key = key
                    if key == 'BACK':
                        display_key = "Backspace"
                    elif key == 'ENTER':
                        display_key = "Enter"
                    elif key == 'SHIFT':
                        display_key = "Shift"
                    elif key == 'CAPS':
                        display_key = "Caps Lock"
                    
                    self.keyboard_buttons[row_index][key_index].config(text=display_key)
    
    def clear_all(self):
        """Clear all text from the display."""
        self.display.delete(0, tk.END)
        self.error_label.config(text="")
    
    def validate_input(self) -> Tuple[bool, str]:
        """
        Validate the entered text.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        text = self.display.get()
        
        # Check if empty
        if not text.strip() and not self.password_mode:
            return False, "Please enter text"
        
        # Check max length
        if self.max_length is not None and len(text) > self.max_length:
            return False, f"Text cannot exceed {self.max_length} characters"
        
        return True, ""
    
    def cancel_click(self, event=None):
        """Close the keyboard dialog without saving."""
        self.destroy()
    
    def ok_click(self, event=None):
        """Validate and save the entered text."""
        is_valid, error_message = self.validate_input()
        
        if not is_valid:
            self.error_label.config(text=error_message)
            return
            
        # Set the value
        try:
            self.variable.set(self.display.get())
            
            # Call callback if provided
            if self.callback:
                self.callback(self.variable.get())
            
            # Close the dialog
            self.destroy()
            
        except Exception as e:
            self.error_label.config(text=f"Error: {str(e)}")




def show_numeric_keypad(parent, variable, title="Enter Value", **kwargs):
    """
    Convenience function to show a numeric keypad dialog with improved visibility.
    
    Args:
        parent: Parent widget
        variable: Variable to store the result
        title: Dialog title
        **kwargs: Additional arguments to pass to NumericKeypad
        
    Returns:
        The keypad instance
    """
    keypad = NumericKeypad(parent, variable, title, **kwargs)
    # Ensure the keypad is visible
    keypad.lift()
    # Schedule focus after dialog is fully realized
    keypad.after(100, keypad.display.focus_set)
    return keypad


def show_alphanumeric_keyboard(parent, variable, title="Enter Text", **kwargs):
    """
    Convenience function to show an alphanumeric keyboard dialog with improved visibility.
    
    Args:
        parent: Parent widget
        variable: Variable to store the result
        title: Dialog title
        **kwargs: Additional arguments to pass to AlphanumericKeyboard
        
    Returns:
        The keyboard instance
    """
    keyboard = AlphanumericKeyboard(parent, variable, title, **kwargs)
    # Ensure the keyboard is visible
    keyboard.lift()
    # Schedule focus after dialog is fully realized
    keyboard.after(100, keyboard.display.focus_set)
    return keyboard


# Example usage if run directly
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Keypad Test")
    
    # Create a test button
    num_var = tk.DoubleVar(value=0.0)
    text_var = tk.StringVar(value="")
    
    def show_num_keypad():
        show_numeric_keypad(root, num_var, "Enter Number")
        
    def show_text_keyboard():
        show_alphanumeric_keyboard(root, text_var, "Enter Text")
    
    ttk.Button(root, text="Show Numeric Keypad", command=show_num_keypad).pack(pady=10)
    ttk.Button(root, text="Show Text Keyboard", command=show_text_keyboard).pack(pady=10)
    
    root.mainloop()