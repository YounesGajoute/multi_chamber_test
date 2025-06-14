
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Password Dialog module for the Multi-Chamber Test application.

This module provides a touchscreen-friendly password dialog for controlling
access to protected application features like settings and calibration.
It leverages the NumericKeypad from ui/keypad.py for input.
"""

import tkinter as tk
from tkinter import ttk
import logging
from typing import Optional, Callable, Dict, Any, List

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS, USER_ROLES
from multi_chamber_test.core.roles import get_role_manager
from multi_chamber_test.ui.keypad import AlphanumericKeyboard, NumericKeypad


class PasswordDialog(tk.Toplevel):
    """
    Touchscreen-friendly password dialog for protected access.
    
    This dialog prompts the user to enter a password for accessing
    protected features like settings and calibration screens.
    It automatically opens an alphanumeric keyboard for password input.
    """
    
    def __init__(self, parent, min_role: str, 
                 on_success: Optional[Callable] = None,
                 on_cancel: Optional[Callable] = None):
        """
        Initialize the password dialog.
        
        Args:
            parent: Parent widget
            min_role: Minimum role required for access
            on_success: Callback function when authentication succeeds
            on_cancel: Callback function when dialog is canceled
        """
        super().__init__(parent)
        self.logger = logging.getLogger('PasswordDialog')
        self._setup_logger()
        
        self.parent = parent
        self.min_role = min_role
        self.on_success = on_success
        self.on_cancel = on_cancel
        self._keypad_open = False
        self.keypad_instance = None
        
        self.title(f"Authentication Required - {min_role}")
        self.configure(bg=UI_COLORS['BACKGROUND'])

        # Set dialog size based on screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = int(screen_width * 0.6)
        height = int(screen_height * 0.5)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Initialize role manager and password variable
        self.role_manager = get_role_manager()
        self.password_var = tk.StringVar()

        # Set up UI
        self.setup_styles()
        self.create_ui()

        # Bind keyboard events
        self.bind('<Return>', self.authenticate)
        self.bind('<Escape>', self.cancel)

        # Log dialog creation
        self.logger.debug(f"Password dialog initialized for role: {min_role}")
        
        # Schedule keypad to appear after dialog is fully rendered
        self.after(100, self.show_keypad)
        
        # Make dialog modal
        self.wait_window(self)
    
    def _setup_logger(self):
        """Configure logging for the password dialog."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def setup_styles(self):
        """Set up custom styles for the password dialog."""
        style = ttk.Style()
    
        style.configure(
            'Header.TLabel',
            font=UI_FONTS['HEADER'],
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['PRIMARY']
        )
        style.configure(
            'TLabel',
            font=UI_FONTS['LABEL'],
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_PRIMARY']
        )
        style.configure(
            'Error.TLabel',
            font=UI_FONTS['LABEL'],
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['ERROR']
        )
        style.configure(
            'Hint.TLabel',
            font=('Helvetica', 10, 'italic'),
            background=UI_COLORS['BACKGROUND'],
            foreground=UI_COLORS['TEXT_SECONDARY']
        )
        style.configure(
            'Action.TButton',
            font=UI_FONTS['BUTTON'],
            padding=10
        )

    def create_ui(self):
        """Create the user interface elements."""
        # Main container with padding
        main_frame = ttk.Frame(self, padding=20, style='TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_label = ttk.Label(
            main_frame,
            text=f"Enter Password for {self.min_role}",
            style='Header.TLabel'
        )
        header_label.pack(pady=(0, 20))
        
        # Password entry frame
        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(fill=tk.X, pady=10)
        
        self.password_entry = ttk.Entry(
            entry_frame,
            textvariable=self.password_var,
            font=('Helvetica', 18),
            width=20,
            justify='center',
            show='*'  # Mask password with asterisks
        )
        self.password_entry.pack(fill=tk.X, padx=50)
        
        # Hint label below password entry
        ttk.Label(
            entry_frame,
            text="Tap to show keypad",
            style='Hint.TLabel'
        ).pack(anchor=tk.CENTER, pady=(5, 0))
        
        # Bind touch/click event to show keypad
        self.password_entry.bind("<Button-1>", self.show_keypad)
        
        # Error message label
        self.error_label = ttk.Label(
            main_frame,
            text="",
            style='Error.TLabel'
        )
        self.error_label.pack(pady=10)
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)
        
        # Cancel button
        cancel_button = ttk.Button(
            button_frame,
            text="Cancel",
            command=self.cancel,
            style='Action.TButton',
            width=10
        )
        cancel_button.pack(side=tk.LEFT, padx=10)
        
        # OK button
        ok_button = ttk.Button(
            button_frame,
            text="OK",
            command=self.authenticate,
            style='Action.TButton',
            width=10
        )
        ok_button.pack(side=tk.RIGHT, padx=10)
    
    def show_keypad(self, event=None):
        """Show the numeric keypad for password entry."""
        if not self._keypad_open:
            self._keypad_open = True
    
            def on_close(value):
                self._keypad_open = False
                self.keypad_instance = None
                self.update_password(value)
                # Return focus to password dialog
                self.focus_set()
                # Check if authentication can proceed automatically
                if value and len(value) >= 4:  # Most passwords are at least 4 digits
                    self.after(100, self.authenticate)
    
            # Create keypad with password variable
            self.keypad_instance = AlphanumericKeyboard(
                self,
                self.password_var,
                title="Enter Password",
                password_mode=True,
                callback=on_close
            )
            
            # Ensure keypad has focus
            if self.keypad_instance and hasattr(self.keypad_instance, 'display'):
                self.keypad_instance.display.focus_set()
    
    def update_password(self, value):
        """
        Update the password value and clear any error messages.
        
        Args:
            value: New password value
        """
        self.password_var.set(value)
        self.error_label.config(text="")
    
    def authenticate(self, event=None):
        """
        Authenticate with the entered password.
        
        Args:
            event: Event data (not used)
        """
        password = self.password_var.get()
        
        # Check if password is empty
        if not password:
            self.error_label.config(text="Please enter a password")
            return
            
        if self.role_manager.authenticate_user(self.min_role, password):
            self.logger.info(f"Authentication successful for {self.min_role}")
            
            # Clean up keypad if open
            if self._keypad_open and self.keypad_instance:
                try:
                    self.keypad_instance.destroy()
                except:
                    pass
                self._keypad_open = False
                
            self.destroy()
            if self.on_success:
                self.on_success()
        else:
            self.error_label.config(text="Invalid password. Please try again.")
            self.password_var.set("")
            self.logger.warning(f"Authentication failed for {self.min_role}")
            
            # Reopen keypad after failed attempt
            self.after(100, self.show_keypad)
    
    def cancel(self, event=None):
        """
        Cancel the authentication and close the dialog.
        
        Args:
            event: Event data (not used)
        """
        # Clean up keypad if open
        if self._keypad_open and self.keypad_instance:
            try:
                self.keypad_instance.destroy()
            except:
                pass
            
        self.destroy()
        if self.on_cancel:
            self.on_cancel()


