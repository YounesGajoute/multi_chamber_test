# -*- coding: utf-8 -*-
"""
User Management Section for the Settings Tab in Multi-Chamber Test application.

This module provides the UserSection class that implements a section for
managing user accounts, changing passwords, and configuring user permissions.

FIXED ISSUES:
1. Fixed alphanumeric keyboard callback handling
2. Fixed variable scope issues in dialog callbacks
3. Improved error handling for keyboard input
4. Added proper dialog focus management
5. CLEANED: Removed duplicate login policy functionality (moved to General Settings)
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS
from multi_chamber_test.ui.settings.base_section import BaseSection
from multi_chamber_test.ui.keypad import show_numeric_keypad, show_alphanumeric_keyboard


class UserSection(BaseSection):
    """
    User management section for the Settings Tab.
    
    This class implements a UI section for user management tasks like:
    - Changing own password
    - Managing user accounts
    - Configuring user permissions and tab access
    """
    
    def __init__(self, parent, role_manager=None):
        """
        Initialize the User Management section.
        """
        # Get role manager - required for user management
        if role_manager is None:
            from multi_chamber_test.core.roles import get_role_manager
            self.role_manager = get_role_manager()
        else:
            self.role_manager = role_manager

        # User management state
        self.selected_user = tk.StringVar()
        self.selected_role = tk.StringVar()
        self.user_list = []
    
        super().__init__(parent)
    
    def create_widgets(self):
        """Create UI widgets for the user management section."""
        # Section title with icon
        title_frame = ttk.Frame(self.content_frame, style='Content.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(
            title_frame,
            text="User Management",
            style='ContentTitle.TLabel'
        ).pack(anchor=tk.W)
 
        # Create user management cards
        self._create_user_info_card()
        self._create_user_management_section()
        self._create_permissions_section()
        self._create_database_management_section()

    def _create_user_info_card(self):
        """Create the user information card with password management."""
        # Create a styled card
        card, content = self.create_card(
            "User Information",
            "Information about the current user and password management."
        )
        
        # Current user and role display
        info_frame = ttk.Frame(content, style='Card.TFrame')
        info_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            info_frame,
            text="Current User:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(side=tk.LEFT)
        
        # Get current user and role
        current_user = self.role_manager.get_current_username() or "Not logged in"
        try:
            from multi_chamber_test.core.roles import get_current_role
            current_role = get_current_role()
        except ImportError:
            current_role = "ADMIN"  # Default role when no role system
        
        ttk.Label(
            info_frame,
            text=f"{current_user} ({current_role})",
            font=UI_FONTS.get('VALUE', ('Helvetica', 12, 'bold')),
            foreground=UI_COLORS.get('PRIMARY', 'blue')
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Change password button
        button_frame = ttk.Frame(content, style='Card.TFrame')
        button_frame.pack(fill=tk.X, pady=10)
        
        change_button = ttk.Button(
            button_frame,
            text="Change Password",
            command=self._change_own_password,
            padding=10
        )
        change_button.pack(side=tk.LEFT)
        
        # Disable button if not logged in
        if current_user == "Not logged in":
            change_button.config(state='disabled')
            ttk.Label(
                button_frame,
                text="You must be logged in to change your password",
                font=('Helvetica', 10, 'italic'),
                foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
            ).pack(side=tk.LEFT, padx=(10, 0))
    
    def _create_user_management_section(self):
        """Create the user management section."""
        # Create a styled card
        card, content = self.create_card(
            "User Account Management",
            "Create, edit, and delete user accounts."
        )
        
        # User list box
        list_frame = ttk.Frame(content, style='Card.TFrame')
        list_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            list_frame,
            text="User Accounts:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        # Create a frame with listbox and scrollbar
        user_list_frame = ttk.Frame(list_frame)
        user_list_frame.pack(fill=tk.BOTH, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(user_list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox
        self.user_listbox = tk.Listbox(
            user_list_frame,
            height=6,
            width=40,
            font=UI_FONTS.get('LABEL', ('Helvetica', 12)),
            selectmode=tk.SINGLE,
            yscrollcommand=scrollbar.set
        )
        self.user_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.user_listbox.yview)
        
        # Bind selection event
        self.user_listbox.bind('<<ListboxSelect>>', self._on_user_selected)
        
        # Action buttons
        button_frame = ttk.Frame(content, style='Card.TFrame')
        button_frame.pack(fill=tk.X, pady=10)
        
        # New user button
        ttk.Button(
            button_frame,
            text="New User",
            command=self._show_new_user_dialog,
            padding=10
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Edit user button (initially disabled)
        self.edit_button = ttk.Button(
            button_frame,
            text="Edit User",
            command=self._show_edit_user_dialog,
            padding=10,
            state='disabled'
        )
        self.edit_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Delete user button (initially disabled)
        self.delete_button = ttk.Button(
            button_frame,
            text="Delete User",
            command=self._delete_user,
            padding=10,
            state='disabled'
        )
        self.delete_button.pack(side=tk.LEFT)

    def _create_database_management_section(self):
        """Create the database management section."""
        # Create a styled card
        card, content = self.create_card(
            "Database Management",
            "Create backups and restore the user database."
        )
        
        # Backup button
        backup_frame = ttk.Frame(content, style='Card.TFrame')
        backup_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            backup_frame,
            text="Create Database Backup",
            command=self._create_backup,
            padding=10
        ).pack(side=tk.LEFT)
        
        ttk.Label(
            backup_frame,
            text="Create a backup of the user database",
            font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Restore button
        restore_frame = ttk.Frame(content, style='Card.TFrame')
        restore_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            restore_frame,
            text="Restore from Backup",
            command=self._show_restore_dialog,
            padding=10
        ).pack(side=tk.LEFT)
        
        ttk.Label(
            restore_frame,
            text="Restore the user database from a backup file",
            font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        ).pack(side=tk.LEFT, padx=(10, 0))
    
    def _show_restore_dialog(self):
        """Show dialog to select and restore a backup file."""
        try:
            # Show file dialog to select backup file
            backup_file = filedialog.askopenfilename(
                title="Select Backup File",
                filetypes=[("Database Backups", "*.bak"), ("All Files", "*.*")]
            )
            
            if not backup_file:
                return  # User canceled
                
            # Confirm restoration
            if not messagebox.askyesno(
                "Confirm Restore",
                f"Are you sure you want to restore from the selected backup?\n\n"
                f"File: {os.path.basename(backup_file)}\n\n"
                f"This will replace the current user database and cannot be undone."
            ):
                return
                
            # Attempt to restore from backup directly
            try:
                import shutil
                
                # Verify backup file exists
                if not os.path.exists(backup_file):
                    self.show_feedback("Backup file not found", is_error=True)
                    return
                
                # Create a backup of current database before restore
                current_backup = f"{self.role_manager.user_db.db_path}.pre_restore.bak"
                try:
                    shutil.copy2(self.role_manager.user_db.db_path, current_backup)
                    if hasattr(self, 'logger'):
                        self.logger.info(f"Created backup of current database: {current_backup}")
                except Exception as e:
                    if hasattr(self, 'logger'):
                        self.logger.warning(f"Could not backup current database: {e}")
                
                # Restore from backup
                shutil.copy2(backup_file, self.role_manager.user_db.db_path)
                
                self.show_feedback("Database successfully restored from backup")
                self.load_users()  # Refresh user list
                
            except Exception as restore_error:
                self.show_feedback(f"Failed to restore from backup: {str(restore_error)}", is_error=True)
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error in restore dialog: {e}")
            self.show_feedback(f"Error: {str(e)}", is_error=True)
    
    def _show_keypad_for_input(self, variable, title, is_password=False, dialog_parent=None):
        """
        Show alphanumeric keypad for input with proper dialog handling.
        
        Args:
            variable: The tkinter variable to update
            title: Title for the keypad dialog
            is_password: Whether this is password input
            dialog_parent: Parent dialog window (for proper modal handling)
        """
        # Use the dialog as parent if provided, otherwise use main parent
        parent_window = dialog_parent if dialog_parent else self.parent
        
        def on_input_complete(text):
            """Callback when keypad input is complete."""
            if text is not None:  # Only update if not cancelled
                variable.set(text)
                # Restore focus to parent dialog if it exists
                if dialog_parent:
                    dialog_parent.focus_set()
                    dialog_parent.lift()
        
        try:
            show_alphanumeric_keyboard(
                parent_window,
                variable,
                title,
                max_length=100 if is_password else 50,
                password_mode=is_password,
                callback=on_input_complete
            )
        except Exception as e:
            # Log error and show fallback
            if hasattr(self, 'logger'):
                self.logger.error(f"Error showing keypad: {e}")
            messagebox.showerror("Error", f"Could not show keypad: {str(e)}")
    
    def _change_own_password(self):
        """Show dialog to change current user's password."""
        current_user = self.role_manager.get_current_username()
        
        if not current_user or current_user == "Not logged in":
            self.show_feedback("You must be logged in to change your password", is_error=True)
            return
        
        # Create password change dialog
        self._show_password_change_dialog(current_user)
    
    def _show_password_change_dialog(self, username: str):
        """Show dialog to change password for a user."""
        # Create dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title(f"Change Password: {username}")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Set size and position
        dialog.geometry("400x300")
        
        # Style
        dialog.configure(bg=UI_COLORS.get('BACKGROUND', '#FFFFFF'))
        
        # Create content frame
        content = ttk.Frame(dialog, padding=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Current password field
        current_frame = ttk.Frame(content)
        current_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            current_frame,
            text="Current Password:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        current_var = tk.StringVar()
        current_entry = ttk.Entry(
            current_frame,
            textvariable=current_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30,
            show="*"
        )
        current_entry.pack(fill=tk.X, pady=5)
        
        # New password field
        new_frame = ttk.Frame(content)
        new_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            new_frame,
            text="New Password:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        new_var = tk.StringVar()
        new_entry = ttk.Entry(
            new_frame,
            textvariable=new_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30,
            show="*"
        )
        new_entry.pack(fill=tk.X, pady=5)
        
        # Confirm password field
        confirm_frame = ttk.Frame(content)
        confirm_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            confirm_frame,
            text="Confirm New Password:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        confirm_var = tk.StringVar()
        confirm_entry = ttk.Entry(
            confirm_frame,
            textvariable=confirm_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30,
            show="*"
        )
        confirm_entry.pack(fill=tk.X, pady=5)
        
        # Status message
        status_var = tk.StringVar()
        status_label = ttk.Label(
            content,
            textvariable=status_var,
            font=UI_FONTS.get('LABEL', ('Helvetica', 12)),
            foreground=UI_COLORS.get('ERROR', 'red')
        )
        status_label.pack(fill=tk.X, pady=10)
        
        # Buttons
        button_frame = ttk.Frame(content)
        button_frame.pack(fill=tk.X, pady=10)
        
        # Change password function
        def change_password():
            current = current_var.get()
            new = new_var.get()
            confirm = confirm_var.get()
            
            # Validate
            if not current:
                status_var.set("Current password is required")
                return
                
            if not new:
                status_var.set("New password is required")
                return
                
            if len(new) < 4:
                status_var.set("New password must be at least 4 characters")
                return
                
            if new != confirm:
                status_var.set("New passwords do not match")
                return
            
            # Verify current password
            if not self.role_manager.authenticate_user(username, current):
                status_var.set("Current password is incorrect")
                return
                
            # Attempt to change password
            try:
                success = self.role_manager.reset_user_password(username, new)
                if success:
                    dialog.destroy()
                    self.show_feedback("Password changed successfully")
                else:
                    status_var.set("Failed to change password. Database error occurred.")
            except Exception as e:
                status_var.set(f"Error: {str(e)}")
        
        # Cancel button
        ttk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            padding=10
        ).pack(side=tk.LEFT)
        
        # Change button
        ttk.Button(
            button_frame,
            text="Change Password",
            command=change_password,
            padding=10
        ).pack(side=tk.RIGHT)
        
        # Focus current password field
        current_entry.focus_set()
    
    def _on_user_selected(self, event):
        """Handle user selection in listbox."""
        selection = self.user_listbox.curselection()
        if not selection:
            # Nothing selected
            self.selected_user.set("")
            self.selected_role.set("")
            self.edit_button.config(state='disabled')
            self.delete_button.config(state='disabled')
            return
        
        # Get selected user
        index = selection[0]
        if index < len(self.user_list):
            username, role = self.user_list[index]
            self.selected_user.set(username)
            self.selected_role.set(role)
            
            # Enable buttons
            self.edit_button.config(state='normal')
            self.delete_button.config(state='normal')
    
    def _show_new_user_dialog(self):
        """Show dialog to create a new user with alphanumeric keypad support."""
        # Create dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title("Create New User")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Set size and position
        dialog.geometry("650x650")  # Increased height for ID number field
        
        # Style
        dialog.configure(bg=UI_COLORS.get('BACKGROUND', '#FFFFFF'))
        
        # Create content frame
        content = ttk.Frame(dialog, padding=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Username field with keypad button
        username_frame = ttk.Frame(content)
        username_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            username_frame,
            text="Username:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        username_input_frame = ttk.Frame(username_frame)
        username_input_frame.pack(fill=tk.X, pady=5)
        
        username_var = tk.StringVar()
        username_entry = ttk.Entry(
            username_input_frame,
            textvariable=username_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30
        )
        username_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        username_keypad_btn = ttk.Button(
            username_input_frame,
            text="KB",
            width=3,
            command=lambda: self._show_keypad_for_input(
                username_var, "Username", is_password=False, dialog_parent=dialog
            )
        )
        username_keypad_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # ID number field with keypad button
        id_number_frame = ttk.Frame(content)
        id_number_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            id_number_frame,
            text="ID Number:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        id_input_frame = ttk.Frame(id_number_frame)
        id_input_frame.pack(fill=tk.X, pady=5)
        
        id_number_var = tk.StringVar()
        id_number_entry = ttk.Entry(
            id_input_frame,
            textvariable=id_number_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30
        )
        id_number_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        id_keypad_btn = ttk.Button(
            id_input_frame,
            text="KB",
            width=3,
            command=lambda: self._show_keypad_for_input(
                id_number_var, "ID Number", is_password=False, dialog_parent=dialog
            )
        )
        id_keypad_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Password field with keypad button
        password_frame = ttk.Frame(content)
        password_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            password_frame,
            text="Password:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        password_input_frame = ttk.Frame(password_frame)
        password_input_frame.pack(fill=tk.X, pady=5)
        
        password_var = tk.StringVar()
        password_entry = ttk.Entry(
            password_input_frame,
            textvariable=password_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30,
            show="*"
        )
        password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        password_keypad_btn = ttk.Button(
            password_input_frame,
            text="KB",
            width=3,
            command=lambda: self._show_keypad_for_input(
                password_var, "Password", is_password=True, dialog_parent=dialog
            )
        )
        password_keypad_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Confirm password field with keypad button
        confirm_frame = ttk.Frame(content)
        confirm_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            confirm_frame,
            text="Confirm Password:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        confirm_input_frame = ttk.Frame(confirm_frame)
        confirm_input_frame.pack(fill=tk.X, pady=5)
        
        confirm_var = tk.StringVar()
        confirm_entry = ttk.Entry(
            confirm_input_frame,
            textvariable=confirm_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30,
            show="*"
        )
        confirm_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        confirm_keypad_btn = ttk.Button(
            confirm_input_frame,
            text="KB",
            width=3,
            command=lambda: self._show_keypad_for_input(
                confirm_var, "Confirm Password", is_password=True, dialog_parent=dialog
            )
        )
        confirm_keypad_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Role selection
        role_frame = ttk.Frame(content)
        role_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            role_frame,
            text="Role:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        role_var = tk.StringVar(value="OPERATOR")
        
        # Get available roles from role manager
        available_roles = self.role_manager.get_available_roles()
        
        role_dropdown = ttk.Combobox(
            role_frame,
            textvariable=role_var,
            values=available_roles,
            state="readonly",
            font=UI_FONTS.get('VALUE', ('Helvetica', 12))
        )
        role_dropdown.pack(fill=tk.X, pady=5)
        
        # Status message
        status_var = tk.StringVar()
        status_label = ttk.Label(
            content,
            textvariable=status_var,
            font=UI_FONTS.get('LABEL', ('Helvetica', 12)),
            foreground=UI_COLORS.get('ERROR', 'red')
        )
        status_label.pack(fill=tk.X, pady=10)
        
        # Buttons
        button_frame = ttk.Frame(content)
        button_frame.pack(fill=tk.X, pady=10)
        
        # Create user function
        def create_user():
            username = username_var.get().strip()
            password = password_var.get().strip()
            id_number = id_number_var.get().strip()  # Get the ID number from the form
            confirm = confirm_var.get().strip()
            role = role_var.get()
            
            # Validate
            if not username:
                status_var.set("Username is required")
                return
            
            if not id_number:
                status_var.set("ID number is required")
                return
                
            if not password:
                status_var.set("Password is required")
                return
                
            if len(password) < 4:
                status_var.set("Password must be at least 4 characters")
                return
                
            if password != confirm:
                status_var.set("Passwords do not match")
                return
                
            # Attempt to create user with the provided ID number
            try:
                # FIXED: Pass the id_number parameter to create_user
                success, error_message = self.role_manager.create_user(username, password, role, id_number)
                if success:
                    dialog.destroy()
                    self.show_feedback(f"User '{username}' created successfully with ID '{id_number}'")
                    self.load_users()  # Refresh user list
                else:
                    status_var.set(f"Failed to create user: {error_message}")
            except Exception as e:
                status_var.set(f"Error: {str(e)}")
        
        # Cancel button
        ttk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            padding=10
        ).pack(side=tk.LEFT)
        
        # Create button
        ttk.Button(
            button_frame,
            text="Create User",
            command=create_user,
            padding=10
        ).pack(side=tk.RIGHT)
        
        # Focus username field
        username_entry.focus_set()
     
    def _show_edit_user_dialog(self):
        """Show dialog to edit a user with alphanumeric keypad support."""
        username = self.selected_user.get()
        role = self.selected_role.get()
        
        if not username:
            return
            
        # Try to get user info with ID number
        user_info = None
        id_number = ""
        if hasattr(self.role_manager, 'get_user_info'):
            try:
                user_info = self.role_manager.get_user_info(username)
                if user_info and 'id_number' in user_info:
                    id_number = user_info['id_number']
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"Error getting user info: {e}")
        
        # Create dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title(f"Edit User: {username}")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Set size and position
        dialog.geometry("450x450")  # Increased for ID number field
        
        # Style
        dialog.configure(bg=UI_COLORS.get('BACKGROUND', '#FFFFFF'))
        
        # Create content frame
        content = ttk.Frame(dialog, padding=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # User info
        info_frame = ttk.Frame(content)
        info_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            info_frame,
            text=f"Editing User: {username}",
            font=UI_FONTS.get('SUBHEADER', ('Helvetica', 14, 'bold')),
            foreground=UI_COLORS.get('PRIMARY', 'blue')
        ).pack(anchor=tk.W)
        
        ttk.Label(
            info_frame,
            text=f"Current Role: {role}",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W, pady=(5, 0))
        
        # ID number field with keypad button
        id_number_frame = ttk.Frame(content)
        id_number_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            id_number_frame,
            text="ID Number:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        id_input_frame = ttk.Frame(id_number_frame)
        id_input_frame.pack(fill=tk.X, pady=5)
        
        id_number_var = tk.StringVar(value=id_number)
        id_number_entry = ttk.Entry(
            id_input_frame,
            textvariable=id_number_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30
        )
        id_number_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        id_keypad_btn = ttk.Button(
            id_input_frame,
            text="KB",
            width=3,
            command=lambda: self._show_keypad_for_input(
                id_number_var, "ID Number", is_password=False, dialog_parent=dialog
            )
        )
        id_keypad_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # New role selection
        role_frame = ttk.Frame(content)
        role_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(
            role_frame,
            text="New Role:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        new_role_var = tk.StringVar(value=role)
        
        # Get available roles
        available_roles = self.role_manager.get_available_roles()
        
        role_dropdown = ttk.Combobox(
            role_frame,
            textvariable=new_role_var,
            values=available_roles,
            state="readonly",
            font=UI_FONTS.get('VALUE', ('Helvetica', 12))
        )
        role_dropdown.pack(fill=tk.X, pady=5)
        
        # Reset password option
        reset_frame = ttk.Frame(content)
        reset_frame.pack(fill=tk.X, pady=10)
        
        reset_var = tk.BooleanVar(value=False)
        reset_check = ttk.Checkbutton(
            reset_frame,
            text="Reset Password",
            variable=reset_var
        )
        reset_check.pack(anchor=tk.W)
        
        # New password field (initially hidden)
        password_frame = ttk.Frame(content)
        password_frame.pack(fill=tk.X, pady=10)
        password_frame.pack_forget()  # Hide initially
        
        ttk.Label(
            password_frame,
            text="New Password:",
            font=UI_FONTS.get('LABEL', ('Helvetica', 12))
        ).pack(anchor=tk.W)
        
        password_input_frame = ttk.Frame(password_frame)
        password_input_frame.pack(fill=tk.X, pady=5)
        
        password_var = tk.StringVar()
        password_entry = ttk.Entry(
            password_input_frame,
            textvariable=password_var,
            font=UI_FONTS.get('VALUE', ('Helvetica', 12)),
            width=30,
            show="*"
        )
        password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        password_keypad_btn = ttk.Button(
            password_input_frame,
            text="KB",
            width=3,
            command=lambda: self._show_keypad_for_input(
                password_var, "New Password", is_password=True, dialog_parent=dialog
            )
        )
        password_keypad_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Show/hide password field based on checkbox
        def toggle_password_field(*args):
            if reset_var.get():
                password_frame.pack(fill=tk.X, pady=10)
            else:
                password_frame.pack_forget()
                
        reset_var.trace_add("write", toggle_password_field)
        
        # Status message
        status_var = tk.StringVar()
        status_label = ttk.Label(
            content,
            textvariable=status_var,
            font=UI_FONTS.get('LABEL', ('Helvetica', 12)),
            foreground=UI_COLORS.get('ERROR', 'red')
        )
        status_label.pack(fill=tk.X, pady=10)
        
        # Buttons
        button_frame = ttk.Frame(content)
        button_frame.pack(fill=tk.X, pady=10)
        
        # Update user function
        def update_user():
            new_role = new_role_var.get()
            new_id_number = id_number_var.get().strip()
            reset_password = reset_var.get()
            new_password = password_var.get().strip() if reset_password else None
            
            # Validate
            if not new_id_number:
                status_var.set("ID number is required")
                return
                
            if reset_password and (not new_password or len(new_password) < 4):
                status_var.set("New password must be at least 4 characters")
                return
            
            # Update role if changed
            role_updated = False
            if new_role != role:
                try:
                    success = self.role_manager.set_user_role(username, new_role)
                    if success:
                        role_updated = True
                    else:
                        status_var.set("Failed to update role")
                        return
                except Exception as e:
                    status_var.set(f"Error updating role: {str(e)}")
                    return
            
            # Reset password if requested
            password_updated = False
            if reset_password and new_password:
                try:
                    success = self.role_manager.reset_user_password(username, new_password)
                    if success:
                        password_updated = True
                    else:
                        status_var.set("Failed to reset password")
                        return
                except Exception as e:
                    status_var.set(f"Error resetting password: {str(e)}")
                    return
            
            # If we got here, everything succeeded
            dialog.destroy()
            
            # Show appropriate feedback
            if role_updated and password_updated:
                self.show_feedback(f"User '{username}' role and password updated")
            elif role_updated:
                self.show_feedback(f"User '{username}' role updated to {new_role}")
            elif password_updated:
                self.show_feedback(f"User '{username}' password reset")
            else:
                self.show_feedback(f"User '{username}' information updated")
                
            # Refresh user list
            self.load_users()
        
        # Cancel button
        ttk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            padding=10
        ).pack(side=tk.LEFT)
        
        # Update button
        ttk.Button(
            button_frame,
            text="Update User",
            command=update_user,
            padding=10
        ).pack(side=tk.RIGHT)
    
    def _delete_user(self):
        """Delete the selected user."""
        username = self.selected_user.get()
        
        if not username:
            return
            
        # Confirm deletion
        if not messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete user '{username}'?\n\nThis cannot be undone."
        ):
            return
        
        # Check if deleting current user
        current_user = self.role_manager.get_current_username()
        if username == current_user:
            messagebox.showerror(
                "Error",
                "You cannot delete your own account while logged in."
            )
            return
        
        # Attempt to delete user
        try:
            success = self.role_manager.delete_user(username)
            if success:
                self.show_feedback(f"User '{username}' deleted successfully")
                self.load_users()  # Refresh user list
                
                # Clear selection
                self.selected_user.set("")
                self.selected_role.set("")
                self.edit_button.config(state='disabled')
                self.delete_button.config(state='disabled')
            else:
                self.show_feedback(f"Failed to delete user '{username}'", is_error=True)
        except Exception as e:
            self.show_feedback(f"Error deleting user: {str(e)}", is_error=True)
    
    def _create_backup(self):
        """Create a backup of the user database."""
        try:
            backup_path = self.role_manager.create_database_backup()
            if backup_path:
                self.show_feedback(f"Backup created: {os.path.basename(backup_path)}")
            else:
                self.show_feedback("Failed to create backup", is_error=True)
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error creating backup: {e}")
            self.show_feedback(f"Error: {str(e)}", is_error=True)
    
    def load_users(self):
        """Load user list from user database."""
        try:
            # Clear existing list
            if hasattr(self, 'user_listbox'):
                self.user_listbox.delete(0, tk.END)
            else:
                return
                
            # Get users from the role manager
            users = self.role_manager.get_all_users()
            
            # Store user list for reference
            self.user_list = users
            
            # Update listbox
            for username, role in self.user_list:
                self.user_listbox.insert(tk.END, f"{username} ({role})")
            
            if hasattr(self, 'logger'):
                self.logger.info(f"Loaded {len(self.user_list)} users")
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error loading users: {e}")
            self.show_feedback(f"Error loading users: {str(e)}", is_error=True)
    
    def refresh_all(self):
        """Refresh all UI components."""
        # Load users - this is the main function of this section
        self.load_users()
    
    def on_selected(self):
        """Called when section is selected."""
        super().on_selected()
        self.refresh_all()
        
    def on_deselected(self):
        """Called when section is deselected."""
        # Remove mousewheel binding when leaving this section
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        return super().on_deselected()
        
    def _create_permissions_section(self):
        """Create the simplified permissions management section focusing only on tab access."""
        # Create a styled card
        card, content = self.create_card(
            "Tab Access Control",
            "Configure which roles can access which tabs."
        )
    
        # Create a tabbed interface for different roles
        role_notebook = ttk.Notebook(content)
        role_notebook.pack(fill=tk.BOTH, expand=True, pady=10)
    
        # Role definitions
        roles = ["OPERATOR", "MAINTENANCE", "ADMIN"]
        self.tab_access_vars = {}
    
        for role in roles:
            # Tab frame
            tab_frame = ttk.Frame(role_notebook)
            role_notebook.add(tab_frame, text=role)
    
            # Canvas and scrollbar for scrollable permissions list
            canvas = tk.Canvas(tab_frame, background=UI_COLORS.get("BACKGROUND", "#FFFFFF"), highlightthickness=0)
            scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
    
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
            # Scrollable frame inside canvas
            scrollable_frame = ttk.Frame(canvas, style='Card.TFrame')
            canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    
            def _resize_scrollregion(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfig(canvas_window, width=event.width)
    
            scrollable_frame.bind("<Configure>", _resize_scrollregion)
            canvas.bind("<Configure>", _resize_scrollregion)
    
            # Add description
            ttk.Label(
                scrollable_frame,
                text=f"Configure tab access for the {role} role:",
                font=UI_FONTS.get('LABEL', ('Helvetica', 12, 'bold')),
                wraplength=500
            ).pack(anchor=tk.W, pady=(0, 10))
    
            # Add tab access checkboxes
            self._create_tab_access_checkboxes(scrollable_frame, role)
    
        # Save button below the notebook
        save_frame = ttk.Frame(content, style='Card.TFrame')
        save_frame.pack(fill=tk.X, pady=10)
    
        ttk.Button(
            save_frame,
            text="Save Tab Access Settings",
            command=self._save_tab_access,
            padding=10
        ).pack(side=tk.RIGHT)
        
    def _create_tab_access_checkboxes(self, parent, role):
        """Create tab access checkboxes for a specific role."""
        # Define available tabs
        tabs = [
            {"id": "login", "label": "Login Tab"},
            {"id": "main", "label": "Main Tab"},
            {"id": "settings", "label": "Settings Tab"},
            {"id": "calibration", "label": "Calibration Tab"},
            {"id": "reference", "label": "Reference Tab"}
        ]
        
        # Current tab access for this role (would be loaded from permission_manager)
        current_access = self._get_role_tab_access(role)
        
        # Create tab access variables dictionary
        self.tab_access_vars = self.tab_access_vars if hasattr(self, 'tab_access_vars') else {}
        if role not in self.tab_access_vars:
            self.tab_access_vars[role] = {}
        
        # Create UI for tab access
        # Tab access frame
        access_frame = ttk.LabelFrame(parent, text="Tab Access", padding=10)
        access_frame.pack(fill=tk.X, pady=5)
        
        # Create checkboxes for each tab
        for tab in tabs:
            tab_id = tab["id"]
            is_enabled = tab_id in current_access
            
            # Create variable if not exists
            if tab_id not in self.tab_access_vars[role]:
                self.tab_access_vars[role][tab_id] = tk.BooleanVar(value=is_enabled)
            else:
                self.tab_access_vars[role][tab_id].set(is_enabled)
            
            # Create checkbox
            checkbox = ttk.Checkbutton(
                access_frame,
                text=tab["label"],
                variable=self.tab_access_vars[role][tab_id]
            )
            
            # Disable certain checkboxes to enforce role hierarchy
            # OPERATOR always has access to login and main
            if role == "OPERATOR" and tab_id in ["login", "main"]:
                checkbox.config(state='disabled')
                self.tab_access_vars[role][tab_id].set(True)
            
            # MAINTENANCE always has access to login and main
            if role == "MAINTENANCE" and tab_id in ["login", "main"]:
                checkbox.config(state='disabled')
                self.tab_access_vars[role][tab_id].set(True)
            
            # ADMIN has access to everything and can't be changed
            if role == "ADMIN":
                checkbox.config(state='disabled')
                self.tab_access_vars[role][tab_id].set(True)
            
            checkbox.pack(anchor=tk.W, pady=2)
    
    def _get_role_tab_access(self, role):
        """Get current tab access for a role."""
        # Default tab access based on role
        default_access = {
            "OPERATOR": ["login", "main"],
            "MAINTENANCE": ["login", "main", "settings", "calibration", "reference"],
            "ADMIN": ["login", "main", "settings", "calibration", "reference"]
        }
        
        # Try to get from permission_manager if available
        try:
            # This assumes your permission_manager has a get_role_tab_access function
            # If it doesn't, we'll use the default permissions
            if hasattr(self.role_manager, 'get_role_tab_access'):
                return self.role_manager.get_role_tab_access(role)
            else:
                return default_access.get(role, [])
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error getting tab access for {role}: {e}")
            return default_access.get(role, [])
    
    def _save_tab_access(self):
        """Save role tab access settings."""
        try:
            roles_updated = []
            
            # For each role, collect enabled tabs
            for role, tabs in self.tab_access_vars.items():
                enabled_tabs = []
                
                # Collect all enabled tabs
                for tab_id, var in tabs.items():
                    if var.get():
                        enabled_tabs.append(tab_id)
                
                # Save to permission_manager if it has the method
                if hasattr(self.role_manager, 'set_role_tab_access'):
                    if self.role_manager.set_role_tab_access(role, enabled_tabs):
                        roles_updated.append(role)
            
            # Show success feedback
            if roles_updated:
                self.show_feedback(f"Updated tab access for roles: {', '.join(roles_updated)}")
            else:
                self.show_feedback("No tab access changes were saved", is_error=True)
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error saving tab access: {e}")
            self.show_feedback(f"Error saving tab access: {str(e)}", is_error=True)

    def cleanup(self):
        """Clean up resources when the section is destroyed."""
        # Remove mousewheel binding
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        super().cleanup()