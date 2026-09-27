"""
Providers Page - Supplier management with ledger tracking
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                                QFrame, QDialog, QMessageBox, QHeaderView, QGroupBox,
                                QDateEdit, QComboBox, QDoubleSpinBox, QTextEdit)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont


class ProvidersPage(QWidget):
    """Provider/Supplier management page with ledger tracking"""
    
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
        title_label = QLabel("🏭 Provider/Supplier Management")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_label.setStyleSheet("color: #333;")
        layout.addWidget(title_label)
        
        # Search row
        search_layout = QHBoxLayout()
        
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by company or salesman...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self.load_providers)
        search_layout.addWidget(self.search_input)
        
        search_layout.addStretch()
        
        # Add provider button (admin only)
        if self.is_admin:
            add_btn = QPushButton("➕ Add New Provider")
            add_btn.clicked.connect(self.open_add_provider_form)
            search_layout.addWidget(add_btn)
        
        layout.addLayout(search_layout)
        
        # Providers table
        self.providers_table = QTableWidget()
        self.providers_table.setColumnCount(6)
        self.providers_table.setHorizontalHeaderLabels([
            "ID", "Company", "Salesman", "Contact", "Payable", "Paid"
        ])
        self.providers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.providers_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.providers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.providers_table.doubleClicked.connect(self.open_provider_popup)
        self.providers_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
            }
        """)
        layout.addWidget(self.providers_table)
        
        self.setLayout(layout)
        
        # Load providers
        self.load_providers()
    
    def load_providers(self):
        """Load providers into the table"""
        self.providers_table.setRowCount(0)
        
        search_text = self.search_input.text().strip()
        
        query = """
            SELECT p.id, p.company_name, p.salesman_name, p.salesman_contact,
                   COALESCE(SUM(pl.orders), 0) as total_orders,
                   COALESCE(SUM(pl.jama), 0) as total_paid
            FROM providers p
            LEFT JOIN provider_ledger pl ON p.id = pl.provider_id
            WHERE 1=1
        """
        params = []
        
        if search_text:
            query += " AND (p.company_name LIKE ? OR p.salesman_name LIKE ?)"
            params.extend([f'%{search_text}%', f'%{search_text}%'])
        
        query += " GROUP BY p.id ORDER BY p.company_name"
        
        self.db.execute(query, tuple(params))
        providers = self.db.fetchall()
        
        for provider in providers:
            row = self.providers_table.rowCount()
            self.providers_table.insertRow(row)
            
            self.providers_table.setItem(row, 0, QTableWidgetItem(str(provider['id'])))
            self.providers_table.setItem(row, 1, QTableWidgetItem(provider['company_name']))
            self.providers_table.setItem(row, 2, QTableWidgetItem(provider['salesman_name'] or ''))
            self.providers_table.setItem(row, 3, QTableWidgetItem(provider['salesman_contact'] or ''))
            
            payable = provider['total_orders'] - provider['total_paid']
            payable_item = QTableWidgetItem(f"Rs. {payable:.2f}")
            if payable > 0:
                payable_item.setBackground(Qt.red)
            self.providers_table.setItem(row, 4, payable_item)
            
            self.providers_table.setItem(row, 5, QTableWidgetItem(f"Rs. {provider['total_paid']:.2f}"))
    
    def open_add_provider_form(self):
        """Open dialog to add new provider"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Provider")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Form fields
        form_layout = QVBoxLayout()
        
        # Company Name
        company_label = QLabel("Company Name *")
        form_layout.addWidget(company_label)
        company_input = QLineEdit()
        form_layout.addWidget(company_input)
        
        # Owner Name
        owner_label = QLabel("Owner Name")
        form_layout.addWidget(owner_label)
        owner_input = QLineEdit()
        form_layout.addWidget(owner_input)
        
        # Owner Contact
        owner_contact_label = QLabel("Owner Contact")
        form_layout.addWidget(owner_contact_label)
        owner_contact_input = QLineEdit()
        form_layout.addWidget(owner_contact_input)
        
        # Salesman Name
        salesman_label = QLabel("Salesman Name")
        form_layout.addWidget(salesman_label)
        salesman_input = QLineEdit()
        form_layout.addWidget(salesman_input)
        
        # Salesman Contact
        salesman_contact_label = QLabel("Salesman Contact")
        form_layout.addWidget(salesman_contact_label)
        salesman_contact_input = QLineEdit()
        form_layout.addWidget(salesman_contact_input)
        
        # Delivery Man
        delivery_label = QLabel("Delivery Man Name")
        form_layout.addWidget(delivery_label)
        delivery_input = QLineEdit()
        form_layout.addWidget(delivery_input)
        
        # Delivery Contact
        delivery_contact_label = QLabel("Delivery Man Contact")
        form_layout.addWidget(delivery_contact_label)
        delivery_contact_input = QLineEdit()
        form_layout.addWidget(delivery_contact_input)
        
        # Address
        address_label = QLabel("Company Address")
        form_layout.addWidget(address_label)
        address_input = QTextEdit()
        address_input.setMaximumHeight(80)
        form_layout.addWidget(address_input)
        
        layout.addLayout(form_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Provider")
        save_btn.clicked.connect(lambda: self.save_provider(
            dialog, company_input, owner_input, owner_contact_input,
            salesman_input, salesman_contact_input, delivery_input,
            delivery_contact_input, address_input
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
    def save_provider(self, dialog, company_input, owner_input, owner_contact_input,
                     salesman_input, salesman_contact_input, delivery_input,
                     delivery_contact_input, address_input):
        """Save new provider to database"""
        company = company_input.text().strip()
        if not company:
            QMessageBox.warning(dialog, "Required Field", "Company Name is required")
            return
        
        try:
            self.db.execute("""
                INSERT INTO providers (company_name, owner_name, owner_contact,
                    salesman_name, salesman_contact, delivery_man_name,
                    delivery_man_contact, company_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (company, owner_input.text().strip(), owner_contact_input.text().strip(),
                  salesman_input.text().strip(), salesman_contact_input.text().strip(),
                  delivery_input.text().strip(), delivery_contact_input.text().strip(),
                  address_input.toPlainText()))
            self.db.commit()
            
            QMessageBox.information(dialog, "Success", "Provider added successfully")
            dialog.close()
            self.load_providers()
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to add provider: {str(e)}")
    
    def open_provider_popup(self, index):
        """Open detailed provider popup with ledger"""
        row = index.row()
        provider_id = int(self.providers_table.item(row, 0).text())
        
        self.db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        provider = self.db.fetchone()
        
        if not provider:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Provider: {provider['company_name']}")
        dialog.setMinimumSize(900, 700)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        
        # Provider info section
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        info_layout = QVBoxLayout()
        
        # Get totals
        self.db.execute("""
            SELECT 
                COALESCE(SUM(orders), 0) as total_orders,
                COALESCE(SUM(jama), 0) as total_paid
            FROM provider_ledger WHERE provider_id = ?
        """, (provider_id,))
        totals = self.db.fetchone()
        total_orders = totals['total_orders'] if totals else 0
        total_paid = totals['total_paid'] if totals else 0
        payable = total_orders - total_paid
        
        info_layout.addWidget(QLabel(f"<b>Company:</b> {provider['company_name']}"))
        if provider['owner_name']:
            info_layout.addWidget(QLabel(f"<b>Owner:</b> {provider['owner_name']} - {provider['owner_contact']}"))
        if provider['salesman_name']:
            info_layout.addWidget(QLabel(f"<b>Salesman:</b> {provider['salesman_name']} - {provider['salesman_contact']}"))
        if provider['delivery_man_name']:
            info_layout.addWidget(QLabel(f"<b>Delivery:</b> {provider['delivery_man_name']} - {provider['delivery_man_contact']}"))
        if provider['company_address']:
            info_layout.addWidget(QLabel(f"<b>Address:</b> {provider['company_address']}"))
        
        totals_label = QLabel(f"<b>Total Payable:</b> Rs. {payable:.2f} | <b>Total Paid:</b> Rs. {total_paid:.2f}")
        totals_label.setStyleSheet("color: red;" if payable > 0 else "color: green;")
        totals_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        info_layout.addWidget(totals_label)
        
        info_frame.setLayout(info_layout)
        main_layout.addWidget(info_frame)
        
        # Ledger section
        ledger_group = QGroupBox("Transaction History")
        ledger_layout = QVBoxLayout()
        
        # Ledger table
        ledger_table = QTableWidget()
        ledger_table.setColumnCount(6)
        ledger_table.setHorizontalHeaderLabels(["ID", "Date", "Description", "Orders", "Jama", "Balance"])
        ledger_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        ledger_table.setSelectionBehavior(QTableWidget.SelectRows)
        ledger_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ledger_layout.addWidget(ledger_table)
        
        # Load ledger
        self.load_provider_ledger(ledger_table, provider_id)
        
        ledger_group.setLayout(ledger_layout)
        main_layout.addWidget(ledger_group)
        
        # Action buttons
        btn_row = QHBoxLayout()
        
        if self.is_admin:
            add_order_btn = QPushButton("➕ Add Order (Manual)")
            add_order_btn.clicked.connect(lambda: self.add_provider_order(provider_id, provider['company_name']))
            btn_row.addWidget(add_order_btn)
        
        make_payment_btn = QPushButton("💰 Make Payment")
        make_payment_btn.clicked.connect(lambda: self.make_provider_payment(provider_id, provider['company_name'], payable))
        btn_row.addWidget(make_payment_btn)
        
        btn_row.addStretch()
        main_layout.addLayout(btn_row)
        
        dialog.setLayout(main_layout)
        dialog.exec()
    
    def load_provider_ledger(self, table, provider_id):
        """Load provider ledger transactions"""
        table.setRowCount(0)
        
        self.db.execute("""
            SELECT id, date, description, orders, jama, balance
            FROM provider_ledger
            WHERE provider_id = ?
            ORDER BY date DESC, id DESC
        """, (provider_id,))
        transactions = self.db.fetchall()
        
        for txn in transactions:
            row = table.rowCount()
            table.insertRow(row)
            
            table.setItem(row, 0, QTableWidgetItem(str(txn['id'])))
            table.setItem(row, 1, QTableWidgetItem(txn['date']))
            table.setItem(row, 2, QTableWidgetItem(txn['description'] or ''))
            
            orders_item = QTableWidgetItem(f"{txn['orders']:.2f}" if txn['orders'] else "-")
            if txn['orders']:
                orders_item.setBackground(Qt.lightGray)
            table.setItem(row, 3, orders_item)
            
            jama_item = QTableWidgetItem(f"{txn['jama']:.2f}" if txn['jama'] else "-")
            if txn['jama']:
                jama_item.setBackground(Qt.green)
            table.setItem(row, 4, jama_item)
            
            table.setItem(row, 5, QTableWidgetItem(f"{txn['balance']:.2f}"))
    
    def add_provider_order(self, provider_id, company_name):
        """Add manual order (debit) for provider"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add Order - {company_name}")
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Amount
        amount_label = QLabel("Order Amount:")
        layout.addWidget(amount_label)
        amount_input = QDoubleSpinBox()
        amount_input.setRange(0.01, 999999)
        amount_input.setValue(0)
        layout.addWidget(amount_input)
        
        # Description
        desc_label = QLabel("Description:")
        layout.addWidget(desc_label)
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("e.g., Manual purchase entry")
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
        
        save_btn = QPushButton("💾 Save Order")
        save_btn.clicked.connect(lambda: self.save_provider_order(
            dialog, provider_id, amount_input, desc_input, date_input
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
    def save_provider_order(self, dialog, provider_id, amount_input, desc_input, date_input):
        """Save provider order entry"""
        amount = amount_input.value()
        if amount <= 0:
            QMessageBox.warning(dialog, "Invalid Amount", "Amount must be greater than zero")
            return
        
        try:
            # Get current balance
            self.db.execute("""
                SELECT COALESCE(SUM(orders - jama), 0) as balance
                FROM provider_ledger WHERE provider_id = ?
            """, (provider_id,))
            result = self.db.fetchone()
            current_balance = result['balance'] if result else 0
            
            new_balance = current_balance + amount
            
            self.db.execute("""
                INSERT INTO provider_ledger (provider_id, date, description, orders, balance)
                VALUES (?, ?, ?, ?, ?)
            """, (provider_id, date_input.date().toString('yyyy-MM-dd'),
                  desc_input.text().strip(), amount, new_balance))
            
            self.db.commit()
            QMessageBox.information(dialog, "Success", "Order added successfully")
            dialog.close()
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to add order: {str(e)}")
    
    def make_provider_payment(self, provider_id, company_name, max_amount):
        """Make payment to provider"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Make Payment - {company_name}")
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Max payable info
        info_label = QLabel(f"Current Payable: Rs. {max_amount:.2f}")
        info_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(info_label)
        
        # Amount
        amount_label = QLabel("Payment Amount:")
        layout.addWidget(amount_label)
        amount_input = QDoubleSpinBox()
        amount_input.setRange(0.01, max_amount if max_amount > 0 else 999999)
        amount_input.setValue(0)
        layout.addWidget(amount_input)
        
        # Description
        desc_label = QLabel("Description:")
        layout.addWidget(desc_label)
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("e.g., Cash payment to supplier")
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
        
        save_btn = QPushButton("💾 Record Payment")
        save_btn.clicked.connect(lambda: self.save_provider_payment(
            dialog, provider_id, amount_input, desc_input, date_input
        ))
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
    def save_provider_payment(self, dialog, provider_id, amount_input, desc_input, date_input):
        """Save provider payment entry"""
        amount = amount_input.value()
        if amount <= 0:
            QMessageBox.warning(dialog, "Invalid Amount", "Amount must be greater than zero")
            return
        
        try:
            # Get current balance
            self.db.execute("""
                SELECT COALESCE(SUM(orders - jama), 0) as balance
                FROM provider_ledger WHERE provider_id = ?
            """, (provider_id,))
            result = self.db.fetchone()
            current_balance = result['balance'] if result else 0
            
            if amount > current_balance:
                reply = QMessageBox.question(dialog, "Exceeds Balance",
                    "Payment amount exceeds current payable. Continue anyway?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
            
            new_balance = current_balance - amount
            
            self.db.execute("""
                INSERT INTO provider_ledger (provider_id, date, description, jama, balance)
                VALUES (?, ?, ?, ?, ?)
            """, (provider_id, date_input.date().toString('yyyy-MM-dd'),
                  desc_input.text().strip(), amount, new_balance))
            
            # Log to history
            self.db.execute("""
                INSERT INTO global_history (transaction_type, description, amount, user_name)
                VALUES (?, ?, ?, ?)
            """, ('Provider Payment', f"Payment to provider {provider_id}", amount, self.user_info['username']))
            
            self.db.commit()
            QMessageBox.information(dialog, "Success", "Payment recorded successfully")
            dialog.close()
            self.load_providers()  # Refresh provider list
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to record payment: {str(e)}")
