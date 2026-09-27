"""
Login Window - Authentication screen for Retail Management System
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QBrush

from database import DatabaseManager


class LoginWindow(QWidget):
    """Login window with username/password authentication"""
    
    login_successful = Signal(dict)  # Emits user info dict
    
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager.get_instance()
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Retail Management System - Login")
        self.setWindowState(Qt.WindowFullScreen)
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: #eee;
            }
            QLineEdit {
                padding: 12px;
                border: 2px solid #16213e;
                border-radius: 8px;
                background-color: #0f3460;
                color: #eee;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #e94560;
            }
            QPushButton {
                padding: 12px 30px;
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
            }
            QPushButton:pressed {
                background-color: #c73e54;
            }
            QLabel {
                color: #eee;
            }
        """)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)
        
        # Center frame with shadow
        center_frame = QFrame()
        center_frame.setObjectName("centerFrame")
        center_frame.setStyleSheet("""
            #centerFrame {
                background-color: #16213e;
                border-radius: 15px;
                padding: 40px;
            }
        """)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 100))
        center_frame.setGraphicsEffect(shadow)
        
        frame_layout = QVBoxLayout()
        frame_layout.setSpacing(20)
        
        # Logo placeholder (colored circle)
        logo_label = QLabel()
        logo_label.setFixedSize(120, 120)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_pixmap = QPixmap(120, 120)
        logo_pixmap.fill(Qt.transparent)
        painter = QPainter(logo_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#e94560")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 120, 120)
        painter.end()
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        
        # Title
        title_label = QLabel("Retail Management System")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        
        subtitle_label = QLabel("Please login to continue")
        subtitle_label.setFont(QFont("Segoe UI", 12))
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #aaa;")
        
        # Username field
        username_label = QLabel("Username")
        username_label.setFont(QFont("Segoe UI", 12))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        self.username_input.returnPressed.connect(self.attempt_login)
        
        # Password field
        password_label = QLabel("Password")
        password_label.setFont(QFont("Segoe UI", 12))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.attempt_login)
        
        # Login button
        self.login_button = QPushButton("LOGIN")
        self.login_button.clicked.connect(self.attempt_login)
        self.login_button.setFixedWidth(200)
        
        # Error label
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        self.error_label.setWordWrap(True)
        
        # Exit hint
        exit_hint = QLabel("Press ESC to exit")
        exit_hint.setAlignment(Qt.AlignCenter)
        exit_hint.setStyleSheet("color: #666; font-size: 11px;")
        
        # Add widgets to frame layout
        frame_layout.addWidget(logo_label, alignment=Qt.AlignCenter)
        frame_layout.addWidget(title_label)
        frame_layout.addWidget(subtitle_label)
        frame_layout.addSpacing(20)
        frame_layout.addWidget(username_label)
        frame_layout.addWidget(self.username_input)
        frame_layout.addWidget(password_label)
        frame_layout.addWidget(self.password_input)
        frame_layout.addSpacing(10)
        frame_layout.addWidget(self.login_button, alignment=Qt.AlignCenter)
        frame_layout.addWidget(self.error_label)
        frame_layout.addSpacing(20)
        frame_layout.addWidget(exit_hint)
        
        center_frame.setLayout(frame_layout)
        
        # Add center frame to main layout
        main_layout.addWidget(center_frame)
        
        self.setLayout(main_layout)
        
        # Set focus to username
        self.username_input.setFocus()
    
    def attempt_login(self):
        """Attempt to login with provided credentials"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            self.error_label.setText("Please enter both username and password")
            return
        
        # Query database
        self.db.execute(
            "SELECT id, username, role FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = self.db.fetchone()
        
        if user:
            # Login successful
            user_info = {
                'id': user['id'],
                'username': user['username'],
                'role': user['role']
            }
            self.login_successful.emit(user_info)
            self.close()
        else:
            # Login failed
            self.error_label.setText("Invalid username or password")
            self.password_input.clear()
            self.password_input.setFocus()
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)
