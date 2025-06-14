#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test History Section module for the Multi-Chamber Test application.

This module provides the HistorySection class that displays test history
and allows viewing detailed test results and filtering past tests.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging
import threading
import time
from datetime import datetime, timedelta
import csv
import os
from typing import Dict, Any, List, Optional, Tuple

from multi_chamber_test.config.constants import UI_COLORS, UI_FONTS
from multi_chamber_test.ui.settings.base_section import BaseSection
from multi_chamber_test.database.test_result_db import TestResultDatabase


class HistorySection(BaseSection):
    """
    Test history section for viewing historical test results.
    
    This section displays a list of past tests with their results and allows
    filtering by date, exporting results, and viewing detailed test information.
    """
    
    def __init__(self, parent, test_manager=None):
        """
        Initialize the test history section.
        
        Args:
            parent: Parent widget
            test_manager: TestManager (optional, for backward compatibility - not used)
        """
        # test_manager is no longer used but kept for backward compatibility
        if test_manager is not None:
            pass  # Ignore the test_manager parameter
        
        # Initialize the test results database
        self.test_db = TestResultDatabase()
        
        # State variables
        self.filter_date = tk.StringVar(value="All Time")
        self.test_records = []
        self.filtered_records = []
        
        # Call base class constructor
        super().__init__(parent)
    
    def create_widgets(self):
        """Create UI widgets for the test history section."""
        # Section title
        title_frame = ttk.Frame(self.content_frame, style='Content.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(
            title_frame,
            text="?? Test History",
            style='ContentTitle.TLabel'
        ).pack(anchor=tk.W)
        
        # Create main history browser
        self.create_history_browser()
        
        # Create detail view (initially hidden)
        self.create_detail_view()
    
    def create_history_browser(self):
        """Create the test history browser with filtering."""
        card, content = self.create_card("Test Records", "View and filter past test results.")
        
        # Filter controls
        filter_frame = ttk.Frame(content, style='Card.TFrame')
        filter_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(filter_frame, text="Filter:", style='CardText.TLabel').pack(side=tk.LEFT)
        
        # Time filter dropdown
        time_options = ["All Time", "Today", "Last 7 Days", "Last 30 Days", "Last 90 Days"]
        time_dropdown = ttk.Combobox(
            filter_frame, textvariable=self.filter_date, values=time_options,
            state="readonly", width=15
        )
        time_dropdown.pack(side=tk.LEFT, padx=10)
        time_dropdown.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        
        # Control buttons
        ttk.Button(filter_frame, text="Refresh", command=self.load_test_records,
                  style='Secondary.TButton').pack(side=tk.RIGHT)
        
        ttk.Button(filter_frame, text="Export All", command=self.export_all_results,
                  style='Secondary.TButton').pack(side=tk.RIGHT, padx=10)
        
        # Create table for test records
        self.create_test_table(content)
    
    def create_test_table(self, parent):
        """Create the table for displaying test records."""
        table_frame = ttk.Frame(parent, style='Card.TFrame')
        table_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create Treeview widget
        columns = ('timestamp', 'duration', 'mode', 'result', 'chamber1', 'chamber2', 'chamber3', 'reference')
        
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse', height=15)
        
        # Configure columns
        column_config = {
            'timestamp': ('Date & Time', 150),
            'duration': ('Duration (s)', 80),
            'mode': ('Test Mode', 100),
            'result': ('Result', 80),
            'chamber1': ('Chamber 1', 100),
            'chamber2': ('Chamber 2', 100),
            'chamber3': ('Chamber 3', 100),
            'reference': ('Reference ID', 150)
        }
        
        for col, (text, width) in column_config.items():
            self.tree.column(col, width=width, anchor='center')
            self.tree.heading(col, text=text)
        
        # Add scrollbars
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        
        # Pack components
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind events
        self.tree.bind('<Double-1>', self.view_test_details)
        
        # Action buttons
        action_frame = ttk.Frame(parent, style='Card.TFrame')
        action_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(action_frame, text="View Details", command=self.view_selected_test,
                  style='Action.TButton').pack(side=tk.LEFT)
        
        ttk.Button(action_frame, text="Export Selected", command=self.export_selected_test,
                  style='Secondary.TButton').pack(side=tk.RIGHT)
    
    def create_detail_view(self):
        """Create the detailed test view panel (initially hidden)."""
        self.detail_frame = ttk.Frame(self.content_frame, style='Card.TFrame')
        
        # Header with back button
        header_frame = ttk.Frame(self.detail_frame, style='Card.TFrame', padding=10)
        header_frame.pack(fill=tk.X)
        
        ttk.Button(header_frame, text="? Back", command=self.hide_test_details,
                  style='Secondary.TButton').pack(side=tk.LEFT)
        
        self.detail_title = ttk.Label(header_frame, text="Test Details", style='CardTitle.TLabel')
        self.detail_title.pack(side=tk.LEFT, padx=(20, 0))
        
        # Detail content container
        self.detail_content = ttk.Frame(self.detail_frame, style='Card.TFrame', padding=10)
        self.detail_content.pack(fill=tk.BOTH, expand=True)
    
    def load_test_records(self):
        """Load test records from the database."""
        try:
            self.frame.config(cursor="watch")
            threading.Thread(target=self._load_records_thread, daemon=True).start()
        except Exception as e:
            self.logger.error(f"Error starting record load: {e}")
            self.frame.config(cursor="")
            self.show_feedback(f"Error loading records: {str(e)}", is_error=True)
    
    def _load_records_thread(self):
        """Background thread for loading test records."""
        try:
            self.test_records = self.test_db.get_all_results()
            self._schedule_ui_update(self._finish_loading_records)
        except Exception as e:
            self.logger.error(f"Database error: {e}")
            self._schedule_ui_update(lambda: self._handle_loading_error(str(e)))
    
    def _finish_loading_records(self):
        """Complete the record loading process."""
        try:
            self.frame.config(cursor="")
            
            if not self.test_records:
                self.show_feedback("No test records found", is_error=False)
                self.filtered_records = []
                self.display_records([])
                return
                
            self.show_feedback(f"Loaded {len(self.test_records)} records", is_error=False)
            self.apply_filters()
        except Exception as e:
            self.logger.error(f"Error displaying records: {e}")
            self.show_feedback(f"Display error: {str(e)}", is_error=True)
    
    def _handle_loading_error(self, error_message):
        """Handle loading errors."""
        self.frame.config(cursor="")
        self.show_feedback(f"Loading error: {error_message}", is_error=True)
    
    def apply_filters(self):
        """Apply selected filters to test records."""
        if not self.test_records:
            self.filtered_records = []
            self.display_records([])
            return
            
        self.filtered_records = self.filter_records(self.test_records)
        self.display_records(self.filtered_records)
    
    def filter_records(self, records):
        """Filter test records based on selected criteria."""
        filter_option = self.filter_date.get()
        
        if filter_option == "All Time":
            return records
        
        # Calculate date cutoff
        now = datetime.now()
        cutoff_map = {
            "Today": now.replace(hour=0, minute=0, second=0, microsecond=0),
            "Last 7 Days": now - timedelta(days=7),
            "Last 30 Days": now - timedelta(days=30),
            "Last 90 Days": now - timedelta(days=90)
        }
        
        cutoff = cutoff_map.get(filter_option)
        if not cutoff:
            return records
        
        # Filter by timestamp
        filtered = []
        for record in records:
            try:
                timestamp = datetime.fromisoformat(record['timestamp'])
                if timestamp >= cutoff:
                    filtered.append(record)
            except (ValueError, TypeError):
                pass  # Skip invalid timestamps
        return filtered
    
    def display_records(self, records):
        """Display filtered records in the tree view."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add records
        for record in records:
            try:
                # Format values
                timestamp = record['timestamp']
                duration = str(record['test_duration'])
                mode = record['test_mode'] or "Unknown"
                result = 'PASS' if record['overall_result'] else 'FAIL'
                reference = record.get('reference', 'N/A')
                
                # Get chamber results
                chambers = record.get('chambers', [])
                chamber_results = []
                
                # Ensure 3 chambers
                while len(chambers) < 3:
                    chambers.append({'enabled': False})
                
                for chamber in chambers:
                    if chamber.get('enabled', False):
                        pressure = chamber.get('final_pressure', 0)
                        status = 'OK' if chamber.get('result', False) else 'FAIL'
                        chamber_results.append(f"{pressure:.1f} ({status})")
                    else:
                        chamber_results.append("Disabled")
                
                # Add to tree
                values = [timestamp, duration, mode, result] + chamber_results + [reference]
                item_id = self.tree.insert('', 'end', values=values)
                
                # Color by result
                tag = 'pass' if record['overall_result'] else 'fail'
                self.tree.item(item_id, tags=(tag,))
                
            except Exception as e:
                self.logger.error(f"Error displaying record: {e}")
        
        # Configure tag colors
        self.tree.tag_configure('pass', background='#DFF0D8')
        self.tree.tag_configure('fail', background='#F2DEDE')
    
    def view_selected_test(self):
        """View details of selected test."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a test to view.")
            return
        
        item_values = self.tree.item(selected[0], 'values')
        if not item_values:
            messagebox.showerror("Error", "Invalid selection.")
            return
        
        timestamp = item_values[0]
        
        # Find corresponding record
        for record in self.filtered_records:
            if record['timestamp'] == timestamp:
                self.show_test_details(record)
                return
        
        messagebox.showerror("Error", "Could not find test details.")
    
    def view_test_details(self, event):
        """Handle double-click event."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            self.view_selected_test()
    
    def show_test_details(self, record):
        """Show detailed view of a test record."""
        # Hide browser, show detail view
        self.tree.master.master.pack_forget()
        self.detail_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Set title
        self.detail_title.config(text=f"Test Details - {record['timestamp']}")
        
        # Clear existing content
        for widget in self.detail_content.winfo_children():
            widget.destroy()
        
        # Add details
        self.populate_test_details(record)
    
    def hide_test_details(self):
        """Hide detail view and show browser."""
        self.detail_frame.pack_forget()
        self.tree.master.master.pack(fill=tk.BOTH, expand=True, pady=10)
    
    def populate_test_details(self, record):
        """Populate detail view with test information."""
        # Test summary section
        summary_frame = ttk.LabelFrame(self.detail_content, text="Test Summary")
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        summary_grid = ttk.Frame(summary_frame)
        summary_grid.pack(fill=tk.X, padx=10, pady=10)
        
        # Summary fields
        fields = [
                    ("Date & Time",       record['timestamp']),
                    ("Duration",          f"{record['test_duration']} seconds"),
                    ("Test Mode",         record['test_mode'] or "Unknown"),
                    ("Operator ID",       record.get('operator_id', 'N/A')),
                    ("Operator Name",     record.get('operator_name', 'N/A')),
                    ("Reference",         record.get('reference', 'N/A')),
                    ("Overall Result",    "PASS" if record['overall_result'] else "FAIL")
        ]
        
        for i, (label, value) in enumerate(fields):
            row, col = i // 3, (i % 3) * 2
            
            ttk.Label(summary_grid, text=f"{label}:", font=('Helvetica', 10, 'bold')).grid(
                row=row, column=col, sticky='w', padx=(10, 5), pady=5)
            
            color = UI_COLORS.get('SUCCESS' if value == "PASS" else 'ERROR' if value == "FAIL" else 'TEXT_PRIMARY', 'black')
            ttk.Label(summary_grid, text=value, foreground=color).grid(
                row=row, column=col+1, sticky='w', padx=(0, 20), pady=5)
        
        # Chamber results section
        chambers_frame = ttk.LabelFrame(self.detail_content, text="Chamber Results")
        chambers_frame.pack(fill=tk.X, pady=(0, 10))
        
        chamber_grid = ttk.Frame(chambers_frame)
        chamber_grid.pack(fill=tk.X, padx=10, pady=10)
        
        # Headers
        headers = ["Chamber", "Status", "Target", "Actual", "Threshold", "Result"]
        for col, header in enumerate(headers):
            ttk.Label(chamber_grid, text=header, font=('Helvetica', 10, 'bold')).grid(
                row=0, column=col, sticky='w', padx=10, pady=(0, 5))
        
        # Chamber data
        chambers = record.get('chambers', [])
        while len(chambers) < 3:
            chambers.append({'enabled': False, 'chamber_id': len(chambers)})
        
        for chamber in chambers:
            chamber_id = chamber.get('chamber_id', 0)
            row = chamber_id + 1
            
            ttk.Label(chamber_grid, text=f"Chamber {chamber_id+1}").grid(
                row=row, column=0, sticky='w', padx=10, pady=5)
            
            if chamber.get('enabled', False):
                # Enabled chamber data
                data = [
                    "Enabled",
                    f"{chamber.get('pressure_target', 0):.1f}",
                    f"{chamber.get('final_pressure', 0):.1f}",
                    f"{chamber.get('pressure_threshold', 0):.1f}",
                    "PASS" if chamber.get('result', False) else "FAIL"
                ]
                
                for col, value in enumerate(data, 1):
                    color = 'black'
                    if col == 5:  # Result column
                        color = UI_COLORS.get('SUCCESS' if value == "PASS" else 'ERROR', 'black')
                    
                    ttk.Label(chamber_grid, text=value, foreground=color).grid(
                        row=row, column=col, sticky='w', padx=10, pady=5)
            else:
                # Disabled chamber
                ttk.Label(chamber_grid, text="Disabled", 
                         foreground=UI_COLORS.get('TEXT_SECONDARY', 'gray')).grid(
                    row=row, column=1, columnspan=5, sticky='w', padx=10, pady=5)
        
        # Export button
        export_frame = ttk.Frame(self.detail_content)
        export_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(export_frame, text="Export This Record", 
                  command=lambda: self.export_record_to_csv(record),
                  style='Secondary.TButton').pack(side=tk.RIGHT)
    
    def export_selected_test(self):
        """Export selected test to CSV."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a test to export.")
            return
        
        item_values = self.tree.item(selected[0], 'values')
        if not item_values:
            messagebox.showerror("Error", "Invalid selection.")
            return
        
        timestamp = item_values[0]
        
        for record in self.filtered_records:
            if record['timestamp'] == timestamp:
                self.export_record_to_csv(record)
                return
        
        messagebox.showerror("Error", "Could not find test details.")
    
    def export_all_results(self):
        """Export all filtered results to CSV."""
        if not self.filtered_records:
            messagebox.showinfo("No Records", "No test records to export.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Test Records"
        )
        
        if file_path:
            try:
                self.frame.config(cursor="watch")
                threading.Thread(target=self._export_records_thread, 
                               args=(self.filtered_records, file_path), daemon=True).start()
            except Exception as e:
                self.logger.error(f"Export error: {e}")
                self.frame.config(cursor="")
                messagebox.showerror("Export Error", f"Export failed: {str(e)}")
    
    def _export_records_thread(self, records, file_path):
        """Background thread for exporting records."""
        try:
            self._export_to_csv(records, file_path)
            self._schedule_ui_update(lambda: self._show_export_success(file_path))
        except Exception as e:
            self.logger.error(f"Export error: {e}")
            self._schedule_ui_update(lambda: self._show_export_error(str(e)))
    
    def _show_export_success(self, file_path):
        """Show export success message."""
        self.frame.config(cursor="")
        messagebox.showinfo("Export Successful", f"Records exported to:\n{file_path}")
    
    def _show_export_error(self, error):
        """Show export error message."""
        self.frame.config(cursor="")
        messagebox.showerror("Export Error", f"Export failed: {error}")
    
    def export_record_to_csv(self, record):
        """Export single record to CSV."""
        default_filename = f"test_{record['timestamp'].replace(':', '-').replace(' ', '_')}.csv"
        default_filename = default_filename.replace('/', '-').replace('\\', '-')
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_filename,
            title="Export Test Record"
        )
        
        if file_path:
            try:
                self._export_to_csv([record], file_path)
                messagebox.showinfo("Export Successful", f"Record exported to:\n{file_path}")
            except Exception as e:
                self.logger.error(f"Export error: {e}")
                messagebox.showerror("Export Error", f"Export failed: {str(e)}")
    
    def _export_to_csv(self, records, file_path):
        """Write records to CSV file."""
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header section
            writer.writerow(["Test ID", "Timestamp", "Operator", "Test Mode", "Reference", 
                           "Duration (s)", "Overall Result"])
            
            # Summary data
            for record in records:
                writer.writerow([
                    record.get('id', ''),
                    record['timestamp'],
                    record.get('operator_id', 'N/A'),
                    record.get('test_mode', 'Unknown'),
                    record.get('reference', 'N/A'),
                    record['test_duration'],
                    "PASS" if record['overall_result'] else "FAIL"
                ])
            
            # Chamber details section
            writer.writerow([])
            writer.writerow(["Test ID", "Chamber", "Enabled", "Target", "Threshold", 
                           "Tolerance", "Final Pressure", "Result"])
            
            for record in records:
                test_id = record.get('id', '')
                for chamber in record.get('chambers', []):
                    writer.writerow([
                        test_id,
                        f"Chamber {chamber.get('chamber_id', 0) + 1}",
                        "Yes" if chamber.get('enabled', False) else "No",
                        chamber.get('pressure_target', 0),
                        chamber.get('pressure_threshold', 0),
                        chamber.get('pressure_tolerance', 0),
                        chamber.get('final_pressure', 0),
                        "PASS" if chamber.get('result', False) else "FAIL"
                    ])
    
    def refresh_all(self):
        """Refresh all UI components."""
        self.load_test_records()
    
    def on_selected(self):
        """Called when section is selected."""
        super().on_selected()
        self.load_test_records()