#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FIXED Base Section module for the Multi-Chamber Test application.

This module provides the BaseSection class that serves as the foundation
for all settings sections, providing common functionality for UI creation,
thread safety, feedback display, and lifecycle management.

FIXES:
- Added missing platform import
- Enhanced error handling for mousewheel events
- Improved cross-platform compatibility
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
import threading
import time
import queue
import platform  # FIXED: Added missing import
from typing import Dict, Any, List, Optional, Callable, Union, Tuple

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS


class BaseSection:
    """
    Base class for all settings sections providing common functionality.
    
    This class implements:
    - Thread-safe UI updates
    - Common UI styling and components
    - Standard lifecycle management (show/hide, selection/deselection)
    - Efficient resource cleanup
    - Scrollable content container for overflow handling
    
    All section implementations should inherit from this class.
    """
    
    def __init__(self, parent, *args, **kwargs):
        """
        Initialize a base settings section.
        
        Args:
            parent: Parent widget (typically a Frame in settings_tab.py)
            *args, **kwargs: Additional arguments for specific section implementations
        """
        self.parent = parent
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logger()
        
        # Thread synchronization
        self._ui_lock = threading.RLock()
        self._timer_ids = set()
        
        # Visibility state
        self.is_shown = False
        self.is_selected = False
        
        # Main container frame
        self.frame = ttk.Frame(parent, style='Content.TFrame')
        
        # Create scrollable container
        scrollable_container = ttk.Frame(self.frame)
        scrollable_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Canvas and scrollbar for scrolling
        self.canvas = tk.Canvas(scrollable_container, highlightthickness=0, 
                               background=UI_COLORS.get('BACKGROUND', '#FFFFFF'))
        self.scrollbar = tk.Scrollbar(scrollable_container, orient="vertical", command=self.canvas.yview, width=30)
        
        # Pack canvas and scrollbar
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Content frame inside canvas
        self.content_parent = ttk.Frame(self.canvas, style='Content.TFrame')
        
        # Add to canvas
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_parent, anchor="nw")
        
        # Configure scrolling
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Update scrollregion when content changes
        self.content_parent.bind("<Configure>", self._update_scrollregion)
        
        # Ensure canvas window is full width
        self.canvas.bind("<Configure>", self._update_canvas_width)
        
        # Add mousewheel scrolling
        self._bind_mousewheel()
        
        # Add content_frame as an alias for compatibility with existing code
        self.content_frame = self.content_parent
        
        # Create section-specific widgets
        self.create_widgets()
        
        # Feedback message (hidden by default)
        self.feedback_frame = ttk.Frame(self.frame, style='Content.TFrame')
        
        # Default colors for feedback if not in UI_COLORS
        success_bg = UI_COLORS.get('SUCCESS_BG', '#DFF0D8')  # Fallback light green
        success_fg = UI_COLORS.get('SUCCESS', '#3C763D')     # Fallback dark green
        error_bg = UI_COLORS.get('ERROR_BG', '#F2DEDE')      # Fallback light red
        error_fg = UI_COLORS.get('ERROR', '#A94442')         # Fallback dark red
        
        self.feedback_label = ttk.Label(
            self.feedback_frame,
            text="",
            background=success_bg,
            foreground=success_fg,
            font=UI_FONTS['LABEL'],
            anchor='center',
            padding=10
        )
        self.feedback_label.pack(fill=tk.X)
        
        # Initially hide frame and feedback
        self.frame.pack_forget()
        self.feedback_frame.pack_forget()
    
    def _update_scrollregion(self, event):
        """Update the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _update_canvas_width(self, event):
        """Resize the canvas window to fit the width of the canvas"""
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)
    
    def _on_mousewheel(self, event):
        """
        FIXED: Handle mousewheel events for scrolling with proper cross-platform support.
        """
        try:
            # Cross-platform compatibility with Windows (event.delta) and Linux/Mac (event.num)
            delta = 0
            
            if hasattr(event, 'delta') and event.delta:
                # Windows and some Mac systems
                if platform.system() == 'Windows':
                    delta = int(-1 * (event.delta / 120))
                else:
                    # Mac with event.delta
                    delta = int(-1 * event.delta)
            elif hasattr(event, 'num'):
                # Linux and some Unix systems
                if event.num == 4:
                    delta = -1
                elif event.num == 5:
                    delta = 1
                else:
                    delta = 0
            
            # Only scroll if we have a valid delta
            if delta != 0:
                # Scroll 3 units at a time for smoother scrolling
                self.canvas.yview_scroll(delta * 3, "units")
                
        except Exception as e:
            self.logger.debug(f"Mousewheel scroll error: {e}")
            # Fallback: ignore the error and continue
    
    def _bind_mousewheel(self):
        """Bind mousewheel events for scrolling with enhanced error handling."""
        try:
            # Different platforms use different event bindings
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)  # Windows and Mac
            self.canvas.bind_all("<Button-4>", self._on_mousewheel)    # Linux scroll up
            self.canvas.bind_all("<Button-5>", self._on_mousewheel)    # Linux scroll down
        except Exception as e:
            self.logger.warning(f"Could not bind mousewheel events: {e}")
    
    def _unbind_mousewheel(self):
        """Unbind mousewheel events when section is not visible."""
        try:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        except Exception as e:
            self.logger.debug(f"Error unbinding mousewheel events: {e}")
    
    def _setup_logger(self):
        """Configure logging for the section."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def create_widgets(self):
        """
        Create UI widgets for the section.
        
        This method should be overridden by subclasses to create
        section-specific UI elements.
        """
        # Base implementation creates a title
        ttk.Label(
            self.content_parent,
            text=self.__class__.__name__,
            style='ContentTitle.TLabel'
        ).pack(anchor=tk.W, pady=(0, 20))
    
    def create_card(self, title: str, description: Optional[str] = None) -> Tuple[ttk.Frame, ttk.Frame]:
        """
        Create a styled card with title and optional description.
        
        Args:
            title: Card title
            description: Optional card description
            
        Returns:
            Tuple of (card_frame, content_frame) for further customization
        """
        # Create card frame with shadow effect
        card_frame = ttk.Frame(self.content_parent, style='Card.TFrame')
        card_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Add padding inside card
        padding_frame = ttk.Frame(card_frame, style='Card.TFrame', padding=15)
        padding_frame.pack(fill=tk.X)
        
        # Card header
        if title:
            ttk.Label(
                padding_frame,
                text=title,
                style='CardTitle.TLabel'
            ).pack(anchor=tk.W)
        
        # Card description
        if description:
            ttk.Label(
                padding_frame,
                text=description,
                style='CardText.TLabel',
                wraplength=800,
                justify=tk.LEFT
            ).pack(anchor=tk.W, pady=(5, 10))
        
        # Content frame for section-specific content
        content_frame = ttk.Frame(padding_frame, style='Card.TFrame')
        content_frame.pack(fill=tk.X, pady=(10, 0))
        
        return card_frame, content_frame
    
    def create_editor_row(self, parent: ttk.Frame, label_text: str, 
                        value_var: Union[tk.StringVar, tk.IntVar, tk.DoubleVar, tk.BooleanVar],
                        edit_command: Callable, unit: Optional[str] = None) -> ttk.Frame:
        """
        Create a standard editor row with label, value, and edit button.
        
        Args:
            parent: Parent frame to contain the row
            label_text: Label text
            value_var: Variable holding the value
            edit_command: Command to execute when edit button is clicked
            unit: Optional unit string to display after value
            
        Returns:
            The created row frame for further customization
        """
        row_frame = ttk.Frame(parent, style='Card.TFrame')
        row_frame.pack(fill=tk.X, pady=10)
        
        # Label
        ttk.Label(
            row_frame,
            text=label_text,
            style='CardText.TLabel'
        ).pack(side=tk.LEFT)
        
        # Value with optional unit
        value_frame = ttk.Frame(row_frame, style='Card.TFrame')
        value_frame.pack(side=tk.LEFT, padx=(10, 0))
        
        value_label = ttk.Label(
            value_frame,
            textvariable=value_var,
            style='Value.TLabel'
        )
        value_label.pack(side=tk.LEFT)
        
        if unit:
            ttk.Label(
                value_frame,
                text=unit,
                style='CardText.TLabel'
            ).pack(side=tk.LEFT, padx=(5, 0))
        
        # Edit button
        edit_button = ttk.Button(
            row_frame,
            text="Edit",
            style='Secondary.TButton',
            command=edit_command
        )
        edit_button.pack(side=tk.RIGHT)
        
        return row_frame
    
    def show_feedback(self, message: str, is_error: bool = False, 
                     duration: Optional[int] = 5000):
        """
        Show a feedback message to the user.
        
        Args:
            message: Message to display
            is_error: Whether this is an error message
            duration: How long to show the message in ms (None for persistent)
        """
        with self._ui_lock:
            try:
                # Configure appearance based on message type
                if is_error:
                    error_bg = UI_COLORS.get('ERROR_BG', '#F2DEDE')  # Fallback light red
                    error_fg = UI_COLORS.get('ERROR', '#A94442')     # Fallback dark red
                    self.feedback_label.configure(
                        background=error_bg,
                        foreground=error_fg,
                        text=message
                    )
                else:
                    success_bg = UI_COLORS.get('SUCCESS_BG', '#DFF0D8')  # Fallback light green
                    success_fg = UI_COLORS.get('SUCCESS', '#3C763D')     # Fallback dark green
                    self.feedback_label.configure(
                        background=success_bg,
                        foreground=success_fg,
                        text=message
                    )
                
                # Show the feedback
                if not self.feedback_frame.winfo_ismapped():
                    self.feedback_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=(0, 20))
                
                # Auto-hide after duration if specified
                if duration is not None:
                    timer_id = self.parent.after(duration, self.hide_feedback)
                    self._register_timer(timer_id)
                    
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
            except Exception as e:
                self.logger.error(f"Error showing feedback: {e}")
    
    def hide_feedback(self):
        """Hide the feedback message."""
        with self._ui_lock:
            try:
                if self.feedback_frame.winfo_ismapped():
                    self.feedback_frame.pack_forget()
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
            except Exception as e:
                self.logger.debug(f"Error hiding feedback: {e}")
    
    def show_confirmation(self, title: str, message: str) -> bool:
        """
        Show a confirmation dialog and return the result.
        
        Args:
            title: Dialog title
            message: Dialog message
            
        Returns:
            True if confirmed, False otherwise
        """
        try:
            return messagebox.askyesno(title, message)
        except Exception as e:
            self.logger.error(f"Error showing confirmation dialog: {e}")
            return False
    
    def show(self):
        """Show this section."""
        with self._ui_lock:
            try:
                if not self.is_shown:
                    self.frame.pack(fill=tk.BOTH, expand=True)
                    self.is_shown = True
                    self.on_selected()
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
            except Exception as e:
                self.logger.error(f"Error showing section: {e}")
    
    def hide(self):
        """Hide this section."""
        with self._ui_lock:
            try:
                if self.is_shown:
                    self.on_deselected()
                    self.frame.pack_forget()
                    self.is_shown = False
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
            except Exception as e:
                self.logger.error(f"Error hiding section: {e}")
    
    def on_selected(self):
        """Called when this section is selected and becomes visible."""
        try:
            self.is_selected = True
            # Rebind mousewheel when section becomes visible
            self._bind_mousewheel()
            # Refresh view
            self.refresh_all()
            # Reset scroll position to top when shown
            self.canvas.yview_moveto(0)
        except Exception as e:
            self.logger.error(f"Error in on_selected: {e}")
    
    def on_deselected(self):
        """
        Called when this section is deselected and becomes hidden.
        
        Returns:
            Bool indicating whether deselection should proceed (True)
            or be canceled (False).
        """
        try:
            self.is_selected = False
            # Unbind mousewheel to prevent conflicts with other sections
            self._unbind_mousewheel()
            return True
        except Exception as e:
            self.logger.error(f"Error in on_deselected: {e}")
            return True  # Allow deselection even if there's an error
    
    def refresh_all(self):
        """
        Refresh all UI components to reflect current settings.
        Called when the section is shown or needs full refresh.
        
        This method should be overridden by subclasses.
        """
        pass
    
    def update_from_monitoring(self):
        """
        Update UI based on data from monitoring thread.
        This is for real-time updates that need to happen while section is visible.
        
        This method should be overridden by subclasses.
        """
        pass
    
    def _register_timer(self, timer_id: Optional[str] = None):
        """
        Register a timer ID for cleanup.
        
        Args:
            timer_id: Timer ID to register
        """
        if timer_id is not None:
            self._timer_ids.add(timer_id)
    
    def _schedule_ui_update(self, update_func: Callable):
        """
        Schedule a UI update to run in the main thread with enhanced error handling.
        
        Args:
            update_func: Function to run for the update
        """
        try:
            # If we're already in the main thread, execute directly
            if threading.current_thread() is threading.main_thread():
                update_func()
            else:
                # Otherwise schedule for execution in main thread
                self.parent.after(10, update_func)
        except tk.TclError:
            # Widget was destroyed, ignore
            pass
        except Exception as e:
            self.logger.error(f"Error scheduling UI update: {e}")
            
    # Alias for backward compatibility with existing code
    schedule_ui_update = _schedule_ui_update
    
    def _cancel_all_timers(self):
        """Cancel all registered timers."""
        for timer_id in list(self._timer_ids):
            try:
                self.parent.after_cancel(timer_id)
            except Exception as e:
                self.logger.debug(f"Error canceling timer {timer_id}: {e}")
        self._timer_ids.clear()
    
    def cleanup(self):
        """
        Perform any cleanup operations when the section is destroyed.
        
        This includes canceling timers, stopping threads, and releasing resources.
        Subclasses should call this base implementation when overriding.
        """
        try:
            # Unbind mousewheel events
            self._unbind_mousewheel()
            
            # Cancel all pending timers
            self._cancel_all_timers()
            
            self.logger.debug(f"Base section cleanup completed for {self.__class__.__name__}")
            
        except Exception as e:
            self.logger.error(f"Error during base section cleanup: {e}")