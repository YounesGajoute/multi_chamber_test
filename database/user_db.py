#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
User Database module for the Multi-Chamber Test application.

This module provides the UserDB class that handles database operations
for user management, including authentication, user creation, and
password management.
"""

import os
import sqlite3
import logging
import hashlib
import time
import shutil
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime

from multi_chamber_test.config.constants import USER_ROLES
DEFAULT_PASSWORD = "9012"


class UserDB:
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the UserDB with a database path.
        If no path given, defaults to ./data/techmac_users.db
        """
        self.logger = logging.getLogger('UserDB')
        self._setup_logger()

        #  New logic: no PASSWORD_FILE 
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "techmac_users.db")
        else:
            self.db_path = db_path

        self._init_database()
    
    def _setup_logger(self):
        """Configure logging for the user database."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _init_database(self):
        """Initialize the database schema if it doesn't exist."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Check if database already exists
            db_exists = os.path.exists(self.db_path)
            
            # Create database connection
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # If database exists, check if it has the proper schema and needs migration
            if db_exists:
                try:
                    # Check if id_number column exists in users table
                    cursor.execute("PRAGMA table_info(users)")
                    columns = [col[1] for col in cursor.fetchall()]
                    
                    if "users" in [table[0] for table in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                        # If users table exists but doesn't have id_number column, add it
                        if "id_number" not in columns:
                            self.logger.info("Migrating database: Adding id_number column to users table")
                            
                            # Add id_number column with default value (using username as default)
                            cursor.execute("ALTER TABLE users ADD COLUMN id_number TEXT DEFAULT ''")
                            
                            # Update existing users with username as initial ID
                            cursor.execute("UPDATE users SET id_number = username")
                            
                            # Commit the migration changes
                            conn.commit()
                            self.logger.info("Database migration completed successfully")
                        
                    # Basic schema check (this will raise exception if schema is wrong)
                    cursor.execute("SELECT username, password_hash, role FROM users LIMIT 1")
                    cursor.fetchone()
                    
                except sqlite3.OperationalError as e:
                    self.logger.warning(f"Database schema issue detected: {e}")
                    
                    # Backup the existing database
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = f"{self.db_path}.{timestamp}.bak"
                    conn.close()
                    
                    try:
                        shutil.copy2(self.db_path, backup_path)
                        self.logger.info(f"Created backup of existing database at {backup_path}")
                        
                        # Remove the problematic database
                        os.remove(self.db_path)
                        self.logger.info("Removed corrupted database file")
                        
                        # Reconnect to create a new database
                        conn = sqlite3.connect(self.db_path)
                        cursor = conn.cursor()
                        db_exists = False
                    except Exception as backup_error:
                        self.logger.error(f"Failed to backup/remove corrupted database: {backup_error}")
                        # Continue anyway and try to recreate the tables
            
            # Create users table if it doesn't exist or had schema issues
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    id_number TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')
            
            # Create login_attempts table for security monitoring
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT
                )
            ''')
            
            # Create role_permissions table to store customized role permissions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role TEXT PRIMARY KEY,
                    level INTEGER NOT NULL,
                    permissions TEXT NOT NULL,
                    tabs TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            
            # Check if default users exist, create if not
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                default_users = [
                    ("admin",    "admin",    self._hash_password(DEFAULT_PASSWORD), "ADMIN"),
                    ("maintenance","maintenance",self._hash_password(DEFAULT_PASSWORD),"MAINTENANCE"),
                    ("operator", "operator", self._hash_password(DEFAULT_PASSWORD), "OPERATOR")
                ]
                cursor.executemany(
                        "INSERT INTO users (username, id_number, password_hash, role) VALUES (?, ?, ?, ?)",
                        default_users
                    )
                conn.commit()
                self.logger.info(
                    f"Created default users (admin, maintenance, operator) with password '{DEFAULT_PASSWORD}'"
                )
            
            
            # Initialize/update role permissions from USER_ROLES constant
            self._initialize_role_permissions(cursor)
            
            conn.commit()
            conn.close()
            self.logger.info("User database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Error initializing user database: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _initialize_role_permissions(self, cursor):
        """
        Initialize or update role permissions in the database with hardcoded defaults,
        focusing only on tab access permissions without relying on external constants.
        
        Args:
            cursor: SQLite cursor to execute database operations
        """
        try:
            # Define default role tab access directly in the method
            default_roles = {
                "ADMIN": {
                    "level": 3,
                    "permissions": [],  # Simplified: no granular permissions
                    "tabs": ["login", "main", "settings", "calibration", "reference"]
                },
                "MAINTENANCE": {
                    "level": 2,
                    "permissions": [],  # Simplified: no granular permissions
                    "tabs": ["login", "main", "calibration"]
                },
                "OPERATOR": {
                    "level": 1,
                    "permissions": [],  # Simplified: no granular permissions
                    "tabs": ["login", "main"]
                },
                "NONE": {
                    "level": 0,
                    "permissions": [],  # No permissions
                    "tabs": ["login"]   # ONLY login tab
                }
            }
            
            # For each role in default_roles, add or update the role_permissions table
            for role_name, role_data in default_roles.items():
                permissions_json = json.dumps(role_data.get("permissions", []))
                tabs_json = json.dumps(role_data.get("tabs", []))
                level = role_data.get("level", 0)
                
                # Check if role already exists
                cursor.execute(
                    "SELECT COUNT(*) FROM role_permissions WHERE role = ?",
                    (role_name,)
                )
                role_exists = cursor.fetchone()[0] > 0
                
                if role_exists:
                    # Update existing role
                    cursor.execute(
                        "UPDATE role_permissions SET level = ?, permissions = ?, tabs = ?, last_updated = CURRENT_TIMESTAMP WHERE role = ?",
                        (level, permissions_json, tabs_json, role_name)
                    )
                else:
                    # Insert new role
                    cursor.execute(
                        "INSERT INTO role_permissions (role, level, permissions, tabs) VALUES (?, ?, ?, ?)",
                        (role_name, level, permissions_json, tabs_json)
                    )
            
            self.logger.info("Role permissions initialized with default tab access")
        except Exception as e:
            self.logger.error(f"Error initializing role permissions: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _hash_password(self, password: str) -> str:
        """
        Create a secure hash of the password.
        
        Args:
            password: Plain text password
            
        Returns:
            str: Hashed password
        """
        # Use SHA-256 hash for password
        return hashlib.sha256(password.encode()).hexdigest()
    
    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """
        Authenticate a user with username and password.
        
        Args:
            username: User's username
            password: User's password
            
        Returns:
            str: User's role if authentication successful, None otherwise
        """
        if not username or not password:
            self.logger.warning("Authentication attempt with empty username or password")
            return None
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Hash the provided password
            password_hash = self._hash_password(password)
            
            # Query user with matching username and password
            try:
                cursor.execute(
                    "SELECT role FROM users WHERE username = ? AND password_hash = ?",
                    (username, password_hash)
                )
                
                result = cursor.fetchone()
            except sqlite3.OperationalError as e:
                self.logger.error(f"Database error during authentication: {e}")
                
                # If there's a schema issue, try to fix the database
                if "no such column: role" in str(e):
                    self.logger.warning("Schema issue detected. Attempting to reinitialize database.")
                    conn.close()
                    
                    # Backup the current database
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = f"{self.db_path}.{timestamp}.bak"
                    try:
                        shutil.copy2(self.db_path, backup_path)
                        self.logger.info(f"Created backup of problematic database at {backup_path}")
                        
                        # Remove the problematic database and reinitialize
                        os.remove(self.db_path)
                        self._init_database()
                        
                        # Try the authentication again
                        return self.authenticate_user(username, password)
                    except Exception as backup_error:
                        self.logger.error(f"Failed to fix database: {backup_error}")
                
                return None
            
            # Log authentication attempt
            success = result is not None
            try:
                cursor.execute(
                    "INSERT INTO login_attempts (username, success) VALUES (?, ?)",
                    (username, success)
                )
            except sqlite3.OperationalError:
                # If login_attempts table doesn't exist, just log and continue
                self.logger.warning("Could not log login attempt - login_attempts table may be missing")
                
            # Update last login timestamp if successful
            if success:
                try:
                    cursor.execute(
                        "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?",
                        (username,)
                    )
                except sqlite3.OperationalError:
                    self.logger.warning("Could not update last_login timestamp")
            
            conn.commit()
            conn.close()
            
            # Return role if authentication successful
            if result:
                self.logger.info(f"User '{username}' authenticated successfully")
                return result[0]
            else:
                self.logger.warning(f"Failed authentication attempt for user '{username}'")
                return None
                
        except Exception as e:
            self.logger.error(f"Error authenticating user: {e}")
            return None
    
    def create_user(self, username: str, id_number: str, password: str, role: str) -> bool:
        """
        Create a new user.
        
        Args:
            username: New user's username
            id_number: New user's ID number
            password: New user's password
            role: New user's role
            
        Returns:
            bool: True if user was created successfully, False otherwise
        """
        if not username or not password or not role:
            self.logger.error("Invalid user creation parameters")
            return False
            
        # Validate role
        if role not in USER_ROLES and role != "NONE":
            self.logger.error(f"Invalid role: {role}")
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if username already exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
            user_exists = cursor.fetchone()[0] > 0
            
            if user_exists:
                # Update existing user
                cursor.execute(
                    "UPDATE users SET password_hash = ?, role = ?, id_number = ? WHERE username = ?",
                    (self._hash_password(password), role, id_number, username)
                )
                self.logger.info(f"User '{username}' updated with role '{role}' and ID '{id_number}'")
            else:
                # Insert new user
                cursor.execute(
                        "INSERT INTO users (username, id_number, password_hash, role) VALUES (?, ?, ?, ?)",
                        (username, id_number, self._hash_password(password), role)
                    )
                self.logger.info(f"User '{username}' created successfully with role '{role}' and ID '{id_number}'")
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating user: {e}")
            return False
    
    def reset_user_password(self, username: str, new_password: str) -> bool:
        """
        Reset a user's password.
        
        Args:
            username: Username to reset password for
            new_password: New password to set
            
        Returns:
            bool: True if password was reset successfully, False otherwise
        """
        if not username or not new_password:
            self.logger.error("Invalid password reset parameters")
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
            user_exists = cursor.fetchone()[0] > 0
            
            if not user_exists:
                self.logger.warning(f"Cannot reset password: User '{username}' not found")
                conn.close()
                return False
            
            # Hash the new password
            password_hash = self._hash_password(new_password)
            
            # Update password
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (password_hash, username)
            )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Password reset successfully for user '{username}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error resetting password: {e}")
            return False
    
    def delete_user(self, username: str) -> bool:
        """
        Delete a user.
        
        Args:
            username: Username to delete
            
        Returns:
            bool: True if user was deleted successfully, False otherwise
        """
        if not username:
            self.logger.error("Invalid username for deletion")
            return False
            
        # Don't allow deleting the last admin user
        if username == "admin":
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Count admin users
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")
                admin_count = cursor.fetchone()[0]
                
                if admin_count <= 1:
                    self.logger.warning("Cannot delete the last admin user")
                    conn.close()
                    return False
                    
                conn.close()
            except Exception as e:
                self.logger.error(f"Error checking admin users: {e}")
                return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Delete user
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            
            # Check if any rows were affected
            if cursor.rowcount == 0:
                self.logger.warning(f"User '{username}' not found for deletion")
                conn.close()
                return False
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"User '{username}' deleted successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error deleting user: {e}")
            return False
    
    def update_user_role(self, username: str, new_role: str) -> bool:
        """
        Update a user's role.
        
        Args:
            username: Username to update
            new_role: New role to assign
            
        Returns:
            bool: True if role was updated successfully, False otherwise
        """
        if not username or not new_role:
            self.logger.error("Invalid parameters for role update")
            return False
            
        # Validate role
        if new_role not in USER_ROLES and new_role != "NONE":
            self.logger.error(f"Invalid role: {new_role}")
            return False
            
        # Don't allow changing the last admin user's role
        if username == "admin":
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get current role
                cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
                current_role = cursor.fetchone()
                
                if current_role and current_role[0] == "ADMIN" and new_role != "ADMIN":
                    # Count admin users
                    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")
                    admin_count = cursor.fetchone()[0]
                    
                    if admin_count <= 1:
                        self.logger.warning("Cannot change role of the last admin user")
                        conn.close()
                        return False
                
                conn.close()
            except Exception as e:
                self.logger.error(f"Error checking admin users: {e}")
                return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Update role
            cursor.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                (new_role, username)
            )
            
            # Check if any rows were affected
            if cursor.rowcount == 0:
                self.logger.warning(f"User '{username}' not found for role update")
                conn.close()
                return False
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Role for user '{username}' updated to '{new_role}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating user role: {e}")
            return False
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a user.
        
        Args:
            username: Username to retrieve
            
        Returns:
            Dict containing user information or None if user not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable dictionary access to rows
            cursor = conn.cursor()
            
            # Query user
            cursor.execute(
                "SELECT id, username, id_number, role, created_at, last_login FROM users WHERE username = ?",
                (username,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                # Convert to dictionary
                user_info = dict(row)
                return user_info
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error retrieving user information: {e}")
            return None
    
    def get_all_users(self) -> List[Tuple[str, str]]:
        """
        Get all users in the database.
        
        Returns:
            List of tuples containing (username, role)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Query all users
            try:
                cursor.execute("SELECT username, role FROM users ORDER BY username")
                users = cursor.fetchall()
            except sqlite3.OperationalError as e:
                self.logger.error(f"Database error getting users: {e}")
                # If there's a schema issue, try to fix the database
                if "no such column: role" in str(e):
                    self.logger.warning("Schema issue detected. Reinitializing database.")
                    conn.close()
                    
                    # Backup the current database
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = f"{self.db_path}.{timestamp}.bak"
                    
                    try:
                        shutil.copy2(self.db_path, backup_path)
                        self.logger.info(f"Created backup of problematic database at {backup_path}")
                        
                        # Remove the problematic database and reinitialize
                        os.remove(self.db_path)
                        self._init_database()
                        
                        # Try getting users again
                        return self.get_all_users()
                    except Exception as backup_error:
                        self.logger.error(f"Failed to fix database: {backup_error}")
                
                # Return admin as a fallback
                return [("admin", "ADMIN")]
            
            conn.close()
            return users
            
        except Exception as e:
            self.logger.error(f"Error retrieving all users: {e}")
            # Return admin as a fallback in case of errors
            return [("admin", "ADMIN")]
    
    def get_login_history(self, username: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get login history for a user or all users.
        
        Args:
            username: Username to retrieve history for (None for all users)
            limit: Maximum number of entries to retrieve
            
        Returns:
            List of dictionaries containing login history
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable dictionary access to rows
            cursor = conn.cursor()
            
            # Query login attempts
            if username:
                cursor.execute(
                    "SELECT * FROM login_attempts WHERE username = ? ORDER BY timestamp DESC LIMIT ?",
                    (username, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM login_attempts ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries
            history = [dict(row) for row in rows]
            return history
            
        except Exception as e:
            self.logger.error(f"Error retrieving login history: {e}")
            return []
    
    def update_role_permissions(self, role: str, level: Optional[int] = None, 
                             permissions: Optional[List[str]] = None, 
                             tabs: Optional[List[str]] = None) -> bool:
        """
        Update permissions for a specific role.
        
        Args:
            role: Role name to update
            level: Role access level (optional)
            permissions: List of permission codes (optional)
            tabs: List of accessible tab names (optional)
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            # Get current permissions
            current = self.get_role_permissions(role)
            if not current and role not in ["OPERATOR", "MAINTENANCE", "ADMIN", "NONE"]:
                self.logger.error(f"Cannot update invalid role: {role}")
                return False
            
            # Use current values for any parameters not provided
            if current:
                level = level if level is not None else current.get("level", 0)
                permissions = permissions if permissions is not None else current.get("permissions", [])
                tabs = tabs if tabs is not None else current.get("tabs", [])
            else:
                # Default values for new roles
                level = level if level is not None else 0
                permissions = permissions if permissions is not None else []
                tabs = tabs if tabs is not None else []
            
            # Validate tabs
            valid_tabs = ["login", "main", "settings", "calibration", "reference"]
            invalid_tabs = [tab for tab in tabs if tab not in valid_tabs]
            if invalid_tabs:
                self.logger.warning(f"Invalid tab names for role {role}: {invalid_tabs}")
                # Filter out invalid tabs
                tabs = [tab for tab in tabs if tab in valid_tabs]
            
            # Ensure certain roles always have minimum required tabs
            if role == "OPERATOR":
                # OPERATOR must have login and main tabs
                required_tabs = ["login", "main"]
                tabs = list(set(tabs + required_tabs))
            elif role == "MAINTENANCE" or role == "ADMIN":
                # These roles should have login and main tabs
                required_tabs = ["login", "main"]
                tabs = list(set(tabs + required_tabs))
            
            # Convert lists to JSON strings
            permissions_json = json.dumps(permissions)
            tabs_json = json.dumps(tabs)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if role exists in database
            cursor.execute(
                "SELECT COUNT(*) FROM role_permissions WHERE role = ?",
                (role,)
            )
            role_exists = cursor.fetchone()[0] > 0
            
            if role_exists:
                # Update existing role
                cursor.execute(
                    "UPDATE role_permissions SET level = ?, permissions = ?, tabs = ?, last_updated = CURRENT_TIMESTAMP WHERE role = ?",
                    (level, permissions_json, tabs_json, role)
                )
            else:
                # Insert new role
                cursor.execute(
                    "INSERT INTO role_permissions (role, level, permissions, tabs) VALUES (?, ?, ?, ?)",
                    (role, level, permissions_json, tabs_json)
                )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Updated permissions for role '{role}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating role permissions: {e}")
            return False
    
    def get_role_permissions(self, role: str) -> Optional[Dict[str, Any]]:
        """
        Get the permissions for a specific role.
        
        Args:
            role: Role name to retrieve permissions for
            
        Returns:
            Dict containing role permissions or None if role not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Query role permissions
            cursor.execute(
                "SELECT * FROM role_permissions WHERE role = ?",
                (role,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                # Parse JSON fields
                permissions = json.loads(row[2])  # permissions column
                tabs = json.loads(row[3])  # tabs column
                
                return {
                    "role": row[0],
                    "level": row[1],
                    "permissions": permissions,
                    "tabs": tabs,
                    "last_updated": row[4]
                }
            else:
                # If not found in database, try to get from USER_ROLES constant
                if role in USER_ROLES:
                    role_data = USER_ROLES[role]
                    return {
                        "role": role,
                        "level": role_data.get("level", 0),
                        "permissions": role_data.get("permissions", []),
                        "tabs": role_data.get("tabs", [])
                    }
                elif role == "NONE":
                    # Special case for NONE role
                    return {
                        "role": "NONE",
                        "level": 0,
                        "permissions": [],
                        "tabs": ["login"]
                    }
                else:
                    return None
                
        except Exception as e:
            self.logger.error(f"Error retrieving role permissions: {e}")
            
            # Fallback to USER_ROLES constant
            if role in USER_ROLES:
                role_data = USER_ROLES[role]
                return {
                    "role": role,
                    "level": role_data.get("level", 0),
                    "permissions": role_data.get("permissions", []),
                    "tabs": role_data.get("tabs", [])
                }
            elif role == "NONE":
                # Special case for NONE role
                return {
                    "role": "NONE",
                    "level": 0,
                    "permissions": [],
                    "tabs": ["login"]
                }
            
            return None
    
    def get_all_role_permissions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get permissions for all roles.
        
        Returns:
            Dict mapping role names to permission details
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Query all roles
            cursor.execute("SELECT * FROM role_permissions")
            rows = cursor.fetchall()
            conn.close()
            
            # Build result dictionary
            result = {}
            for row in rows:
                role_name = row[0]
                # Parse JSON fields
                permissions = json.loads(row[2])  # permissions column
                tabs = json.loads(row[3])  # tabs column
                
                result[role_name] = {
                    "level": row[1],
                    "permissions": permissions,
                    "tabs": tabs,
                    "last_updated": row[4]
                }
            
            # Add any missing roles from USER_ROLES
            for role_name, role_data in USER_ROLES.items():
                if role_name not in result:
                    result[role_name] = {
                        "level": role_data.get("level", 0),
                        "permissions": role_data.get("permissions", []),
                        "tabs": role_data.get("tabs", []),
                        "last_updated": None
                    }
            
            # Always include NONE role
            if "NONE" not in result:
                result["NONE"] = {
                    "level": 0,
                    "permissions": [],
                    "tabs": ["login"],
                    "last_updated": None
                }
                
            return result
                
        except Exception as e:
            self.logger.error(f"Error retrieving all role permissions: {e}")
            
            # Fallback to USER_ROLES constant
            result = {}
            for role_name, role_data in USER_ROLES.items():
                result[role_name] = {
                    "level": role_data.get("level", 0),
                    "permissions": role_data.get("permissions", []),
                    "tabs": role_data.get("tabs", []),
                    "last_updated": None
                }
            
            # Add NONE role
            result["NONE"] = {
                "level": 0,
                "permissions": [],
                "tabs": ["login"],
                "last_updated": None
            }
            
            return result