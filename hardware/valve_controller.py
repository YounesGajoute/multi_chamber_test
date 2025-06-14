#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Valve Controller module for the Multi-Chamber Test application.

This module provides a ValveController class for controlling the inlet,
outlet, and empty valves for each chamber using GPIO pins.
"""

import logging
import time
from typing import List, Optional, Dict, Any, Tuple

from multi_chamber_test.config.constants import GPIO_PINS
from multi_chamber_test.hardware.gpio_manager import GPIOManager

class ValveController:
    """
    Controller for pneumatic valves in the multi-chamber test system.
    
    This class provides methods to control the inlet, outlet, and empty
    valves for each of the three test chambers, with safety checks to
    prevent unsafe valve configurations.
    """
    
    def __init__(self, gpio_manager: GPIOManager):
        """
        Initialize the ValveController with a GPIO manager.
        
        Args:
            gpio_manager: Initialized GPIOManager instance
        """
        self.logger = logging.getLogger('ValveController')
        self._setup_logger()
        
        self.gpio_manager = gpio_manager
        
        # Valve state tracking (helps with logging and safety checks)
        self.valve_states = {
            'inlet': [False, False, False],      # Inlet valves for chambers 0-2
            'outlet': [False, False, False],     # Outlet valves for chambers 0-2
            'empty': [False, False, False]       # Empty valves for chambers 0-2
        }
        
        # Timestamps for last valve operations (for rate limiting)
        self.last_operation_time = {
            'inlet': [0.0, 0.0, 0.0],
            'outlet': [0.0, 0.0, 0.0],
            'empty': [0.0, 0.0, 0.0]
        }
        
        # Minimum time between valve operations (seconds)
        self.min_operation_interval = 0.05
        
        # Initialize all valves to closed state
        self.all_valves_closed()
    
    def _setup_logger(self):
        """Configure logging for the valve controller."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def all_valves_closed(self) -> bool:
        """
        Close all valves in all chambers.
        
        Returns:
            bool: True if all valves were closed successfully, False otherwise
        """
        success = True
        
        for chamber_index in range(3):
            try:
                # Close all valves for this chamber
                inlet_success = self.set_inlet_valve(chamber_index, False)
                outlet_success = self.set_outlet_valve(chamber_index, False)
                empty_success = self.set_empty_valve(chamber_index, False)
                
                if not (inlet_success and outlet_success and empty_success):
                    success = False
            except Exception as e:
                self.logger.error(f"Error closing valves for chamber {chamber_index}: {e}")
                success = False
        
        if success:
            self.logger.info("All valves closed successfully")
        else:
            self.logger.error("Failed to close all valves")
        
        return success
    
    def set_inlet_valve(self, chamber_index: int, state: bool) -> bool:
        """
        Set the state of an inlet valve.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            state: Valve state (True for open, False for closed)
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        # Rate limiting to prevent valve damage
        current_time = time.time()
        last_time = self.last_operation_time['inlet'][chamber_index]
        
        if current_time - last_time < self.min_operation_interval and state != self.valve_states['inlet'][chamber_index]:
            time.sleep(self.min_operation_interval - (current_time - last_time))
        
        try:
            # Safety check: Don't allow inlet and outlet to be open at the same time
            if state and self.valve_states['outlet'][chamber_index]:
                self.logger.warning(f"Closing outlet valve for safety before opening inlet for chamber {chamber_index}")
                self.set_outlet_valve(chamber_index, False)
            
            # Get pin for this chamber's inlet valve
            inlet_pin = GPIO_PINS["INLET_PINS"][chamber_index]
            
            # Set valve state
            result = self.gpio_manager.set_output(inlet_pin, state)
            if result:
                self.valve_states['inlet'][chamber_index] = state
                self.last_operation_time['inlet'][chamber_index] = time.time()
                
                log_msg = f"Chamber {chamber_index + 1} inlet valve {'opened' if state else 'closed'}"
                if state:
                    self.logger.info(log_msg)
                else:
                    self.logger.debug(log_msg)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error controlling inlet valve for chamber {chamber_index}: {e}")
            # Try to close the valve on error
            try:
                inlet_pin = GPIO_PINS["INLET_PINS"][chamber_index]
                self.gpio_manager.set_output(inlet_pin, False)
                self.valve_states['inlet'][chamber_index] = False
            except:
                pass
            return False
    
    def set_outlet_valve(self, chamber_index: int, state: bool) -> bool:
        """
        Set the state of an outlet valve.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            state: Valve state (True for open, False for closed)
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        # Rate limiting to prevent valve damage
        current_time = time.time()
        last_time = self.last_operation_time['outlet'][chamber_index]
        
        if current_time - last_time < self.min_operation_interval and state != self.valve_states['outlet'][chamber_index]:
            time.sleep(self.min_operation_interval - (current_time - last_time))
        
        try:
            # Safety check: Don't allow inlet and outlet to be open at the same time
            if state and self.valve_states['inlet'][chamber_index]:
                self.logger.warning(f"Closing inlet valve for safety before opening outlet for chamber {chamber_index}")
                self.set_inlet_valve(chamber_index, False)
            
            # Get pin for this chamber's outlet valve
            outlet_pin = GPIO_PINS["OUTLET_PINS"][chamber_index]
            
            # Set valve state
            result = self.gpio_manager.set_output(outlet_pin, state)
            if result:
                self.valve_states['outlet'][chamber_index] = state
                self.last_operation_time['outlet'][chamber_index] = time.time()
                
                log_msg = f"Chamber {chamber_index + 1} outlet valve {'opened' if state else 'closed'}"
                if state:
                    self.logger.info(log_msg)
                else:
                    self.logger.debug(log_msg)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error controlling outlet valve for chamber {chamber_index}: {e}")
            # Try to close the valve on error
            try:
                outlet_pin = GPIO_PINS["OUTLET_PINS"][chamber_index]
                self.gpio_manager.set_output(outlet_pin, False)
                self.valve_states['outlet'][chamber_index] = False
            except:
                pass
            return False
    
    def set_empty_valve(self, chamber_index: int, state: bool) -> bool:
        """
        Set the state of an empty valve.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            state: Valve state (True for open, False for closed)
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        # Rate limiting to prevent valve damage
        current_time = time.time()
        last_time = self.last_operation_time['empty'][chamber_index]
        
        if current_time - last_time < self.min_operation_interval and state != self.valve_states['empty'][chamber_index]:
            time.sleep(self.min_operation_interval - (current_time - last_time))
        
        try:
            # Get pin for this chamber's empty valve
            empty_pin = GPIO_PINS["EMPTY_TANK_PINS"][chamber_index]
            
            # Set valve state
            result = self.gpio_manager.set_output(empty_pin, state)
            if result:
                self.valve_states['empty'][chamber_index] = state
                self.last_operation_time['empty'][chamber_index] = time.time()
                
                log_msg = f"Chamber {chamber_index + 1} empty valve {'opened' if state else 'closed'}"
                if state:
                    self.logger.info(log_msg)
                else:
                    self.logger.debug(log_msg)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error controlling empty valve for chamber {chamber_index}: {e}")
            # Try to close the valve on error
            try:
                empty_pin = GPIO_PINS["EMPTY_TANK_PINS"][chamber_index]
                self.gpio_manager.set_output(empty_pin, False)
                self.valve_states['empty'][chamber_index] = False
            except:
                pass
            return False
    
    def set_chamber_valves(self, chamber_index: int, inlet_state: bool, outlet_state: bool) -> bool:
        """
        Set both inlet and outlet valves for a chamber with safety checks.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            inlet_state: State of inlet valve (True for open, False for closed)
            outlet_state: State of outlet valve (True for open, False for closed)
            
        Returns:
            bool: True if operations were successful, False otherwise
        """
        if inlet_state and outlet_state:
            self.logger.error("Cannot open both inlet and outlet valves at the same time.")
            return False
        
        # Close the opposite valve first, then open the requested valve
        if inlet_state:
            success_outlet = self.set_outlet_valve(chamber_index, False)
            success_inlet = self.set_inlet_valve(chamber_index, True)
            return success_outlet and success_inlet
        elif outlet_state:
            success_inlet = self.set_inlet_valve(chamber_index, False)
            success_outlet = self.set_outlet_valve(chamber_index, True)
            return success_inlet and success_outlet
        else:
            # Both valves should be closed
            success_inlet = self.set_inlet_valve(chamber_index, False)
            success_outlet = self.set_outlet_valve(chamber_index, False)
            return success_inlet and success_outlet
    
    def empty_chamber(self, chamber_index: int) -> bool:
        """
        Safely empty a chamber by closing inlet and opening outlet and empty valves.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            
        Returns:
            bool: True if operations were successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        try:
            # First close inlet to prevent new air from entering
            inlet_success = self.set_inlet_valve(chamber_index, False)
            if not inlet_success:
                self.logger.error(f"Failed to close inlet valve for chamber {chamber_index}")
                return False
            
            # Then open outlet and empty valves to release pressure
            outlet_success = self.set_outlet_valve(chamber_index, True)
            empty_success = self.set_empty_valve(chamber_index, True)
            
            self.logger.info(f"Started emptying chamber {chamber_index + 1}")
            
            return outlet_success and empty_success
        
        except Exception as e:
            self.logger.error(f"Error emptying chamber {chamber_index}: {e}")
            return False
    
    def fill_chamber(self, chamber_index: int) -> bool:
        """
        Start filling a chamber by closing outlet and opening inlet valve.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            
        Returns:
            bool: True if operations were successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        try:
            # First close outlet and empty valves
            outlet_success = self.set_outlet_valve(chamber_index, False)
            empty_success = self.set_empty_valve(chamber_index, False)
            
            if not (outlet_success and empty_success):
                self.logger.error(f"Failed to close outlet or empty valve for chamber {chamber_index}")
                return False
            
            # Then open inlet valve to start filling
            inlet_success = self.set_inlet_valve(chamber_index, True)
            
            self.logger.info(f"Started filling chamber {chamber_index + 1}")
            
            return inlet_success
        
        except Exception as e:
            self.logger.error(f"Error filling chamber {chamber_index}: {e}")
            return False
    
    def stop_chamber(self, chamber_index: int) -> bool:
        """
        Stop all valve operations for a chamber by closing all valves.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            
        Returns:
            bool: True if operations were successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        try:
            # Close all valves
            inlet_success = self.set_inlet_valve(chamber_index, False)
            outlet_success = self.set_outlet_valve(chamber_index, False)
            empty_success = self.set_empty_valve(chamber_index, False)
            
            self.logger.info(f"Stopped all valve operations for chamber {chamber_index + 1}")
            
            return inlet_success and outlet_success and empty_success
        
        except Exception as e:
            self.logger.error(f"Error stopping chamber {chamber_index}: {e}")
            return False
    
    def pulse_valve(self, chamber_index: int, valve_type: str, duration: float = 0.1) -> bool:
        """
        Pulse a valve open for a short duration and then close it.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            valve_type: Type of valve ('inlet', 'outlet', or 'empty')
            duration: Duration to keep the valve open in seconds
            
        Returns:
            bool: True if operations were successful, False otherwise
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return False
        
        if valve_type not in ['inlet', 'outlet', 'empty']:
            self.logger.error(f"Invalid valve type: {valve_type}. Must be 'inlet', 'outlet', or 'empty'.")
            return False
        
        try:
            # Get the appropriate valve control method
            if valve_type == 'inlet':
                valve_method = self.set_inlet_valve
            elif valve_type == 'outlet':
                valve_method = self.set_outlet_valve
            else:  # empty
                valve_method = self.set_empty_valve
            
            # Open the valve
            open_success = valve_method(chamber_index, True)
            if not open_success:
                self.logger.error(f"Failed to open {valve_type} valve for pulse")
                return False
            
            # Wait for the specified duration
            time.sleep(duration)
            
            # Close the valve
            close_success = valve_method(chamber_index, False)
            
            self.logger.debug(f"Pulsed {valve_type} valve for chamber {chamber_index + 1} for {duration:.2f}s")
            
            return close_success
        
        except Exception as e:
            self.logger.error(f"Error pulsing {valve_type} valve for chamber {chamber_index}: {e}")
            # Try to close the valve on error
            try:
                valve_method(chamber_index, False)
            except:
                pass
            return False
    
    def get_valve_state(self, chamber_index: int, valve_type: str) -> Optional[bool]:
        """
        Get the current state of a valve.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            valve_type: Type of valve ('inlet', 'outlet', or 'empty')
            
        Returns:
            bool: True if valve is open, False if closed, None on error
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return None
        
        if valve_type not in ['inlet', 'outlet', 'empty']:
            self.logger.error(f"Invalid valve type: {valve_type}. Must be 'inlet', 'outlet', or 'empty'.")
            return None
        
        try:
            return self.valve_states[valve_type][chamber_index]
        except Exception as e:
            self.logger.error(f"Error getting {valve_type} valve state for chamber {chamber_index}: {e}")
            return None
    
    def set_min_operation_interval(self, interval: float):
        """
        Set the minimum time between valve operations.
        
        Args:
            interval: Minimum time in seconds
        """
        if interval < 0:
            self.logger.error(f"Invalid interval: {interval}. Must be non-negative.")
            return
        
        self.min_operation_interval = interval
        self.logger.info(f"Set minimum valve operation interval to {interval:.3f}s")
