"""
POS Terminal Page - Point of Sale checkout interface
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                                QFrame, QScrollArea, QDialog, QComboBox, QDoubleSpinBox,
                                QMessageBox, QHeaderView, QSplitter, QGroupBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class POSPage(QWidget):
    """POS Terminal page for fast checkout"""
    
    def __init__(self, user_info: dict, db):
        super().__init__()
        self.user_info = user_info
        self.db = db
        self.cart = []  # List of cart items
        self.discount_value = 0
        self.discount_type = 'fixed'  # 'fixed' or 'percent'
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Splitter for left (products) and right (cart) panels
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Product selection
        left_panel = self.create_product_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - Cart and checkout
        right_panel = self.create_cart_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        self.setLayout(layout)
    
    def create_product_panel(self) -> QWidget:
        """Create the product selection panel"""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Search section
        search_layout = QHBoxLayout()
        
        # Barcode input
        barcode_label = QLabel("Barcode:")
        barcode_label.setFont(QFont("Segoe UI", 10))
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or enter barcode")
        self.barcode_input.returnPressed.connect(self.add_product_by_barcode)
        search_layout.addWidget(barcode_label)
        search_layout.addWidget(self.barcode_input)
        
        # Search by name
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search product by name...")
        self.search_input.textChanged.connect(self.search_products)
        search_layout.addWidget(self.search_input)
        
        layout.addLayout(search_layout)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        
        add_weight_btn = QPushButton("⚖️ Add by Weight")
        add_weight_btn.clicked.connect(self.add_by_weight)
        btn_layout.addWidget(add_weight_btn)
        
        add_rs_btn = QPushButton("💰 Add by Rs.")
        add_rs_btn.clicked.connect(self.add_by_amount)
        btn_layout.addWidget(add_rs_btn)
        
        layout.addLayout(btn_layout)
        
        # Product table
        self.product_table = QTableWidget()
        self.product_table.setColumnCount(5)
        self.product_table.setHorizontalHeaderLabels(["Barcode", "Name", "Price", "Stock", "Unit"])
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.product_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.product_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.product_table.doubleClicked.connect(self.add_product_to_cart)
        self.product_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #e94560;
                color: white;
            }
        """)
        layout.addWidget(self.product_table)
        
        # Load products
        self.load_products()
        
        panel.setLayout(layout)
        return panel
    
    def create_cart_panel(self) -> QWidget:
        """Create the cart and checkout panel"""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Cart title
        cart_title = QLabel("🛒 Shopping Cart")
        cart_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(cart_title)
        
        # Cart table
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(5)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Qty", "Price", "Total", ""])
        self.cart_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cart_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """)
        layout.addWidget(self.cart_table)
        
        # Quantity controls
        qty_layout = QHBoxLayout()
        
        qty_label = QLabel("Quantity:")
        qty_layout.addWidget(qty_label)
        
        self.minus_btn = QPushButton("-")
        self.minus_btn.setFixedSize(40, 35)
        self.minus_btn.clicked.connect(self.decrease_quantity)
        qty_layout.addWidget(self.minus_btn)
        
        self.qty_input = QLineEdit()
        self.qty_input.setFixedWidth(60)
        self.qty_input.setAlignment(Qt.AlignCenter)
        self.qty_input.textChanged.connect(self.update_quantity_from_input)
        qty_layout.addWidget(self.qty_input)
        
        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedSize(40, 35)
        self.plus_btn.clicked.connect(self.increase_quantity)
        qty_layout.addWidget(self.plus_btn)
        
        remove_btn = QPushButton("🗑️ Remove")
        remove_btn.clicked.connect(self.remove_from_cart)
        qty_layout.addWidget(remove_btn)
        
        qty_layout.addStretch()
        layout.addLayout(qty_layout)
        
        # Discount section
        discount_group = QGroupBox("Discount")
        discount_layout = QHBoxLayout()
        
        self.discount_input = QDoubleSpinBox()
        self.discount_input.setRange(0, 999999)
        self.discount_input.setValue(0)
        self.discount_input.valueChanged.connect(self.apply_discount)
        discount_layout.addWidget(self.discount_input)
        
        self.discount_combo = QComboBox()
        self.discount_combo.addItem("Fixed", "fixed")
        self.discount_combo.addItem("Percent", "percent")
        self.discount_combo.currentIndexChanged.connect(self.apply_discount)
        discount_layout.addWidget(self.discount_combo)
        
        discount_group.setLayout(discount_layout)
        layout.addWidget(discount_group)
        
        # Totals section
        totals_frame = QFrame()
        totals_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        totals_layout = QVBoxLayout()
        totals_layout.setSpacing(8)
        
        self.subtotal_label = QLabel("Subtotal: Rs. 0.00")
        self.subtotal_label.setFont(QFont("Segoe UI", 12))
        totals_layout.addWidget(self.subtotal_label)
        
        self.discount_label = QLabel("Discount: Rs. 0.00")
        self.discount_label.setFont(QFont("Segoe UI", 12))
        totals_layout.addWidget(self.discount_label)
        
        total_label = QLabel("TOTAL:")
        total_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        totals_layout.addWidget(total_label)
        
        self.total_label = QLabel("Rs. 0.00")
        self.total_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self.total_label.setStyleSheet("color: #e94560;")
        totals_layout.addWidget(self.total_label)
        
        totals_frame.setLayout(totals_layout)
        layout.addWidget(totals_frame)
        
        # Buyer field
        buyer_layout = QHBoxLayout()
        buyer_label = QLabel("Buyer Name:")
        buyer_label.setFont(QFont("Segoe UI", 11))
        layout.addWidget(buyer_label)
        
        self.buyer_input = QLineEdit()
        self.buyer_input.setPlaceholderText("Customer name (optional)")
        layout.addWidget(self.buyer_input)
        
        # Payment buttons
        pay_layout = QHBoxLayout()
        pay_layout.setSpacing(10)
        
        self.walkin_btn = QPushButton("🚶 Walk-in (Cash)")
        self.walkin_btn.clicked.connect(lambda: self.complete_sale('walkin'))
        pay_layout.addWidget(self.walkin_btn)
        
        self.khata_btn = QPushButton("📖 Khata (Credit)")
        self.khata_btn.clicked.connect(lambda: self.complete_sale('khata'))
        pay_layout.addWidget(self.khata_btn)
        
        self.dasti_btn = QPushButton("🤝 Dasti (Loan)")
        self.dasti_btn.clicked.connect(lambda: self.complete_sale('dasti'))
        pay_layout.addWidget(self.dasti_btn)
        
        layout.addLayout(pay_layout)
        
        # Main PAY button
        self.pay_btn = QPushButton("💵 PAY (Enter)")
        self.pay_btn.setFixedHeight(60)
        self.pay_btn.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.pay_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.pay_btn.clicked.connect(self.open_payment_dialog)
        layout.addWidget(self.pay_btn)
        
        panel.setLayout(layout)
        return panel
    
    def load_products(self, search_text: str = ""):
        """Load products into the table"""
        self.product_table.setRowCount(0)
        
        if search_text:
            query = """
                SELECT barcode, name, sell_price, stock_qty, unit_id 
                FROM products 
                WHERE name LIKE ? OR barcode LIKE ?
                ORDER BY name
            """
            params = (f'%{search_text}%', f'%{search_text}%')
        else:
            query = "SELECT barcode, name, sell_price, stock_qty, unit_id FROM products ORDER BY name"
            params = ()
        
        self.db.execute(query, params)
        products = self.db.fetchall()
        
        for product in products:
            row = self.product_table.rowCount()
            self.product_table.insertRow(row)
            
            self.product_table.setItem(row, 0, QTableWidgetItem(product['barcode'] or ''))
            self.product_table.setItem(row, 1, QTableWidgetItem(product['name']))
            self.product_table.setItem(row, 2, QTableWidgetItem(f"Rs. {product['sell_price']:.2f}"))
            self.product_table.setItem(row, 3, QTableWidgetItem(str(product['stock_qty'])))
            
            # Get unit name
            unit_name = ''
            if product['unit_id']:
                self.db.execute("SELECT name FROM units WHERE id = ?", (product['unit_id'],))
                unit = self.db.fetchone()
                if unit:
                    unit_name = unit['name']
            self.product_table.setItem(row, 4, QTableWidgetItem(unit_name))
    
    def search_products(self):
        """Search products by name"""
        search_text = self.search_input.text().strip()
        self.load_products(search_text)
    
    def add_product_by_barcode(self):
        """Add product to cart by barcode"""
        barcode = self.barcode_input.text().strip()
        if not barcode:
            return
        
        self.db.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
        product = self.db.fetchone()
        
        if product:
            self.add_to_cart(product)
            self.barcode_input.clear()
        else:
            QMessageBox.warning(self, "Not Found", f"No product found with barcode: {barcode}")
    
    def add_product_to_cart(self, index):
        """Add product to cart when double-clicked"""
        row = index.row()
        barcode = self.product_table.item(row, 0).text()
        
        if barcode:
            self.db.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
            product = self.db.fetchone()
            if product:
                self.add_to_cart(product)
    
    def add_to_cart(self, product):
        """Add a product to the cart"""
        # Check if product already in cart
        for item in self.cart:
            if item['id'] == product['id']:
                item['quantity'] += 1
                self.update_cart_display()
                self.calculate_totals()
                return
        
        # Add new item to cart
        cart_item = {
            'id': product['id'],
            'name': product['name'],
            'price': product['sell_price'],
            'quantity': 1,
            'stock': product['stock_qty']
        }
        self.cart.append(cart_item)
        self.update_cart_display()
        self.calculate_totals()
    
    def update_cart_display(self):
        """Update the cart table display"""
        self.cart_table.setRowCount(0)
        
        for item in self.cart:
            row = self.cart_table.rowCount()
            self.cart_table.insertRow(row)
            
            self.cart_table.setItem(row, 0, QTableWidgetItem(item['name']))
            
            # Quantity with +/- buttons would be implemented here
            qty_item = QTableWidgetItem(str(item['quantity']))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.cart_table.setItem(row, 1, qty_item)
            
            self.cart_table.setItem(row, 2, QTableWidgetItem(f"Rs. {item['price']:.2f}"))
            
            total = item['quantity'] * item['price']
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"Rs. {total:.2f}"))
            
            # Delete button
            delete_btn = QPushButton("🗑️")
            delete_btn.setFixedSize(30, 30)
            delete_btn.clicked.connect(lambda checked, r=row: self.remove_item_at(r))
            self.cart_table.setCellWidget(row, 4, delete_btn)
    
    def remove_item_at(self, row: int):
        """Remove item at specific row"""
        if 0 <= row < len(self.cart):
            self.cart.pop(row)
            self.update_cart_display()
            self.calculate_totals()
    
    def increase_quantity(self):
        """Increase quantity of selected item"""
        selected_rows = self.cart_table.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            if 0 <= row < len(self.cart):
                self.cart[row]['quantity'] += 1
                self.update_cart_display()
                self.calculate_totals()
    
    def decrease_quantity(self):
        """Decrease quantity of selected item"""
        selected_rows = self.cart_table.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            if 0 <= row < len(self.cart):
                if self.cart[row]['quantity'] > 1:
                    self.cart[row]['quantity'] -= 1
                    self.update_cart_display()
                    self.calculate_totals()
    
    def update_quantity_from_input(self):
        """Update quantity from direct input"""
        try:
            selected_rows = self.cart_table.selectedItems()
            if selected_rows:
                row = selected_rows[0].row()
                if 0 <= row < len(self.cart):
                    qty = int(self.qty_input.text())
                    if qty > 0:
                        self.cart[row]['quantity'] = qty
                        self.update_cart_display()
                        self.calculate_totals()
        except:
            pass
    
    def remove_from_cart(self):
        """Remove selected item from cart"""
        selected_rows = self.cart_table.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            self.remove_item_at(row)
    
    def apply_discount(self):
        """Apply discount to cart"""
        self.discount_value = self.discount_input.value()
        self.discount_type = self.discount_combo.currentData()
        self.calculate_totals()
    
    def calculate_totals(self):
        """Calculate subtotal, discount, and total"""
        subtotal = sum(item['quantity'] * item['price'] for item in self.cart)
        
        if self.discount_type == 'percent':
            discount = subtotal * (self.discount_value / 100)
        else:
            discount = self.discount_value
        
        total = subtotal - discount
        
        self.subtotal_label.setText(f"Subtotal: Rs. {subtotal:.2f}")
        self.discount_label.setText(f"Discount: Rs. {discount:.2f}")
        self.total_label.setText(f"Rs. {total:.2f}")
        
        return subtotal, discount, total
    
    def add_by_weight(self):
        """Add product by weight (dialog)"""
        QMessageBox.information(self, "Add by Weight", "Weight-based entry dialog would open here")
    
    def add_by_amount(self):
        """Add product by custom amount"""
        QMessageBox.information(self, "Add by Rs.", "Custom amount entry dialog would open here")
    
    def open_payment_dialog(self):
        """Open payment method selection dialog"""
        if not self.cart:
            QMessageBox.warning(self, "Empty Cart", "Please add items to the cart first")
            return
        
        self.complete_sale('walkin')  # Default to walk-in for now
    
    def complete_sale(self, payment_method: str):
        """Complete the sale transaction"""
        if not self.cart:
            QMessageBox.warning(self, "Empty Cart", "Please add items to the cart first")
            return
        
        subtotal, discount, total = self.calculate_totals()
        
        if total <= 0:
            QMessageBox.warning(self, "Invalid Total", "Total amount must be greater than zero")
            return
        
        # Get buyer name
        buyer_name = self.buyer_input.text().strip() or "Walk-in"
        
        # For khata, would open customer selection dialog
        customer_id = None
        if payment_method == 'khata':
            # Open customer selection (simplified)
            QMessageBox.information(self, "Khata Sale", "Customer selection dialog would open here")
        
        try:
            # Insert sale record
            self.db.execute("""
                INSERT INTO sales (customer_id, buyer_name, subtotal, discount, discount_type, 
                                   total, amount_paid, change_amount, payment_method, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (customer_id, buyer_name, subtotal, discount, self.discount_type,
                  total, total, 0, payment_method, self.user_info['id']))
            
            sale_id = self.db.cursor.lastrowid
            
            # Insert sale items and update stock
            for item in self.cart:
                self.db.execute("""
                    INSERT INTO sale_items (sale_id, product_id, product_name, quantity, unit_price, total)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sale_id, item['id'], item['name'], item['quantity'], 
                      item['price'], item['quantity'] * item['price']))
                
                # Update stock
                self.db.execute("""
                    UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?
                """, (item['quantity'], item['id']))
            
            # Update customer ledger if khata
            if payment_method == 'khata' and customer_id:
                self.db.execute("""
                    INSERT INTO customer_ledger (customer_id, date, description, khata, balance)
                    VALUES (?, date('now'), ?, ?, ?)
                """, (customer_id, f"Sale #{sale_id}", total, total))
            
            # Add to dasti if dasti sale
            if payment_method == 'dasti':
                self.db.execute("""
                    INSERT INTO dasti (date, customer_name, user_name, description, amount, status)
                    VALUES (?, ?, ?, ?, ?, 'Pending')
                """, (buyer_name, self.user_info['username'], f"Sale #{sale_id}", total))
            
            # Log to global history
            self.db.execute("""
                INSERT INTO global_history (transaction_type, description, amount, user_name)
                VALUES (?, ?, ?, ?)
            """, ('Sale', f"Sale #{sale_id} - {buyer_name}", total, self.user_info['username']))
            
            self.db.commit()
            
            # Show success message
            QMessageBox.information(self, "Sale Completed", 
                                  f"Sale completed successfully!\nTotal: Rs. {total:.2f}")
            
            # Clear cart
            self.cart = []
            self.update_cart_display()
            self.discount_input.setValue(0)
            self.buyer_input.clear()
            self.calculate_totals()
            self.load_products()  # Refresh product list with updated stock
            
        except Exception as e:
            self.db.connection.rollback()
            QMessageBox.critical(self, "Error", f"Failed to complete sale: {str(e)}")
