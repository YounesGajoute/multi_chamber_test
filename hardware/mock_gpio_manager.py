#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mock GPIO Manager for the Multi-Chamber Test application.

This module provides a mock implementation of the GPIOManager class for
development and testing without hardware. It simulates GPIO pin behavior
and implements all methods of the real GPIOManager.
"""

import logging
from typing import Optional, Dict, Any, List, Callable

class MockGPIOManager:
    """
    Mock implementation of GPIO manager for development and testing without hardware.
    
    This class provides simulated GPIO functionality that mimics the behavior of
    the real GPIOManager but doesn't require physical hardware. It keeps track of
    pin states and can simulate inputs and outputs.
    """
    
    def __init__(self):
        """Initialize the MockGPIOManager."""
        self.logger = logging.getLogger('MockGPIOManager')
        self._setup_logger()
        
        # Initialize pins dictionary to track pin states
        self.pins = {}
        self.initialized = False
        self.registered_pins = set()
        self._callbacks = {}
        
        # Constants to match RPi.GPIO
        self.BCM = "BCM"
        self.OUT = "OUT"
        self.IN = "IN"
        self.HIGH = 1
        self.LOW = 0
        self.PUD_UP = "PUD_UP"
        self.PUD_DOWN = "PUD_DOWN"
        self.RISING = "RISING"
        self.FALLING = "FALLING"
        self.BOTH = "BOTH"
    
    def _setup_logger(self):
        """Configure logging for the mock GPIO manager."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def initialize(self):
        """Initialize the mock GPIO system."""
        self.logger.info("Mock GPIO initialized (no real hardware).")
        self.initialized = True
        return True
    
    def setup_pin(self, pin: int, mode: str, initial: Optional[int] = None, 
                 pull_up_down: Optional[str] = None):
        """
        Set up a GPIO pin with the specified mode and initial state.
        
        Args:
            pin: GPIO pin number
            mode: Pin mode (self.IN or self.OUT)
            initial: Initial state for output pins (self.HIGH or self.LOW)
            pull_up_down: Pull-up/down resistor configuration for input pins
        """
        if not self.initialized:
            self.logger.warning("Mock GPIO not initialized. Call initialize() first.")
            return
        
        # Set up pin state
        self.pins[pin] = {
            'mode': mode,
            'value': initial if mode == self.OUT and initial is not None else self.LOW,
            'pull': pull_up_down
        }
        
        self.registered_pins.add(pin)
        self.logger.debug(f"Mock setup_pin(pin={pin}, mode={mode}, initial={initial}, pull_up_down={pull_up_down})")
    
    def set_output(self, pin: int, state: int) -> bool:
        """
        Set the state of an output pin.
        
        Args:
            pin: GPIO pin number
            state: Pin state (self.HIGH or self.LOW)
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        if not self.initialized:
            self.logger.warning("Mock GPIO not initialized.")
            return False
        
        # Check if pin exists
        if pin not in self.pins:
            self.setup_pin(pin, self.OUT)
        
        # Set pin value
        self.pins[pin]['value'] = state
        self.logger.debug(f"Mock set_output(pin={pin}, state={state})")
        return True
    
    def read_input(self, pin: int) -> Optional[int]:
        """
        Read the state of an input pin.
        
        Args:
            pin: GPIO pin number
            
        Returns:
            int: Pin state (self.HIGH or self.LOW) or None on error
        """
        if not self.initialized:
            self.logger.warning("Mock GPIO not initialized.")
            return None
        
        # Check if pin exists
        if pin not in self.pins:
            self.setup_pin(pin, self.IN)
            return self.LOW
        
        return self.pins[pin]['value']
    
    def add_event_detect(self, pin: int, edge: str, callback: Callable, bouncetime: int = 200) -> bool:
        """
        Add event detection to a GPIO pin.
        
        Args:
            pin: GPIO pin number
            edge: Edge detection type (self.RISING, self.FALLING, or self.BOTH)
            callback: Function to call when event is detected
            bouncetime: Debounce time in milliseconds
            
        Returns:
            bool: True if event detection was added successfully, False otherwise
        """
        if not self.initialized:
            self.logger.warning("Mock GPIO not initialized.")
            return False
        
        # Check if pin exists
        if pin not in self.pins:
            self.setup_pin(pin, self.IN)
        
        # Store callback
        self._callbacks[pin] = {
            'callback': callback,
            'edge': edge,
            'bouncetime': bouncetime
        }
        
        self.logger.debug(f"Mock add_event_detect(pin={pin}, edge={edge})")
        return True
    
    def remove_event_detect(self, pin: int) -> bool:
        """
        Remove event detection from a GPIO pin.
        
        Args:
            pin: GPIO pin number
            
        Returns:
            bool: True if event detection was removed successfully, False otherwise
        """
        if not self.initialized:
            return True  # If GPIO is not initialized, no event detection to remove
        
        # Remove callback if exists
        if pin in self._callbacks:
            del self._callbacks[pin]
            
        self.logger.debug(f"Mock remove_event_detect(pin={pin})")
        return True
    
    def cleanup(self):
        """Clean up all GPIO pins."""
        self.pins = {}
        self._callbacks = {}
        self.registered_pins = set()
        self.initialized = False
        self.logger.info("Mock GPIO cleanup completed.")
    
    def simulate_input(self, pin: int, value: int):
        """
        Simulate an input change for testing.
        
        Args:
            pin: GPIO pin number
            value: New pin value (self.HIGH or self.LOW)
        """
        if not self.initialized:
            self.logger.warning("Mock GPIO not initialized.")
            return
        
        # Set value
        old_value = self.pins.get(pin, {}).get('value', self.LOW)
        
        # Update pin value
        if pin not in self.pins:
            self.setup_pin(pin, self.IN)
        
        self.pins[pin]['value'] = value
        
        # Check for edge detection
        if pin in self._callbacks:
            callback_info = self._callbacks[pin]
            edge = callback_info['edge']
            
            # Check if edge matches
            if ((edge == self.RISING and old_value == self.LOW and value == self.HIGH) or
                (edge == self.FALLING and old_value == self.HIGH and value == self.LOW) or
                (edge == self.BOTH and old_value != value)):
                
                # Call callback
                try:
                    callback_info['callback'](pin)
                except Exception as e:
                    self.logger.error(f"Error in callback for pin {pin}: {e}")
        
        self.logger.debug(f"Mock simulate_input(pin={pin}, value={value})")