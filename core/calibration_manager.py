#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

class CalibrationManager:
    """
    Manages chamber offset calibration.
    """
    
    def __init__(self, pressure_sensor, calibration_db, db_path: Optional[str] = None):
        """
        Initialize the CalibrationManager.
        
        Args:
            pressure_sensor: PressureSensor instance
            calibration_db: CalibrationDatabase instance
            db_path: Optional custom database path
        """
        self.logger = logging.getLogger('CalibrationManager')
        self._setup_logger()
        
        self.pressure_sensor = pressure_sensor
        
        # Use provided calibration_db or create a new one
        if calibration_db:
            self.calibration_db = calibration_db
        else:
            try:
                self.calibration_db = CalibrationDatabase(db_path)
            except Exception as e:
                self.logger.error(f"Failed to initialize calibration database: {e}")
                print(f"WARNING! Failed to initialize calibration database: {e}")
                # Create an in-memory database as fallback
                self.calibration_db = CalibrationDatabase(":memory:")
        
        # Load and apply active offsets
        self._load_active_offsets()
    
    def _setup_logger(self):
        """Configure logging for the calibration manager."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        self.logger.setLevel(logging.INFO)
    
    def _load_active_offsets(self):
        """Load active offsets from database and apply to pressure sensor."""
        try:
            # Load for all three chambers
            for chamber_id in range(3):
                offset = self.calibration_db.get_active_chamber_offset(chamber_id)
                
                if offset is not None:
                    # Apply the offset to the pressure sensor
                    self.pressure_sensor.set_chamber_offset(chamber_id, offset)
                    self.logger.info(f"Loaded and applied offset of {offset:.1f} mbar for chamber {chamber_id+1}")
                    
        except Exception as e:
            self.logger.error(f"Error loading active offsets: {e}")
    
    def save_chamber_offset(self, chamber_id: int, offset: float) -> bool:
        """
        Save an offset value for a specific chamber and apply it to pressure sensor.
        
        Args:
            chamber_id: Chamber ID (0-2)
            offset: Pressure offset value in mbar
            
        Returns:
            True if successfully saved, False otherwise
        """
        if not 0 <= chamber_id <= 2:
            self.logger.error(f"Invalid chamber ID: {chamber_id}")
            return False
        
        try:
            # Save to database
            success = self.calibration_db.save_chamber_offset(chamber_id, offset)
            
            if success:
                # Apply to pressure sensor
                self.pressure_sensor.set_chamber_offset(chamber_id, offset)
                self.logger.info(f"Saved and applied offset of {offset:.1f} mbar for chamber {chamber_id+1}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error saving chamber offset: {e}")
            return False
    
    def load_all_chamber_offsets(self) -> List[float]:
        """
        Load current offset values for all chambers.
        
        Returns:
            List of offset values (one per chamber)
        """
        offsets = []
        
        try:
            for chamber_id in range(3):
                offset = self.calibration_db.get_active_chamber_offset(chamber_id)
                
                if offset is not None:
                    offsets.append(offset)
                else:
                    # Default to 0.0 if no offset found
                    offsets.append(0.0)
            
            self.logger.info(f"Loaded chamber offsets: {offsets}")
            return offsets
            
        except Exception as e:
            self.logger.error(f"Error loading chamber offsets: {e}")
            return [0.0, 0.0, 0.0]  # Default values on error
    
    def get_offset_history(self, chamber_id: int, limit: int = 10) -> List[dict]:
        """
        Get offset history for a chamber.
        
        Args:
            chamber_id: Chamber ID (0-2)
            limit: Maximum number of records to return
            
        Returns:
            List of offset dictionaries
        """
        try:
            return self.calibration_db.get_chamber_offset_history(chamber_id, limit)
        except Exception as e:
            self.logger.error(f"Error retrieving offset history: {e}")
            return []
            
    def get_calibration_history(self, chamber_id: int, limit: int = 10) -> List[Any]:
        """
        Get calibration history for a chamber.
        This method adapts the offset history to a format expected by the UI.
        
        Args:
            chamber_id: Chamber ID (0-2)
            limit: Maximum number of records to return
            
        Returns:
            List of calibration history entries
        """
        try:
            # Get offset history from database
            history = self.calibration_db.get_chamber_offset_history(chamber_id, limit)
            
            # Convert to the format expected by the UI
            calibration_history = []
            for entry in history:
                # Create a calibration history object with expected attributes
                calibration_entry = type('CalibrationHistoryEntry', (), {
                    'calibration_date': entry['date'],
                    'offset': entry['offset'],
                    'is_active': entry['is_active']
                })
                calibration_history.append(calibration_entry)
            
            return calibration_history
            
        except Exception as e:
            self.logger.error(f"Error retrieving calibration history: {e}")
            return []