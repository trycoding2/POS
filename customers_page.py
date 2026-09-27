"""
Customers Page - Customer management with ledger and Khata tracking
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                                QFrame, QDialog, QFileDialog, QMessageBox, QHeaderView,
                                QScrollArea, QDateEdit, QComboBox, QDoubleSpinBox, QTextEdit)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont


class CustomersPage(QWidget):
    """Customer management page with ledger tracking"""
    
    def __init__(self, user_info: dict, db):
        super().__init__()
        self.user_info = user_info
        self.db = db
        self.is_admin = user_info['role'] == 'Admin'
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("👥 Customer Management")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_label.setStyleSheet("color: #333;")
        layout.addWidget(title_label)
        
        # Search row
        search_layout = QHBoxLayout()
        
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name, father's name, or phone...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self.load_customers)
        search_layout.addWidget(self.search_input)
        
        search_layout.addStretch()
        
        # Add customer button
        if self.is_admin:
            add_btn = QPushButton("➕ Add New Customer")
            add_btn.clicked.connect(self.open_add_customer_form)
            search_layout.addWidget(add_btn)
        
        layout.addLayout(search_layout)
        
        # Customers table
        self.customers_table = QTableWidget()
        self.customers_table.setColumnCount(5)
        self.customers_table.setHorizontalHeaderLabels([
            "ID", "Name", "Father's Name", "Phone", "Balance"
        ])
        self.customers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.customers_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.customers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.customers_table.doubleClicked.connect(self.open_customer_popup)
        self.customers_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
            }
        """)
        layout.addWidget(self.customers_table)
        
        self.setLayout(layout)
        
        # Load customers
        self.load_customers()
    
    def load_customers(self):
        """Load customers into the table"""
        self.customers_table.setRowCount(0)
        
        search_text = self.search_input.text().strip()
        
        query = """
            SELECT c.id, c.name, c.father_name, c.contact1,
                   COALESCE(SUM(cl.khata - cl.jama), 0) as balance
            FROM customers c
            LEFT JOIN customer_ledger cl ON c.id = cl.customer_id
            WHERE 1=1
        """
        params = []
        
        if search_text:
            query += " AND (c.name LIKE ? OR c.father_name LIKE ? OR c.contact1 LIKE ?)"
            params.extend([f'%{search_text}%', f'%{search_text}%', f'%{search_text}%'])
        
        query += " GROUP BY c.id ORDER BY c.name"
        
        self.db.execute(query, tuple(params))
        customers = self.db.fetchall()
        
        for customer in customers:
            row = self.customers_table.rowCount()
            self.customers_table.insertRow(row)
            
            self.customers_table.setItem(row, 0, QTableWidgetItem(str(customer['id'])))
            self.customers_table.setItem(row, 1, QTableWidgetItem(customer['name']))
            self.customers_table.setItem(row, 2, QTableWidgetItem(customer['father_name'] or ''))
            self.customers_table.setItem(row, 3, QTableWidgetItem(customer['contact1']))
            
            # Balance with color coding
            balance = customer['balance']
            balance_item = QTableWidgetItem(f"Rs. {balance:.2f}")
            if balance > 0:
                balance_item.setBackground(Qt.red)
            else:
                balance_item.setBackground(Qt.green)
            self.customers_table.setItem(row, 4, balance_item)
    
    def open_add_customer_form(self):
        """Open dialog to add new customer"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Customer")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Form fields
        form_layout = QVBoxLayout()
        
        # Name
        name_label = QLabel("Full Name *")
        form_layout.addWidget(name_label)
        name_input = QLineEdit()
        form_layout.addWidget(name_input)
        
        # Father's Name
        father_label = QLabel("Father's Name")
        form_layout.addWidget(father_label)
        father_input = QLineEdit()
        form_layout.addWidget(father_input)
        
        # Contact 1
        contact1_label = QLabel("Contact 1 *")
        form_layout.addWidget(contact1_label)
        contact1_input = QLineEdit()
        form_layout.addWidget(contact1_input)
        
        # Contact 2
        contact2_label = QLabel("Contact 2")
        form_layout.addWidget(contact2_label)
        contact2_input = QLineEdit()
        form_layout.addWidget(contact2_input)
        
        # Address
        address_label = QLabel("Address")
        form_layout.addWidget(address_label)
        address_input = QTextEdit()
        address_input.setMaximumHeight(80)
        form_layout.addWidget(address_input)
        
        layout.addLayout(form_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Save New Customer")
        save_btn.clicked.connect(lambda: self.save_customer(
            dialog, name_input, father_input, contact1_input, contact2_input, address_input
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
    def save_customer(self, dialog, name_input, father_input, contact1_input, 
                     contact2_input, address_input):
        """Save new customer to database"""
        name = name_input.text().strip()
        if not name:
            QMessageBox.warning(dialog, "Required Field", "Full Name is required")
            return
        
        contact1 = contact1_input.text().strip()
        if not contact1:
            QMessageBox.warning(dialog, "Required Field", "Contact 1 is required")
            return
        
        try:
            self.db.execute("""
                INSERT INTO customers (name, father_name, contact1, contact2, address)
                VALUES (?, ?, ?, ?, ?)
            """, (name, father_input.text().strip(), contact1, 
                  contact2_input.text().strip(), address_input.toPlainText()))
            self.db.commit()
            
            QMessageBox.information(dialog, "Success", "Customer added successfully")
            dialog.close()
            self.load_customers()
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to add customer: {str(e)}")
    
    def open_customer_popup(self, index):
        """Open detailed customer popup with ledger"""
        row = index.row()
        customer_id = int(self.customers_table.item(row, 0).text())
        
        self.db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        customer = self.db.fetchone()
        
        if not customer:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Customer: {customer['name']}")
        dialog.setMinimumSize(900, 700)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        
        # Customer info section
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        info_layout = QVBoxLayout()
        
        # Get outstanding balance
        self.db.execute("""
            SELECT COALESCE(SUM(khata - jama), 0) as balance
            FROM customer_ledger WHERE customer_id = ?
        """, (customer_id,))
        balance_result = self.db.fetchone()
        balance = balance_result['balance'] if balance_result else 0
        
        info_layout.addWidget(QLabel(f"<b>Name:</b> {customer['name']}"))
        info_layout.addWidget(QLabel(f"<b>Father's Name:</b> {customer['father_name'] or 'N/A'}"))
        info_layout.addWidget(QLabel(f"<b>Contact:</b> {customer['contact1']}"))
        if customer['contact2']:
            info_layout.addWidget(QLabel(f"<b>Alternate Contact:</b> {customer['contact2']}"))
        info_layout.addWidget(QLabel(f"<b>Address:</b> {customer['address'] or 'N/A'}"))
        
        balance_label = QLabel(f"<b>Outstanding Balance:</b> Rs. {balance:.2f}")
        balance_label.setStyleSheet("color: red;" if balance > 0 else "color: green;")
        balance_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        info_layout.addWidget(balance_label)
        
        info_frame.setLayout(info_layout)
        main_layout.addWidget(info_frame)
        
        # Ledger section
        ledger_group = QGroupBox("Transaction History (Ledger)")
        ledger_layout = QVBoxLayout()
        
        # Filter row
        filter_row = QHBoxLayout()
        
        filter_label = QLabel("Filter:")
        filter_row.addWidget(filter_label)
        
        filter_combo = QComboBox()
        filter_combo.addItem("All Transactions", "all")
        filter_combo.addItem("Khata Only", "khata")
        filter_combo.addItem("Jama Only", "jama")
        filter_combo.addItem("Last 7 Days", "7days")
        filter_combo.addItem("Last 30 Days", "30days")
        filter_combo.currentIndexChanged.connect(lambda: self.load_customer_ledger(ledger_table, customer_id, filter_combo))
        filter_row.addWidget(filter_combo)
        
        filter_row.addStretch()
        ledger_layout.addLayout(filter_row)
        
        # Ledger table
        ledger_table = QTableWidget()
        ledger_table.setColumnCount(6)
        ledger_table.setHorizontalHeaderLabels(["ID", "Date", "Description", "Khata", "Jama", "Balance"])
        ledger_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        ledger_table.setSelectionBehavior(QTableWidget.SelectRows)
        ledger_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ledger_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
            }
        """)
        ledger_layout.addWidget(ledger_table)
        
        # Load ledger
        self.load_customer_ledger(ledger_table, customer_id, filter_combo)
        
        ledger_group.setLayout(ledger_layout)
        main_layout.addWidget(ledger_group)
        
        # Action buttons
        btn_row = QHBoxLayout()
        
        if self.is_admin:
            add_khata_btn = QPushButton("➕ Add Khata (Purchase)")
            add_khata_btn.clicked.connect(lambda: self.add_customer_khata(customer_id, customer['name']))
            btn_row.addWidget(add_khata_btn)
        
        add_jama_btn = QPushButton("💰 Add Jama (Payment)")
        add_jama_btn.clicked.connect(lambda: self.add_customer_jama(customer_id, customer['name']))
        btn_row.addWidget(add_jama_btn)
        
        schedule_btn = QPushButton("📅 Schedule Payment")
        schedule_btn.clicked.connect(lambda: self.schedule_payment(customer_id, customer['name']))
        btn_row.addWidget(schedule_btn)
        
        whatsapp_btn = QPushButton("📱 Send WhatsApp")
        whatsapp_btn.clicked.connect(lambda: self.send_whatsapp_balance(customer_id, customer['name'], balance))
        btn_row.addWidget(whatsapp_btn)
        
        btn_row.addStretch()
        main_layout.addLayout(btn_row)
        
        dialog.setLayout(main_layout)
        dialog.exec()
    
    def load_customer_ledger(self, table, customer_id, filter_combo):
        """Load customer ledger transactions"""
        table.setRowCount(0)
        
        filter_type = filter_combo.currentData()
        
        query = """
            SELECT id, date, description, khata, jama, balance
            FROM customer_ledger
            WHERE customer_id = ?
        """
        params = [customer_id]
        
        if filter_type == '7days':
            query += " AND date >= date('now', '-7 days')"
        elif filter_type == '30days':
            query += " AND date >= date('now', '-30 days')"
        
        query += " ORDER BY date DESC, id DESC"
        
        self.db.execute(query, tuple(params))
        transactions = self.db.fetchall()
        
        for txn in transactions:
            row = table.rowCount()
            table.insertRow(row)
            
            table.setItem(row, 0, QTableWidgetItem(str(txn['id'])))
            table.setItem(row, 1, QTableWidgetItem(txn['date']))
            table.setItem(row, 2, QTableWidgetItem(txn['description'] or ''))
            
            khata_item = QTableWidgetItem(f"{txn['khata']:.2f}" if txn['khata'] else "-")
            if txn['khata']:
                khata_item.setBackground(Qt.lightGray)
            table.setItem(row, 3, khata_item)
            
            jama_item = QTableWidgetItem(f"{txn['jama']:.2f}" if txn['jama'] else "-")
            if txn['jama']:
                jama_item.setBackground(Qt.green)
            table.setItem(row, 4, jama_item)
            
            table.setItem(row, 5, QTableWidgetItem(f"{txn['balance']:.2f}"))
    
    def add_customer_khata(self, customer_id, customer_name):
        """Add Khata (credit purchase) for customer"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add Khata - {customer_name}")
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Amount
        amount_label = QLabel("Amount (Khata):")
        layout.addWidget(amount_label)
        amount_input = QDoubleSpinBox()
        amount_input.setRange(0.01, 999999)
        amount_input.setValue(0)
        layout.addWidget(amount_input)
        
        # Description
        desc_label = QLabel("Description:")
        layout.addWidget(desc_label)
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("e.g., Purchase on credit")
        layout.addWidget(desc_input)
        
        # Date
        date_label = QLabel("Date:")
        layout.addWidget(date_label)
        date_input = QDateEdit()
        date_input.setDate(QDate.currentDate())
        date_input.setCalendarPopup(True)
        layout.addWidget(date_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Khata")
        save_btn.clicked.connect(lambda: self.save_khata(
            dialog, customer_id, amount_input, desc_input, date_input
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
    def save_khata(self, dialog, customer_id, amount_input, desc_input, date_input):
        """Save Khata entry"""
        amount = amount_input.value()
        if amount <= 0:
            QMessageBox.warning(dialog, "Invalid Amount", "Amount must be greater than zero")
            return
        
        try:
            # Get current balance
            self.db.execute("""
                SELECT COALESCE(SUM(khata - jama), 0) as balance
                FROM customer_ledger WHERE customer_id = ?
            """, (customer_id,))
            result = self.db.fetchone()
            current_balance = result['balance'] if result else 0
            
            new_balance = current_balance + amount
            
            self.db.execute("""
                INSERT INTO customer_ledger (customer_id, date, description, khata, balance)
                VALUES (?, ?, ?, ?, ?)
            """, (customer_id, date_input.date().toString('yyyy-MM-dd'),
                  desc_input.text().strip(), amount, new_balance))
            
            # Log to history
            self.db.execute("""
                INSERT INTO global_history (transaction_type, description, amount, user_name)
                VALUES (?, ?, ?, ?)
            """, ('Customer Khata', f"Khata added for customer {customer_id}", amount, self.user_info['username']))
            
            self.db.commit()
            QMessageBox.information(dialog, "Success", "Khata added successfully")
            dialog.close()
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to add Khata: {str(e)}")
    
    def add_customer_jama(self, customer_id, customer_name):
        """Add Jama (payment) for customer"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add Payment - {customer_name}")
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Amount
        amount_label = QLabel("Payment Amount:")
        layout.addWidget(amount_label)
        amount_input = QDoubleSpinBox()
        amount_input.setRange(0.01, 999999)
        amount_input.setValue(0)
        layout.addWidget(amount_input)
        
        # Description
        desc_label = QLabel("Description:")
        layout.addWidget(desc_label)
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("e.g., Cash payment received")
        layout.addWidget(desc_input)
        
        # Date
        date_label = QLabel("Date:")
        layout.addWidget(date_label)
        date_input = QDateEdit()
        date_input.setDate(QDate.currentDate())
        date_input.setCalendarPopup(True)
        layout.addWidget(date_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Payment")
        save_btn.clicked.connect(lambda: self.save_jama(
            dialog, customer_id, amount_input, desc_input, date_input
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
    def save_jama(self, dialog, customer_id, amount_input, desc_input, date_input):
        """Save Jama (payment) entry"""
        amount = amount_input.value()
        if amount <= 0:
            QMessageBox.warning(dialog, "Invalid Amount", "Amount must be greater than zero")
            return
        
        try:
            # Get current balance
            self.db.execute("""
                SELECT COALESCE(SUM(khata - jama), 0) as balance
                FROM customer_ledger WHERE customer_id = ?
            """, (customer_id,))
            result = self.db.fetchone()
            current_balance = result['balance'] if result else 0
            
            new_balance = current_balance - amount
            
            self.db.execute("""
                INSERT INTO customer_ledger (customer_id, date, description, jama, balance)
                VALUES (?, ?, ?, ?, ?)
            """, (customer_id, date_input.date().toString('yyyy-MM-dd'),
                  desc_input.text().strip(), amount, new_balance))
            
            # Log to history
            self.db.execute("""
                INSERT INTO global_history (transaction_type, description, amount, user_name)
                VALUES (?, ?, ?, ?)
            """, ('Customer Payment', f"Payment received from customer {customer_id}", amount, self.user_info['username']))
            
            self.db.commit()
            QMessageBox.information(dialog, "Success", "Payment recorded successfully")
            dialog.close()
            self.load_customers()  # Refresh customer list
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to record payment: {str(e)}")
    
    def schedule_payment(self, customer_id, customer_name):
        """Schedule a future payment"""
        QMessageBox.information(self, "Schedule Payment", 
                              "Payment scheduling dialog would open here")
    
    def send_whatsapp_balance(self, customer_id, customer_name, balance):
        """Send balance reminder via WhatsApp"""
        QMessageBox.information(self, "WhatsApp", 
                              f"Would send balance reminder to {customer_name}\nBalance: Rs. {balance:.2f}")