class PasswordChangeDialog(tk.Toplevel):
    """
    Dialog for changing user passwords.
    
    This dialog allows users to change passwords for roles they have access to.
    It prompts for current password, new password, and confirmation.
    """
    
    def __init__(self, parent, role: str,
                 on_success: Optional[Callable] = None,
                 on_cancel: Optional[Callable] = None):
        """
        Initialize the password change dialog.
        
        Args:
            parent: Parent widget
            role: Role to change password for
            on_success: Callback function when password change succeeds
            on_cancel: Callback function when dialog is canceled
        """
        super().__init__(parent)
        self.role = role
        self.on_success = on_success
        self.on_cancel = on_cancel
        self.role_manager = get_role_manager()
        self._keypad_open = False

        self.title(f"Change Password - {role.title()}")
        self.configure(bg=UI_COLORS['BACKGROUND'])

        # Set dialog size based on screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = int(screen_width * 0.5)
        height = int(screen_height * 0.6)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Initialize password variables
        self.current_password = tk.StringVar()
        self.new_password = tk.StringVar()
        self.confirm_password = tk.StringVar()

        # Set up UI
        self.setup_styles()
        self.create_ui()
        
        # Bind keyboard events
        self.bind('<Escape>', self.cancel)

    def setup_styles(self):
        """Set up custom styles for the password change dialog."""
        style = ttk.Style()
        style.configure('Label.TLabel', font=UI_FONTS['LABEL'], background=UI_COLORS['BACKGROUND'])
        style.configure('Error.TLabel', font=UI_FONTS['LABEL'], foreground=UI_COLORS['ERROR'], background=UI_COLORS['BACKGROUND'])
        style.configure('Hint.TLabel', font=('Helvetica', 10, 'italic'), background=UI_COLORS['BACKGROUND'], foreground=UI_COLORS['TEXT_SECONDARY'])
        style.configure('Action.TButton', font=UI_FONTS['BUTTON'], padding=10)

    def create_ui(self):
        """Create the user interface elements."""
        frame = ttk.Frame(self, padding=20, style='TFrame')
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"Change password for {self.role.title()}", style='Label.TLabel').pack(anchor=tk.W, pady=(0, 10))

        # Create password entry fields
        self.current_entry = self._add_password_entry(frame, "Current Password", self.current_password, show='*')
        self.new_entry = self._add_password_entry(frame, "New Password", self.new_password, show='*')
        self.confirm_entry = self._add_password_entry(frame, "Confirm New Password", self.confirm_password, show='*')

        # Error message label
        self.error_label = ttk.Label(frame, text="", style='Error.TLabel')
        self.error_label.pack(pady=(5, 10))

        # Action buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="Cancel", command=self.cancel, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Save", command=self.change_password, style='Action.TButton').pack(side=tk.RIGHT, padx=10)

    def _add_password_entry(self, parent, label_text, variable, show=''):
        """
        Add a password entry field with label and hint.
        
        Args:
            parent: Parent widget
            label_text: Label text for the field
            variable: StringVar to store the value
            show: Character to show instead of actual input (for masking)
            
        Returns:
            The created entry widget
        """
        # Container frame
        container = ttk.Frame(parent)
        container.pack(fill=tk.X, pady=(10, 0))
        
        # Label
        ttk.Label(container, text=label_text, style='Label.TLabel').pack(anchor=tk.W)
        
        # Entry
        entry = ttk.Entry(container, textvariable=variable, show=show, font=('Helvetica', 14))
        entry.pack(fill=tk.X, pady=(5, 0))
        
        # Hint label
        ttk.Label(container, text="Tap to show keypad", style='Hint.TLabel').pack(anchor=tk.W, pady=(2, 0))
        
        # Bind click to show keypad
        entry.bind("<Button-1>", lambda e, v=variable, t=label_text: self.show_keypad(e, v, t))
        
        return entry

    def show_keypad(self, event, variable, title):
        """
        Show numeric keypad for password entry.
        
        Args:
            event: Event data
            variable: StringVar to bind to keypad
            title: Keypad title
        """
        if not self._keypad_open:
            self._keypad_open = True
            
            def on_close(value):
                self._keypad_open = False
                
                # Set focus to next field if appropriate
                widget = event.widget
                if widget == self.current_entry and value:
                    self.new_entry.focus_set()
                elif widget == self.new_entry and value:
                    self.confirm_entry.focus_set()
                elif widget == self.confirm_entry and value:
                    self.after(100, self.change_password)
            
            AlphanumericKeyboard(
                self,
                variable,
                title=f"Enter {title}",
                password_mode=title.lower().endswith("password"),
                callback=on_close
            )

    def cancel(self, event=None):
        """
        Cancel password change and close dialog.
        
        Args:
            event: Event data (not used)
        """
        self.destroy()
        if self.on_cancel:
            self.on_cancel()

    def change_password(self):
        """Validate inputs and change password if valid."""
        current = self.current_password.get()
        new = self.new_password.get()
        confirm = self.confirm_password.get()

        # Validate inputs
        if not current:
            self.error_label.config(text="Please enter your current password.")
            self.current_entry.focus_set()
            return
            
        if not new:
            self.error_label.config(text="Please enter a new password.")
            self.new_entry.focus_set()
            return
            
        if new != confirm:
            self.error_label.config(text="New passwords do not match.")
            self.confirm_password.set("")
            self.confirm_entry.focus_set()
            return

        if len(new) < 4:
            self.error_label.config(text="Password must be at least 4 characters.")
            self.new_entry.focus_set()
            return

        # Attempt to change password
        if self.role_manager.change_password(self.role, current, new):
            self.destroy()
            if self.on_success:
                self.on_success()
        else:
            self.error_label.config(text="Current password is incorrect.")
            self.current_password.set("")
            self.current_entry.focus_set()