"""
Inventory Management Page - Product list, add/edit products, categories, and units
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                                QFrame, QScrollArea, QComboBox, QTabWidget, QFileDialog,
                                QMessageBox, QHeaderView, QGroupBox, QFormLayout,
                                QSpinBox, QDoubleSpinBox, QTextEdit, QDateEdit, QCheckBox)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont


class InventoryPage(QWidget):
    """Inventory management page with product list and editing capabilities"""
    
    def __init__(self, user_info: dict, db):
        super().__init__()
        self.user_info = user_info
        self.db = db
        self.is_admin = user_info['role'] == 'Admin'
        self.current_product_id = None
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("📦 Inventory Management")
        title_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_label.setStyleSheet("color: #333;")
        layout.addWidget(title_label)
        
        # Tab widget for different sections
        tabs = QTabWidget()
        
        # Products tab
        products_tab = self.create_products_tab()
        tabs.addTab(products_tab, "Products")
        
        # Categories tab (admin only)
        if self.is_admin:
            categories_tab = self.create_categories_tab()
            tabs.addTab(categories_tab, "Categories")
            
            # Units tab (admin only)
            units_tab = self.create_units_tab()
            tabs.addTab(units_tab, "Units")
            
            # Import/Export tab (admin only)
            import_export_tab = self.create_import_export_tab()
            tabs.addTab(import_export_tab, "Import/Export")
        
        layout.addWidget(tabs)
        self.setLayout(layout)
    
    def create_products_tab(self) -> QWidget:
        """Create the products list tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Filter and search row
        filter_row = QHBoxLayout()
        
        # Filter dropdown
        filter_label = QLabel("Filter:")
        filter_row.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Items", "all")
        self.filter_combo.addItem("Low Stock Alerts", "low_stock")
        self.filter_combo.addItem("Expiry Alerts", "expiry")
        self.filter_combo.currentIndexChanged.connect(self.load_products)
        filter_row.addWidget(self.filter_combo)
        
        filter_row.addStretch()
        
        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name, barcode, or SKU...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self.load_products)
        filter_row.addWidget(self.search_input)
        
        layout.addLayout(filter_row)
        
        # Products table
        self.products_table = QTableWidget()
        self.products_table.setColumnCount(8)
        self.products_table.setHorizontalHeaderLabels([
            "ID", "Barcode", "SKU", "Name", "Price", "Stock", "Category", "Unit"
        ])
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.products_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.products_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.products_table.doubleClicked.connect(self.on_product_double_click)
        self.products_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 8px;
            }
        """)
        layout.addWidget(self.products_table)
        
        # Action buttons (admin only)
        if self.is_admin:
            btn_row = QHBoxLayout()
            
            add_btn = QPushButton("➕ Add New Product")
            add_btn.clicked.connect(self.open_add_product_form)
            btn_row.addWidget(add_btn)
            
            edit_btn = QPushButton("✏️ Edit Selected")
            edit_btn.clicked.connect(self.edit_selected_product)
            btn_row.addWidget(edit_btn)
            
            delete_btn = QPushButton("🗑️ Delete Selected")
            delete_btn.clicked.connect(self.delete_selected_product)
            btn_row.addWidget(delete_btn)
            
            btn_row.addStretch()
            layout.addLayout(btn_row)
        
        tab.setLayout(layout)
        
        # Load products
        self.load_products()
        
        return tab
    
    def create_categories_tab(self) -> QWidget:
        """Create the categories management tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Search
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        
        self.category_search = QLineEdit()
        self.category_search.setPlaceholderText("Search categories...")
        self.category_search.textChanged.connect(self.load_categories)
        search_layout.addWidget(self.category_search)
        search_layout.addStretch()
        
        layout.addLayout(search_layout)
        
        # Category tree/list would go here
        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(3)
        self.categories_table.setHorizontalHeaderLabels(["ID", "Name", "Parent"])
        self.categories_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.categories_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.categories_table)
        
        # Add category form
        add_layout = QHBoxLayout()
        
        self.new_category_name = QLineEdit()
        self.new_category_name.setPlaceholderText("New category name")
        add_layout.addWidget(self.new_category_name)
        
        self.parent_category_combo = QComboBox()
        self.parent_category_combo.addItem("Top Level", None)
        add_layout.addWidget(self.parent_category_combo)
        
        add_btn = QPushButton("Add Category")
        add_btn.clicked.connect(self.add_category)
        add_layout.addWidget(add_btn)
        
        layout.addLayout(add_layout)
        
        tab.setLayout(layout)
        
        # Load categories
        self.load_categories()
        
        return tab
    
    def create_units_tab(self) -> QWidget:
        """Create the units management tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Units list
        self.units_table = QTableWidget()
        self.units_table.setColumnCount(2)
        self.units_table.setHorizontalHeaderLabels(["ID", "Name"])
        self.units_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.units_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.units_table)
        
        # Add unit form
        add_layout = QHBoxLayout()
        
        self.new_unit_name = QLineEdit()
        self.new_unit_name.setPlaceholderText("New unit name (e.g., kg, pcs, liters)")
        add_layout.addWidget(self.new_unit_name)
        
        add_btn = QPushButton("Add Unit")
        add_btn.clicked.connect(self.add_unit)
        add_layout.addWidget(add_btn)
        
        layout.addLayout(add_layout)
        
        tab.setLayout(layout)
        
        # Load units
        self.load_units()
        
        return tab
    
    def create_import_export_tab(self) -> QWidget:
        """Create the import/export CSV tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)
        
        # Export section
        export_group = QGroupBox("Export Products to CSV")
        export_layout = QVBoxLayout()
        
        export_desc = QLabel("Export all products with their details to a CSV file.")
        export_layout.addWidget(export_desc)
        
        export_btn = QPushButton("📥 Export to CSV")
        export_btn.clicked.connect(self.export_to_csv)
        export_layout.addWidget(export_btn)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        # Import section
        import_group = QGroupBox("Import Products from CSV")
        import_layout = QVBoxLayout()
        
        import_desc = QLabel("Import products from a CSV file. Existing products will be updated.")
        import_desc.setWordWrap(True)
        import_layout.addWidget(import_desc)
        
        import_btn = QPushButton("📤 Import from CSV")
        import_btn.clicked.connect(self.import_from_csv)
        import_layout.addWidget(import_btn)
        
        import_group.setLayout(import_layout)
        layout.addWidget(import_group)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def load_products(self):
        """Load products into the table"""
        self.products_table.setRowCount(0)
        
        filter_type = self.filter_combo.currentData()
        search_text = self.search_input.text().strip()
        
        query = """
            SELECT p.id, p.barcode, p.sku, p.name, p.sell_price, p.stock_qty,
                   c.name as category_name, u.name as unit_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN units u ON p.unit_id = u.id
            WHERE 1=1
        """
        params = []
        
        if search_text:
            query += " AND (p.name LIKE ? OR p.barcode LIKE ? OR p.sku LIKE ?)"
            params.extend([f'%{search_text}%', f'%{search_text}%', f'%{search_text}%'])
        
        if filter_type == 'low_stock':
            query += " AND p.stock_qty <= 5"
        elif filter_type == 'expiry':
            query += " AND p.expiry_date IS NOT NULL AND p.expiry_date <= date('now', '+10 days')"
        
        query += " ORDER BY p.name"
        
        self.db.execute(query, tuple(params))
        products = self.db.fetchall()
        
        for product in products:
            row = self.products_table.rowCount()
            self.products_table.insertRow(row)
            
            self.products_table.setItem(row, 0, QTableWidgetItem(str(product['id'])))
            self.products_table.setItem(row, 1, QTableWidgetItem(product['barcode'] or ''))
            self.products_table.setItem(row, 2, QTableWidgetItem(product['sku'] or ''))
            self.products_table.setItem(row, 3, QTableWidgetItem(product['name']))
            self.products_table.setItem(row, 4, QTableWidgetItem(f"Rs. {product['sell_price']:.2f}"))
            
            # Stock with color coding
            stock_item = QTableWidgetItem(str(product['stock_qty']))
            if product['stock_qty'] <= 5:
                stock_item.setBackground(Qt.red)
            self.products_table.setItem(row, 5, stock_item)
            
            self.products_table.setItem(row, 6, QTableWidgetItem(product['category_name'] or ''))
            self.products_table.setItem(row, 7, QTableWidgetItem(product['unit_name'] or ''))
    
    def load_categories(self):
        """Load categories into the table"""
        self.categories_table.setRowCount(0)
        
        search_text = self.category_search.text().strip()
        
        query = """
            SELECT c.id, c.name, p.name as parent_name
            FROM categories c
            LEFT JOIN categories p ON c.parent_id = p.id
            WHERE c.name LIKE ? OR p.name LIKE ?
            ORDER BY c.name
        """
        params = (f'%{search_text}%', f'%{search_text}%')
        
        self.db.execute(query, params)
        categories = self.db.fetchall()
        
        for cat in categories:
            row = self.categories_table.rowCount()
            self.categories_table.insertRow(row)
            
            self.categories_table.setItem(row, 0, QTableWidgetItem(str(cat['id'])))
            self.categories_table.setItem(row, 1, QTableWidgetItem(cat['name']))
            self.categories_table.setItem(row, 2, QTableWidgetItem(cat['parent_name'] or 'Top Level'))
        
        # Update parent combo
        self.parent_category_combo.clear()
        self.parent_category_combo.addItem("Top Level", None)
        for cat in categories:
            self.parent_category_combo.addItem(cat['name'], cat['id'])
    
    def load_units(self):
        """Load units into the table"""
        self.units_table.setRowCount(0)
        
        self.db.execute("SELECT id, name FROM units ORDER BY name")
        units = self.db.fetchall()
        
        for unit in units:
            row = self.units_table.rowCount()
            self.units_table.insertRow(row)
            
            self.units_table.setItem(row, 0, QTableWidgetItem(str(unit['id'])))
            self.units_table.setItem(row, 1, QTableWidgetItem(unit['name']))
    
    def on_product_double_click(self, index):
        """Handle double-click on product"""
        row = index.row()
        product_id = int(self.products_table.item(row, 0).text())
        
        if self.is_admin:
            self.open_edit_product_form(product_id)
        else:
            self.show_product_details(product_id)
    
    def show_product_details(self, product_id: int):
        """Show product details popup (read-only for users)"""
        self.db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = self.db.fetchone()
        
        if not product:
            return
        
        msg = QMessageBox()
        msg.setWindowTitle("Product Details")
        msg.setIcon(QMessageBox.Information)
        
        details = f"""
        Name: {product['name']}
        Barcode: {product['barcode'] or 'N/A'}
        SKU: {product['sku'] or 'N/A'}
        Price: Rs. {product['sell_price']:.2f}
        Stock: {product['stock_qty']}
        Description: {product['description'] or 'No description'}
        """
        msg.setText(details)
        msg.exec()
    
    def open_add_product_form(self):
        """Open form to add new product"""
        # This would open a detailed form dialog
        QMessageBox.information(self, "Add Product", "Product form dialog would open here")
    
    def open_edit_product_form(self, product_id: int):
        """Open form to edit existing product"""
        QMessageBox.information(self, "Edit Product", f"Edit form for product {product_id} would open here")
    
    def edit_selected_product(self):
        """Edit the selected product"""
        selected_rows = self.products_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a product to edit")
            return
        
        row = selected_rows[0].row()
        product_id = int(self.products_table.item(row, 0).text())
        self.open_edit_product_form(product_id)
    
    def delete_selected_product(self):
        """Delete the selected product"""
        selected_rows = self.products_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a product to delete")
            return
        
        reply = QMessageBox.question(self, "Confirm Delete",
                                    "Are you sure you want to delete this product?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            row = selected_rows[0].row()
            product_id = int(self.products_table.item(row, 0).text())
            
            try:
                self.db.execute("DELETE FROM products WHERE id = ?", (product_id,))
                self.db.commit()
                self.load_products()
                QMessageBox.information(self, "Deleted", "Product deleted successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {str(e)}")
    
    def add_category(self):
        """Add a new category"""
        name = self.new_category_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Empty Name", "Please enter a category name")
            return
        
        parent_id = self.parent_category_combo.currentData()
        
        try:
            self.db.execute(
                "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
                (name, parent_id)
            )
            self.db.commit()
            self.new_category_name.clear()
            self.load_categories()
            QMessageBox.information(self, "Success", "Category added successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add category: {str(e)}")
    
    def add_unit(self):
        """Add a new unit"""
        name = self.new_unit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Empty Name", "Please enter a unit name")
            return
        
        try:
            self.db.execute("INSERT INTO units (name) VALUES (?)", (name,))
            self.db.commit()
            self.new_unit_name.clear()
            self.load_units()
            QMessageBox.information(self, "Success", "Unit added successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add unit: {str(e)}")
    
    def export_to_csv(self):
        """Export products to CSV file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            try:
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Barcode', 'SKU', 'Name', 'Brand', 'Category', 
                                   'Unit', 'Purchase Price', 'Sell Price', 'Stock', 'Expiry Date'])
                    
                    self.db.execute("""
                        SELECT p.barcode, p.sku, p.name, p.brand, c.name, u.name,
                               p.purchase_price, p.sell_price, p.stock_qty, p.expiry_date
                        FROM products p
                        LEFT JOIN categories c ON p.category_id = c.id
                        LEFT JOIN units u ON p.unit_id = u.id
                    """)
                    
                    for row in self.db.fetchall():
                        writer.writerow([
                            row['barcode'] or '',
                            row['sku'] or '',
                            row['name'],
                            row['brand'] or '',
                            row[4] or '',
                            row[5] or '',
                            row['purchase_price'] or 0,
                            row['sell_price'],
                            row['stock_qty'],
                            row['expiry_date'] or ''
                        ])
                
                QMessageBox.information(self, "Export Complete", 
                                      f"Products exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export: {str(e)}")
    
    def import_from_csv(self):
        """Import products from CSV file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import from CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            try:
                import csv
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    count = 0
                    
                    for row in reader:
                        # Get or create category
                        category_id = None
                        if row.get('Category'):
                            self.db.execute(
                                "SELECT id FROM categories WHERE name = ?",
                                (row['Category'],)
                            )
                            cat = self.db.fetchone()
                            if not cat:
                                self.db.execute(
                                    "INSERT INTO categories (name) VALUES (?)",
                                    (row['Category'],)
                                )
                                category_id = self.db.cursor.lastrowid
                            else:
                                category_id = cat['id']
                        
                        # Get or create unit
                        unit_id = None
                        if row.get('Unit'):
                            self.db.execute(
                                "SELECT id FROM units WHERE name = ?",
                                (row['Unit'],)
                            )
                            unit = self.db.fetchone()
                            if not unit:
                                self.db.execute(
                                    "INSERT INTO units (name) VALUES (?)",
                                    (row['Unit'],)
                                )
                                unit_id = self.db.cursor.lastrowid
                            else:
                                unit_id = unit['id']
                        
                        # Insert or update product
                        self.db.execute("""
                            INSERT OR REPLACE INTO products 
                            (barcode, sku, name, brand, category_id, unit_id, 
                             purchase_price, sell_price, stock_qty, expiry_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            row.get('Barcode', ''),
                            row.get('SKU', ''),
                            row.get('Name', ''),
                            row.get('Brand', ''),
                            category_id,
                            unit_id,
                            float(row.get('Purchase Price', 0) or 0),
                            float(row.get('Sell Price', 0)),
                            float(row.get('Stock', 0) or 0),
                            row.get('Expiry Date') or None
                        ))
                        count += 1
                    
                    self.db.commit()
                    self.load_products()
                    QMessageBox.information(self, "Import Complete",
                                          f"Successfully imported {count} products")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import: {str(e)}")
