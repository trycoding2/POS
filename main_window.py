"""
Main Window - Primary application window with sidebar navigation
"""

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                QFrame, QLabel, QPushButton, QScrollArea, QStackedWidget,
                                QGraphicsDropShadowEffect, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush

from database import DatabaseManager


class MainWindow(QMainWindow):
    """Main application window with sidebar and content area"""
    
    def __init__(self, user_info: dict):
        super().__init__()
        self.user_info = user_info
        self.db = DatabaseManager.get_instance()
        self.sidebar_expanded = True
        self.current_font_size = 10
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Retail Management System")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Sidebar
        self.sidebar = self.create_sidebar()
        main_layout.addWidget(self.sidebar)
        
        # Content area
        content_frame = QFrame()
        content_frame.setObjectName("contentFrame")
        content_frame.setStyleSheet("""
            #contentFrame {
                background-color: #f5f6fa;
            }
        """)
        
        content_layout = QVBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        self.header = self.create_header()
        content_layout.addWidget(self.header)
        
        # Stacked widget for pages
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #f5f6fa;")
        content_layout.addWidget(self.stack)
        
        content_frame.setLayout(content_layout)
        main_layout.addWidget(content_frame, 1)
        
        central_widget.setLayout(main_layout)
        
        # Apply dark mode if enabled
        self.apply_theme()
        
    def create_sidebar(self):
        """Create the sidebar navigation panel"""
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebar")
        sidebar_frame.setMinimumWidth(250)
        sidebar_frame.setMaximumWidth(250)
        sidebar_frame.setStyleSheet("""
            #sidebar {
                background-color: #1a1a2e;
                border-right: 1px solid #16213e;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo/Title section
        title_frame = QFrame()
        title_frame.setFixedHeight(80)
        title_frame.setStyleSheet("""
            QFrame {
                border-bottom: 1px solid #16213e;
            }
        """)
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignCenter)
        
        # Logo circle
        logo = QLabel()
        logo.setFixedSize(50, 50)
        logo_pixmap = QPixmap(50, 50)
        logo_pixmap.fill(Qt.transparent)
        painter = QPainter(logo_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#e94560")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 50, 50)
        painter.end()
        logo.setPixmap(logo_pixmap)
        
        title_label = QLabel("Retail\nSystem")
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_label.setStyleSheet("color: white;")
        title_label.setAlignment(Qt.AlignCenter)
        
        title_layout.addWidget(logo)
        title_layout.addWidget(title_label)
        title_frame.setLayout(title_layout)
        layout.addWidget(title_frame)
        
        # Navigation buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        nav_widget = QWidget()
        nav_layout = QVBoxLayout()
        nav_layout.setSpacing(5)
        nav_layout.setContentsMargins(10, 15, 10, 15)
        
        # Define menu items based on role
        is_admin = self.user_info['role'] == 'Admin'
        
        self.menu_buttons = {}
        menu_items = [
            ('Dashboard', 'dashboard', True),
            ('POS Terminal', 'pos', True),
            ('Inventory', 'inventory', True),
            ('Customers', 'customers', True),
            ('Providers', 'providers', True),
            ('Stocks', 'stocks', is_admin),
            ('Expenses', 'expenses', is_admin),
            ('Dasti', 'dasti', True),
            ('Notes', 'notes', True),
            ('Media Player', 'media', True),
            ('Payments', 'payments', True),
            ('Demands', 'demands', True),
            ('Analytics', 'analytics', is_admin),
            ('Settings', 'settings', is_admin),
            ('History', 'history', is_admin),
            ('Shortcuts', 'shortcuts', is_admin),
        ]
        
        for text, name, show in menu_items:
            if show:
                btn = self.create_menu_button(text, name)
                nav_layout.addWidget(btn)
                self.menu_buttons[name] = btn
        
        nav_layout.addStretch()
        nav_widget.setLayout(nav_layout)
        scroll.setWidget(nav_widget)
        layout.addWidget(scroll)
        
        sidebar_frame.setLayout(layout)
        return sidebar_frame
    
    def create_menu_button(self, text: str, name: str) -> QPushButton:
        """Create a navigation button for the sidebar"""
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(45)
        btn.setFont(QFont("Segoe UI", 11))
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #aaa;
                text-align: left;
                padding-left: 20px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #16213e;
                color: white;
            }
            QPushButton:checked {
                background-color: #e94560;
                color: white;
                font-weight: bold;
            }
        """)
        btn.clicked.connect(lambda: self.navigate_to(name))
        return btn
    
    def create_header(self):
        """Create the top header bar"""
        header_frame = QFrame()
        header_frame.setFixedHeight(60)
        header_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-bottom: 1px solid #ddd;
            }
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        
        # Hamburger button
        hamburger_btn = QPushButton("☰")
        hamburger_btn.setFixedSize(40, 40)
        hamburger_btn.setFont(QFont("Segoe UI", 16))
        hamburger_btn.setCursor(Qt.PointingHandCursor)
        hamburger_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border-radius: 8px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        hamburger_btn.clicked.connect(self.toggle_sidebar)
        layout.addWidget(hamburger_btn)
        
        layout.addStretch()
        
        # User info
        user_label = QLabel(f"👤 {self.user_info['username']} ({self.user_info['role']})")
        user_label.setFont(QFont("Segoe UI", 11))
        user_label.setStyleSheet("color: #333;")
        layout.addWidget(user_label)
        
        layout.addSpacing(20)
        
        # Font size slider
        font_label = QLabel("A")
        font_label.setFont(QFont("Segoe UI", 10))
        font_label.setStyleSheet("color: #666;")
        layout.addWidget(font_label)
        
        from PySide6.QtWidgets import QSlider
        font_slider = QSlider(Qt.Horizontal)
        font_slider.setRange(10, 20)
        font_slider.setValue(10)
        font_slider.setFixedWidth(100)
        font_slider.valueChanged.connect(self.change_font_size)
        layout.addWidget(font_slider)
        
        font_label2 = QLabel("A")
        font_label2.setFont(QFont("Segoe UI", 14))
        font_label2.setStyleSheet("color: #666;")
        layout.addWidget(font_label2)
        
        layout.addSpacing(20)
        
        # Dark mode toggle
        from PySide6.QtWidgets import QCheckBox
        dark_mode_cb = QCheckBox("🌙")
        dark_mode_cb.setChecked(True)
        dark_mode_cb.setCursor(Qt.PointingHandCursor)
        dark_mode_cb.setStyleSheet("""
            QCheckBox {
                font-size: 16px;
                color: #333;
            }
            QCheckBox::indicator {
                width: 0px;
                height: 0px;
            }
        """)
        dark_mode_cb.toggled.connect(self.toggle_dark_mode)
        layout.addWidget(dark_mode_cb)
        
        header_frame.setLayout(layout)
        return header_frame
    
    def navigate_to(self, page_name: str):
        """Navigate to a specific page"""
        # Update button states
        for name, btn in self.menu_buttons.items():
            btn.setChecked(name == page_name)
        
        # Import and create page if not exists
        if page_name == 'dashboard':
            from dashboard_page import DashboardPage
            page = DashboardPage(self.user_info, self.db)
        elif page_name == 'pos':
            from pos_page import POSPage
            page = POSPage(self.user_info, self.db)
        elif page_name == 'inventory':
            from inventory_page import InventoryPage
            page = InventoryPage(self.user_info, self.db)
        elif page_name == 'customers':
            from customers_page import CustomersPage
            page = CustomersPage(self.user_info, self.db)
        elif page_name == 'providers':
            from providers_page import ProvidersPage
            page = ProvidersPage(self.user_info, self.db)
        else:
            # Placeholder for other pages
            from PySide6.QtWidgets import QLabel
            page = QLabel(f"<h2 style='color: #666; padding: 50px;'>{page_name.title()} Module - Coming Soon</h2>")
            page.setAlignment(Qt.AlignCenter)
        
        # Add or get existing page
        index = self.find_page_index(page_name)
        if index == -1:
            self.stack.addWidget(page)
            self.stack.setCurrentWidget(page)
        else:
            self.stack.setCurrentIndex(index)
    
    def find_page_index(self, page_name: str) -> int:
        """Find the index of a page by name"""
        # Simple implementation - in production would use page object names
        return -1
    
    def toggle_sidebar(self):
        """Toggle sidebar visibility"""
        self.sidebar_expanded = not self.sidebar_expanded
        if self.sidebar_expanded:
            self.sidebar.setMinimumWidth(250)
            self.sidebar.setMaximumWidth(250)
        else:
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(0)
    
    def change_font_size(self, value: int):
        """Change the global font size"""
        self.current_font_size = value
        self.setFont(QFont("Segoe UI", value))
    
    def toggle_dark_mode(self, checked: bool):
        """Toggle between dark and light mode"""
        if checked:
            self.apply_theme()
        else:
            self.apply_light_theme()
    
    def apply_theme(self):
        """Apply dark theme"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
        """)
    
    def apply_light_theme(self):
        """Apply light theme"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f6fa;
            }
        """)
