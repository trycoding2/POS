"""
Retail Management System - Main Entry Point
A comprehensive POS and inventory management system built with PySide6
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from database import DatabaseManager
from login_window import LoginWindow
from main_window import MainWindow


def main():
    """Main entry point for the application"""
    
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Retail Management System")
    app.setOrganizationName("RetailSoft")
    
    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Initialize database
    db = DatabaseManager.get_instance()
    
    # Show login window
    login = LoginWindow()
    
    # Create main window reference
    main_win = None
    
    def on_login_success(user_info):
        nonlocal main_win
        main_win = MainWindow(user_info)
        main_win.show()
        # Navigate to dashboard by default
        main_win.navigate_to('dashboard')
    
    login.login_successful.connect(on_login_success)
    login.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
