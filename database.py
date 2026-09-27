"""
Database Manager - SQLite database handling for Retail Management System
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


class DatabaseManager:
    """Singleton database manager for SQLite operations"""
    
    _instance = None
    _db_path = "retail_system.db"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.connection = None
            cls._instance.cursor = None
        return cls._instance
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.connect()
            cls._instance.create_tables()
            cls._instance.create_default_users()
        return cls._instance
    
    def connect(self):
        """Connect to the database"""
        self.connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return the cursor"""
        self.cursor.execute(query, params)
        return self.cursor
    
    def commit(self):
        """Commit changes"""
        self.connection.commit()
    
    def fetchall(self):
        """Fetch all results"""
        return self.cursor.fetchall()
    
    def fetchone(self):
        """Fetch one result"""
        return self.cursor.fetchone()
    
    def create_tables(self):
        """Create all necessary tables if they don't exist"""
        
        # Users table
        self.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'User',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Categories table
        self.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                image BLOB,
                FOREIGN KEY (parent_id) REFERENCES categories(id)
            )
        """)
        
        # Units table
        self.execute("""
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
        
        # Products table
        self.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT UNIQUE,
                sku TEXT UNIQUE,
                name TEXT NOT NULL,
                brand TEXT,
                category_id INTEGER,
                unit_id INTEGER,
                purchase_price REAL DEFAULT 0,
                sell_price REAL NOT NULL,
                stock_qty REAL DEFAULT 0,
                mfg_date DATE,
                expiry_date DATE,
                returnable INTEGER DEFAULT 0,
                replaceable INTEGER DEFAULT 0,
                replace_days INTEGER DEFAULT 0,
                refund_days INTEGER DEFAULT 0,
                description TEXT,
                image BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
        """)
        
        # Product alerts table
        self.execute("""
            CREATE TABLE IF NOT EXISTS product_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,
                threshold REAL NOT NULL,
                color TEXT DEFAULT 'red',
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        
        # Product attributes table
        self.execute("""
            CREATE TABLE IF NOT EXISTS product_attributes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                attr_key TEXT NOT NULL,
                attr_value TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        
        # Customers table
        self.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                father_name TEXT,
                contact1 TEXT NOT NULL,
                contact2 TEXT,
                address TEXT,
                profile_image BLOB,
                blocked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Customer ledger table
        self.execute("""
            CREATE TABLE IF NOT EXISTS customer_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                date DATE NOT NULL,
                description TEXT,
                khata REAL DEFAULT 0,
                jama REAL DEFAULT 0,
                balance REAL DEFAULT 0,
                sale_id INTEGER,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                FOREIGN KEY (sale_id) REFERENCES sales(id)
            )
        """)
        
        # Scheduled payments table
        self.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                due_date DATE NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                paid INTEGER DEFAULT 0,
                paid_date DATE,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            )
        """)
        
        # Providers table
        self.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                owner_name TEXT,
                owner_contact TEXT,
                salesman_name TEXT,
                salesman_contact TEXT,
                delivery_man_name TEXT,
                delivery_man_contact TEXT,
                company_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Provider ledger table
        self.execute("""
            CREATE TABLE IF NOT EXISTS provider_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                date DATE NOT NULL,
                description TEXT,
                orders REAL DEFAULT 0,
                jama REAL DEFAULT 0,
                balance REAL DEFAULT 0,
                purchase_id INTEGER,
                FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
                FOREIGN KEY (purchase_id) REFERENCES purchases(id)
            )
        """)
        
        # Purchases table (stock receiving)
        self.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                date DATE NOT NULL,
                total_amount REAL NOT NULL,
                FOREIGN KEY (provider_id) REFERENCES providers(id)
            )
        """)
        
        # Purchase items table
        self.execute("""
            CREATE TABLE IF NOT EXISTS purchase_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL,
                total REAL NOT NULL,
                mfg_date DATE,
                expiry_date DATE,
                FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        
        # Sales table
        self.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                customer_id INTEGER,
                buyer_name TEXT,
                subtotal REAL NOT NULL,
                discount REAL DEFAULT 0,
                discount_type TEXT DEFAULT 'fixed',
                total REAL NOT NULL,
                amount_paid REAL NOT NULL,
                change_amount REAL DEFAULT 0,
                payment_method TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                receipt_settings BLOB,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Sale items table
        self.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        
        # Expenses table
        self.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Dasti table (temporary loans)
        self.execute("""
            CREATE TABLE IF NOT EXISTS dasti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                customer_name TEXT NOT NULL,
                user_name TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL,
                paid REAL DEFAULT 0,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Notes table
        self.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                date DATE NOT NULL,
                description TEXT,
                amount REAL,
                user_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Demands table
        self.execute("""
            CREATE TABLE IF NOT EXISTS demands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                product_name TEXT NOT NULL,
                customer_name TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Media favourites table
        self.execute("""
            CREATE TABLE IF NOT EXISTS media_favourites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Global history table
        self.execute("""
            CREATE TABLE IF NOT EXISTS global_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                transaction_type TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL,
                user_name TEXT,
                details BLOB
            )
        """)
        
        # Settings table
        self.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Shortcuts table
        self.execute("""
            CREATE TABLE IF NOT EXISTS shortcuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT UNIQUE NOT NULL,
                shortcut_key TEXT NOT NULL
            )
        """)
        
        self.commit()
        
        # Insert default settings if not exist
        default_settings = [
            ('store_name', 'My Store'),
            ('welcome_message', 'Welcome to Our Store'),
            ('store_contact', ''),
            ('receipt_heading', 'Thank you for your purchase!'),
            ('receipt_width', '400'),
            ('receipt_theme', 'default'),
            ('music_folder', ''),
            ('font_size', '10'),
            ('dark_mode', 'true')
        ]
        
        for key, value in default_settings:
            self.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        self.commit()
        
        # Insert default shortcuts
        default_shortcuts = [
            ('pos_complete_sale', 'Return'),
            ('pos_khata_sale', 'F5')
        ]
        
        for action, shortcut in default_shortcuts:
            self.execute(
                "INSERT OR IGNORE INTO shortcuts (action, shortcut_key) VALUES (?, ?)",
                (action, shortcut)
            )
        self.commit()
    
    def create_default_users(self):
        """Create default admin and user accounts"""
        default_users = [
            ('admin', 'admin', 'Admin'),
            ('user', 'user', 'User')
        ]
        
        for username, password, role in default_users:
            try:
                self.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    (username, password, role)
                )
            except sqlite3.IntegrityError:
                pass  # User already exists
        
        self.commit()
    
    def backup_database(self, backup_path: str):
        """Create a backup of the database"""
        import shutil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{backup_path}/retail_backup_{timestamp}.db"
        shutil.copy2(self._db_path, backup_file)
        return backup_file
    
    def clear_all_data(self):
        """Clear all data except users and settings"""
        tables = [
            'sales', 'sale_items', 'customer_ledger', 'scheduled_payments',
            'provider_ledger', 'purchases', 'purchase_items', 'expenses',
            'dasti', 'notes', 'demands', 'media_favourites', 'global_history',
            'products', 'product_alerts', 'product_attributes',
            'customers', 'providers', 'categories', 'units'
        ]
        
        # Disable foreign keys temporarily
        self.execute("PRAGMA foreign_keys = OFF")
        
        for table in tables:
            self.execute(f"DELETE FROM {table}")
        
        # Re-enable foreign keys
        self.execute("PRAGMA foreign_keys = ON")
        self.commit()
