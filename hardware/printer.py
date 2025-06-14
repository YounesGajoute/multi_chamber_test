#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fixed Printer module for the Multi-Chamber Test application.

This module provides a PrinterManager class that interfaces with a USB
printer device (Zebra ZD421) via the standard USB printer interface.
"""

import logging
import time
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

class PrinterManager:
    """
    Manager for USB printer operations via device file.
    
    This class provides methods to send ZPL commands to a Zebra printer
    connected as a USB printer device.
    """
    
    def __init__(self):
        """Initialize the PrinterManager."""
        self.logger = logging.getLogger('PrinterManager')
        self._setup_logger()
        
        # Possible device paths in order of preference
        self.device_paths = [
            "/dev/zebra_printer",  # udev symlink
            "/dev/usb/lp0",       # standard USB printer device
            "/dev/usb/lp1",       # alternate USB printer device
        ]
        
        self.device_path = None
        self._find_printer()
    
    def _setup_logger(self):
        """Configure logging for the printer manager."""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _find_printer(self):
        """Find the printer device."""
        for path in self.device_paths:
            if os.path.exists(path):
                try:
                    # Test if we can open the device
                    with open(path, 'wb') as f:
                        pass
                    self.device_path = path
                    self.logger.info(f"Printer found at: {path}")
                    return
                except PermissionError:
                    self.logger.warning(f"Permission denied for {path}")
                except Exception as e:
                    self.logger.warning(f"Cannot access {path}: {e}")
        
        self.logger.warning("No accessible printer device found")
    
    def connect(self) -> bool:
        """
        Connect to the printer (compatibility method).
        
        Returns:
            bool: True if printer device is available, False otherwise
        """
        self._find_printer()
        return self.device_path is not None
    
    def is_printer_available(self) -> bool:
        """
        Check if the printer is available.
        
        Returns:
            bool: True if printer is available, False otherwise
        """
        return self.device_path is not None and os.path.exists(self.device_path)
    
    def _send_zpl(self, zpl_commands: str) -> bool:
        """
        Send ZPL commands to the printer.
        
        Args:
            zpl_commands: ZPL command string to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.device_path:
            self.logger.error("No printer device available")
            return False
        
        try:
            with open(self.device_path, 'wb') as printer:
                printer.write(zpl_commands.encode('utf-8'))
                printer.flush()
            self.logger.debug(f"Sent {len(zpl_commands)} bytes to printer")
            return True
        except PermissionError:
            self.logger.error(f"Permission denied writing to {self.device_path}")
            self.logger.info("Try: sudo chmod 666 " + self.device_path)
            return False
        except Exception as e:
            self.logger.error(f"Error writing to printer: {e}")
            return False
    
    def print_test_results(self, test_data: List[Dict[str, Any]]) -> bool:
        """
        Print test results with specific label format only if all chambers pass
    
        Args:
            test_data: List of dictionaries containing test results for each chamber
    
        Returns:
            bool: True if printing was successful, False otherwise
        """
        try:
            # 1. Check if all enabled chambers passed
            all_passed = all(
                chamber.get('result') == 'PASS'
                for chamber in test_data
                if chamber.get('enabled', True)
            )
    
            if not all_passed:
                self.logger.info("Not printing results - one or more chambers failed")
                return False
    
            # 2. Get current timestamp
            now = datetime.now()
            date_str = now.strftime("%d/%m/%Y")
            time_str = now.strftime("%H:%M:%S")
    
            # 3. Get reference and operator_id from the first chamber s data
            reference = test_data[0].get('reference', "")
            operator_id = test_data[0].get('operator_id', "")
    
            # 4. Prepare stripped values:
            #    - For model line, strip first 3 characters if possible
            if reference and len(reference) > 3:
                stripped_model = reference[3:]
            else:
                stripped_model = reference
    
            #    - For barcode, strip first 7 characters if possible
            if reference and len(reference) > 7:
                stripped_barcode = reference[7:]
            else:
                stripped_barcode = reference
    
            # 5. Build ZPL, inserting "OP:<operator_id>" and using stripped_barcode in the barcodes
            zpl = (
                "^XA\n"
                "^PW799^LH70,10\n"
                "^A0N,25,25^FO70,15^FDLEAR - KENITRA^FS\n"
                "^A0N,25,25^FO70,50^FDGROMET EB V216^FS\n"
                f"^A0N,25,25^FO70,85^FDOp.Nr.{operator_id}^FS\n"
                f"^A0N,50,50^FO70,140^FD{stripped_model}^FS\n"
                f"^A0N,25,25^FO70,210^FDDATE:{date_str}^FS\n"
                f"^A0N,25,25^FO70,240^FDTIME:{time_str}^FS\n"
                "^A0N,50,50^FO70,280^FDGROMMET TEST PASS^FS\n"
                # Right vertical barcode
                "^FT570,75\n"
                f"^BY2^BCR,50,Y,N,N^FD{stripped_barcode}^FS\n"
                # Bottom horizontal barcode
                "^FT0,285\n"
                f"^BY2^BCB,50,Y,N,N^FD{stripped_barcode}^FS\n"
                "^XZ"
            )
            
            # 6. Send ZPL to printer
            success = self._send_zpl(zpl)
            if success:
                self.logger.info(f"Test results printed successfully for reference: {reference}")
            return success
    
        except Exception as e:
            self.logger.error(f"Printing error: {e}")
            return False
    
    def print_calibration_report(self, calibration_data: Dict[str, Any]) -> bool:
        """
        Print a calibration report.
        
        Args:
            calibration_data: Dictionary containing calibration data
            
        Returns:
            bool: True if printing was successful, False otherwise
        """
        try:
            chamber_num = calibration_data.get('chamber_number', 'N/A')
            date = calibration_data.get('date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            voltage_offset = calibration_data.get('voltage_offset', 'N/A')
            voltage_multiplier = calibration_data.get('voltage_multiplier', 'N/A')
            points = calibration_data.get('points', [])
            
            # Create ZPL commands
            zpl = f"""^XA
^MMT
^PW400
^LL800
^LS0
^MNY
^FO20,20^A0N,35,35^FDCalibration Report^FS
^FO20,60^A0N,25,25^FDChamber {chamber_num}^FS
^FO20,100^A0N,20,20^FD{date}^FS
^FO20,150^A0N,25,25^FDOffset: {voltage_offset}^FS
^FO20,180^A0N,25,25^FDMultiplier: {voltage_multiplier}^FS
^FO20,210^GB360,3,3^FS
^FO20,230^A0N,25,25^FDCalibration Points:^FS"""
            
            # Add calibration points
            y_pos = 270
            for i, point in enumerate(points):
                pressure = point.get('pressure', 'N/A')
                voltage = point.get('voltage', 'N/A')
                zpl += f"\n^FO30,{y_pos}^A0N,20,20^FDPoint {i+1}: {pressure} mbar - {voltage} V^FS"
                y_pos += 30
            
            zpl += "\n^PQ1,0,1,Y\n^XZ"
            
            success = self._send_zpl(zpl)
            if success:
                self.logger.info(f"Calibration report printed for chamber {chamber_num}")
            return success
            
        except Exception as e:
            self.logger.error(f"Printing error: {e}")
            return False
    
    def print_simple_status(self, message: str) -> bool:
        """
        Print a simple status message.
        
        Args:
            message: Status message to print
            
        Returns:
            bool: True if printing was successful, False otherwise
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            zpl = f"""^XA
^MMT
^PW400
^LL300
^LS0
^MNY
^FO20,20^A0N,20,20^FD{timestamp}^FS
^FO20,60^A0N,30,30^FD{message}^FS
^PQ1,0,1,Y
^XZ"""
            
            success = self._send_zpl(zpl)
            if success:
                self.logger.info(f"Status message printed: {message}")
            return success
            
        except Exception as e:
            self.logger.error(f"Printing error: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test the printer connection by printing a small test label.
        
        Returns:
            bool: True if test was successful, False otherwise
        """
        try:
            if not self.is_printer_available():
                self.logger.error("Printer not available")
                return False
            
            # Simple test label
            zpl = f"""^XA
^PW400
^LL200
^FO50,30^A0N,30,30^FDPrinter Test^FS
^FO50,70^A0N,20,20^FD{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}^FS
^FO50,100^A0N,15,15^FDDevice: {self.device_path}^FS
^PQ1,0,1,Y
^XZ"""
            
            success = self._send_zpl(zpl)
            if success:
                self.logger.info("Printer test successful")
            return success
            
        except Exception as e:
            self.logger.error(f"Printer test error: {e}")
            return False
    
    def get_printer_status(self) -> Dict[str, Any]:
        """
        Get detailed printer status information.
        
        Returns:
            Dict containing printer status information
        """
        status = {
            'available': False,
            'connected': False,
            'device_path': self.device_path,
            'accessible': False
        }
        
        try:
            status['available'] = self.is_printer_available()
            status['connected'] = status['available']
            
            if self.device_path and os.path.exists(self.device_path):
                # Check if we can write to the device
                try:
                    with open(self.device_path, 'wb') as f:
                        pass
                    status['accessible'] = True
                except:
                    status['accessible'] = False
            
        except Exception as e:
            self.logger.error(f"Error getting printer status: {e}")
            status['error'] = str(e)
        
        return status
    
    def close(self):
        """Clean up printer connection resources (compatibility method)."""
        pass  # Nothing to clean up for device file access
    
    def __enter__(self):
        """Context manager entry."""
        if self.connect():
            return self
        else:
            raise RuntimeError("Failed to connect to printer")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Convenience function for quick printer status check
def check_printer_status() -> Dict[str, Any]:
    """
    Quick function to check printer status.
    
    Returns:
        Dict containing printer status information
    """
    manager = PrinterManager()
    return manager.get_printer_status()


# Convenience function for quick test print
def test_printer() -> bool:
    """
    Quick function to test printer connectivity.
    
    Returns:
        bool: True if test successful, False otherwise
    """
    try:
        manager = PrinterManager()
        return manager.test_connection()
    except Exception as e:
        logging.getLogger('PrinterManager').error(f"Quick test failed: {e}")
        return False