import mysql.connector
from mysql.connector import Error

# -----------------------------------------------------------------
# DATABASE CONNECTION HELPER
# -----------------------------------------------------------------
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",              # Change this if using another MySQL user
            password="", # Change this to your MySQL password
            database="umak_lebs",      # Ensure this database exists
            port=3306
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# -----------------------------------------------------------------
# INITIALIZE DATABASE TABLES
# -----------------------------------------------------------------
def init_db():
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor()

    # Pending administrators table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_admins (
            pending_id INT AUTO_INCREMENT PRIMARY KEY,
            first_name VARCHAR(50),
            last_name VARCHAR(50),
            email VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            verification_code VARCHAR(10),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Administrators table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INT AUTO_INCREMENT PRIMARY KEY,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            verification_code VARCHAR(10),
            otp VARCHAR(6),
            otp_expiry DATETIME,
            is_verified TINYINT(1) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Borrowers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS borrowers (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            rfid VARCHAR(50) UNIQUE NOT NULL,
            borrower_id VARCHAR(15) UNIQUE NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            first_name VARCHAR(50) NOT NULL,
            department VARCHAR(30),
            course VARCHAR(70),
            image TEXT DEFAULT NULL,
            roles VARCHAR(30) DEFAULT 'Student',
            umak_email VARCHAR(100)
        )
    """)

    # Inventory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            item_id INT AUTO_INCREMENT PRIMARY KEY,
            item_name VARCHAR(100) NOT NULL,
            type VARCHAR(100),
            quantity INT NOT NULL DEFAULT 0,
            borrowed INT NOT NULL DEFAULT 0,
            status VARCHAR(20) DEFAULT 'Available',
            image_path VARCHAR(255)
        )
    """)

    # Transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            borrow_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            admin_id INT NOT NULL,
            instructor_id INT NOT NULL,
            instructor_rfid VARCHAR(50) NOT NULL,
            subject VARCHAR(100) NOT NULL,
            room VARCHAR(50) NOT NULL,
            rfid VARCHAR(50) NOT NULL,
            item_id INT NOT NULL,
            borrowed_qty INT DEFAULT 1 NOT NULL,
            returned_qty INT DEFAULT 0,
            borrow_date DATE NOT NULL,
            borrow_time TIME NOT NULL,
            before_condition TEXT,
            after_condition TEXT,
            return_date DATE,
            return_time TIME,
            FOREIGN KEY (user_id) REFERENCES borrowers(user_id) ON DELETE CASCADE,
            FOREIGN KEY (admin_id) REFERENCES admins(admin_id) ON DELETE SET NULL,
            FOREIGN KEY (item_id) REFERENCES inventory(item_id) ON DELETE CASCADE
        )
    """)

    # Pending returns table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_returns (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            return_data JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status ENUM('pending', 'approved', 'completed','declined') DEFAULT 'pending',
            FOREIGN KEY (user_id) REFERENCES borrowers(user_id)
        )
    """)

    # History table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            transaction_id INT AUTO_INCREMENT PRIMARY KEY,
            equipment_no VARCHAR(50),
            name VARCHAR(100),
            borrower VARCHAR(100),
            borrow_date VARCHAR(50),
            date_returned VARCHAR(50),
            status VARCHAR(50)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_archive (
            archive_id INT AUTO_INCREMENT PRIMARY KEY,
            item_id INT,
            item_name VARCHAR(100) NOT NULL,
            type VARCHAR(100),
            quantity INT NOT NULL DEFAULT 0,
            borrowed INT NOT NULL DEFAULT 0,
            status VARCHAR(20),
            image_path VARCHAR(255),
            deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expire_at DATETIME GENERATED ALWAYS AS (DATE_ADD(deleted_at, INTERVAL 1 YEAR)) STORED
        )
    """) 

    # -----------------------------------------------------------------
    # ARCHIVE TABLE: Borrowers Archive
    # -----------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS archive_borrowers (
            archive_id INT AUTO_INCREMENT PRIMARY KEY,
            rfid VARCHAR(50),
            borrower_id VARCHAR(15),
            last_name VARCHAR(50) NOT NULL,
            first_name VARCHAR(50) NOT NULL,
            department VARCHAR(30),
            course VARCHAR(70),
            image TEXT DEFAULT NULL,
            roles VARCHAR(30) DEFAULT 'Student',
            umak_email VARCHAR(100),
            archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """) 

    conn.commit()
    cursor.close()
    conn.close()


