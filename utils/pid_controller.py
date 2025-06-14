#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PID Controller Wrapper Fix

This module provides a corrected PIDControllerWrapper class that includes
the missing 'update' method which is causing the error in your TestManager.

The error occurs because the TestManager is calling:
    pid_output = chamber.pid_controller.update(current_pressure)
    
But the PIDControllerWrapper class doesn't have an 'update' method.
"""

import time
from typing import Optional, Tuple


class PIDControllerWrapper:
    """
    A wrapper class for PID controller functionality.
    
    This class provides PID control with proper update method and reset functionality.
    """
    
    def __init__(self, 
                 setpoint: float = 0.0,
                 kp: float = 1.0, 
                 ki: float = 0.1, 
                 kd: float = 0.05,
                 output_limits: Optional[Tuple[float, float]] = None,
                 sample_time: float = 0.01):
        """
        Initialize the PID controller.
        
        Args:
            setpoint: The target value for the controller
            kp: Proportional gain
            ki: Integral gain  
            kd: Derivative gain
            output_limits: Tuple of (min, max) output limits
            sample_time: Minimum time between updates in seconds
        """
        self.setpoint = setpoint
        self.kp = kp
        self.ki = ki
        self.kd = kd
        
        # Output limits
        self.output_limits = output_limits or (0.0, 1.0)
        self.output_min, self.output_max = self.output_limits
        
        # Sample time
        self.sample_time = sample_time
        
        # Internal state
        self._last_time = None
        self._last_error = 0.0
        self._integral = 0.0
        self._last_input = None
        
        # Reset the controller
        self.reset()
    
    def update(self, current_value: float, dt: Optional[float] = None) -> float:
        """
        Update the PID controller with a new measurement.
        
        Args:
            current_value: Current process variable value
            dt: Optional time delta. If None, uses internal timing
            
        Returns:
            PID controller output
        """
        current_time = time.time()
        
        # Calculate time delta
        if dt is not None:
            delta_time = dt
        elif self._last_time is None:
            delta_time = 0.0
        else:
            delta_time = current_time - self._last_time
            
        # Check if enough time has passed (sample time)
        if delta_time < self.sample_time and self._last_time is not None:
            # Return last output if not enough time has passed
            return getattr(self, '_last_output', 0.0)
        
        # Calculate error
        error = self.setpoint - current_value
        
        # Proportional term
        proportional = self.kp * error
        
        # Integral term
        if delta_time > 0:
            self._integral += error * delta_time
            
            # Prevent integral windup
            if self.output_limits:
                # Clamp integral to prevent windup
                max_integral = (self.output_max - proportional) / max(self.ki, 1e-10)
                min_integral = (self.output_min - proportional) / max(self.ki, 1e-10)
                self._integral = max(min_integral, min(max_integral, self._integral))
        
        integral = self.ki * self._integral
        
        # Derivative term
        if delta_time > 0 and self._last_input is not None:
            # Use derivative on measurement to avoid derivative kick
            derivative_input = -(current_value - self._last_input) / delta_time
            derivative = self.kd * derivative_input
        else:
            derivative = 0.0
        
        # Calculate total output
        output = proportional + integral + derivative
        
        # Apply output limits
        if self.output_limits:
            output = max(self.output_min, min(self.output_max, output))
        
        # Store values for next iteration
        self._last_time = current_time
        self._last_error = error
        self._last_input = current_value
        self._last_output = output
        
        return output
    
    def __call__(self, current_value: float, dt: Optional[float] = None) -> float:
        """
        Make the controller callable.
        
        Args:
            current_value: Current process variable value
            dt: Optional time delta
            
        Returns:
            PID controller output
        """
        return self.update(current_value, dt)
    
    def reset(self):
        """Reset the PID controller internal state."""
        self._last_time = None
        self._last_error = 0.0
        self._integral = 0.0
        self._last_input = None
        self._last_output = 0.0
    
    def set_setpoint(self, setpoint: float):
        """Set a new setpoint for the controller."""
        self.setpoint = setpoint
    
    def set_gains(self, kp: float, ki: float, kd: float):
        """Set new PID gains."""
        self.kp = kp
        self.ki = ki  
        self.kd = kd
    
    def set_output_limits(self, limits: Tuple[float, float]):
        """Set new output limits."""
        self.output_limits = limits
        self.output_min, self.output_max = limits
    
    def get_components(self) -> dict:
        """
        Get the individual PID components from the last update.
        
        Returns:
            Dictionary with P, I, D components and total output
        """
        if not hasattr(self, '_last_output'):
            return {'P': 0, 'I': 0, 'D': 0, 'output': 0}
            
        error = self._last_error
        proportional = self.kp * error
        integral = self.ki * self._integral
        derivative = self._last_output - proportional - integral
        
        return {
            'P': proportional,
            'I': integral, 
            'D': derivative,
            'output': self._last_output,
            'error': error
        }
