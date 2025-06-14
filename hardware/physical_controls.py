#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Physical Controls module for the Multi-Chamber Test application.

This module provides a PhysicalControls class for handling the interaction
with physical buttons (start/stop) and status LEDs, synchronizing their
state with the GUI.

FIXED: Added missing LED control methods and proper thread management.
"""

import logging
import threading
import time
from typing import Callable, Optional

import RPi.GPIO as GPIO

from multi_chamber_test.config.constants import GPIO_PINS
from multi_chamber_test.hardware.gpio_manager import GPIOManager

class PhysicalControls:
    """
    Manager for physical buttons and LEDs.
    
    This class provides methods to handle physical start/stop buttons
    and status LEDs, synchronizing their state with the GUI and
    registering callbacks for button press events.
    """
    
    POLL_INTERVAL = 0.05  # seconds

    def __init__(self, gpio_manager: GPIOManager):
        """
        Initialize PhysicalControls.
    
        Args:
            gpio_manager: GPIOManager instance for pin I/O
        """
        self.logger = logging.getLogger('PhysicalControls')
        self._setup_logger()
    
        self.gpio_manager = gpio_manager
    
        # Button pin definitions
        self.start_btn_pin = GPIO_PINS.get("START_BTN")
        self.stop_btn_pin  = GPIO_PINS.get("STOP_BTN")
    
        # LED pin definitions
        self.start_led_pin  = GPIO_PINS.get("STATUS_LED_GREEN")
        self.stop_led_pin   = GPIO_PINS.get("STATUS_LED_RED")
        self.status_led_pin = GPIO_PINS.get("STATUS_LED_YELLOW")
    
        # Callbacks (to be registered via register_*_callback)
        self.start_callback = None
        self.stop_callback  = None
    
        # State tracking for polling
        # Buttons idle LOW (False) and go HIGH (True) when pressed
        self._last_start_state: bool = False
        self._last_stop_state:  bool = False
    
        # Thread control for background poller
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running: bool = False
    
        # Whether each button press is allowed
        self.start_btn_enabled: bool = True
        self.stop_btn_enabled:  bool = False
    
        # For status LED blinking
        self._blink_thread: Optional[threading.Thread] = None
        self._blink_running: bool = False
        self._blink_mode: Optional[str] = None
        self._blink_lock = threading.Lock()
    
        # Only true if all required pins are defined
        self.initialized: bool = all(pin is not None for pin in (
            self.start_btn_pin,
            self.stop_btn_pin,
            self.start_led_pin,
            self.stop_led_pin
        ))
        
        # Status LED is optional - log warning if missing
        if not self.status_led_pin:
            self.logger.warning("Status LED pin not defined - status LED functionality disabled")

    def _setup_logger(self):
        """Configure logging for the physical controls."""
        handler = logging.StreamHandler()
        fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        handler.setFormatter(logging.Formatter(fmt))
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def setup(self) -> bool:
        """
        Configure button inputs (pulled down) and LEDs, then start the polling thread.
        Returns True on success, False on error.
        """
        if not self.initialized:
            self.logger.warning("Required GPIO pins missing; cannot initialize physical controls.")
            return False
    
        try:
            # Configure button pins as inputs with pull-down (idle LOW, pressed HIGH)
            for pin in (self.start_btn_pin, self.stop_btn_pin):
                self.gpio_manager.setup_pin(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    
            # Read and store the idle state so the first rising edge is detected
            self._last_start_state = bool(self.gpio_manager.read_input(self.start_btn_pin))
            self._last_stop_state  = bool(self.gpio_manager.read_input(self.stop_btn_pin))
    
            # Configure LED pins as outputs, all off initially
            for pin in (self.start_led_pin, self.stop_led_pin):
                self.gpio_manager.setup_pin(pin, GPIO.OUT, initial=GPIO.LOW)
                
            # Configure status LED if available
            if self.status_led_pin:
                self.gpio_manager.setup_pin(self.status_led_pin, GPIO.OUT, initial=GPIO.LOW)
    
            # Sync LEDs to current enabled state
            self.sync_led_states()
    
            # Start the background button-polling thread
            self._start_monitor_thread()
    
            self.logger.info("Physical controls initialized successfully")
            return True
    
        except Exception as e:
            self.logger.error(f"Error initializing physical controls: {e}")
            return False
        
    def register_start_callback(self, cb: Callable) -> bool:
        """Register callback for start button press."""
        self.start_callback = cb
        self.logger.debug("Start button callback registered")
        return True
    
    def register_stop_callback(self, cb: Callable) -> bool:
        """Register callback for stop button press."""
        self.stop_callback = cb
        self.logger.debug("Stop button callback registered")
        return True
    
    def _start_monitor_thread(self):
        """Start the button monitoring thread."""
        if self._monitor_running:
            return
        self._monitor_running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="PhysicalControlsMonitor")
        self._monitor_thread.start()
        self.logger.debug("Button monitor thread started")
    
    def _stop_monitor_thread(self):
        """Stop the button monitoring thread."""
        self._monitor_running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
            if self._monitor_thread.is_alive():
                self.logger.warning("Monitor thread did not terminate gracefully")
        self.logger.debug("Button monitor thread stopped")

    def _monitor_loop(self):
        """
        Background loop to monitor button state changes.
        Detects rising edges (button presses) and calls registered callbacks.
        """
        self.logger.debug("Button monitor loop started")
        
        while self._monitor_running:
            try:
                # Read current states (False = unpressed, True = pressed)
                cur_start = bool(self.gpio_manager.read_input(self.start_btn_pin))
                cur_stop  = bool(self.gpio_manager.read_input(self.stop_btn_pin))
    
                # Detect rising edge = button press (LOW ? HIGH)
                if self.start_btn_enabled and cur_start and not self._last_start_state:
                    self.logger.info("Start button pressed (physical)")
                    if self.start_callback:
                        try:
                            self.start_callback()
                        except Exception as e:
                            self.logger.error(f"Error in start button callback: {e}")
    
                if self.stop_btn_enabled and cur_stop and not self._last_stop_state:
                    self.logger.info("Stop button pressed (physical)")
                    if self.stop_callback:
                        try:
                            self.stop_callback()
                        except Exception as e:
                            self.logger.error(f"Error in stop button callback: {e}")
    
                # Update last-state for next iteration
                self._last_start_state = cur_start
                self._last_stop_state  = cur_stop
    
            except Exception as e:
                self.logger.error(f"Error in button monitor loop: {e}")
    
            time.sleep(self.POLL_INTERVAL)
        
        self.logger.debug("Button monitor loop ended")
    
    def set_start_button_enabled(self, enabled: bool) -> bool:
        """
        Enable or disable the start button and update its LED.
        
        Args:
            enabled: True to enable button, False to disable
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.start_btn_enabled = enabled
            success = self.gpio_manager.set_output(
                self.start_led_pin, GPIO.HIGH if enabled else GPIO.LOW)
            
            if success:
                self.logger.debug(f"Start button {'enabled' if enabled else 'disabled'}")
            else:
                self.logger.error("Failed to set start button LED state")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Error setting start button state: {e}")
            return False
    
    def set_stop_button_enabled(self, enabled: bool) -> bool:
        """
        Enable or disable the stop button and update its LED.
        
        Args:
            enabled: True to enable button, False to disable
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.stop_btn_enabled = enabled
            success = self.gpio_manager.set_output(
                self.stop_led_pin, GPIO.HIGH if enabled else GPIO.LOW)
            
            if success:
                self.logger.debug(f"Stop button {'enabled' if enabled else 'disabled'}")
            else:
                self.logger.error("Failed to set stop button LED state")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Error setting stop button state: {e}")
            return False
    
    def sync_led_states(self) -> bool:
        """
        Synchronize LED states with current button enabled states.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            start_success = self.gpio_manager.set_output(
                self.start_led_pin, GPIO.HIGH if self.start_btn_enabled else GPIO.LOW)
            stop_success = self.gpio_manager.set_output(
                self.stop_led_pin,  GPIO.HIGH if self.stop_btn_enabled  else GPIO.LOW)
            
            success = start_success and stop_success
            
            if success:
                self.logger.debug("LED states synchronized")
            else:
                self.logger.error("Failed to synchronize LED states")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Error syncing LEDs: {e}")
            return False
    
    def set_status_led(self, mode: Optional[str]) -> bool:
        """
        Set the status LED mode.
        
        Args:
            mode: LED mode - None (off), "solid" (on), "blink-slow", "blink-fast"
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.status_led_pin:
            self.logger.debug(f"Status LED mode '{mode}' requested but no status LED pin configured")
            return True  # Not an error if no status LED available
        
        try:
            with self._blink_lock:
                # Stop any current blinking
                self._stop_blink_thread()
                
                # Set new mode
                self._blink_mode = mode
                
                if mode is None:
                    # Turn off LED
                    success = self.gpio_manager.set_output(self.status_led_pin, GPIO.LOW)
                    self.logger.debug("Status LED turned off")
                    
                elif mode == "solid":
                    # Turn on LED solid
                    success = self.gpio_manager.set_output(self.status_led_pin, GPIO.HIGH)
                    self.logger.debug("Status LED set to solid")
                    
                elif mode in ["blink-slow", "blink-fast"]:
                    # Start blinking thread
                    success = self._start_blink_thread(mode)
                    self.logger.debug(f"Status LED set to {mode}")
                    
                else:
                    self.logger.warning(f"Unknown status LED mode: {mode}")
                    success = False
                
                return success
                
        except Exception as e:
            self.logger.error(f"Error setting status LED mode '{mode}': {e}")
            return False
    
    def _start_blink_thread(self, mode: str) -> bool:
        """
        Start the LED blinking thread.
        
        Args:
            mode: Blink mode ("blink-slow" or "blink-fast")
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self._blink_running:
                self._stop_blink_thread()
            
            self._blink_running = True
            self._blink_thread = threading.Thread(
                target=self._blink_loop, 
                args=(mode,), 
                daemon=True, 
                name="StatusLEDBlink"
            )
            self._blink_thread.start()
            
            self.logger.debug(f"Blink thread started for mode: {mode}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting blink thread: {e}")
            self._blink_running = False
            return False
    
    def _stop_blink_thread(self) -> bool:
        """
        Stop the LED blinking thread.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._blink_running:
                return True
            
            self._blink_running = False
            
            if self._blink_thread and self._blink_thread.is_alive():
                self._blink_thread.join(timeout=1.0)
                if self._blink_thread.is_alive():
                    self.logger.warning("Blink thread did not terminate gracefully")
            
            # Ensure LED is off after stopping blink
            if self.status_led_pin:
                self.gpio_manager.set_output(self.status_led_pin, GPIO.LOW)
            
            self.logger.debug("Blink thread stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping blink thread: {e}")
            return False
    
    def _blink_loop(self, mode: str):
        """
        LED blinking loop that runs in a separate thread.
        
        Args:
            mode: Blink mode ("blink-slow" or "blink-fast")
        """
        try:
            # Set timing based on mode
            if mode == "blink-fast":
                on_time = 0.1   # 100ms on
                off_time = 0.1  # 100ms off
            else:  # blink-slow
                on_time = 0.5   # 500ms on
                off_time = 0.5  # 500ms off
            
            self.logger.debug(f"Blink loop started: {mode} (on={on_time}s, off={off_time}s)")
            
            led_state = False
            
            while self._blink_running:
                try:
                    # Toggle LED state
                    led_state = not led_state
                    self.gpio_manager.set_output(
                        self.status_led_pin, 
                        GPIO.HIGH if led_state else GPIO.LOW
                    )
                    
                    # Wait for appropriate duration
                    sleep_time = on_time if led_state else off_time
                    
                    # Break sleep into smaller chunks to allow quick exit
                    slept = 0.0
                    while slept < sleep_time and self._blink_running:
                        chunk = min(0.05, sleep_time - slept)  # 50ms chunks max
                        time.sleep(chunk)
                        slept += chunk
                    
                except Exception as e:
                    self.logger.error(f"Error in blink loop: {e}")
                    break
            
        except Exception as e:
            self.logger.error(f"Critical error in blink loop: {e}")
        
        finally:
            # Ensure LED is off when thread exits
            try:
                if self.status_led_pin:
                    self.gpio_manager.set_output(self.status_led_pin, GPIO.LOW)
            except:
                pass
            
            self.logger.debug("Blink loop ended")
    
    def get_status(self) -> dict:
        """
        Get current status of physical controls.
        
        Returns:
            dict: Status information
        """
        return {
            'initialized': self.initialized,
            'start_button_enabled': self.start_btn_enabled,
            'stop_button_enabled': self.stop_btn_enabled,
            'status_led_mode': self._blink_mode,
            'monitor_running': self._monitor_running,
            'blink_running': self._blink_running,
            'pins': {
                'start_button': self.start_btn_pin,
                'stop_button': self.stop_btn_pin,
                'start_led': self.start_led_pin,
                'stop_led': self.stop_led_pin,
                'status_led': self.status_led_pin
            }
        }
    
    def cleanup(self):
        """
        Stop all threads, turn off all LEDs, and clean up resources.
        """
        self.logger.info("Cleaning up physical controls...")
        
        try:
            # Stop threads
            self._stop_blink_thread()
            self._stop_monitor_thread()
            
            # Turn off all LEDs
            for pin in (self.start_led_pin, self.stop_led_pin, self.status_led_pin):
                if pin:
                    try:
                        self.gpio_manager.set_output(pin, GPIO.LOW)
                    except Exception as e:
                        self.logger.error(f"Error turning off LED on pin {pin}: {e}")
            
            # Remove any edge detection if it was used
            try:
                if self.start_btn_pin:
                    self.gpio_manager.remove_event_detect(self.start_btn_pin)
            except:
                pass  # May not have been set up
                
            try:
                if self.stop_btn_pin:
                    self.gpio_manager.remove_event_detect(self.stop_btn_pin)
            except:
                pass  # May not have been set up
            
            # Clear callbacks
            self.start_callback = None
            self.stop_callback = None
            
            self.logger.info("Physical controls cleaned up successfully")
            
        except Exception as e:
            self.logger.error(f"Error during physical controls cleanup: {e}")