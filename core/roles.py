#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced Role Manager module for the Multi-Chamber Test application.

This module provides role-based access control functionality with database-backed
permissions storage, ensuring proper handling of USER_ROLES structure while
maintaining backward compatibility.

CORRECTED VERSION - Fixes ID number saving issues
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
import hashlib
import time

from multi_chamber_test.config.constants import USER_ROLES
from multi_chamber_test.database.user_db import UserDB

class RoleManager:
    """
    Enhanced manager for role-based access control with database-backed permissions.
    
    This class manages user authentication, role permissions, and tab access control
    for the Multi-Chamber Test application, with permissions stored in the database.
    
    CORRECTED VERSION - Fixes ID number management issues
    """
    
    def __init__(self):
        self.logger = logging.getLogger('RoleManager')
        self._setup_logger()
        self.user_db = UserDB()

        self.current_role = "OPERATOR"
        self.current_username = None
        self.authenticated = False
        self.last_auth_time = 0
        self.session_timeout = 600  # seconds (10 minutes)
        
        # Settings for the "require login" feature
        self.require_login = False
        self.default_role = "OPERATOR"
        
        # Cache for role permissions (refreshed as needed)
        self._role_permissions_cache = {}
        self._refresh_role_permissions()
        
        # Load settings
        self._load_settings()
    
    def _setup_logger(self):
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _refresh_role_permissions(self):
        """Refresh the role permissions cache from the database."""
        try:
            self._role_permissions_cache = self.user_db.get_all_role_permissions()
            self.logger.debug("Role permissions cache refreshed")
        except Exception as e:
            self.logger.error(f"Error refreshing role permissions: {e}")
            # Fall back to USER_ROLES constant if database fails
            self._role_permissions_cache = {}
            for role_name, role_data in USER_ROLES.items():
                self._role_permissions_cache[role_name] = {
                    "level": role_data.get("level", 0),
                    "permissions": role_data.get("permissions", []),
                    "tabs": role_data.get("tabs", [])
                }
            # Add NONE role
            self._role_permissions_cache["NONE"] = {
                "level": 0,
                "permissions": [],
                "tabs": ["login"]
            }
    
    def _load_settings(self):
        """Load authentication settings from SettingsManager if available."""
        try:
            from multi_chamber_test.config.settings import SettingsManager
            settings = SettingsManager()
            
            # Load require_login setting (default to False if not found)
            self.require_login = bool(settings.get_setting('require_login', False))
            
            # Load default_role setting (default to OPERATOR if not found)
            self.default_role = settings.get_setting('default_role', "OPERATOR")
            
            # Load session timeout (default to 10 minutes if not found)
            self.session_timeout = int(settings.get_setting('session_timeout', 600))
            
            self.logger.info(f"Loaded authentication settings: require_login={self.require_login}, default_role={self.default_role}, session_timeout={self.session_timeout}s")
        except Exception as e:
            self.logger.warning(f"Failed to load authentication settings: {e}")
    
    def _validate_id_number(self, id_number: str, username: str = None) -> Tuple[bool, str]:
        """
        Validate ID number format and uniqueness.
        
        Args:
            id_number: ID number to validate
            username: Username (for uniqueness check, can be None for new users)
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if not id_number:
            return False, "ID number cannot be empty"
        
        # Basic format validation
        id_number = id_number.strip()
        if len(id_number) < 3:
            return False, "ID number must be at least 3 characters long"
        
        # Check for invalid characters (optional - adjust as needed)
        if not id_number.replace('-', '').replace('_', '').isalnum():
            return False, "ID number can only contain letters, numbers, hyphens, and underscores"
        
        # Check uniqueness in database
        try:
            existing_users = self.user_db.get_all_users()
            for existing_username, _ in existing_users:
                if existing_username != username:  # Skip the current user when updating
                    existing_user_info = self.user_db.get_user(existing_username)
                    if existing_user_info and existing_user_info.get('id_number') == id_number:
                        return False, f"ID number '{id_number}' is already in use by user '{existing_username}'"
        except Exception as e:
            self.logger.error(f"Error checking ID number uniqueness: {e}")
            return False, "Error validating ID number uniqueness"
        
        return True, ""
    
    def _generate_default_id_number(self, username: str, role: str) -> str:
        """
        Generate a default ID number for a user based on role and username.
        
        Args:
            username: Username
            role: User role
            
        Returns:
            str: Generated ID number
        """
        # Role-based prefixes
        role_prefixes = {
            "ADMIN": "ADM",
            "MAINTENANCE": "MNT", 
            "OPERATOR": "OPR",
            "NONE": "USR"
        }
        
        prefix = role_prefixes.get(role, "USR")
        
        # Try to generate a unique ID number
        for i in range(1, 1000):  # Try up to 999 numbers
            id_number = f"{prefix}{i:03d}"  # e.g., ADM001, OPR042, etc.
            
            # Check if this ID is already in use
            is_valid, _ = self._validate_id_number(id_number)
            if is_valid:
                return id_number
        
        # Fallback: use username with prefix if all numbers are taken
        return f"{prefix}_{username.upper()}"
    
    # ==============================================
    # TAB PERMISSION METHODS (unchanged)
    # ==============================================
    
    def has_tab_access(self, tab_name: str) -> bool:
        """
        Check if the current user has access to a specific tab.
        
        Args:
            tab_name: Name of the tab to check access for
            
        Returns:
            bool: True if user has access to the tab, False otherwise
        """
        current_role = self.get_current_role()
        
        # Get tabs for current role from cache
        role_data = self._role_permissions_cache.get(current_role, {})
        allowed_tabs = role_data.get("tabs", [])
        
        # Refresh from database if empty (first request or cache miss)
        if not allowed_tabs and current_role in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
            role_info = self.user_db.get_role_permissions(current_role)
            if role_info:
                allowed_tabs = role_info.get("tabs", [])
                # Update cache
                if current_role in self._role_permissions_cache:
                    self._role_permissions_cache[current_role]["tabs"] = allowed_tabs
            else:
                # Fall back to USER_ROLES constant
                if current_role in USER_ROLES:
                    allowed_tabs = USER_ROLES[current_role].get("tabs", [])
                elif current_role == "NONE":
                    allowed_tabs = ["login"]
        
        return tab_name in allowed_tabs
    
    def get_accessible_tabs(self, role: Optional[str] = None) -> List[str]:
        """
        Get list of tabs accessible to a role.
        
        Args:
            role: Role to check (or None for current role)
            
        Returns:
            List of accessible tab names
        """
        role = role or self.get_current_role()
        
        # Get tabs from cache
        role_data = self._role_permissions_cache.get(role, {})
        tabs = role_data.get("tabs", [])
        
        # Refresh from database if empty
        if not tabs and role in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
            role_info = self.user_db.get_role_permissions(role)
            if role_info:
                tabs = role_info.get("tabs", [])
                # Update cache
                if role in self._role_permissions_cache:
                    self._role_permissions_cache[role]["tabs"] = tabs
            else:
                # Fall back to USER_ROLES constant
                if role in USER_ROLES:
                    tabs = USER_ROLES[role].get("tabs", [])
                elif role == "NONE":
                    tabs = ["login"]
        
        return tabs
    
    def set_role_tab_access(self, role: str, tab_list: List[str]) -> bool:
        """
        Set which tabs a role can access.
        
        Args:
            role: Role name
            tab_list: List of tab names the role should have access to
            
        Returns:
            bool: True if access was set successfully
        """
        if role not in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
            self.logger.error(f"Invalid role: {role}")
            return False
        
        # Validate tab names
        valid_tabs = ["login", "main", "settings", "calibration", "reference"]
        invalid_tabs = [tab for tab in tab_list if tab not in valid_tabs]
        if invalid_tabs:
            self.logger.error(f"Invalid tab names: {invalid_tabs}")
            return False
        
        # Enforce minimum permissions for certain roles
        if role == "OPERATOR":
            # OPERATOR must always have access to login and main
            required_tabs = ["login", "main"]
            tab_list = list(set(tab_list + required_tabs))
        elif role == "MAINTENANCE":
            # MAINTENANCE must have access to login and main
            required_tabs = ["login", "main"]
            tab_list = list(set(tab_list + required_tabs))
        elif role == "ADMIN":
            # ADMIN gets access to everything by default
            tab_list = valid_tabs
        
        # Get current role data from database
        role_info = self.user_db.get_role_permissions(role)
        
        if role_info:
            # Update existing role's tabs
            level = role_info.get("level", 0)
            permissions = role_info.get("permissions", [])
            
            # Update in database
            success = self.user_db.update_role_permissions(
                role, level=level, permissions=permissions, tabs=tab_list
            )
            
            if success:
                # Update cache
                if role in self._role_permissions_cache:
                    self._role_permissions_cache[role]["tabs"] = tab_list
                else:
                    self._role_permissions_cache[role] = {
                        "level": level,
                        "permissions": permissions,
                        "tabs": tab_list
                    }
                
                self.logger.info(f"Updated tab access for {role}: {tab_list}")
                return True
            else:
                self.logger.error(f"Failed to update tab access for {role}")
                return False
        else:
            # Create new role permission entry
            # Determine appropriate level based on role name
            level = 0
            if role == "OPERATOR":
                level = 1
            elif role == "MAINTENANCE":
                level = 2
            elif role == "ADMIN":
                level = 3
            
            # For new roles, start with empty permissions
            permissions = []
            
            # Create in database
            success = self.user_db.update_role_permissions(
                role, level=level, permissions=permissions, tabs=tab_list
            )
            
            if success:
                # Update cache
                self._role_permissions_cache[role] = {
                    "level": level,
                    "permissions": permissions,
                    "tabs": tab_list
                }
                
                self.logger.info(f"Created new tab access for {role}: {tab_list}")
                return True
            else:
                self.logger.error(f"Failed to create tab access for {role}")
                return False
    
    def get_role_tab_access(self, role: str) -> List[str]:
        """
        Get list of tabs accessible to a specific role.
        
        Args:
            role: Role name
            
        Returns:
            List of accessible tab names
        """
        return self.get_accessible_tabs(role)
    
    # ==============================================
    # AUTHENTICATION METHODS (unchanged for most)
    # ==============================================
    
    def set_require_login(self, required: bool):
        """
        Set whether login is required to use the system.
        
        Args:
            required: Whether login is required
        """
        self.require_login = bool(required)
        self.logger.info(f"Require login set to: {self.require_login}")
        
        # Try to save to settings if possible
        try:
            from multi_chamber_test.config.settings import SettingsManager
            settings = SettingsManager()
            settings.set_setting('require_login', self.require_login)
            settings.save_settings()
        except Exception as e:
            self.logger.warning(f"Could not save require_login setting: {e}")
    
    def get_require_login(self) -> bool:
        """
        Get whether login is required to use the system.
        
        Returns:
            bool: Whether login is required
        """
        return self.require_login
    
    def set_default_role(self, role: str):
        """
        Set the default role when no user is logged in.
        
        Args:
            role: Default role
        """
        if role in ["OPERATOR", "MAINTENANCE", "ADMIN"]:
            self.default_role = role
            self.logger.info(f"Default role set to: {role}")
            
            # Try to save to settings if possible
            try:
                from multi_chamber_test.config.settings import SettingsManager
                settings = SettingsManager()
                settings.set_setting('default_role', self.default_role)
                settings.save_settings()
            except Exception as e:
                self.logger.warning(f"Could not save default_role setting: {e}")
        else:
            self.logger.error(f"Invalid role: {role}")
    
    def get_default_role(self) -> str:
        """
        Get the default role when no user is logged in.
        
        Returns:
            str: Default role
        """
        return self.default_role
    
    def set_session_timeout(self, timeout_seconds: int) -> None:
        """
        Set the session timeout period.
        
        Args:
            timeout_seconds: Session timeout in seconds
        """
        if timeout_seconds < 60:
            self.logger.warning(f"Session timeout too short: {timeout_seconds}s. Using 60s minimum.")
            timeout_seconds = 60
            
        self.session_timeout = timeout_seconds
        self.logger.info(f"Session timeout set to {timeout_seconds}s")
        
        # Try to save to settings if possible
        try:
            from multi_chamber_test.config.settings import SettingsManager
            settings = SettingsManager()
            settings.set_setting('session_timeout', self.session_timeout)
            settings.save_settings()
        except Exception as e:
            self.logger.warning(f"Could not save session_timeout setting: {e}")
    
    def get_session_timeout(self) -> int:
        """
        Get the session timeout period in seconds.
        
        Returns:
            int: Session timeout in seconds
        """
        return self.session_timeout
    
    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """
        Authenticate a user with username and password.
        
        Args:
            username: Username to authenticate
            password: Password to verify
            
        Returns:
            str: Role of authenticated user or None if authentication failed
        """
        role = self.user_db.authenticate_user(username, password)
        if role:
            self.current_role = role
            self.current_username = username
            self.authenticated = True
            self.last_auth_time = time.time()
            self.logger.info(f"Authenticated user '{username}' as {role}")
            return role
        return None
    
    # ==============================================
    # CORRECTED USER MANAGEMENT METHODS
    # ==============================================
    
    def create_user(self, username: str, password: str, role: str, id_number: str = "") -> Tuple[bool, str]:
        """
        Create a new user account with proper ID number handling.
        
        Args:
            username: Username for the new account
            password: Password for the new account
            role: Role to assign to the new user
            id_number: ID number for the user (auto-generated if empty)
            
        Returns:
            Tuple[bool, str]: (success, error_message)
        """
        # Validate basic inputs
        if not username or not password or not role:
            return False, "Username, password, and role are required"
        
        if role not in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
            return False, f"Invalid role: {role}"
        
        # Clean up inputs
        username = username.strip()
        id_number = id_number.strip()
        
        # Handle ID number
        if not id_number:
            # Auto-generate ID number based on role
            id_number = self._generate_default_id_number(username, role)
            self.logger.info(f"Auto-generated ID number '{id_number}' for user '{username}'")
        else:
            # Validate provided ID number
            is_valid, error_msg = self._validate_id_number(id_number, username)
            if not is_valid:
                return False, f"Invalid ID number: {error_msg}"
        
        # Check if username already exists
        existing_user = self.user_db.get_user(username)
        if existing_user:
            return False, f"Username '{username}' already exists"
        
        # Create the user in database
        try:
            success = self.user_db.create_user(username, id_number, password, role)
            if success:
                self.logger.info(f"Successfully created user '{username}' with ID '{id_number}' and role '{role}'")
                return True, ""
            else:
                return False, "Failed to create user in database"
        except Exception as e:
            self.logger.error(f"Error creating user: {e}")
            return False, f"Error creating user: {str(e)}"
    
    def update_user(self, username: str, password: str = None, role: str = None, id_number: str = None) -> Tuple[bool, str]:
        """
        Update an existing user's information.
        
        Args:
            username: Username to update
            password: New password (optional)
            role: New role (optional)
            id_number: New ID number (optional)
            
        Returns:
            Tuple[bool, str]: (success, error_message)
        """
        if not username:
            return False, "Username is required"
        
        # Check if user exists
        existing_user = self.user_db.get_user(username)
        if not existing_user:
            return False, f"User '{username}' not found"
        
        # Validate role if provided
        if role is not None and role not in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
            return False, f"Invalid role: {role}"
        
        # Validate ID number if provided
        if id_number is not None:
            id_number = id_number.strip()
            if id_number:  # Only validate if not empty
                is_valid, error_msg = self._validate_id_number(id_number, username)
                if not is_valid:
                    return False, f"Invalid ID number: {error_msg}"
        
        try:
            # Update password if provided
            if password is not None:
                if not self.user_db.reset_user_password(username, password):
                    return False, "Failed to update password"
            
            # Update role if provided
            if role is not None:
                if not self.user_db.update_user_role(username, role):
                    return False, "Failed to update role"
            
            # Update ID number if provided
            if id_number is not None and hasattr(self.user_db, 'update_user_id_number'):
                if not self.user_db.update_user_id_number(username, id_number):
                    return False, "Failed to update ID number"
            elif id_number is not None:
                # Fallback: recreate user with new ID number
                current_user = self.user_db.get_user(username)
                current_role = role or current_user.get('role', 'OPERATOR')
                current_password = password or "temp_password_needs_reset"
                
                # Delete and recreate (not ideal, but works if update method doesn't exist)
                if self.user_db.delete_user(username):
                    if not self.user_db.create_user(username, id_number, current_password, current_role):
                        return False, "Failed to recreate user with new ID number"
                else:
                    return False, "Failed to update user"
            
            self.logger.info(f"Successfully updated user '{username}'")
            return True, ""
            
        except Exception as e:
            self.logger.error(f"Error updating user: {e}")
            return False, f"Error updating user: {str(e)}"

    def reset_user_password(self, username: str, new_password: str) -> bool:
        """
        Reset a user's password.
        
        Args:
            username: Username to reset password for
            new_password: New password to set
            
        Returns:
            bool: True if password was reset successfully, False otherwise
        """
        return self.user_db.reset_user_password(username, new_password)

    def delete_user(self, username: str) -> bool:
        """
        Delete a user.
        
        Args:
            username: Username to delete
            
        Returns:
            bool: True if user was deleted successfully, False otherwise
        """
        return self.user_db.delete_user(username)
    
    def set_user_role(self, username: str, new_role: str) -> bool:
        """
        Update a user's role.
        
        Args:
            username: Username to update role for
            new_role: New role to assign
            
        Returns:
            bool: True if role was updated successfully, False otherwise
        """
        return self.user_db.update_user_role(username, new_role)

    def get_users(self) -> List[Tuple[str, str]]:
        """
        Get a list of all users and their roles.
        
        Returns:
            List of tuples with (username, role)
        """
        return self.user_db.get_all_users()

    def get_all_users(self) -> List[Tuple[str, str]]:
        """
        Get a list of all users and their roles.
        
        Returns:
            List of tuples with (username, role)
        """
        return self.user_db.get_all_users()
    
    def get_all_users_detailed(self) -> List[Dict[str, Any]]:
        """
        Get detailed information for all users including ID numbers.
        
        Returns:
            List of dictionaries with user details
        """
        users = []
        try:
            user_list = self.user_db.get_all_users()
            for username, role in user_list:
                user_info = self.user_db.get_user(username)
                if user_info:
                    users.append({
                        'username': username,
                        'id_number': user_info.get('id_number', ''),
                        'role': role,
                        'created_at': user_info.get('created_at', ''),
                        'last_login': user_info.get('last_login', '')
                    })
                else:
                    # Fallback if detailed info not available
                    users.append({
                        'username': username,
                        'id_number': '',
                        'role': role,
                        'created_at': '',
                        'last_login': ''
                    })
        except Exception as e:
            self.logger.error(f"Error getting detailed user list: {e}")
        
        return users

    def get_available_roles(self) -> List[str]:
        """
        Get list of available roles.
        
        Returns:
            List of role names
        """
        roles = ["OPERATOR", "MAINTENANCE", "ADMIN"]
        
        # Add NONE role when require_login is active
        if self.require_login:
            roles.append("NONE")
            
        return roles

    # ==============================================
    # SESSION MANAGEMENT (unchanged)
    # ==============================================

    def is_authenticated(self) -> bool:
        """
        Check if current user is authenticated and session is still valid.
        
        Returns:
            bool: True if authenticated and session is valid, False otherwise
        """
        if not self.authenticated:
            return False
        if time.time() - self.last_auth_time > self.session_timeout:
            self.logger.info("Session expired")
            self.authenticated = False
            self.current_role = self.default_role
            self.current_username = None
            return False
        return True
    
    def refresh_session(self) -> None:
        """Refresh the authentication session timeout."""
        if self.authenticated:
            self.last_auth_time = time.time()
    
    def logout(self):
        """Log out the current user."""
        self.authenticated = False
        self.current_role = self.default_role
        self.current_username = None
        self.logger.info("User logged out")
    
    def get_current_role(self) -> str:
        """
        Get the current user role.
        
        If no user is authenticated:
        - Return "NONE" if require_login is True
        - Return default_role (usually "OPERATOR") if require_login is False
        
        Returns:
            str: Current role
        """
        if self.is_authenticated():
            return self.current_role
        
        # If authentication is required, return NONE role when not logged in
        if self.require_login:
            return "NONE"
            
        # Otherwise return the default role (usually OPERATOR)
        return self.default_role
    
    def get_current_username(self) -> Optional[str]:
        """
        Get the username of the currently authenticated user.
        
        Returns:
            str: Current username or None if not authenticated
        """
        return self.current_username if self.is_authenticated() else None
    
    def get_current_user(self) -> Optional[str]:
        """
        Get the username of the currently authenticated user.
        Alias for get_current_username for backward compatibility.
        
        Returns:
            str: Current username or None if not authenticated
        """
        return self.get_current_username()
    
    def get_role_level(self, role: Optional[str] = None) -> int:
        """
        Get the numeric level of a role.
        
        Args:
            role: Role name (or None to use current role)
            
        Returns:
            int: Role level (0 for NONE role)
        """
        role = role or self.get_current_role()
        
        # Check cache first
        if role in self._role_permissions_cache:
            return self._role_permissions_cache[role].get("level", 0)
        
        # Special case for NONE role
        if role == "NONE":
            return 0
        
        # Try to get from database
        role_info = self.user_db.get_role_permissions(role)
        if role_info:
            # Update cache
            if role not in self._role_permissions_cache:
                self._role_permissions_cache[role] = {}
            self._role_permissions_cache[role]["level"] = role_info.get("level", 0)
            return role_info.get("level", 0)
        
        # Fallback to hardcoded values
        role_levels = {
            "OPERATOR": 1,
            "MAINTENANCE": 2,
            "ADMIN": 3
        }
        
        return role_levels.get(role, 0)
    
    def has_permission(self, permission: str) -> bool:
        """
        Check if the current role has the specified permission.
        
        Args:
            permission: Permission to check
            
        Returns:
            bool: True if role has permission, False otherwise
        """
        current_role = self.get_current_role()
        
        # NONE role has no permissions
        if current_role == "NONE":
            return False
        
        # Simplified permission checking based on role level
        if permission.startswith("tab:"):
            # Tab access permission
            tab_name = permission.replace("tab:", "")
            return self.has_tab_access(tab_name)
        
        # Get permissions from cache
        if current_role in self._role_permissions_cache:
            role_permissions = self._role_permissions_cache[current_role].get("permissions", [])
            if permission in role_permissions:
                return True
        
        # Try to get from database if not in cache
        role_info = self.user_db.get_role_permissions(current_role)
        if role_info:
            # Update cache
            if current_role not in self._role_permissions_cache:
                self._role_permissions_cache[current_role] = {}
            self._role_permissions_cache[current_role]["permissions"] = role_info.get("permissions", [])
            
            # Check permission
            return permission in role_info.get("permissions", [])
        
        # Legacy permission checking for backward compatibility
        if current_role in USER_ROLES:
            role_permissions = USER_ROLES[current_role].get('permissions', [])
            return permission in role_permissions
        
        return False
    
    def get_current_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the current authenticated user.
        
        Returns:
            Dict with user information or None if not authenticated
        """
        if not self.is_authenticated():
            return None
        return self.user_db.get_user(self.current_username)
    
    def has_access(self, min_role: str) -> bool:
        """
        Check if current role has access to features requiring the specified role.
        
        Args:
            min_role: Minimum role required for access
            
        Returns:
            bool: True if current role has sufficient access, False otherwise
        """
        return self.get_role_level() >= self.get_role_level(min_role)
    
    def require_role(self, min_role: str) -> bool:
        """
        Check if user is authenticated and has the required role.
        
        Args:
            min_role: Minimum role required for access
            
        Returns:
            bool: True if authenticated and has sufficient role, False otherwise
        """
        return self.is_authenticated() and self.has_access(min_role)
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a user.
        
        Args:
            username: Username to get info for
            
        Returns:
            Dict with user information or None if user not found
        """
        return self.user_db.get_user(username)
    
    def update_role_permissions(self, role: str, permissions: List[str]) -> bool:
        """
        Update the permission list for a role.
        
        Args:
            role: Role name to update
            permissions: New list of permissions
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        # Get current role data
        role_info = self.user_db.get_role_permissions(role)
        
        if role_info:
            # Update permissions while keeping other attributes
            level = role_info.get("level", 0)
            tabs = role_info.get("tabs", [])
            
            # Update in database
            success = self.user_db.update_role_permissions(
                role, level=level, permissions=permissions, tabs=tabs
            )
            
            if success:
                # Update cache
                if role in self._role_permissions_cache:
                    self._role_permissions_cache[role]["permissions"] = permissions
                
                self.logger.info(f"Updated permissions for {role}: {permissions}")
                return True
            else:
                self.logger.error(f"Failed to update permissions for {role}")
                return False
        else:
            # Role doesn't exist in database, attempt to create it
            if role in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
                # Determine level based on role name
                level = 0
                if role == "OPERATOR":
                    level = 1
                elif role == "MAINTENANCE":
                    level = 2
                elif role == "ADMIN":
                    level = 3
                
                # Use default tabs from USER_ROLES
                tabs = []
                if role in USER_ROLES:
                    tabs = USER_ROLES[role].get("tabs", [])
                elif role == "NONE":
                    tabs = ["login"]
                
                # Create in database
                success = self.user_db.update_role_permissions(
                    role, level=level, permissions=permissions, tabs=tabs
                )
                
                if success:
                    # Update cache
                    self._role_permissions_cache[role] = {
                        "level": level,
                        "permissions": permissions,
                        "tabs": tabs
                    }
                    
                    self.logger.info(f"Created new permissions for {role}: {permissions}")
                    return True
                else:
                    self.logger.error(f"Failed to create permissions for {role}")
                    return False
            else:
                self.logger.error(f"Cannot update permissions for invalid role: {role}")
                return False

    # ==============================================
    # ID NUMBER MANAGEMENT METHODS (NEW)
    # ==============================================
    
    def update_user_id_number(self, username: str, new_id_number: str) -> Tuple[bool, str]:
        """
        Update a user's ID number.
        
        Args:
            username: Username to update
            new_id_number: New ID number to assign
            
        Returns:
            Tuple[bool, str]: (success, error_message)
        """
        if not username:
            return False, "Username is required"
        
        if not new_id_number:
            return False, "ID number is required"
        
        # Check if user exists
        existing_user = self.user_db.get_user(username)
        if not existing_user:
            return False, f"User '{username}' not found"
        
        # Validate new ID number
        is_valid, error_msg = self._validate_id_number(new_id_number.strip(), username)
        if not is_valid:
            return False, error_msg
        
        # Use the update_user method if available, otherwise try direct database method
        try:
            if hasattr(self.user_db, 'update_user_id_number'):
                success = self.user_db.update_user_id_number(username, new_id_number.strip())
                if success:
                    self.logger.info(f"Updated ID number for user '{username}' to '{new_id_number}'")
                    return True, ""
                else:
                    return False, "Failed to update ID number in database"
            else:
                # Fallback: update through user recreation (not ideal but works)
                current_user = existing_user
                current_role = current_user.get('role', 'OPERATOR')
                
                # This is a workaround - in a real implementation, you'd add an update_user_id_number method to UserDB
                # For now, we'll log that this functionality needs to be implemented
                self.logger.warning("update_user_id_number method not available in UserDB. ID number update not performed.")
                return False, "ID number update functionality not implemented in database layer"
                
        except Exception as e:
            self.logger.error(f"Error updating ID number: {e}")
            return False, f"Error updating ID number: {str(e)}"
    
    def get_user_by_id_number(self, id_number: str) -> Optional[Dict[str, Any]]:
        """
        Find a user by their ID number.
        
        Args:
            id_number: ID number to search for
            
        Returns:
            Dict with user information or None if not found
        """
        if not id_number:
            return None
        
        try:
            # Get all users and search through them
            # This is not the most efficient method, but works with current UserDB structure
            user_list = self.user_db.get_all_users()
            for username, role in user_list:
                user_info = self.user_db.get_user(username)
                if user_info and user_info.get('id_number') == id_number:
                    return user_info
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error searching for user by ID number: {e}")
            return None
    
    def validate_id_number_format(self, id_number: str) -> Tuple[bool, str]:
        """
        Validate ID number format without checking uniqueness.
        
        Args:
            id_number: ID number to validate
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if not id_number:
            return False, "ID number cannot be empty"
        
        # Basic format validation
        id_number = id_number.strip()
        if len(id_number) < 3:
            return False, "ID number must be at least 3 characters long"
        
        # Check for invalid characters
        if not id_number.replace('-', '').replace('_', '').isalnum():
            return False, "ID number can only contain letters, numbers, hyphens, and underscores"
        
        return True, ""
    
    def generate_id_number_suggestion(self, username: str, role: str) -> str:
        """
        Generate a suggested ID number for a user.
        
        Args:
            username: Username
            role: User role
            
        Returns:
            str: Suggested ID number
        """
        return self._generate_default_id_number(username, role)
    
    def get_id_number_usage_report(self) -> Dict[str, Any]:
        """
        Get a report on ID number usage across all users.
        
        Returns:
            Dict with ID number usage statistics
        """
        report = {
            "total_users": 0,
            "users_with_id_numbers": 0,
            "users_without_id_numbers": 0,
            "duplicate_id_numbers": [],
            "id_number_by_role": {},
            "id_number_patterns": {}
        }
        
        try:
            user_list = self.user_db.get_all_users()
            id_number_count = {}
            
            for username, role in user_list:
                report["total_users"] += 1
                
                user_info = self.user_db.get_user(username)
                if user_info:
                    id_number = user_info.get('id_number', '')
                    
                    if id_number:
                        report["users_with_id_numbers"] += 1
                        
                        # Track ID number usage
                        if id_number in id_number_count:
                            id_number_count[id_number].append(username)
                        else:
                            id_number_count[id_number] = [username]
                        
                        # Count by role
                        if role not in report["id_number_by_role"]:
                            report["id_number_by_role"][role] = 0
                        report["id_number_by_role"][role] += 1
                        
                        # Analyze patterns (prefix)
                        if len(id_number) >= 3:
                            prefix = id_number[:3].upper()
                            if prefix not in report["id_number_patterns"]:
                                report["id_number_patterns"][prefix] = 0
                            report["id_number_patterns"][prefix] += 1
                    else:
                        report["users_without_id_numbers"] += 1
            
            # Find duplicates
            for id_number, users in id_number_count.items():
                if len(users) > 1:
                    report["duplicate_id_numbers"].append({
                        "id_number": id_number,
                        "users": users,
                        "count": len(users)
                    })
            
        except Exception as e:
            self.logger.error(f"Error generating ID number usage report: {e}")
        
        return report


# ==============================================
# GLOBAL INSTANCE AND CONVENIENCE FUNCTIONS
# ==============================================

_role_manager = None

def get_role_manager() -> RoleManager:
    """
    Get the global RoleManager instance.
    
    Returns:
        RoleManager: Global instance of RoleManager
    """
    global _role_manager
    if _role_manager is None:
        _role_manager = RoleManager()
    return _role_manager

def get_permission_manager() -> RoleManager:
    """
    Get the permission manager (alias for role manager).
    This replaces simple_permissions.get_permission_manager()
    
    Returns:
        RoleManager: Global instance of RoleManager
    """
    return get_role_manager()

def has_access(min_role: str) -> bool:
    """
    Check if current role has access to features requiring the specified role.
    
    Args:
        min_role: Minimum role required for access
        
    Returns:
        bool: True if current role has sufficient access, False otherwise
    """
    return get_role_manager().has_access(min_role)

def get_current_role() -> str:
    """
    Get the current user role.
    
    Returns:
        str: Current role
    """
    return get_role_manager().get_current_role()

def get_current_username() -> Optional[str]:
    """
    Get the username of the currently authenticated user.
    
    Returns:
        str: Current username or None if not authenticated
    """
    return get_role_manager().get_current_username()

def has_tab_access(tab_name: str) -> bool:
    """
    Check if the current user has access to a specific tab.
    This replaces simple_permissions.has_tab_access()
    
    Args:
        tab_name: Name of the tab to check access for
        
    Returns:
        bool: True if user has access to the tab, False otherwise
    """
    return get_role_manager().has_tab_access(tab_name)

def set_current_role(role: str) -> None:
    """
    Set the current role (for compatibility with permission_manager).
    This is handled by authentication, but provided for API compatibility.
    
    Args:
        role: Role to set
    """
    # This functionality is handled by authentication in this simplified system
    # but provided for API compatibility
    role_manager = get_role_manager()
    if not role_manager.is_authenticated():
        # Only allow setting role if not authenticated (for default role scenarios)
        role_manager.current_role = role
        role_manager.logger.info(f"Set current role to {role} (unauthenticated)")

# ==============================================
# CONVENIENCE FUNCTIONS FOR ID NUMBER MANAGEMENT
# ==============================================

def create_user_with_id(username: str, password: str, role: str, id_number: str = "") -> Tuple[bool, str]:
    """
    Convenience function to create a user with proper ID number handling.
    
    Args:
        username: Username for the new account
        password: Password for the new account  
        role: Role to assign to the new user
        id_number: ID number for the user (auto-generated if empty)
        
    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    return get_role_manager().create_user(username, password, role, id_number)

def update_user_id(username: str, new_id_number: str) -> Tuple[bool, str]:
    """
    Convenience function to update a user's ID number.
    
    Args:
        username: Username to update
        new_id_number: New ID number
        
    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    return get_role_manager().update_user_id_number(username, new_id_number)

def find_user_by_id(id_number: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to find a user by ID number.
    
    Args:
        id_number: ID number to search for
        
    Returns:
        Dict with user info or None if not found
    """
    return get_role_manager().get_user_by_id_number(id_number)

def get_users_detailed() -> List[Dict[str, Any]]:
    """
    Convenience function to get all users with detailed information.
    
    Returns:
        List of user detail dictionaries
    """
    return get_role_manager().get_all_users_detailed()

def suggest_id_number(username: str, role: str) -> str:
    """
    Convenience function to get an ID number suggestion.
    
    Args:
        username: Username
        role: User role
        
    Returns:
        Suggested ID number
    """
    return get_role_manager().generate_id_number_suggestion(username, role)