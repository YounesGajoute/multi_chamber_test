#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Export Settings section for the Multi-Chamber Test application.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
from typing import Optional, Dict, Any

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS
from multi_chamber_test.ui.settings.base_section import BaseSection
from multi_chamber_test.database.test_result_db import TestResultDatabase
from multi_chamber_test.utils.file_exporter import FileExporter


class ExportSection(BaseSection):
    """Data Export settings section for exporting test results."""
    
    def __init__(self, parent, test_manager=None):
        # Create file exporter and database
        self.file_exporter = FileExporter()
        self.database = TestResultDatabase()
        
        # test_manager is no longer used but kept for backward compatibility
        if test_manager is not None:
            pass  # Ignore the test_manager parameter
        
        # State variables
        self.usb_connected = False
        self.usb_detection_active = False
        self.usb_detection_thread = None
        self.usb_path = None
        self.usb_info = {}
        self.detection_interval = 2.0
        self.detection_last_change = 0
        
        super().__init__(parent)
    
    def create_widgets(self):
        """Create UI widgets for the export settings section."""
        # Title
        title_frame = ttk.Frame(self.content_frame, style='Content.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(
            title_frame,
            text="?? Data Export",
            style='ContentTitle.TLabel'
        ).pack(anchor=tk.W)
        
        # Status message
        ttk.Label(
            self.content_frame,
            text="Insert USB drive to export test data.",
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray'),
            background=UI_COLORS.get('BACKGROUND', 'white'),
            wraplength=600
        ).pack(anchor=tk.W, pady=(0, 20))
        
        # Create cards
        self.create_usb_status_card()
        self.create_export_options_card()
        self.create_usb_management_card()
        
        # Bottom padding
        ttk.Frame(self.content_frame, height=20).pack(fill=tk.X)
    
    def create_usb_status_card(self):
        """Create USB status card."""
        card, content = self.create_card("USB Status", "Connect USB drive to export.")
        
        # Status indicator
        status_frame = ttk.Frame(content, style='Card.TFrame')
        status_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(status_frame, text="Status:", font=UI_FONTS.get('LABEL', ('Helvetica', 12))).pack(side=tk.LEFT)
        
        # Status display
        self.status_frame = ttk.Frame(status_frame, style='Card.TFrame')
        self.status_frame.pack(side=tk.LEFT, padx=15)
        
        self.status_icon = ttk.Label(self.status_frame, text="?", font=('Helvetica', 16))
        self.status_icon.pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(
            self.status_frame,
            text="Not Connected",
            font=UI_FONTS.get('VALUE', ('Helvetica', 12, 'bold')),
            foreground=UI_COLORS.get('ERROR', 'red')
        )
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Check button
        self.recheck_button = ttk.Button(status_frame, text="Check", command=self._check_usb_now)
        self.recheck_button.pack(side=tk.RIGHT)
        
        # Path display
        self.path_frame = ttk.Frame(content, style='Card.TFrame')
        ttk.Label(self.path_frame, text="Path:", font=UI_FONTS.get('LABEL', ('Helvetica', 12))).pack(side=tk.LEFT)
        self.path_label = ttk.Label(
            self.path_frame, text="N/A", font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        )
        self.path_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Space info
        self.space_frame = ttk.Frame(content, style='Card.TFrame')
        ttk.Label(self.space_frame, text="Space:", font=UI_FONTS.get('LABEL', ('Helvetica', 12))).pack(side=tk.LEFT)
        self.space_label = ttk.Label(
            self.space_frame, text="N/A", font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        )
        self.space_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Hide initially
        self.path_frame.pack_forget()
        self.space_frame.pack_forget()
    
    def create_export_options_card(self):
        """Create export options card."""
        card, content = self.create_card("Export Options", "Choose data to export.")
        
        # Export all button
        export_all_frame = ttk.Frame(content, style='Card.TFrame')
        export_all_frame.pack(fill=tk.X, pady=10)
        
        self.export_all_button = ttk.Button(
            export_all_frame, text="Export All Results", command=self._export_all_tests,
            state='disabled', width=20
        )
        self.export_all_button.pack(side=tk.LEFT)
        
        ttk.Label(
            export_all_frame, text="Complete test history",
            font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        ).pack(side=tk.LEFT, padx=(15, 0))
        
        # Export last button
        export_last_frame = ttk.Frame(content, style='Card.TFrame')
        export_last_frame.pack(fill=tk.X, pady=10)
        
        self.export_last_button = ttk.Button(
            export_last_frame, text="Export Last Result", command=self._export_last_test,
            state='disabled', width=20
        )
        self.export_last_button.pack(side=tk.LEFT)
        
        ttk.Label(
            export_last_frame, text="Most recent test only",
            font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        ).pack(side=tk.LEFT, padx=(15, 0))
    
    def create_usb_management_card(self):
        """Create USB management card."""
        card, content = self.create_card("USB Management", "Safely remove USB drive.")
        
        unmount_frame = ttk.Frame(content, style='Card.TFrame')
        unmount_frame.pack(fill=tk.X, pady=10)
        
        self.unmount_button = ttk.Button(
            unmount_frame, text="Safely Remove", command=self._safely_unmount_usb,
            state='disabled', width=15
        )
        self.unmount_button.pack(side=tk.LEFT)
        
        ttk.Label(
            unmount_frame, text="Unmount before removing",
            font=('Helvetica', 10, 'italic'),
            foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')
        ).pack(side=tk.LEFT, padx=(15, 0))
    
    def _check_usb_now(self):
        """Check USB status now."""
        self.recheck_button.config(state='disabled')
        self.status_icon.config(text="??")
        self.status_label.config(text="Checking...", foreground=UI_COLORS.get('PRIMARY', 'blue'))
        
        threading.Thread(target=self._perform_usb_check, daemon=True).start()
    
    def _perform_usb_check(self):
        """Perform USB check in background."""
        try:
            is_connected = self.file_exporter.is_usb_connected()
            usb_path = self.file_exporter.find_usb_path() if is_connected else None
            usb_info = self.file_exporter.get_usb_info() if is_connected else {}
            
            self._schedule_ui_update(lambda: self._update_usb_status(is_connected, usb_path, usb_info))
            self.detection_last_change = time.time()
            
        except Exception as e:
            self.logger.error(f"USB check error: {e}")
            self._schedule_ui_update(lambda: self._show_usb_error(str(e)))
    
    def _update_usb_status(self, is_connected: bool, usb_path: Optional[str] = None, usb_info: Dict[str, Any] = None):
        """Update USB status display."""
        old_status = self.usb_connected
        self.usb_connected = is_connected
        self.usb_path = usb_path
        self.usb_info = usb_info or {}
        
        if is_connected:
            self.status_icon.config(text="?")
            self.status_label.config(text="Connected", foreground=UI_COLORS.get('SUCCESS', 'green'))
            
            if usb_path:
                self.path_label.config(text=usb_path)
                self.path_frame.pack(fill=tk.X, pady=(0, 10))
                
                if usb_info:
                    free_space = usb_info.get('free_space', 0)
                    total_space = usb_info.get('total_space', 0)
                    
                    if free_space > 0 and total_space > 0:
                        free_gb = free_space / (1024**3)
                        total_gb = total_space / (1024**3)
                        filesystem = usb_info.get('filesystem', 'Unknown')
                        
                        space_text = f"{free_gb:.1f}/{total_gb:.1f} GB ({filesystem})"
                        self.space_label.config(text=space_text)
                        self.space_frame.pack(fill=tk.X, pady=(0, 10))
            
            # Enable buttons
            self.export_all_button.config(state='normal')
            self.export_last_button.config(state='normal')
            self.unmount_button.config(state='normal')
            
        else:
            self.status_icon.config(text="?")
            self.status_label.config(text="Not Connected", foreground=UI_COLORS.get('ERROR', 'red'))
            
            self.path_frame.pack_forget()
            self.space_frame.pack_forget()
            
            # Disable buttons
            self.export_all_button.config(state='disabled')
            self.export_last_button.config(state='disabled')
            self.unmount_button.config(state='disabled')
        
        self.recheck_button.config(state='normal')
        
        # Log status change
        if old_status != is_connected:
            if is_connected:
                self.logger.info(f"USB connected: {usb_path}")
                self.show_feedback(f"USB connected")
            else:
                self.logger.info("USB disconnected")
                self.show_feedback("USB disconnected")
    
    def _show_usb_error(self, error_message: str):
        """Show USB error state."""
        self.status_icon.config(text="??")
        self.status_label.config(text="Error", foreground=UI_COLORS.get('WARNING', 'orange'))
        self.recheck_button.config(state='normal')
        
        self.export_all_button.config(state='disabled')
        self.export_last_button.config(state='disabled')
        self.unmount_button.config(state='disabled')
        
        self.show_feedback(f"USB error: {error_message}", is_error=True)
    
    def _export_all_tests(self):
        """Export all test results."""
        if not self.usb_connected:
            messagebox.showwarning("USB Not Connected", "Connect USB drive first.")
            return
        
        if not messagebox.askyesno("Export All", "Export all test results?"):
            return
        
        self._start_export_operation()
        
        def do_export():
            try:
                test_data = self._get_all_test_data()
                if not test_data:
                    self._schedule_ui_update(lambda: messagebox.showinfo("No Data", "No test results found."))
                    return
                
                success = self.file_exporter.export_all_tests(test_data)
                self._schedule_ui_update(lambda: self._show_export_result(success, len(test_data)))
                
            except Exception as e:
                self.logger.error(f"Export error: {e}")
                self._schedule_ui_update(lambda: messagebox.showerror("Export Error", f"Export failed: {e}"))
            finally:
                self._schedule_ui_update(lambda: self._end_export_operation())
        
        threading.Thread(target=do_export, daemon=True).start()
    
    def _export_last_test(self):
        """Export last test result."""
        if not self.usb_connected:
            messagebox.showwarning("USB Not Connected", "Connect USB drive first.")
            return
        
        self._start_export_operation()
        
        def do_export():
            try:
                test_data = self._get_last_test_data()
                if not test_data:
                    self._schedule_ui_update(lambda: messagebox.showinfo("No Data", "No recent test found."))
                    return
                
                success = self.file_exporter.export_last_test(test_data)
                self._schedule_ui_update(lambda: self._show_export_result(success, 1))
                
            except Exception as e:
                self.logger.error(f"Export error: {e}")
                self._schedule_ui_update(lambda: messagebox.showerror("Export Error", f"Export failed: {e}"))
            finally:
                self._schedule_ui_update(lambda: self._end_export_operation())
        
        threading.Thread(target=do_export, daemon=True).start()
    
    def _safely_unmount_usb(self):
        """Safely unmount USB drive."""
        if not self.usb_connected:
            messagebox.showwarning("USB Not Connected", "No USB drive connected.")
            return
        
        if not messagebox.askyesno("Unmount USB", f"Safely remove USB drive?\n\nPath: {self.usb_path}"):
            return
        
        self.frame.config(cursor="watch")
        self.unmount_button.config(state='disabled')
        
        def do_unmount():
            try:
                success = self.file_exporter.safely_unmount_usb()
                if success:
                    self._schedule_ui_update(lambda: self._handle_unmount_success())
                else:
                    self._schedule_ui_update(lambda: self._handle_unmount_error())
            except Exception as e:
                self.logger.error(f"Unmount error: {e}")
                self._schedule_ui_update(lambda: self._handle_unmount_error(str(e)))
        
        threading.Thread(target=do_unmount, daemon=True).start()
    
    def _handle_unmount_success(self):
        """Handle successful unmount."""
        self.frame.config(cursor="")
        messagebox.showinfo("USB Unmounted", "USB drive safely removed.")
        self._check_usb_now()
    
    def _handle_unmount_error(self, error_message: str = None):
        """Handle unmount error."""
        self.frame.config(cursor="")
        self.unmount_button.config(state='normal' if self.usb_connected else 'disabled')
        
        error_msg = "Failed to unmount USB drive"
        if error_message:
            error_msg += f": {error_message}"
        
        messagebox.showerror("Unmount Error", error_msg)
    
    def _get_all_test_data(self):
        """Get all test data."""
        try:
            test_data = self.database.get_all_results()
            self.logger.info(f"Retrieved {len(test_data)} records")
            return test_data
        except Exception as e:
            self.logger.error(f"Database error: {e}")
            return []
    
    def _get_last_test_data(self):
        """Get last test data."""
        try:
            all_tests = self.database.get_all_results()
            if all_tests:
                last_test = all_tests[-1]
                self.logger.info(f"Retrieved last test: ID {last_test.get('id', 'Unknown')}")
                return last_test
            return None
        except Exception as e:
            self.logger.error(f"Error getting last test: {e}")
            return None
    
    def _show_export_result(self, success: bool, record_count: int = 0):
        """Show export result."""
        if success:
            record_text = f"{record_count} record{'s' if record_count != 1 else ''}"
            messagebox.showinfo("Export Complete", f"Exported {record_text} successfully.")
            self.show_feedback(f"Export complete: {record_text}")
        else:
            messagebox.showerror("Export Failed", "Export failed. Check USB drive.")
            self.show_feedback("Export failed", is_error=True)
    
    def _start_export_operation(self):
        """Start export operation UI state."""
        self.frame.config(cursor="watch")
        self.parent.config(cursor="watch")
        self.export_all_button.config(state='disabled')
        self.export_last_button.config(state='disabled')
    
    def _end_export_operation(self):
        """End export operation UI state."""
        self.frame.config(cursor="")
        self.parent.config(cursor="")
        if self.usb_connected:
            self.export_all_button.config(state='normal')
            self.export_last_button.config(state='normal')
    
    def _start_usb_detection(self):
        """Start USB detection thread."""
        if self.usb_detection_active:
            return
            
        self.usb_detection_active = True
        self.usb_detection_thread = threading.Thread(
            target=self._run_usb_detection, daemon=True, name="UsbDetection"
        )
        self.usb_detection_thread.start()
        self.logger.debug("USB detection started")
    
    def _stop_usb_detection(self):
        """Stop USB detection thread."""
        self.usb_detection_active = False
        self.usb_detection_thread = None
        self.logger.debug("USB detection stopped")
    
    def _run_usb_detection(self):
        """USB detection thread function."""
        last_check_time = 0
        last_status = None
        
        while self.usb_detection_active:
            try:
                current_time = time.time()
                if current_time - last_check_time < self.detection_interval:
                    time.sleep(0.1)
                    continue
                    
                last_check_time = current_time
                
                if current_time - self.detection_last_change < self.detection_interval:
                    time.sleep(0.1)
                    continue
                
                is_connected = self.file_exporter.is_usb_connected()
                
                if last_status != is_connected:
                    last_status = is_connected
                    usb_path = self.file_exporter.find_usb_path() if is_connected else None
                    usb_info = self.file_exporter.get_usb_info() if is_connected else {}
                    
                    self._schedule_ui_update(
                        lambda c=is_connected, p=usb_path, i=usb_info: self._update_usb_status(c, p, i)
                    )
                
                time.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"USB detection error: {e}")
                time.sleep(1.0)
    
    def refresh_all(self):
        """Refresh UI components."""
        self._check_usb_now()
    
    def update_from_monitoring(self):
        """Update from monitoring thread."""
        pass
    
    def on_selected(self):
        """Called when section is selected."""
        super().on_selected()
        self._start_usb_detection()
        self._check_usb_now()
    
    def on_deselected(self):
        """Called when section is deselected."""
        self._stop_usb_detection()
        return True
    
    def cleanup(self):
        """Cleanup operations."""
        self._stop_usb_detection()
        super().cleanup()