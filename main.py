#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main entry point for the Multi-Chamber Test application.

This script initializes and runs the MainWindow class, which serves as
the application's entry point.
"""

import os
import sys
import argparse
import logging
import traceback
from datetime import datetime

from multi_chamber_test.ui.main_window import MainWindow
from multi_chamber_test.config.constants import BASE_DIR

def setup_logging(debug_mode: bool) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        debug_mode: Whether to enable debug-level logging
    
    Returns:
        Logger instance for the main module
    """
    # Create logs directory if not exists
    logs_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(logs_dir, f"multi_chamber_test_{timestamp}.log")
    
    # Set up root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    
    # File handler for logs
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(console_handler)
    
    # Create main logger
    main_logger = logging.getLogger("main")
    
    return main_logger

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Multi-Chamber Test Application")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--test", action="store_true", help="Run in test mode (mock hardware)")
    parser.add_argument("--login", action="store_true", help="Start with login screen")
    return parser.parse_args()

def excepthook(exc_type, exc_value, exc_traceback):
    """
    Global exception handler to log unhandled exceptions.
    
    Args:
        exc_type: Exception type
        exc_value: Exception value
        exc_traceback: Exception traceback
    """
    logger = logging.getLogger('ExceptionHandler')
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Print the exception to stderr
    traceback.print_exception(exc_type, exc_value, exc_traceback)

def main():
    """Main entry point for the application."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up logging
    logger = setup_logging(args.debug)
    logger.info("Starting Multi-Chamber Test Application")
    
    # Set up global exception handler
    sys.excepthook = excepthook
    
    # Set test mode flag in environment for other modules
    if args.test:
        logger.info("Running in test mode with mock hardware")
        os.environ['MULTI_CHAMBER_TEST_MODE'] = 'test'
    
    try:
        # Create and run the main application window
        app = MainWindow(start_with_login=args.login)
        app.run()
        logger.info("Application exited normally")
        return 0
    
    except Exception as e:
        logger.critical(f"Failed to start application: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())