# -----------------------------------------------------------------
# PRE-FILL INVENTORY DATA
# -----------------------------------------------------------------
def fill_inventory():
    conn = get_db_connection()
    if not conn:
        print("❌ Database connection failed.")
        return
    cursor = conn.cursor()

    items = [
        (1, 'Flathead Wrench', 'Hand Tools', 4, 0, 'Available'),
        (2, 'Ratchet Wrench', 'Hand Tools', 3, 0, 'Available'),
        (3, 'Torx Wrench', 'Hand Tools', 3, 0, 'Available'),
        (4, 'Needle-nose Pliers', 'Hand Tools', 3, 0, 'Available'),
        (5, 'Slip Joint Pliers', 'Hand Tools', 2, 0, 'Available'),
        (6, 'Locking Pliers', 'Hand Tools', 2, 0, 'Available'),
        (7, 'Claw Hammer', 'Hand Tools', 4, 0, 'Available'),
        (8, 'Ball-peen Hammer', 'Hand Tools', 3, 0, 'Available'),
        (9, 'Mallet', 'Hand Tools', 3, 0, 'Available'),
        (10, 'Allen Keys', 'Hand Tools', 2, 0, 'Available'),
        (11, 'Socket Keys', 'Hand Tools', 2, 0, 'Available'),
        (12, 'Measuring Tape', 'Hand Tools', 3, 0, 'Available'),
        (13, 'Ruler', 'Hand Tools', 5, 0, 'Available'),
        (14, 'Hand Saw', 'Hand Tools', 2, 0, 'Available'),
        (15, 'Hacksaw', 'Hand Tools', 2, 0, 'Available'),
        (16, 'Coping Saw', 'Hand Tools', 2, 0, 'Available'),
        (17, 'Angle Grinder', 'Power Tools', 5, 0, 'Available'),
        (18, 'Drill Press', 'Power Tools', 2, 0, 'Available'),
        (19, 'Power Screwdriver', 'Power Tools', 3, 0, 'Available'),
        (20, 'Soldering Iron', 'Power Tools', 2, 0, 'Available'),
        (21, 'Hot Glue Gun', 'Power Tools', 2, 0, 'Available'),
        (22, 'Electric Cutter', 'Power Tools', 2, 0, 'Available'),
        (23, 'Vernier Caliper', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (24, 'Digital Caliper', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (25, 'Micrometer', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (26, 'Multimeter', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (27, 'Oscilloscope', 'Measuring & Testing Instruments', 1, 0, 'Available'),
        (28, 'Clamp Meter', 'Measuring & Testing Instruments', 4, 0, 'Available'),
        (29, 'Spirit Level', 'Measuring & Testing Instruments', 2, 0, 'Available'),
        (30, 'Laser Level', 'Measuring & Testing Instruments', 1, 0, 'Available'),
        (31, 'Dial Gauge', 'Measuring & Testing Instruments', 5, 0, 'Unavailable'),
        (32, 'Box Cutter', 'Cutting Tools', 20, 0, 'Available'),
        (33, 'Utility Knife', 'Cutting Tools', 15, 0, 'Available'),
        (34, 'Chisels', 'Cutting Tools', 10, 0, 'Available'),
        (35, 'Knife', 'Cutting Tools', 5, 0, 'Unavailable'),
        (36, 'Shears', 'Cutting Tools', 5, 0, 'Unavailable'),
        (37, 'Lathe Machine', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (38, 'Milling Cutter', 'Heavy Equipment Machinery & Tools', 20, 0, 'Available'),
        (39, 'Heavy Drill Press', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (40, 'Machine Accessories', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (41, 'Welding Machine', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (42, 'Grinders', 'Heavy Equipment Machinery & Tools', 6, 0, 'Available'),
        (43, 'Buffers', 'Heavy Equipment Machinery & Tools', 4, 0, 'Available'),
        (44, 'Safety Goggles', 'Safety Equipment', 10, 0, 'Available'),
        (45, 'Face Shields', 'Safety Equipment', 10, 0, 'Available'),
        (46, 'Insulated Gloves', 'Safety Equipment', 5, 0, 'Available'),
        (47, 'Heat-Resistant Gloves', 'Safety Equipment', 5, 0, 'Available'),
        (48, 'Lab Coats', 'Safety Equipment', 4, 0, 'Available'),
        (49, 'Aprons', 'Safety Equipment', 3, 0, 'Available'),
        (50, 'Ear Protection', 'Safety Equipment', 10, 0, 'Available'),
        (51, 'First Aid Kit', 'Safety Equipment', 1, 0, 'Available'),
        (52, 'Fire Extinguishers', 'Safety Equipment', 6, 0, 'Available'),
        (53, 'Toolboxes', 'Storage & Supporting Equipment', 3, 0, 'Unavailable'),
        (54, 'Tool Cabinets', 'Storage & Supporting Equipment', 2, 0, 'Unavailable'),
        (55, 'Workbenches with Vises', 'Storage & Supporting Equipment', 6, 0, 'Available'),
        (56, 'Carts', 'Storage & Supporting Equipment', 5, 0, 'Available'),
        (57, 'Trolleys', 'Storage & Supporting Equipment', 4, 0, 'Available'),
        (58, 'Storage Racks', 'Storage & Supporting Equipment', 7, 0, 'Available')
    ]
    print(f"Inserting {len(items)} items into inventory...")

    for item in items:
        cursor.execute("""
            INSERT IGNORE INTO inventory (item_id, item_name, type, quantity, borrowed, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, item)

    conn.commit()
    cursor.close()
    conn.close()