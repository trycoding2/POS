"""
Dashboard Page - Overview with summary cards and real-time data
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QFrame, QScrollArea, QGridLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class DashboardPage(QWidget):
    """Dashboard page with summary cards showing key metrics"""
    
    def __init__(self, user_info: dict, db):
        super().__init__()
        self.user_info = user_info
        self.db = db
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Title
        title_label = QLabel("Dashboard")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_label.setStyleSheet("color: #333;")
        layout.addWidget(title_label)
        
        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        # Cards container
        cards_widget = QWidget()
        cards_layout = QGridLayout()
        cards_layout.setSpacing(20)
        
        # Create summary cards
        self.cards = {}
        card_data = [
            ('total_revenue', 'Total Revenue', 'Rs. 0', '#4CAF50', '💰'),
            ('total_orders', 'Total Orders', '0', '#2196F3', '📦'),
            ('active_customers', 'Active Customers', '0', '#FF9800', '👥'),
            ('net_profit', 'Net Profit', 'Rs. 0', '#9C27B0', '📈'),
            ('low_stock', 'Low Stock Items', '0', '#F44336', '⚠️'),
            ('pending_orders', "Today's Sales", '0', '#00BCD4', '🛒'),
            ('total_suppliers', 'Total Suppliers', '0', '#795548', '🏭'),
            ('monthly_expenses', 'Monthly Expenses', 'Rs. 0', '#E91E63', '💸'),
        ]
        
        row = 0
        col = 0
        for key, title, value, color, icon in card_data:
            card = self.create_card(title, value, color, icon)
            cards_layout.addWidget(card, row, col)
            self.cards[key] = {'card': card, 'value_label': card.findChild(QLabel, f'{key}_value')}
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
        
        cards_widget.setLayout(cards_layout)
        scroll.setWidget(cards_widget)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        
        # Load data
        self.load_dashboard_data()
    
    def create_card(self, title: str, value: str, color: str, icon: str) -> QFrame:
        """Create a summary card widget"""
        card = QFrame()
        card.setObjectName("summaryCard")
        card.setStyleSheet(f"""
            #summaryCard {{
                background-color: white;
                border-radius: 12px;
                padding: 20px;
                border-left: 5px solid {color};
            }}
            #summaryCard:hover {{
                background-color: #f8f9fa;
            }}
        """)
        
        # Add shadow
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Icon and title row
        header_layout = QHBoxLayout()
        
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 24))
        header_layout.addWidget(icon_label)
        
        header_layout.addStretch()
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 11))
        title_label.setStyleSheet("color: #666;")
        header_layout.addWidget(title_label)
        
        layout.addLayout(header_layout)
        
        # Value label
        value_label = QLabel(value)
        value_label.setObjectName(f'{title.replace(" ", "_").lower()}_value')
        value_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(value_label)
        
        card.setLayout(layout)
        return card
    
    def load_dashboard_data(self):
        """Load and update dashboard data from database"""
        try:
            # Total Revenue
            self.db.execute("SELECT COALESCE(SUM(total), 0) as total FROM sales")
            result = self.db.fetchone()
            total_revenue = result['total'] if result else 0
            self.update_card_value('total_revenue', f'Rs. {total_revenue:,.2f}')
            
            # Total Orders
            self.db.execute("SELECT COUNT(*) as count FROM sales")
            result = self.db.fetchone()
            total_orders = result['count'] if result else 0
            self.update_card_value('total_orders', str(total_orders))
            
            # Active Customers (customers who purchased this month)
            self.db.execute("""
                SELECT COUNT(DISTINCT customer_id) as count 
                FROM sales 
                WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
                AND customer_id IS NOT NULL
            """)
            result = self.db.fetchone()
            active_customers = result['count'] if result else 0
            self.update_card_value('active_customers', str(active_customers))
            
            # Net Profit (simplified: revenue - cost)
            self.db.execute("""
                SELECT 
                    COALESCE(SUM(s.total), 0) - COALESCE(SUM(si.quantity * p.purchase_price), 0) as profit
                FROM sales s
                LEFT JOIN sale_items si ON s.id = si.sale_id
                LEFT JOIN products p ON si.product_id = p.id
            """)
            result = self.db.fetchone()
            net_profit = result['profit'] if result else 0
            self.update_card_value('net_profit', f'Rs. {net_profit:,.2f}')
            
            # Low Stock Items
            self.db.execute("""
                SELECT COUNT(*) as count FROM products 
                WHERE stock_qty <= 5
            """)
            result = self.db.fetchone()
            low_stock = result['count'] if result else 0
            self.update_card_value('low_stock', str(low_stock))
            
            # Today's Sales
            self.db.execute("""
                SELECT COUNT(*) as count FROM sales 
                WHERE date(date) = date('now')
            """)
            result = self.db.fetchone()
            pending_orders = result['count'] if result else 0
            self.update_card_value('pending_orders', str(pending_orders))
            
            # Total Suppliers
            self.db.execute("SELECT COUNT(*) as count FROM providers")
            result = self.db.fetchone()
            total_suppliers = result['count'] if result else 0
            self.update_card_value('total_suppliers', str(total_suppliers))
            
            # Monthly Expenses
            self.db.execute("""
                SELECT COALESCE(SUM(amount), 0) as total FROM expenses
                WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            """)
            result = self.db.fetchone()
            monthly_expenses = result['total'] if result else 0
            self.update_card_value('monthly_expenses', f'Rs. {monthly_expenses:,.2f}')
            
        except Exception as e:
            print(f"Error loading dashboard data: {e}")
    
    def update_card_value(self, card_key: str, value: str):
        """Update the value displayed on a card"""
        if card_key in self.cards:
            value_label = self.cards[card_key]['value_label']
            if value_label:
                value_label.setText(value)
