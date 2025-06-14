#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pressure Sensor module for the Multi-Chamber Test application.

This module provides a PressureSensor class that interfaces with the Adafruit ADS1115
analog-to-digital converter to read voltage values from pressure sensors and convert
them to pressure values in mbar, including chamber-specific offset adjustments and
Kalman filtering for noise reduction.
"""

import logging
import time
import Adafruit_ADS1x15
import numpy as np
from typing import List, Optional, Tuple, Dict, Any, Union

from multi_chamber_test.config.constants import ADC_ADDRESS, ADC_BUS_NUM, ADC_CONVERSION, PRESSURE_DEFAULTS

class KalmanFilter:
    """
    Kalman filter implementation for pressure sensor readings.
    
    This class implements a simple 1D Kalman filter optimized for pressure readings,
    providing robust noise filtering while maintaining responsiveness to real changes
    in pressure values.
    """
    
    def __init__(self, 
                 process_variance: float = 0.01, 
                 measurement_variance: float = 0.5,
                 initial_estimate: float = 0.0):
        """
        Initialize the Kalman filter.
        
        Args:
            process_variance: Process noise variance (Q) - how much we expect the 
                             true pressure to change between readings (lower = more stable)
            measurement_variance: Measurement noise variance (R) - how noisy we expect 
                                 the sensor readings to be (higher = more filtering)
            initial_estimate: Initial estimate of the pressure
        """
        # Initial state
        self.x = initial_estimate  # State estimate (pressure)
        self.P = 1.0               # Estimate uncertainty/error covariance
        
        # Kalman filter parameters
        self.Q = process_variance        # Process noise covariance (how much pressure naturally varies)
        self.R = measurement_variance    # Measurement noise covariance (sensor noise level)
        
        # Kalman filter helpers
        self.K = 0.0  # Kalman gain
        
    def update(self, measurement: float) -> float:
        """
        Update the filter with a new measurement and return the filtered value.
        
        Args:
            measurement: New pressure reading from sensor
            
        Returns:
            float: Filtered pressure estimate
        """
        # Prediction step (time update)
        # x = A*x + B*u, but A=1 and B*u=0 for our simple model
        # P = A*P*A' + Q, but A=1, so P = P + Q
        self.P += self.Q
        
        # Update step (measurement update)
        # K = P*H' / (H*P*H' + R), but H=1 for our simple model
        self.K = self.P / (self.P + self.R)
        
        # x = x + K*(z - H*x), but H=1 for our simple model
        self.x = self.x + self.K * (measurement - self.x)
        
        # P = (I - K*H)*P, but H=1 for our simple model
        self.P = (1 - self.K) * self.P
        
        return self.x
    
    def reset(self, initial_estimate: float = 0.0):
        """
        Reset the filter to initial conditions.
        
        Args:
            initial_estimate: New initial estimate
        """
        self.x = initial_estimate
        self.P = 1.0
        
    def set_process_variance(self, process_variance: float):
        """
        Set the process noise variance (Q).
        
        Args:
            process_variance: New Q value (how much we expect the pressure to naturally change)
        """
        if process_variance < 0:
            raise ValueError("Process variance must be non-negative")
        self.Q = process_variance
        
    def set_measurement_variance(self, measurement_variance: float):
        """
        Set the measurement noise variance (R).
        
        Args:
            measurement_variance: New R value (how noisy the sensor readings are)
        """
        if measurement_variance < 0:
            raise ValueError("Measurement variance must be non-negative")
        self.R = measurement_variance
        
    def get_parameters(self) -> Dict[str, float]:
        """
        Get the current filter parameters.
        
        Returns:
            Dictionary with filter parameters
        """
        return {
            'process_variance': self.Q,
            'measurement_variance': self.R,
            'current_estimate': self.x,
            'current_estimate_error': self.P,
            'current_kalman_gain': self.K
        }


class PressureSensor:
    

    def __init__(self, address: int = ADC_ADDRESS, bus_num: int = ADC_BUS_NUM):

        self.logger = logging.getLogger('PressureSensor')
        self._setup_logger()
            
        # Store configuration parameters
        self.address = address
        self.bus_num = bus_num
            
        # Default conversion parameters
        self.voltage_offset = ADC_CONVERSION['VOLTAGE_OFFSET']
        self.voltage_multiplier = ADC_CONVERSION['VOLTAGE_MULTIPLIER']
            
        # Chamber-specific offsets (calibration) - now the main calibration method
        self.chamber_offsets = [0.0, 0.0, 0.0]  # Offsets in mbar for chambers 0-2
            
        # Initialize ADC
        self.adc = None
        self.initialized = False
        self.initialization_attempts = 0
        self.max_init_attempts = 3
        self.last_init_attempt = 0
        self.init_retry_interval = 5.0  # seconds between retry attempts
            
        # Channel-specific Kalman filter parameters
        # Define process and measurement variance values for each channel
        self.process_variance = {
            0: 0.0010,  # Channel 0 (optimal Q value)
            1: 0.0010,  # Channel 1 (optimal Q value)
            2: 0.0010,  # Channel 2 (optimal Q value)
            3: 0.04     # Default value for channel 3
        }
            
        self.measurement_variance = {
            0: 3.67,    # Channel 0 (optimal R value)
            1: 0.90,    # Channel 1 (optimal R value)
            2: 1.91,    # Channel 2 (optimal R value)
            3: 4.0      # Default value for channel 3
        }
            
            # Initialize Kalman filters for each channel with channel-specific parameters
        self.kalman_filters = [
            KalmanFilter(self.process_variance[0], self.measurement_variance[0]),
            KalmanFilter(self.process_variance[1], self.measurement_variance[1]),
            KalmanFilter(self.process_variance[2], self.measurement_variance[2]),
            KalmanFilter(self.process_variance[3], self.measurement_variance[3])
        ]
            
        # Default gain
        self.gain = 1  # +/- 4.096V
            
        # Error tracking
        self.consecutive_errors = [0, 0, 0, 0]  # Track errors per channel
        self.max_consecutive_errors = 5  # Threshold before temporary disabling
        self.error_sleep_duration = 2.0  # Seconds to wait after max errors
            
        # Try initial initialization
        self.ensure_initialized()
    
    def _setup_logger(self):
        """Configure logging for the pressure sensor."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def ensure_initialized(self) -> bool:
        """
        Attempt to initialize ADC if not already initialized.
        
        Includes retry logic with backoff to avoid excessive error messages.
        
        Returns:
            bool: True if initialized successfully, False otherwise
        """
        # If already initialized, return True
        if self.initialized and self.adc is not None:
            return True
            
        # Check if we should retry yet
        current_time = time.time()
        if (current_time - self.last_init_attempt < self.init_retry_interval and 
            self.initialization_attempts > 0):
            # Too soon to retry
            return False
            
        # Update attempt tracking
        self.last_init_attempt = current_time
        self.initialization_attempts += 1
        
        # Attempt initialization
        try:
            self.adc = Adafruit_ADS1x15.ADS1115(address=self.address, busnum=self.bus_num)
            self.initialized = True
            self.logger.info(f"ADC initialized at address 0x{self.address:02X} on bus {self.bus_num}")
            
            # Reset error tracking on successful init
            self.consecutive_errors = [0, 0, 0, 0]
            
            return True
            
        except Exception as e:
            self.initialized = False
            self.adc = None
            
            # Only log detailed error on first few attempts to avoid log flooding
            if self.initialization_attempts <= self.max_init_attempts:
                self.logger.error(f"Failed to initialize ADC (attempt {self.initialization_attempts}): {e}")
            elif self.initialization_attempts % 10 == 0:
                # Log less frequently after max attempts
                self.logger.warning(f"Still unable to initialize ADC after {self.initialization_attempts} attempts")
                
            return False
    
    def set_conversion_parameters(self, offset: float, multiplier: float):
        """
        Set the voltage to pressure conversion parameters.
        
        Args:
            offset: Voltage offset value
            multiplier: Voltage multiplier value
        """
        self.voltage_offset = offset
        self.voltage_multiplier = multiplier
        self.logger.info(f"Set conversion parameters: offset={offset}, multiplier={multiplier}")
    
    def set_chamber_offset(self, chamber_index: int, offset: float):
        """
        Set the calibration offset for a specific chamber.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            offset: Pressure offset value in mbar
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return
            
        self.chamber_offsets[chamber_index] = offset
        self.logger.info(f"Set chamber {chamber_index} offset to {offset:.1f} mbar")
    
    def get_chamber_offset(self, chamber_index: int) -> float:
        """
        Get the calibration offset for a specific chamber.
        
        Args:
            chamber_index: Index of the chamber (0-2)
            
        Returns:
            float: The offset value in mbar
        """
        if not 0 <= chamber_index <= 2:
            self.logger.error(f"Invalid chamber index: {chamber_index}. Must be 0-2.")
            return 0.0
            
        return self.chamber_offsets[chamber_index]
    
    def read_voltage(self, channel: int) -> Optional[float]:
        """
        Read the raw voltage from the ADC channel.
        
        Args:
            channel: ADC channel to read (0-3)
            
        Returns:
            float: Voltage reading or None on error
        """
        # Check if channel is valid
        if not 0 <= channel <= 3:
            self.logger.error(f"Invalid channel: {channel}. Must be 0-3.")
            return None
            
        # Check if we're experiencing too many consecutive errors
        if self.consecutive_errors[channel] >= self.max_consecutive_errors:
            # Log only once when we hit the threshold to avoid log flooding
            if self.consecutive_errors[channel] == self.max_consecutive_errors:
                self.logger.warning(f"Channel {channel} disabled due to {self.consecutive_errors[channel]} consecutive errors")
                self.consecutive_errors[channel] += 1  # Increment to prevent repeated warnings
            return None
            
        # Try to ensure initialization before reading
        if not self.initialized or self.adc is None:
            if not self.ensure_initialized():
                # Increment error counter for this channel
                self.consecutive_errors[channel] += 1
                return None
        
        try:
            # Read raw ADC value
            raw = self.adc.read_adc(channel, gain=self.gain)
            
            # Convert to voltage (ADS1115 with gain=1 has range of +/- 4.096V)
            voltage = (raw / 32767.0) * 4.096
            
            # Reset error counter on success
            self.consecutive_errors[channel] = 0
            
            return voltage
            
        except Exception as e:
            # Handle error with backoff
            self.consecutive_errors[channel] += 1
            
            # Only log errors if not excessive to avoid log flooding
            if self.consecutive_errors[channel] <= self.max_consecutive_errors:
                self.logger.error(f"Error reading voltage from channel {channel}: {e}")
                
            # Check if we need to re-initialize the ADC
            if "No such device" in str(e) or "I/O error" in str(e):
                self.initialized = False
                self.adc = None
                
            return None
    
    def read_pressure(self, channel: int, apply_filter: bool = True) -> Optional[float]:
        """
        Fixed version of PressureSensor.read_pressure to properly handle error cases
        and avoid passing test state as an error message.
        
        Args:
            channel: ADC channel to read (0-3)
            apply_filter: Whether to apply Kalman filtering to the reading
            
        Returns:
            float: Pressure reading in mbar with offset and filtering applied, or None on error
        """
        # Check if channel is valid
        if not 0 <= channel <= 3:
            self.logger.error(f"Invalid channel: {channel}. Must be 0-3.")
            return None
        
        # Check if we're experiencing too many consecutive errors
        if self.consecutive_errors[channel] >= self.max_consecutive_errors:
            # Only sleep if we just hit the threshold
            if self.consecutive_errors[channel] == self.max_consecutive_errors:
                time.sleep(self.error_sleep_duration)
            return None
            
        try:
            # Read voltage
            voltage = self.read_voltage(channel)
            if voltage is None:
                return None
                
            # Convert to base pressure (mbar) using voltage conversion
            base_pressure = voltage * self.voltage_multiplier * 1000.0 + self.voltage_offset * 1000.0
            
            # Apply chamber-specific offset if applicable (main calibration method)
            if channel <= 2:  # Chambers are mapped to channels 0-2
                # Add the offset to correct the pressure reading
                calibrated_pressure = base_pressure + self.chamber_offsets[channel]
            else:
                calibrated_pressure = base_pressure
            
            # Ensure pressure is not negative
            raw_pressure = max(0, calibrated_pressure)
                
            # Apply Kalman filtering if requested
            if apply_filter:
                filtered_pressure = self.kalman_filters[channel].update(raw_pressure)
                return filtered_pressure
            else:
                return raw_pressure
                
        except Exception as e:
            # Increment error counter
            self.consecutive_errors[channel] += 1
            
            # Only log errors if not excessive
            if self.consecutive_errors[channel] <= self.max_consecutive_errors:
                self.logger.error(f"Error reading pressure from channel {channel}: {str(e)}")
                
            return None
    
    def read_all_pressures(self, apply_filter: bool = True) -> List[Optional[float]]:
        """
        Read pressure values from all three chamber channels with offset and filtering.
        
        Args:
            apply_filter: Whether to apply Kalman filtering to the readings
            
        Returns:
            List of pressure readings in mbar with offsets and filtering applied (None for any failed readings)
        """
        # Try to ensure initialization before reading
        if not self.initialized or self.adc is None:
            self.ensure_initialized()
            
        pressures = []
        for channel in range(3):  # Read channels 0-2 for the three chambers
            pressure = self.read_pressure(channel, apply_filter)
            pressures.append(pressure)
        return pressures
    
    def take_averaged_reading(self, channel: int, num_samples: int = 10, 
                             delay: float = 0.01) -> Optional[float]:
        """
        Take multiple pressure readings and return the average with offset applied.
        
        Args:
            channel: ADC channel to read (0-3)
            num_samples: Number of samples to take
            delay: Delay between samples in seconds
            
        Returns:
            float: Average pressure reading in mbar with offset applied, or None on error
        """
        # Try to ensure initialization before reading
        if not self.initialized or self.adc is None:
            if not self.ensure_initialized():
                return None
            
        try:
            readings = []
            errors = 0
            max_errors = num_samples  # Allow retries up to 2x the requested samples
            
            # Keep trying until we get enough samples or hit max errors
            while len(readings) < num_samples and errors < max_errors:
                # Take reading without filtering
                pressure = self.read_pressure(channel, apply_filter=False)
                if pressure is not None:
                    readings.append(pressure)
                else:
                    errors += 1
                    
                time.sleep(delay)
                
            if not readings:
                self.logger.warning(f"Failed to get any valid samples from channel {channel}")
                return None
                
            # Calculate average
            avg_pressure = sum(readings) / len(readings)
            
            # Update Kalman filter with this averaged value
            filtered_value = self.kalman_filters[channel].update(avg_pressure)
            
            # Reset error counter after successful averaged reading
            self.consecutive_errors[channel] = 0
            
            return filtered_value
            
        except Exception as e:
            self.logger.error(f"Error taking averaged reading from channel {channel}: {e}")
            return None
    
    def check_sensor_stability(self, channel: int, num_samples: int = 10, 
                              delay: float = 0.01, tolerance: float = 1.0) -> Tuple[bool, float, float]:
        """
        Check if pressure sensor readings are stable (with offset applied).
        
        Args:
            channel: ADC channel to read (0-3)
            num_samples: Number of samples to take
            delay: Delay between samples in seconds
            tolerance: Maximum acceptable standard deviation in mbar
            
        Returns:
            Tuple of (is_stable, average_pressure, standard_deviation)
        """
        # Try to ensure initialization before reading
        if not self.initialized or self.adc is None:
            if not self.ensure_initialized():
                return False, 0.0, 0.0
            
        try:
            readings = []
            errors = 0
            max_errors = num_samples  # Allow retries up to 2x the requested samples
            
            # Keep trying until we get enough samples or hit max errors
            while len(readings) < num_samples and errors < max_errors:
                # Take reading without filtering
                pressure = self.read_pressure(channel, apply_filter=False)
                if pressure is not None:
                    readings.append(pressure)
                else:
                    errors += 1
                    
                time.sleep(delay)
                
            if not readings:
                self.logger.warning(f"Failed to get any valid samples for stability check from channel {channel}")
                return False, 0.0, 0.0
                
            # Calculate average and standard deviation
            avg_pressure = sum(readings) / len(readings)
            std_dev = np.std(readings)
            
            is_stable = std_dev <= tolerance
            
            # Reset error counter after successful stability check
            self.consecutive_errors[channel] = 0
            
            return is_stable, avg_pressure, std_dev
            
        except Exception as e:
            self.logger.error(f"Error checking stability for channel {channel}: {e}")
            return False, 0.0, 0.0
    
    def validate_sensors(self) -> Dict[int, bool]:
        """
        Validate all pressure sensors by taking sample readings (with offsets applied).
        
        Returns:
            Dictionary mapping channel numbers to validation results (True/False)
        """
        # Try to ensure initialization before validation
        if not self.initialized or self.adc is None:
            self.ensure_initialized()
            
        results = {}
        for channel in range(3):  # Check channels 0-2 for the three chambers
            try:
                # Attempt to take a reading
                pressure = self.read_pressure(channel, apply_filter=False)
                
                # A reading is considered valid if it's not None and within a reasonable range
                # (negative or extremely high pressures indicate sensor problems)
                is_valid = pressure is not None and 0 <= pressure <= PRESSURE_DEFAULTS['MAX_PRESSURE'] * 1.1
                
                results[channel] = is_valid
                
                if not is_valid:
                    self.logger.warning(f"Pressure sensor on channel {channel} failed validation")
                
            except Exception as e:
                self.logger.error(f"Error validating sensor on channel {channel}: {e}")
                results[channel] = False
                
        return results
    
    def get_all_chamber_offsets(self) -> List[float]:
        """
        Get all chamber offsets.
        
        Returns:
            List of offset values for chambers 0-2
        """
        return self.chamber_offsets.copy()
    
    def set_all_chamber_offsets(self, offsets: List[float]):
        """
        Set all chamber offsets at once.
        
        Args:
            offsets: List of offset values for chambers 0-2
        """
        if len(offsets) != 3:
            self.logger.error(f"Expected 3 offsets, got {len(offsets)}")
            return
        
        for i, offset in enumerate(offsets):
            self.set_chamber_offset(i, offset)
        
        self.logger.info(f"Set all chamber offsets: {offsets}")
    
    def reset_chamber_offsets(self):
        """Reset all chamber offsets to zero."""
        self.chamber_offsets = [0.0, 0.0, 0.0]
        self.logger.info("Reset all chamber offsets to 0.0")
    
    def set_kalman_parameters(self, process_variance: float, measurement_variance: float):
        """
        Set the Kalman filter parameters for all channels.
        
        Args:
            process_variance: Process noise variance (Q) - how much we expect the 
                             true pressure to change between readings
            measurement_variance: Measurement noise variance (R) - how noisy we expect 
                                 the sensor readings to be
        """
        if process_variance < 0 or measurement_variance < 0:
            self.logger.error("Variance values must be non-negative")
            return
            
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        
        # Update all filters
        for filter in self.kalman_filters:
            filter.set_process_variance(process_variance)
            filter.set_measurement_variance(measurement_variance)
            
        self.logger.info(f"Set Kalman filter parameters: Q={process_variance}, R={measurement_variance}")
    
    def set_channel_kalman_parameters(self, channel: int, process_variance: float, measurement_variance: float):
        """
        Set the Kalman filter parameters for a specific channel.
        
        Args:
            channel: Channel index (0-3)
            process_variance: Process noise variance (Q)
            measurement_variance: Measurement noise variance (R)
        """
        if not 0 <= channel <= 3:
            self.logger.error(f"Invalid channel: {channel}. Must be 0-3.")
            return
            
        if process_variance < 0 or measurement_variance < 0:
            self.logger.error("Variance values must be non-negative")
            return
            
        self.kalman_filters[channel].set_process_variance(process_variance)
        self.kalman_filters[channel].set_measurement_variance(measurement_variance)
        
        self.logger.info(f"Set Kalman filter parameters for channel {channel}: Q={process_variance}, R={measurement_variance}")
    
    def reset_filters(self):
        """Reset all Kalman filters to initial conditions."""
        for channel, filter in enumerate(self.kalman_filters):
            filter.reset()
        self.logger.info("Reset all Kalman filters")
    
    def reset_channel_filter(self, channel: int, initial_value: float = 0.0):
        """
        Reset a specific channel's Kalman filter.
        
        Args:
            channel: Channel index (0-3)
            initial_value: Initial estimate to reset to
        """
        if not 0 <= channel <= 3:
            self.logger.error(f"Invalid channel: {channel}. Must be 0-3.")
            return
            
        self.kalman_filters[channel].reset(initial_value)
        self.logger.info(f"Reset Kalman filter for channel {channel}")
    
    def reset_error_counters(self):
        """Reset all error counters, allowing retry of problematic channels."""
        self.consecutive_errors = [0, 0, 0, 0]
        self.logger.info("Reset all sensor error counters")
        
    def set_error_threshold(self, max_errors: int):
        """
        Set the threshold for consecutive errors before temporarily disabling a channel.
        
        Args:
            max_errors: Maximum number of consecutive errors allowed
        """
        if max_errors < 1:
            self.logger.error("Error threshold must be at least 1")
            return
            
        self.max_consecutive_errors = max_errors
        self.logger.info(f"Set error threshold to {max_errors} consecutive errors")
    
    def get_kalman_parameters(self) -> Dict[str, Any]:
        """
        Get information about current Kalman filter parameters.
        
        Returns:
            Dictionary with Kalman filter parameters
        """
        params = {
            'global_process_variance': self.process_variance,
            'global_measurement_variance': self.measurement_variance,
            'channel_parameters': {}
        }
        
        for channel, filter in enumerate(self.kalman_filters):
            params['channel_parameters'][channel] = filter.get_parameters()
            
        return params
    
    def get_calibration_info(self) -> Dict[str, Any]:
        """
        Get information about current calibration settings.
        
        Returns:
            Dictionary with calibration information
        """
        return {
            'voltage_offset': self.voltage_offset,
            'voltage_multiplier': self.voltage_multiplier,
            'chamber_offsets': self.chamber_offsets.copy(),
            'calibration_method': 'offset_based',
            'filtering_method': 'kalman',
            'kalman_parameters': self.get_kalman_parameters()
        }