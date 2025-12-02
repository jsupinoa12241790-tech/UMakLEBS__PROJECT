from flask import Flask, flash, render_template, request, session, redirect, url_for, jsonify, send_file # Flask imports
import json # for JSON operations
import sqlite3 # for database operations
from werkzeug.security import generate_password_hash, check_password_hash # for password hashing
from functools import wraps # for login required decorator
from flask_socketio import SocketIO # for real-time communication
from werkzeug.utils import secure_filename # for secure file names
import calendar # for calendar operations
from datetime import datetime, timezone, timedelta, timezone, date # for date and time handling
from zoneinfo import ZoneInfo # for timezone handling
import os, re, random # standard libraries
import io  # for in-memory file operations
from io import BytesIO  # for in-memory file operations
import smtplib # for sending emails
from email.mime.multipart import MIMEMultipart # for email construction
from email.mime.text import MIMEText # for email text content
from email.mime.application import MIMEApplication # for email attachments
from email.message import EmailMessage # for constructing email messages
from docx import Document # for Word document generation

# Matplotlib backend MUST be set before importing pyplot
import matplotlib
matplotlib.use('Agg')  # non-GUI backend suitable for servers
import matplotlib.pyplot as plt # for plotting graphs

# ReportLab imports
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader

import base64 # for encoding images in emails
from dotenv import load_dotenv # for loading environment variables from .env file
load_dotenv() # load environment variables from .env file

# -----------------------------------------------------------------
# FLASK APP SETUP
# -----------------------------------------------------------------
app = Flask(__name__) # initialize Flask app
socketio = SocketIO(app, cors_allowed_origins="*") # initialize SocketIO with CORS allowed for all origins

app.secret_key = os.urandom(24)  # this line for session security
DB_NAME = "lebsData.db" # database file name 

# email configuration (using environment variables for security)
smtp_user = os.getenv("EMAIL_USER")
smtp_pass = os.getenv("EMAIL_PASS")

# in-memory buffer for PDF generation
buffer = io.BytesIO()
# logic to prevent caching of pages (after_request) to ensure fresh data on each load 
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
# -----------------------------------------------------------------
# DATABASE SETUP
# -----------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Pending administrators table (for email verification)
    cursor.execute("""CREATE TABLE IF NOT EXISTS pending_admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        last_name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        verification_code TEXT,
        created_at TEXT
    );""")

    #Administrator's table
    cursor.execute("""CREATE TABLE IF NOT EXISTS admins (
        admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name VARCHAR(50) NOT NULL,
        last_name VARCHAR(50) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        verification_code VARCHAR(10),
        otp VARCHAR(6),
        otp_expiry TEXT,
        is_verified TINYINT(1) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );""")

    # Borrowers table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS borrowers (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfid TEXT UNIQUE NOT NULL,
        borrower_id VARCHAR(15) UNIQUE NOT NULL,
        last_name VARCHAR(50) NOT NULL,
        first_name VARCHAR(50) NOT NULL,
        department VARCHAR(30),
        course VARCHAR(70),
        image TEXT DEFAULT NULL,
        roles VARCHAR(30) DEFAULT 'Student',
        umak_email TEXT
    )
    """)

    # Inventory table (merged schema)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        type TEXT,
        quantity INTEGER NOT NULL DEFAULT 0,
        borrowed INTEGER NOT NULL DEFAULT 0,
        status TEXT DEFAULT 'Available'
    )
    """)

    # Borrowed items table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        borrow_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        instructor_id INTEGER NOT NULL,        -- instructor (authorization)
        instructor_rfid TEXT NOT NULL,         -- instructor RFID scanned
        subject TEXT NOT NULL,                 -- subject name
        room TEXT NOT NULL,                    -- room where equipment will be used
        rfid TEXT NOT NULL,
        item_id INT NOT NULL,
        borrowed_qty INT DEFAULT 1 NOT NULL, -- how many have been borrowed
        returned_qty INT DEFAULT 0,  -- how many have been returned
        borrow_date DATE NOT NULL,
        borrow_time TIME NOT NULL,
        before_condition TEXT,
        after_condition TEXT,
        return_date DATE,
        return_time TIME,
        FOREIGN KEY (user_id) REFERENCES borrowers(user_id),
        FOREIGN KEY (item_id) REFERENCES inventory(item_id)
    )
    """)

    #Pending returns table (modified for your structure)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        borrow_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        return_data TEXT NOT NULL, -- JSON string of returned items
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (borrow_id) REFERENCES transactions(borrow_id),
        FOREIGN KEY (user_id) REFERENCES borrowers(user_id)
    )
    """)

    # History table (from inventory_routes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_no TEXT,
        name TEXT,
        borrower TEXT,
        borrow_date TEXT,
        date_returned TEXT,
        status TEXT
    )
    """)

    conn.commit()
    conn.close()

# -----------------------------------------------------------------
# PRE-FILL INVENTORY DATA (from inventory_routes.py)
# -----------------------------------------------------------------
def fill_inventory():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    items = [
        # Hand Tools - Wrenches/Spanners separated
        (1, 'Flathead Wrench', 'Hand Tools', 4, 0, 'Available'),
        (2, 'Ratchet Wrench', 'Hand Tools', 3, 0, 'Available'),
        (3, 'Torx Wrench', 'Hand Tools', 3, 0, 'Available'),
        
        # Hand Tools - Pliers separated
        (4, 'Needle-nose Pliers', 'Hand Tools', 3, 0, 'Available'),
        (5, 'Slip Joint Pliers', 'Hand Tools', 2, 0, 'Available'),
        (6, 'Locking Pliers', 'Hand Tools', 2, 0, 'Available'),
        
        # Hand Tools - Hammers separated
        (7, 'Claw Hammer', 'Hand Tools', 4, 0, 'Available'),
        (8, 'Ball-peen Hammer', 'Hand Tools', 3, 0, 'Available'),
        (9, 'Mallet', 'Hand Tools', 3, 0, 'Available'),
        
        # Hand Tools - Keys
        (10, 'Allen Keys', 'Hand Tools', 2, 0, 'Available'),
        (11, 'Socket Keys', 'Hand Tools', 2, 0, 'Available'),
        
        # Hand Tools - Measuring
        (12, 'Measuring Tape', 'Hand Tools', 3, 0, 'Available'),
        (13, 'Ruler', 'Hand Tools', 5, 0, 'Available'),
        
        # Hand Tools - Saws
        (14, 'Hand Saw', 'Hand Tools', 2, 0, 'Available'),
        (15, 'Hacksaw', 'Hand Tools', 2, 0, 'Available'),
        (16, 'Coping Saw', 'Hand Tools', 2, 0, 'Available'),
        
        # Power Tools
        (17, 'Angle Grinder', 'Power Tools', 5, 0, 'Available'),
        (18, 'Drill Press', 'Power Tools', 2, 0, 'Available'),
        (19, 'Power Screwdriver', 'Power Tools', 3, 0, 'Available'),
        (20, 'Soldering Iron', 'Power Tools', 2, 0, 'Available'),
        (21, 'Hot Glue Gun', 'Power Tools', 2, 0, 'Available'),
        (22, 'Electric Cutter', 'Power Tools', 2, 0, 'Available'),
        
        # Measuring & Testing Instruments
        (23, 'Vernier Caliper', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (24, 'Digital Caliper', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (25, 'Micrometer', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (26, 'Multimeter', 'Measuring & Testing Instruments', 5, 0, 'Available'),
        (27, 'Oscilloscope', 'Measuring & Testing Instruments', 1, 0, 'Available'),
        (28, 'Clamp Meter', 'Measuring & Testing Instruments', 4, 0, 'Available'),
        (29, 'Spirit Level', 'Measuring & Testing Instruments', 2, 0, 'Available'),
        (30, 'Laser Level', 'Measuring & Testing Instruments', 1, 0, 'Available'),
        (31, 'Dial Gauge', 'Measuring & Testing Instruments', 5, 0, 'Unavailable'),
        
        # Cutting Tools
        (32, 'Box Cutter', 'Cutting Tools', 20, 0, 'Available'),
        (33, 'Utility Knife', 'Cutting Tools', 15, 0, 'Available'),
        (34, 'Chisels', 'Cutting Tools', 10, 0, 'Available'),
        (35, 'Knife', 'Cutting Tools', 5, 0, 'Unavailable'),
        (36, 'Shears', 'Cutting Tools', 5, 0, 'Unavailable'),
        
        # Heavy Equipment Machinery & Tools
        (37, 'Lathe Machine', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (38, 'Milling Cutter', 'Heavy Equipment Machinery & Tools', 20, 0, 'Available'),
        (39, 'Heavy Drill Press', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (40, 'Machine Accessories', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (41, 'Welding Machine', 'Heavy Equipment Machinery & Tools', 10, 0, 'Available'),
        (42, 'Grinders', 'Heavy Equipment Machinery & Tools', 6, 0, 'Available'),
        (43, 'Buffers', 'Heavy Equipment Machinery & Tools', 4, 0, 'Available'),
        
        # Safety Equipment
        (44, 'Safety Goggles', 'Safety Equipment', 10, 0, 'Available'),
        (45, 'Face Shields', 'Safety Equipment', 10, 0, 'Available'),
        (46, 'Insulated Gloves', 'Safety Equipment', 5, 0, 'Available'),
        (47, 'Heat-Resistant Gloves', 'Safety Equipment', 5, 0, 'Available'),
        (48, 'Lab Coats', 'Safety Equipment', 4, 0, 'Available'),
        (49, 'Aprons', 'Safety Equipment', 3, 0, 'Available'),
        (50, 'Ear Protection', 'Safety Equipment', 10, 0, 'Available'),
        (51, 'First Aid Kit', 'Safety Equipment', 1, 0, 'Available'),
        (52, 'Fire Extinguishers', 'Safety Equipment', 6, 0, 'Available'),
        
        # Storage & Supporting Equipment
        (53, 'Toolboxes', 'Storage & Supporting Equipment', 3, 0, 'Unavailable'),
        (54, 'Tool Cabinets', 'Storage & Supporting Equipment', 2, 0, 'Unavailable'),
        (55, 'Workbenches with Vises', 'Storage & Supporting Equipment', 6, 0, 'Available'),
        (56, 'Carts', 'Storage & Supporting Equipment', 5, 0, 'Available'),
        (57, 'Trolleys', 'Storage & Supporting Equipment', 4, 0, 'Available'),
        (58, 'Storage Racks', 'Storage & Supporting Equipment', 7, 0, 'Available')
    ]

    for item in items:
        cursor.execute("""
            INSERT OR IGNORE INTO inventory (item_id, item_name, type, quantity, borrowed, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, item)

    conn.commit()
    conn.close()

# -----------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------
#-------------------------------------------------
#LOGIN ROUTE
#-------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, password, first_name, last_name FROM admins WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        # Check if user exists and password is correct
        if not user or not check_password_hash(user[1], password):
            flash("❌ Invalid credentials", "error")
            return redirect(url_for("login_page"))

        # Generate OTP (6 digits) and expiry (10 minutes)
        otp = str(random.randint(100000, 999999))
        expiry = (datetime.now() + timedelta(minutes=10)).isoformat()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE admins SET otp=?, otp_expiry=? WHERE admin_id=?", (otp, expiry, user[0]))
        conn.commit()
        conn.close()

        # Send OTP via email
        send_verification_email(email, otp)

        # Store email temporarily in session for OTP step
        session["pending_email"] = email

        # Instead of redirecting to dashboard, render login page with JS instruction to open OTP modal
        return render_template("LogIn.html", show_otp_modal=True, email=email)

    return render_template("LogIn.html")
# -----------------------------
# STEP 1: Admin Email + Password Check
# -----------------------------
@app.route('/login_step1', methods=['POST'])
def login_step1():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins WHERE email=?", (email,))
    admin = cur.fetchone()

    # Validation
    if not admin:
        conn.close()
        return jsonify({'success': False, 'error': 'Account not found.'})
    if not check_password_hash(admin['password'], password):
        conn.close()
        return jsonify({'success': False, 'error': 'Incorrect password.'})

    # Generate 6-digit OTP and expiry (UTC+8)
    otp_code = str(random.randint(100000, 999999))
    expiry_time = datetime.now(timezone(timedelta(hours=8))) + timedelta(minutes=10)
    expiry_iso = expiry_time.isoformat()

    # Store OTP and expiry
    cur.execute(
        "UPDATE admins SET otp=?, otp_expiry=? WHERE admin_id=?",
        (otp_code, expiry_iso, admin['admin_id'])
    )
    conn.commit()
    conn.close()

    # Send OTP via email
    try:
        send_verification_email(email, otp_code)
    except Exception as e:
        print(f"[ERROR] Failed to send OTP: {e}")
        return jsonify({'success': False, 'error': 'Failed to send verification email.'})

    return jsonify({'success': True, 'message': 'OTP sent to your email.'})


# -----------------------------
# STEP 2: Verify OTP → Complete Login
# -----------------------------
@app.route('/login_step2', methods=['POST'])
def login_step2():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins WHERE email=?", (email,))
    admin = cur.fetchone()

    if not admin:
        conn.close()
        return jsonify({'success': False, 'error': 'Account not found.'})

    otp_stored = admin['otp']
    otp_expiry = admin['otp_expiry']

    # Validate OTP match
    if not otp_stored or otp_stored != code:
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid verification code.'})

    # Convert expiry safely
    try:
        otp_expiry_dt = datetime.fromisoformat(otp_expiry)
        if otp_expiry_dt.tzinfo is None:
            otp_expiry_dt = otp_expiry_dt.replace(tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid OTP expiry format.'})

    now_ph = datetime.now(timezone(timedelta(hours=8)))

    if otp_expiry_dt < now_ph:
        conn.close()
        return jsonify({'success': False, 'error': 'OTP expired. Please log in again.'})

    # ✅ OTP verified → start session
    session['admin_id'] = admin['admin_id']
    session['email'] = admin['email']
    session['first_name'] = admin['first_name']
    session['last_name'] = admin['last_name']
    session['loggedin'] = True

    # Clear OTP (security)
    cur.execute("UPDATE admins SET otp=NULL, otp_expiry=NULL WHERE admin_id=?", (admin['admin_id'],))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# route to verify OTP for two-factor authentication
@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    code = request.form.get("otp_code")
    email = session.get("pending_email")

    if not email or not code:
        flash("❌ Missing OTP or session expired.", "error")
        return redirect(url_for("login_page"))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id, otp, otp_expiry, first_name, last_name FROM admins WHERE email=?", (email,))
    user = cursor.fetchone()

    if not user or user[1] != code:
        conn.close()
        flash("❌ Invalid OTP", "error")
        return redirect(url_for("login_page"))

    if datetime.datetime.fromisoformat(user[2]) < datetime.datetime.now():
        conn.close()
        flash("❌ OTP expired", "error")
        return redirect(url_for("login_page"))

    # OTP valid → clear OTP and create session
    cursor.execute("UPDATE admins SET otp=NULL, otp_expiry=NULL WHERE admin_id=?", (user[0],))
    conn.commit()
    conn.close()

    session["admin_id"] = user[0]
    session["email"] = email
    session["first_name"] = user[3]
    session["last_name"] = user[4]
    session["loggedin"] = True
    session.pop("pending_email", None)

    flash("✅ Login successful!", "success")
    return redirect(url_for("dashboard"))

# -----------------------------------------------------------------
# DATABASE CONNECTION HELPER
# -----------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

#protect logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function
#verification code logic or sending in the email
def send_verification_email(receiver_email, code):
    smtp_user = os.getenv("EMAIL_USER")
    smtp_pass = os.getenv("EMAIL_PASS")

    msg = MIMEText(f"Your verification code is: {code}")
    msg["Subject"] = "Verification Code"
    msg["From"] = smtp_user
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [receiver_email], msg.as_string())
        print("✅ Verification email sent successfully")
    except Exception as e:
        print("❌ Error sending email:", str(e))

def generate_code():
    return str(random.randint(100000, 999999))

def save_verification_code(email, code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE admins
        SET verification_code = ?
        WHERE email = ?
    """, (code, email))
    conn.commit()
    conn.close()
    
# -----------------------------------
# ROUTE 1: Landing Page
# -----------------------------------
@app.route('/landing_page')
def landing_page():
    return render_template('Landing.html')
# -----------------------------------------------------------------
# ROUTE 2: BORROW PAGE
# -----------------------------------------------------------------
@app.route("/borrow")
@login_required
def borrow_page():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        item_id, 
        item_name, 
        quantity, 
        borrowed, 
        CASE 
            WHEN (quantity - borrowed) < 0 THEN 0 
            ELSE (quantity - borrowed) 
        END AS available, 
        type
        FROM inventory
        ORDER BY item_name ASC
    """)
    items = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT type 
        FROM inventory 
        WHERE type IS NOT NULL AND type != '' 
        ORDER BY type ASC
    """)
    types = [row["type"] for row in cursor.fetchall()]
    conn.close()

    equipment = [
        {
            "id": item["item_id"],
            "name": item["item_name"],
            "all_quantity": item["quantity"],
            "on_borrowed": item["borrowed"],
            "available": item["available"],
            "type": item["type"],
        }
        for item in items
    ]

    return render_template("borrow.html", equipment=equipment, types=types)


# -----------------------------------------------------------------
# ROUTE 2: BORROW CONFIRMATION
# -----------------------------------------------------------------
@app.route("/borrow_confirm", methods=["POST"])
def borrow_confirm():
    try:
        # --- RFID duplicate scan prevention ---
        last_rfid = session.get("last_rfid")
        last_time = session.get("last_time", 0)
        

        rfid = request.form.get("rfid")
        if not rfid:
            flash("⚠️ RFID missing. Please scan again.", "warning")
            return redirect(url_for("borrow_page"))

        if last_rfid == rfid and (datetime.now(ZoneInfo("Asia/Manila")).timestamp() - last_time < 5):
            flash("⚠️ Please wait a moment before scanning again.", "warning")
            return redirect(url_for("kiosk_borrow_page"))

        session["last_rfid"] = rfid
        session["last_time"] = datetime.now(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d %H:%M:%S")

        # --- Retrieve form lists ---
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        before_condition_list = request.form.getlist("before_condition[]")
        subject = request.form.get("subject")
        room = request.form.get("room")
        instructor_rfid = request.form.get("instructor_rfid")

        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = ?", (session['admin_id'],))
        admin = cursor.fetchone()
        admin_full_name = f"{admin['first_name']} {admin['last_name']}" if admin else "Tool Room Admin"

        # --- Fetch borrower info ---
        cursor.execute("""
            SELECT user_id, borrower_id, first_name, last_name, department, course, umak_email
            FROM borrowers WHERE rfid = ?
        """, (rfid,))
        borrower = cursor.fetchone()

        if not borrower:
            flash("❌ RFID not recognized.", "error")
            conn.close()
            return redirect(url_for("borrow_page"))

        user_id = borrower["user_id"]
        borrower_no = borrower["borrower_id"]
        full_name = f"{borrower['first_name']} {borrower['last_name']}"
        department = borrower["department"]
        course = borrower["course"]
        borrower_email = borrower["umak_email"]

        # --- Verify instructor RFID ---
        cursor.execute("""
            SELECT user_id, first_name, last_name, roles, umak_email
            FROM borrowers WHERE rfid = ?
        """, (instructor_rfid,))
        instructor = cursor.fetchone()

        if not instructor or instructor["roles"].lower() != "instructor":
            flash("❌ Invalid or unauthorized instructor RFID.", "error")
            conn.close()
            return redirect(url_for("borrow_page"))

        instructor_id = instructor["user_id"]
        instructor_name = f"{instructor['first_name']} {instructor['last_name']}"
        instructor_email = instructor["umak_email"]

        # --- Loop through borrowed items ---
        items = []
        for eq_name, qty, cond in zip(equipment_list, quantity_list, before_condition_list):
            qty = int(qty) if qty.isdigit() else 0
            if qty <= 0:
                continue

            # ✅ Use correct column names
            cursor.execute("SELECT item_id, quantity, borrowed FROM inventory WHERE item_name = ?", (eq_name,))
            item = cursor.fetchone()
            if not item:
                flash(f"⚠️ Item '{eq_name}' not found in inventory.", "warning")
                continue

            item_id = item["item_id"]
            available = item["quantity"] - item["borrowed"]

            if available < qty:
                flash(f"⚠️ Not enough stock for {eq_name}. Only {available} available.", "warning")
                continue

            # Insert borrow record
            ph_time = datetime.now(ZoneInfo("Asia/Manila"))
            borrow_date = ph_time.strftime("%Y-%m-%d")
            borrow_time = ph_time.strftime("%H:%M:%S")

            cursor.execute("""
                INSERT INTO transactions 
                (user_id, instructor_id, instructor_rfid, subject, room, rfid, item_id, borrowed_qty, before_condition, borrow_date, borrow_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, instructor_id, instructor_rfid, subject, room, rfid, item_id, qty, cond, borrow_date, borrow_time))

            # Update inventory status
            cursor.execute("""
                UPDATE inventory 
                SET borrowed = borrowed + ?,
                    status = CASE WHEN borrowed + ? >= quantity THEN 'Borrowed' ELSE 'Available' END
                WHERE item_id = ?
            """, (qty, qty, item_id))

            items.append({"name": eq_name, "qty": qty, "condition": cond})

        # --- Get last borrow ID and format it ---
        cursor.execute("SELECT MAX(borrow_id) AS last_id FROM transactions")
        last_id = cursor.fetchone()["last_id"] or 1
        formatted_borrow_id = f"{last_id:07d}"

        cursor.execute("SELECT COUNT(*) FROM transactions")
        print("📊 Total transactions now:", cursor.fetchone()[0])

        conn.commit()
        conn.close()

        # --- Prepare transaction data for slip and email ---
        transaction = {
            "transaction_number": formatted_borrow_id,
            "name": full_name,
            "user_id": borrower_no,
            "department": department,
            "course": course,
            "instructor_name": instructor_name,
            "subject": subject,
            "room": room,
            "date": datetime.now(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d %H:%M:%S"),
            "time": datetime.now(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d %H:%M:%S"),
            "items": items,
            "admin_name": admin_full_name
        }

        # --- Generate and email borrow slip ---
        file_path = generate_borrow_slip(transaction)
        send_transaction_email(borrower_email, file_path, transaction)

        flash("✅ Borrow transaction successful.", "success")
        # ✅ Determine if it's kiosk or admin
        # --- Render success page ---
        if request.form.get("from_kiosk") == "true":
            # Kiosk version
            return render_template("KioskSuccess.html", transaction=transaction)
        else:
            # Admin or normal user version
            return render_template("transaction_success.html", transaction=transaction)

    except Exception as e:
        import traceback
        print("❌ Error during borrow_confirm:", e)
        print(traceback.format_exc())
        flash("❌ Error processing transaction.", "error")
        return redirect(url_for("borrow_page"))

# -----------------------------------------------------------------
# RFID Scanner route
# -----------------------------------------------------------------
@app.route('/rfid_scanner', methods=['POST'])
@login_required
def rfid_scanner():
    try:
        # Retrieve all arrays from Borrow.html form
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        condition_list = request.form.getlist("before_condition[]")
        instructor_rfid = request.form.get("instructor_rfid")  
        subject = request.form.get("subject")
        room = request.form.get("room")

        if not equipment_list:
            flash("⚠️ No equipment data received.", "error")
            return redirect(url_for("borrow_page"))
        
        # Pass arrays to the RFID scanner page
        return render_template(
            "RfidScanner.html",
            action_url=url_for("borrow_confirm"),
            equipment_list=equipment_list,
            quantity_list=quantity_list,
            condition_list=condition_list,
            instructor_rfid=request.form.get("instructor_rfid"),
            subject=request.form.get("subject"),
            room=request.form.get("room"),
            zip=zip  # Pass zip function to template for iteration
        )

    except Exception as e:
        print("Error in /rfid_scanner:", e)
        flash("An error occurred while preparing RFID scanning.", "error")
        return redirect(url_for("borrow_page"))

# route for transaction success page pop-up in admin panel
@app.route('/transaction_success/<borrow_id>')
@login_required
def view_transaction(borrow_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- Fetch main transaction info ---
    cursor.execute("""
        SELECT 
            t.borrow_id,
            t.borrow_date AS date,
            t.borrow_time AS time,
            t.subject,
            t.room,
            b.first_name,
            b.last_name,
            b.department,
            b.course,
            b.borrower_id AS user_id,
            i2.first_name AS instructor_first,
            i2.last_name AS instructor_last
        FROM transactions t
        JOIN borrowers b ON t.user_id = b.user_id
        JOIN borrowers i2 ON t.instructor_id = i2.user_id
        WHERE t.borrow_id = ?
        LIMIT 1
    """, (borrow_id,))
    main = cursor.fetchone()

    if not main:
        conn.close()
        flash("❌ Borrow transaction not found.", "error")
        return redirect(url_for("dashboard"))

    # --- Fetch all items for this borrow_id ---
    cursor.execute("""
        SELECT i.item_name AS equipment, t.borrowed_qty AS quantity, t.before_condition AS condition
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.borrow_id = ?
    """, (borrow_id,))
    items = cursor.fetchall()

    conn.close()

    # --- Build transaction dictionary ---
    transaction = {
        "transaction_number": f"{main['borrow_id']:07d}",
        "date": main["date"],
        "time": main["time"],
        "name": f"{main['first_name']} {main['last_name']}",
        "user_id": main["user_id"],
        "department": main["department"],
        "course": main["course"],
        "instructor_name": f"{main['instructor_first']} {main['instructor_last']}",
        "subject": main["subject"],
        "room": main["room"],
        "items": items
    }

    return render_template("transaction_success.html", transaction=transaction)

#------------------------------------------------------------------
# Send borrower's transaction slip via email
def generate_borrow_slip(transaction):
    """Generate a PDF borrow slip and return its file path."""
    folder = "generated_slips"
    os.makedirs(folder, exist_ok=True)

    filename = f"borrow_slip_{transaction['transaction_number']}.pdf"
    file_path = os.path.join(folder, filename)

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Header Section
    elements.append(Paragraph("<b>UNIVERSITY OF MAKATI</b>", styles["Title"]))
    elements.append(Paragraph("Laboratory Equipment Borrow Slip", styles["Heading2"]))
    elements.append(Spacer(1, 12))

    # Transaction and Borrower Info
    info_data = [
        ["Borrow ID:", transaction["transaction_number"]],
        ["Name:", transaction["name"]],
        ["Borrower ID:", transaction["user_id"]],
        ["Department:", transaction["department"]],
        ["Course:", transaction["course"]],
        ["Instructor:", transaction["instructor_name"]],
        ["Subject:", transaction["subject"]],
        ["Room:", transaction["room"]],
        ["Date:", transaction["date"]],
        ["Time:", transaction["time"]],
    ]
    info_table = Table(info_data, colWidths=[120, 300])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("BOX", (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.black),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # Borrowed Items Table
    elements.append(Paragraph("<b>Borrowed Items</b>", styles["Heading3"]))
    item_data = [["Item Name", "Quantity", "Condition Before Borrowing"]]
    for item in transaction["items"]:
        item_data.append([item["name"], str(item["qty"]), item["condition"]])
    item_table = Table(item_data, colWidths=[200, 80, 200])
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("BOX", (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.black),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 24))

    # Footer Section
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("<b>Approved by:</b>", styles["Normal"]))
    elements.append(Paragraph(f"{transaction['admin_name']}", styles["Normal"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<i>Note: Please return borrowed items in good condition and on time.</i>", styles["Italic"]))

    doc.build(elements)
    return file_path

# send email function for borrowing slip
def send_transaction_email(recipient, file_path, transaction):
    """Send an email with the borrow slip PDF attached."""
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")

    subject = f"Borrow Slip - {transaction['transaction_number']}"
    body = f"""
Dear {transaction['name']},

Attached is your borrow slip for your recent equipment borrowing transaction.

Borrow ID: {transaction['transaction_number']}
Date: {transaction['date']}
Subject: {transaction['subject']}
Room: {transaction['room']}

Thank you,
University of Makati - LEBS
"""

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    # Attach the PDF
    with open(file_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(file_path))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(sender_email, sender_password)
        smtp.send_message(msg)

# -----------------------------------------------------------------
# RETURN ROUTES
# -----------------------------------------------------------------
# Route for RFID scanning in return page
@app.route("/rfid_scanner_return", methods=["GET", "POST"])
@login_required
def rfid_scanner_return():
    if request.method == "GET":
        return render_template("RfidScannerReturn.html")

    rfid = request.form.get("rfid")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔹 Get borrower info
    cursor.execute("SELECT * FROM borrowers WHERE rfid = ?", (rfid,))
    borrower = cursor.fetchone()

    if not borrower:
        flash("❌ Borrower not found for this RFID.")
        conn.close()
        return redirect(url_for("rfid_scanner_return"))

    # 🔹 Get borrowed items that are not yet fully returned
    cursor.execute("""
        SELECT 
            t.borrow_id,
            i.item_name,
            t.borrowed_qty,
            IFNULL(t.returned_qty, 0) AS returned_qty,
            t.before_condition,
            t.after_condition,
            t.borrow_date,
            t.borrow_time
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.rfid = ? 
        AND (t.returned_qty < t.borrowed_qty OR t.returned_qty IS NULL)
    """, (rfid,))
    items = cursor.fetchall()

    # Close DB connection early
    conn.close()

    # 🔹 If all items have been returned
    if not items:
        flash("✅ All items for this borrower have already been returned.")
        return redirect(url_for("rfid_scanner_return"))

    # 🔹 Prepare borrower info for ReturnForm.html
    borrower_info = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",  # formatted borrow_id
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower["image"],
        "date": items[0]['borrow_date'],  
        "time": items[0]['borrow_time']
    }

    # 🔹 Render ReturnForm.html with all borrowed items
    return render_template("ReturnForm.html", borrower=borrower_info, items=items)

# -----------------------------------------------------------------
#Route to receive the RFID from the scanner page and checks if the borrower exists and has pending returns
# -----------------------------------------------------------------
@app.route("/return_confirm", methods=["POST"])
@login_required
def return_confirm():
    rfid = request.form.get("rfid")

    if not rfid:
        flash("❌ No RFID received. Please try again.")
        return redirect(url_for("rfid_scanner_return"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔹 Verify borrower exists
    cursor.execute("SELECT * FROM borrowers WHERE rfid = ?", (rfid,))
    borrower = cursor.fetchone()

    if not borrower:
        flash("⚠️ RFID not found in the system.")
        conn.close()
        return redirect(url_for("rfid_scanner_return"))

    # 🔹 Fetch all items not yet fully returned
    cursor.execute("""
        SELECT 
            t.borrow_id,
            i.item_name,
            t.borrowed_qty,
            IFNULL(t.returned_qty, 0) AS returned_qty,
            t.before_condition,
            t.borrow_date,
            t.borrow_time
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.rfid = ? 
          AND (t.returned_qty < t.borrowed_qty OR t.returned_qty IS NULL)
    """, (rfid,))
    items = cursor.fetchall()
    conn.close()

    # 🔹 If no items pending return
    if not items:
        flash("✅ All items for this borrower are already returned.")
        return redirect(url_for("rfid_scanner_return"))

    # 🔹 Build borrower info dict
    borrower_data = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",  # formatted 0000001 style
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower["image"],
        "date": items[0]["borrow_date"],
        "time": items[0]["borrow_time"]
    }

    # 🔹 Build item list for template
    items_data = [
        {
            "borrow_id": f"{item['borrow_id']:07d}",
            "item_name": item["item_name"],
            "quantity_borrowed": item["borrowed_qty"],
            "quantity_returned": item["returned_qty"],
            "condition_borrowed": item["before_condition"],
        }
        for item in items
    ]

    # 🔹 Render ReturnForm.html
    return render_template("ReturnForm.html", borrower=borrower_data, items=items_data)

# -----------------------------------------------------------------
#Route to finalized the return, updates inventory, and logs history in ReturnForm.html
# -----------------------------------------------------------------
@app.route("/process_return", methods=["POST"])
@login_required
def process_return():
    transaction_no = request.form.get("transaction_no")
    rfid = request.form.get("rfid")
    item_names = request.form.getlist("item_name[]")
    qty_returned = request.form.getlist("quantity_returned[]")
    cond_returned = request.form.getlist("condition_returned[]")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get borrower info
    cursor.execute("SELECT * FROM borrowers WHERE rfid = ?", (rfid,))
    borrower = cursor.fetchone()

    if not borrower:
        flash("⚠️ Borrower not found.")
        conn.close()
        return redirect(url_for("rfid_scanner_return"))

    # 🔹 Get transaction details including subject, room, and instructor info
    cursor.execute("""
        SELECT t.subject, t.room, b.first_name AS instructor_first, b.last_name AS instructor_last
        FROM transactions t
        JOIN borrowers b ON t.instructor_rfid = b.rfid
        WHERE t.borrow_id = ?
        LIMIT 1
    """, (transaction_no,))
    trans_details = cursor.fetchone()

    returned_items = []

    for i in range(len(item_names)):
        item = item_names[i]
        qty = int(qty_returned[i])
        cond = cond_returned[i]

        # Get item_id
        cursor.execute("SELECT item_id FROM inventory WHERE item_name = ?", (item,))
        item_row = cursor.fetchone()
        if not item_row:
            continue
        item_id = item_row["item_id"]

        # Update transaction
        cursor.execute("""
            UPDATE transactions
            SET 
                returned_qty = CASE 
                    WHEN (IFNULL(returned_qty,0) + ?) > borrowed_qty THEN borrowed_qty
                    ELSE IFNULL(returned_qty,0) + ?
                END,
                after_condition = ?,
                return_date = DATE('now'),
                return_time = TIME('now')
            WHERE borrow_id = ? AND item_id = ?
        """, (qty, qty, cond, int(transaction_no), item_id))

        # Update inventory (never allow negative borrowed count)
        cursor.execute("""
            UPDATE inventory
            SET borrowed = MAX(borrowed - ?, 0)
            WHERE item_id = ?
        """, (qty, item_id))

        returned_items.append({
            "equipment": item,
            "quantity": qty,
            "condition": cond
        })

    # Get current date/time
    cursor.execute("SELECT DATE('now'), TIME('now')")
    date, time = cursor.fetchone()

    # 🔹 Get logged-in admin info
    cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = ?", (session["admin_id"],))
    admin = cursor.fetchone()
    admin_name = f"{admin['first_name']} {admin['last_name']}" if admin else "Unknown"

    conn.commit()
    conn.close()

    # Prepare transaction data for PDF and email
    transaction = {
        "borrow_id": f"{int(transaction_no):07d}",
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "user_id": borrower["borrower_id"],
        "department": borrower["department"],
        "course": borrower["course"],
        "instructor_name": f"{trans_details['instructor_first']} {trans_details['instructor_last']}" if trans_details else "N/A",
        "subject": trans_details["subject"] if trans_details else "N/A",
        "room": trans_details["room"] if trans_details else "N/A",
        "date": date,
        "time": time,
        "items": returned_items,
        "admin_name": admin_name,
        "email": borrower["umak_email"]
    }

    # 🔹 Generate PDF return slip and send email
    pdf_path = generate_return_slip(transaction)
    send_return_email(
        recipient=transaction["email"],
        file_path=pdf_path,
        transaction=transaction
    )

    return render_template("SuccessReturn.html", transaction=transaction)

# Send borrower's return slip via email
def generate_return_slip(transaction):
    """Generate a PDF return slip and return its file path."""
    folder = "generated_slips"
    os.makedirs(folder, exist_ok=True)

    filename = f"return_slip_{transaction['borrow_id']}.pdf"
    file_path = os.path.join(folder, filename)

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Header Section
    elements.append(Paragraph("<b>UNIVERSITY OF MAKATI</b>", styles["Title"]))
    elements.append(Paragraph("Laboratory Equipment Return Slip", styles["Heading2"]))
    elements.append(Spacer(1, 12))

    # Transaction and Borrower Info
    info_data = [
        ["Borrow ID:", transaction["transaction_number"]],
        ["Name:", transaction["name"]],
        ["Borrower ID:", transaction["user_id"]],
        ["Department:", transaction["department"]],
        ["Course:", transaction["course"]],
        ["Instructor:", transaction["instructor_name"]],
        ["Subject:", transaction["subject"]],
        ["Room:", transaction["room"]],
        ["Date Returned:", transaction["date"]],
        ["Time Returned:", transaction["time"]],
    ]
    info_table = Table(info_data, colWidths=[120, 300])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("BOX", (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.black),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # Returned Items Table
    elements.append(Paragraph("<b>Returned Items</b>", styles["Heading3"]))
    item_data = [["Item Name", "Quantity", "Condition After Return"]]
    for item in transaction["items"]:
        item_data.append([item["name"], str(item["qty"]), item["condition"]])
    item_table = Table(item_data, colWidths=[200, 80, 200])
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("BOX", (0,0), (-1,-1), 0.5, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.black),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 24))

    # Footer Section
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("<b>Processed by:</b>", styles["Normal"]))
    elements.append(Paragraph(f"{transaction['admin_name']}", styles["Normal"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<i>Note: Please ensure that all returned items are in good condition.</i>", styles["Italic"]))

    doc.build(elements)
    return file_path


# Send email function for return slip
def send_return_email(recipient, file_path, transaction):
    """Send an email with the return slip PDF attached."""
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")

    subject = f"Return Slip - {transaction['borrow_id']}"
    body = f"""
Dear {transaction['name']},

Attached is your return slip for the equipment you have returned.

Borrow ID: {transaction['borrow_id']}
Date Returned: {transaction['date']}
Subject: {transaction['subject']}
Room: {transaction['room']}

Thank you for returning your borrowed items in good condition.

University of Makati - LEBS
"""

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    # Attach the PDF
    with open(file_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(file_path))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(sender_email, sender_password)
        smtp.send_message(msg)

# -----------------------------------------------------------------
#DASHBOARD ROUTE
# -----------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # ====== STATS ======
    cursor.execute("SELECT COUNT(*) FROM borrowers")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM transactions")
    borrowed_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(returned_qty) FROM transactions")
    total_returned = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM inventory")
    total_items = cursor.fetchone()[0]

    # Returned = transactions with return_date NOT NULL
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE return_date IS NOT NULL")
    returned = cursor.fetchone()[0]

    # ====== NEW: PENDING RETURNS COUNT ======
    cursor.execute("SELECT COUNT(*) FROM pending_returns")
    pending_returns_count = cursor.fetchone()[0]

    # ====== NEW: PENDING RETURNS DATA ======
    cursor.execute("""
        SELECT 
            pr.id as pending_id,
            pr.borrow_id,
            pr.user_id,
            pr.return_data,
            pr.created_at,
            b.first_name || ' ' || b.last_name AS borrower_name,
            b.borrower_id,
            b.department,
            b.course,
            t.borrow_date,
            t.borrow_time
        FROM pending_returns pr
        JOIN borrowers b ON pr.user_id = b.user_id
        JOIN transactions t ON pr.borrow_id = t.borrow_id
        ORDER BY pr.created_at DESC
    """)
    pending_returns = cursor.fetchall()

    # ====== TRANSACTION HISTORY ======
    cursor.execute("""
        SELECT 
            b.borrow_date, 
            b.borrow_time, 
            i.item_name, 
            s.first_name || ' ' || s.last_name AS borrower, 
            b.borrowed_qty,
            b.returned_qty,
            CASE 
                WHEN IFNULL(b.returned_qty, 0) = 0 THEN 'borrowed'
                WHEN IFNULL(b.returned_qty, 0) < b.borrowed_qty THEN 'partial'
                WHEN IFNULL(b.returned_qty, 0) = b.borrowed_qty THEN 'returned'
            END AS status
        FROM transactions b
        JOIN borrowers s ON b.user_id = s.user_id
        JOIN inventory i ON b.item_id = i.item_id
        ORDER BY b.borrow_date DESC, b.borrow_time DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    history = {}
    total_returned_qty = 0
    status_counts = {}

    for row in rows:
        borrow_date, borrow_time, item_name, borrower, quantity, returned_qty, status = row
        history.setdefault(borrow_date, []).append({
            "time": borrow_time,
            "tool": item_name,
            "user": borrower,
            "quantity": quantity,
            "returned_qty": returned_qty,
            "status": status
        })
        total_returned_qty += returned_qty if returned_qty else 0
        status_counts[status] = status_counts.get(status, 0) + 1

    stats = {
        "users": users,
        "borrowed": borrowed_count,
        "total_trans": borrowed_count,
        "total_returned": total_returned,
        "status_counts": status_counts,
        # NEW: Add pending returns count to stats
        "pending_returns": pending_returns_count
    }

    # ====== WEEKLY CHART (Mon–Sun) ======
    weekly_chart = []
    today_dt = datetime.now()
    monday = (today_dt - timedelta(days=today_dt.weekday())).date()

    conn2 = sqlite3.connect(DB_NAME)
    cursor2 = conn2.cursor()
    for i in range(7):
        day = monday + timedelta(days=i)
        cursor2.execute(
            "SELECT SUM(borrowed_qty) FROM transactions WHERE date(borrow_date) = ?",
            (day.strftime('%Y-%m-%d'),)
        )
        weekly_chart.append(cursor2.fetchone()[0] or 0)
    conn2.close()

    # ====== MONTHLY CHART (Grouped by weeks with dynamic labels) ======
    today = datetime.now().date()
    year, month = today.year, today.month
    first_day = datetime(year, month, 1).date()

    # Compute the last day of the month
    if month == 12:
        next_month_first = datetime(year + 1, 1, 1).date()
    else:
        next_month_first = datetime(year, month + 1, 1).date()
    last_day = next_month_first - timedelta(days=1)

    # Determine number of weeks
    num_weeks = ((last_day.day - 1) // 7) + 1

    monthly_chart = []
    monthly_labels = []

    conn3 = sqlite3.connect(DB_NAME)
    cursor3 = conn3.cursor()

    for week in range(1, num_weeks + 1):
        week_start = first_day + timedelta(days=(week - 1) * 7)
        week_end = week_start + timedelta(days=6)
        if week_end > last_day:
            week_end = last_day

        # Sum borrowed items within this week
        cursor3.execute("""
            SELECT SUM(borrowed_qty)
            FROM transactions
            WHERE date(borrow_date) BETWEEN ? AND ?
        """, (week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
        weekly_total = cursor3.fetchone()[0] or 0
        monthly_chart.append(weekly_total)

        # Dynamic label (e.g., Week 1 (Oct 1–6))
        start_label = week_start.strftime("%b %d").lstrip("0").replace(" 0", " ")
        end_label = week_end.strftime("%d").lstrip("0").replace(" 0", " ")
        label = f"Week {week} ({start_label}–{end_label})"
        monthly_labels.append(label)

    conn3.close()

    # ====== YEARLY CHART (Jan–Dec) ======
    yearly_chart = []
    yearly_labels = []
    conn4 = sqlite3.connect(DB_NAME)
    cursor4 = conn4.cursor()
    for m in range(1, 13):
        cursor4.execute("""
            SELECT SUM(borrowed_qty)
            FROM transactions
            WHERE strftime('%Y', borrow_date) = ? AND strftime('%m', borrow_date) = ?
        """, (str(year), f"{m:02d}"))
        yearly_chart.append(cursor4.fetchone()[0] or 0)
        yearly_labels.append(calendar.month_abbr[m])
    conn4.close()

    # ====== RENDER DASHBOARD ======
    return render_template(
        "Dashboard.html",
        stats=stats,
        history=history,
        # NEW: Pass pending returns data to template
        pending_returns=pending_returns,
        weekly_chart=weekly_chart,
        weekly_labels=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
        monthly_chart=monthly_chart,
        monthly_labels=monthly_labels,
        yearly_chart=yearly_chart,
        yearly_labels=yearly_labels
    )
# ------------------------------------------------------------
# ------------------------------------------------------------
# Admin Confirm Return Route
@app.route('/admin/confirm-return/<int:pending_id>', methods=['POST'])
@login_required
def confirm_return(pending_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1️⃣ Fetch the pending return
        cursor.execute("SELECT borrow_id, user_id, return_data FROM pending_returns WHERE id = ?", (pending_id,))
        pending = cursor.fetchone()
        if not pending:
            return {"success": False, "error": "Pending return not found"}, 404

        borrow_id, user_id, return_data_json = pending
        return_items = json.loads(return_data_json)

        # 2️⃣ Fetch borrower details for email
        cursor.execute("SELECT first_name, last_name, umak_email FROM borrowers WHERE user_id = ?", (user_id,))
        borrower = cursor.fetchone()
        if not borrower:
            return {"success": False, "error": "Borrower not found"}, 404

        borrower_name = f"{borrower[0]} {borrower[1]}"
        borrower_email = borrower[2]

        # 3️⃣ Update transactions + inventory
        for item in return_items:
            equipment_name = item['equipment']
            returned_qty = int(item['quantity'])
            after_condition = item['condition']

            # Get the item_id
            cursor.execute("SELECT item_id FROM inventory WHERE item_name = ?", (equipment_name,))
            inventory_item = cursor.fetchone()
            if not inventory_item:
                continue
            item_id = inventory_item[0]

            # Update transactions
            cursor.execute("""
                UPDATE transactions
                SET returned_qty = returned_qty + ?, 
                    after_condition = ?,
                    return_date = DATE('now'),
                    return_time = TIME('now')
                WHERE borrow_id = ? AND item_id = ?
            """, (returned_qty, after_condition, borrow_id, item_id))

            # ✅ Update inventory correctly (only adjust 'borrowed', never 'quantity')
            cursor.execute("""
                UPDATE inventory
                SET borrowed = CASE 
                        WHEN borrowed - ? < 0 THEN 0 
                        ELSE borrowed - ? 
                    END,
                    status = CASE 
                        WHEN borrowed - ? <= 0 THEN 'Available' 
                        ELSE 'Borrowed' 
                    END
                WHERE item_id = ?
            """, (returned_qty, returned_qty, returned_qty, item_id))

        # 4️⃣ Delete pending record
        cursor.execute("DELETE FROM pending_returns WHERE id = ?", (pending_id,))
        conn.commit()

        # ✅ Close connection *after* DB work only
        conn.close()

        # 5️⃣ Send PDF slip to borrower
        generate_and_send_return_slip_pdf(borrow_id, borrower_name, borrower_email, return_items)

        # ✅ Notify kiosk that return was confirmed (no broadcast arg)
        socketio.emit("return_confirmed", {
            "borrow_id": f"{borrow_id:07d}",
            "borrower_name": borrower_name
        })

        return {"success": True, "message": "Return confirmed and slip sent."}

    except Exception as e:
        # Make sure rollback only happens if connection still open
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        print("❌ Error in confirm_return:", e)
        return {"success": False, "error": str(e)}, 500

# -----------------------------------------------------------------
# Send return slip email to borrower
def generate_and_send_return_slip_pdf(borrow_id, borrower_name, borrower_email, items):
    # --- Generate PDF in memory ---
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph("<b>University of Makati</b><br/>Laboratory Equipment Borrowing System", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Return Slip</b><br/>Transaction No: {borrow_id:07d}", styles['Heading2']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Borrower:</b> {borrower_name}", styles['Normal']))
    elements.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Table Data
    data = [["Equipment", "Returned Qty", "Condition After Return"]]
    for item in items:
        data.append([item['equipment'], str(item['quantity']), item['condition']])

    table = Table(data, colWidths=[200, 100, 180])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    elements.append(table)

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Confirmed by:</b> Administrator", styles['Normal']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Thank you for returning the items responsibly.", styles['Italic']))

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()

    # --- Send Email with PDF attachment ---
    try:
        sender_email = os.getenv("EMAIL_USER")
        sender_password = os.getenv("EMAIL_PASS")

        if not sender_email or not sender_password:
            print("⚠️ Missing EMAIL_USER or EMAIL_PASS environment variables.")
            return

        # ✅ Construct the email first before sending
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = borrower_email
        msg["Subject"] = f"Return Slip Confirmation - Transaction #{borrow_id:07d}"

        body = MIMEText(
            f"""Dear {borrower_name},

Your returned items have been confirmed.
Please find the attached return slip for your reference.

Thank you,
UMAK-LEBS System
""",
            "plain"
        )
        msg.attach(body)

        # Attach PDF
        pdf_attachment = MIMEApplication(pdf_data, _subtype="pdf")
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename=f"ReturnSlip_{borrow_id:07d}.pdf")
        msg.attach(pdf_attachment)

        # ✅ Send email via Gmail SMTP SSL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

        print(f"✅ Return slip email sent successfully to {borrower_email}.")

    except Exception as e:
        print("❌ Error sending return slip email:", e)

# -----------------------------------------------------------------
# Admin reject return route
@app.route('/admin/reject-return/<int:pending_id>', methods=['POST'])
@login_required
def reject_return(pending_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Just delete the pending return without touching transactions/inventory
        cursor.execute("DELETE FROM pending_returns WHERE id = ?", (pending_id,))
        conn.commit()
        conn.close()

        return {"success": True}

    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "error": str(e)}, 500
# -----------------------------------------------------------------
#route for inventory.html
#route to show the items in the inventory in the buttons
@app.route("/inventory")
@login_required
def inventory_page():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory")
    items = cursor.fetchall()
    conn.close()
    return render_template("inventory.html", items=items)

#route to get the types of inventory in the database
@app.route('/types')
@login_required
def inventory_types():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT type FROM inventory WHERE type IS NOT NULL AND type != '' ORDER BY type ASC")
    types = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(types)
#route to add items in the database
@app.route("/add", methods=["POST"])
@login_required
def add_item():
    name = request.form.get("name")
    type_ = request.form.get("type")
    quantity = int(request.form.get("quantity", 0))
    borrowed = int(request.form.get("borrowed", 0))
    status = request.form.get("status", "Available")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO inventory (item_name, type, quantity, borrowed, status)
        VALUES (?, ?, ?, ?, ?)
    """, (name, type_, quantity, borrowed, status))
    conn.commit()
    conn.close()

    return "OK", 200
#route to edit items in the database
@app.route('/edit', methods=['POST'])
@login_required
def edit_item():
    item_id = request.form.get('id')
    name = request.form.get('name')
    type_ = request.form.get('type')
    quantity = request.form.get('quantity')
    borrowed = request.form.get('borrowed')
    status = request.form.get('status')

    # make sure item_id is int
    if not item_id:
        return "Missing ID", 400

    try:
        item_id_int = int(item_id)
    except ValueError:
        return "Invalid ID", 400

    # Validate numeric fields
    try:
        quantity_int = int(quantity) if quantity is not None and quantity != '' else 0
    except ValueError:
        return "Invalid quantity", 400

    try:
        borrowed_int = int(borrowed) if borrowed is not None and borrowed != '' else 0
    except ValueError:
        return "Invalid borrowed value", 400

    # Ensure borrowed does not exceed quantity
    if borrowed_int > quantity_int:
        return "Borrowed cannot be greater than quantity", 400

    # Basic sanitization for status
    status = status or ('Unavailable' if borrowed_int >= quantity_int and quantity_int > 0 else 'Available')

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE inventory
            SET item_name = ?, type = ?, quantity = ?, borrowed = ?, status = ?
            WHERE item_id = ?
            """,
            (name, type_, quantity_int, borrowed_int, status, item_id_int)
        )
        conn.commit()
        conn.close()
        return "OK", 200
    except Exception as e:
        # Log server-side error and return 500
        print(f"Edit item error: {e}")
        return ("Server error", 500)

@app.route('/delete', methods=['POST'])
@login_required
def delete_item():
    data = request.get_json()  # parse JSON body
    ids = data.get("ids", [])

    if not ids:
        return jsonify({"status": "error", "message": "No IDs received"}), 400

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Delete multiple IDs safely
        cursor.executemany("DELETE FROM inventory WHERE item_id = ?", [(i,) for i in ids])

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Items deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------------------
# USERS MANAGEMENT ROUTES
#-------------------------------
@app.route("/users")
@login_required
def users_page():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            u.user_id,
            u.borrower_id,
            u.last_name,
            u.first_name,
            u.department,
            u.course,
            u.roles,
            u.image,
            u.umak_email,
            (u.last_name || ', ' || u.first_name) AS name,
            (
                SELECT COUNT(*) 
                FROM transactions b 
                WHERE b.user_id = u.user_id
            ) AS transactions
        FROM borrowers u
        ORDER BY u.user_id DESC
    """)

    users = [
        {
            "user_id": row[0],
            "stud_no": row[1],
            "last_name": row[2],
            "first_name": row[3],
            "department": row[4],
            "course": row[5],
            "image": row[7],
            "roles": row[6],
            "email": row[8],
            "name": row[9],
            "transactions": row[10]
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template("UsersPage.html", users=users)
#route to get the transactions of a specific user by their user_id
@app.route("/user_transactions/<int:user_id>")
@login_required
def user_transactions(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # ✅ Added CASE for status: shows Borrowed / Returned
    cursor.execute("""
        SELECT 
            t.borrow_id,                                       -- 0
            printf('%07d', t.borrow_id) AS formatted_borrow_id, -- 1 formatted ID
            i.item_name,                                       -- 2
            t.borrowed_qty,                                    -- 3
            t.returned_qty,                                    -- 4
            t.borrow_date,                                     -- 5
            t.return_date,                                     -- 6
            CASE 
                WHEN t.return_date IS NULL THEN 'Borrowed'
                ELSE 'Returned'
            END AS status                                      -- 7
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.user_id = ?
        ORDER BY t.borrow_date DESC
    """, (user_id,))

    # ✅ Corrected index mapping
    transactions = [
        {
            "transaction_id": row[1],      # formatted_borrow_id (0000001)
            "item_name": row[2],
            "status": row[7],              # new status
            "borrowed_date": row[5],
            "returned_date": row[6] or "-"
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    
    return {"transactions": transactions}

#route to add a user in the database
@app.route("/add_user", methods=["POST"])
@login_required
def add_user():
    # Check if request is JSON or form data
    if request.is_json:
        data = request.get_json()
        rfid = data.get("rfid")
        last_name = data.get("lastName")  # Note: changed from "last_name"
        first_name = data.get("firstName")  # Note: changed from "first_name"
        stud_no = data.get("stud_no")
        college = data.get("college")
        course = data.get("course")
        roles = data.get("roles")
        umak_email = data.get("umak_email")
    else:
        # Fallback to form data
        rfid = request.form.get("rfid")
        last_name = request.form.get("lastName")
        first_name = request.form.get("firstName")
        stud_no = request.form.get("stud_no")
        college = request.form.get("college")
        course = request.form.get("course")
        roles = request.form.get("roles")
        umak_email = request.form.get("umakEmail")

    if not (rfid and last_name and first_name and stud_no):
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO borrowers (rfid, borrower_id, last_name, first_name, department, course, roles, umak_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (rfid, stud_no, last_name, first_name, college, course, roles, umak_email))
        conn.commit()
        return jsonify({"status": "success", "message": "User added successfully"})
    except sqlite3.IntegrityError as e:
        error_msg = str(e)
        if "UNIQUE constraint failed: borrowers.rfid" in error_msg:
            return jsonify({"status": "error", "message": "RFID already exists"}), 400
        elif "UNIQUE constraint failed: borrowers.borrower_id" in error_msg:
            return jsonify({"status": "error", "message": "Student number already exists"}), 400
        else:
            return jsonify({"status": "error", "message": "Database error: " + error_msg}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": "Server error: " + str(e)}), 500
    finally:
        conn.close()

#route to edit a user in the database
@app.route("/edit_user/<int:user_id>", methods=["PUT"])
@login_required
def edit_user(user_id):
    data = request.get_json()
    last_name = data.get("last_name")
    first_name = data.get("first_name")
    stud_no = data.get("stud_no")
    college = data.get("college")
    course = data.get("course")
    roles = data.get("roles")
    umak_email = data.get("umak_email")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE borrowers
        SET last_name=?, first_name=?, department=?, course=?, roles=?, umak_email=?
        WHERE user_id=?
    """, (last_name, first_name, college, course, roles, umak_email, user_id))

    # Update borrower info in transactions too
    cursor.execute("""
        UPDATE transactions
        SET rfid = rfid -- keep RFID unchanged, but user_id stays consistent
        WHERE user_id = ?
    """, (user_id,))
    
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

#delete user route
@app.route("/delete_user/<int:user_id>", methods=["DELETE"])
@login_required
def delete_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # First delete transactions linked to this user
    cursor.execute("DELETE FROM transactions WHERE user_id=?", (user_id,))
    # Then delete borrower
    cursor.execute("DELETE FROM borrowers WHERE user_id=?", (user_id,))
    
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

#----------------------------------------------------------
#route for history page
@app.route("/history")
@login_required
def history_page():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    selected_date = request.args.get("date")

    base_query = """
        SELECT b.borrow_date, b.borrow_time, i.item_name, 
                s.first_name || ' ' || s.last_name AS borrower,
                b.borrowed_qty, b.returned_qty,
                CASE 
                    WHEN IFNULL(b.returned_qty, 0) = 0 THEN 'borrowed'
                    WHEN IFNULL(b.returned_qty, 0) < b.borrowed_qty THEN 'partial'
                    WHEN IFNULL(b.returned_qty, 0) = b.borrowed_qty THEN 'returned'
                END AS status
        FROM transactions b
        JOIN borrowers s ON b.user_id = s.user_id
        JOIN inventory i ON b.item_id = i.item_id
    """

    if selected_date:
        cursor.execute(
            base_query + " WHERE b.borrow_date = ? ORDER BY b.borrow_date DESC, b.borrow_time DESC",
            (selected_date,)
        )
    else:
        cursor.execute(base_query + " ORDER BY b.borrow_date DESC, b.borrow_time DESC")

    rows = cursor.fetchall()
    conn.close()

    # Group by date only (NOT by transaction)
    history = {}
    for borrow_date, borrow_time, item_name, borrower, quantity, returned_qty, status in rows:
        # each borrowed item = its own record
        if borrow_date not in history:
            history[borrow_date] = []
        history[borrow_date].append({
            "time": borrow_time,
            "tool": item_name,
            "user": borrower,
            "quantity": quantity,
            "returned_qty": returned_qty,
            "status": status
        })

    return render_template("History.html", history=history or {})

#----------------------------------------------------------
# Route for report and data analytics 
@app.route("/report")
@login_required
def report_page():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Total borrows
    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_borrows = cursor.fetchone()[0]

    # Items currently borrowed
    cursor.execute("""
        SELECT SUM(
            CASE 
                WHEN (borrowed_qty - returned_qty) > 0 
                THEN (borrowed_qty - returned_qty)
                ELSE 0
            END
        )
        FROM transactions
    """)
    currently_borrowed = cursor.fetchone()[0] or 0

    # Available items
    cursor.execute("SELECT SUM(quantity - borrowed) FROM inventory")
    available_items = cursor.fetchone()[0] or 0

    # Items needing attention
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE status != 'Available'")
    items_attention = cursor.fetchone()[0]

    # Most borrowed items
    cursor.execute("""
        SELECT i.item_name, i.type, SUM(b.borrowed_qty) as total_borrowed
        FROM transactions b
        JOIN inventory i ON b.item_id = i.item_id
        GROUP BY b.item_id
        ORDER BY total_borrowed DESC
        LIMIT 5
    """)
    most_borrowed = [
        {"name": row[0], "type": row[1], "quantity": row[2]}
        for row in cursor.fetchall()
    ]

    # Items in poor condition
    cursor.execute("""
        SELECT i.item_name, i.type, b.after_condition as condition
        FROM transactions b
        JOIN inventory i ON b.item_id = i.item_id
        WHERE b.after_condition IS NOT NULL
        AND b.after_condition NOT IN ('new-unused','like-new','excellent','very-good','good')
        GROUP BY b.item_id
    """)
    poor_condition_items = [
        {"name": row[0], "type": row[1], "condition": row[2]}
        for row in cursor.fetchall()
    ]

    # Unavailable items
    cursor.execute("""
        SELECT i.item_name, i.type, i.status
        FROM inventory i
        WHERE i.status != 'Available'
    """)
    unavailable_items = []
    for row in cursor.fetchall():
        # Safely handle non-numeric values
        try:
            days = int(float(row[2])) if row[2] is not None else 0
        except (ValueError, TypeError):
            days = 0
        unavailable_items.append({
            "name": row[0],
            "type": row[1],
            "days_unavailable": days
        })

    # ---------------- Chart Data ----------------
    today = datetime.now().date()

    # Daily chart
    slot_hours = [6,8,10,12,14,16,18,20,22]
    daily_chart = []
    today_str = today.strftime('%Y-%m-%d')
    for h in slot_hours:
        start_time = f"{h:02d}:00:00"
        end_time = f"{h+1:02d}:59:59" if h < 22 else "23:59:59"
        cursor.execute("""
            SELECT SUM(borrowed_qty) FROM transactions
            WHERE date(borrow_date) = ? AND time(borrow_time) BETWEEN ? AND ?
        """, (today_str, start_time, end_time))
        daily_chart.append(cursor.fetchone()[0] or 0)

    # Weekly chart
    today_dt = datetime.now()
    today_day = today_dt.weekday()  # 0=Mon
    monday = (today_dt - timedelta(days=today_day)).date()
    weekly_chart = []
    for i in range(7):
        day = monday + timedelta(days=i)
        cursor.execute("SELECT SUM(borrowed_qty) FROM transactions WHERE date(borrow_date) = ?", (day.strftime('%Y-%m-%d'),))
        weekly_chart.append(cursor.fetchone()[0] or 0)

    # Monthly chart
    monthly_chart = []
    year, month = today.year, today.month
    first_day = datetime(year, month, 1).date()
    if month == 12:
        next_month_first = datetime(year + 1, 1, 1).date()
    else:
        next_month_first = datetime(year, month + 1, 1).date()
    last_day = next_month_first - timedelta(days=1)
    num_weeks = ((last_day.day - 1) // 7) + 1

    for week in range(1, num_weeks + 1):
        week_start = first_day + timedelta(days=(week - 1) * 7)
        week_end = min(week_start + timedelta(days=6), last_day)
        cursor.execute("""
            SELECT SUM(borrowed_qty) FROM transactions
            WHERE date(borrow_date) BETWEEN ? AND ?
        """, (week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
        monthly_chart.append(cursor.fetchone()[0] or 0)

    conn.close()

    return render_template(
        "Reports.html",
        total_borrows=total_borrows,
        currently_borrowed=currently_borrowed,
        available_items=available_items,
        items_attention=items_attention,
        most_borrowed=most_borrowed,
        poor_condition_items=poor_condition_items,
        unavailable_items=unavailable_items,
        daily_chart=daily_chart,
        weekly_chart=weekly_chart,
        monthly_chart=monthly_chart
    )


#----------------------------------------------------------
# Route to Generate PDF Report
@app.route("/generate_report_pdf")
@login_required
def generate_report_pdf():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Report summary
    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_borrows = cursor.fetchone()[0]

    # Items currently borrowed
    cursor.execute("""
        SELECT SUM(
            CASE 
                WHEN (borrowed_qty - returned_qty) > 0 
                THEN (borrowed_qty - returned_qty)
                ELSE 0
            END
        )
        FROM transactions
    """)
    currently_borrowed = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(quantity - borrowed) FROM inventory")
    available_items = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM inventory WHERE status != 'Available'")
    items_attention = cursor.fetchone()[0]

    cursor.execute("SELECT item_name, type, quantity, borrowed, status FROM inventory")
    inventory_data = cursor.fetchall()
    conn.close()

    # Generate charts
    charts = []

    def make_chart(data, title, labels):
        plt.figure(figsize=(5, 2.5))
        plt.bar(labels, data, color='skyblue')
        plt.title(title)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        charts.append(buf)
        plt.close()

    # Example dummy chart data (replace with your own logic)
    make_chart([1, 2, 3, 4, 5], "Sample Weekly Chart", ["Mon", "Tue", "Wed", "Thu", "Fri"])

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = []

    # Title and date
    elements.append(Paragraph("<b>Laboratory Equipment Borrowing System Report</b>", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Date Generated: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Summary section
    summary_data = [
        ["Total Borrows", total_borrows],
        ["Currently Borrowed", currently_borrowed],
        ["Available Items", available_items],
        ["Items Needing Attention", items_attention]
    ]
    summary_table = Table(summary_data, colWidths=[200, 150])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER')
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 18))

    # Inventory list
    inv_table_data = [["Item Name", "Type", "Quantity", "Borrowed", "Status"]] + list(inventory_data)
    inv_table = Table(inv_table_data, repeatRows=1)
    inv_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9)
    ]))
    elements.append(Paragraph("<b>Inventory List</b>", styles['Heading2']))
    elements.append(inv_table)
    elements.append(Spacer(1, 18))

    # ✅ Add charts directly (no ImageReader)
    for chart in charts:
        elements.append(Image(chart, width=400, height=200))
        elements.append(Spacer(1, 12))

    doc.build(elements)
    buffer.seek(0)

    # Send PDF as a download
    return send_file(buffer, as_attachment=True, download_name="UMAK_LEBS_Report.pdf", mimetype="application/pdf")

#-------------------------------------------------
# AUTHENTICATION ROUTES
#--------------------------------------------------
#route for creating an account for admin
@app.route('/CreateAccount', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        fname = request.form.get('fname', '').strip()
        lname = request.form.get('lname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirmPassword = request.form.get('confirm-password', '')

        if not fname or not lname or not email or not password:
            flash('Please fill out all fields.', 'danger')
            return render_template('CreateAccount.html', fname=fname, lname=lname, email=email)

        if not re.match(r'[^@]+@umak\.edu\.ph$', email):
            flash('Please use a valid UMak email address.', 'danger')
            return render_template('CreateAccount.html', fname=fname, lname=lname, email=email)
        
        if password != confirmPassword:
            flash("Passwords do not match! Please re-enter.", "error")
            return render_template('CreateAccount.html', fname=fname, lname=lname, email=email) # or whatever your route name is
        
        # Password complexity validation
        password_requirements = [
            (len(password) >= 8, "Password must be at least 8 characters long."),
            (re.search(r'[A-Z]', password), "Password must contain at least one uppercase letter."),
            (re.search(r'[a-z]', password), "Password must contain at least one lowercase letter."),
            (re.search(r'\d', password), "Password must contain at least one number."),
            (re.search(r'[!@#$%^&*(),.?\":{}|<>]', password), "Password must contain at least one special character."),
        ]

        for valid, msg in password_requirements:
            if not valid:
                flash(msg, 'danger')
                return render_template('CreateAccount.html', fname=fname, lname=lname, email=email)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT admin_id FROM admins WHERE email = ?', (email,))
            if cursor.fetchone():
                flash('Account already exists. Please log in.', 'warning')
                conn.close()
                return redirect(url_for('login_page'))  # Changed to login_page

            hashed = generate_password_hash(password)
            code = str(os.urandom(3).hex()).upper()           
            ph_time = timezone(timedelta(hours=8))
            now = datetime.now(ph_time).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO pending_admins (first_name, last_name, email, password, verification_code, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fname, lname, email, hashed, code, now))
            
            conn.commit()

            # ✅ Send email here
            send_verification_email(email, code)

            session['pending_email'] = email
            flash('Verification code has been sent to your email.', 'success')
            return redirect(url_for('verification', email=email))
            
        except Exception as e:
            conn.rollback()
            print(f"Create account error: {e}")
            flash('An error occurred while creating the account.', 'danger')
            return render_template('CreateAccount.html')
        finally:
            conn.close()

    return render_template('CreateAccount.html')

# Route to render the verification page
@app.route("/verification/<email>", methods=["GET", "POST"])
def verification(email):
    if request.method == "POST":
        code = request.form.get("verification_code", "").strip()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check pending_admins for matching email + code
        cursor.execute("""
            SELECT id, first_name, last_name, email, password, verification_code, created_at
            FROM pending_admins
            WHERE email = ? AND verification_code = ?
        """, (email, code))
        pending = cursor.fetchone()

        if pending:
            try:
                # Move verified user to admins table
                cursor.execute("""
                    INSERT INTO admins (first_name, last_name, email, password, is_verified, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                """, (pending[1], pending[2], pending[3], pending[4], pending[6]))

                # Remove from pending_admins
                cursor.execute("DELETE FROM pending_admins WHERE email = ?", (email,))
                conn.commit()

                flash("✅ Verification successful! You can now log in.", "success")
                return redirect(url_for("login_page"))

            except Exception as e:
                conn.rollback()
                print(f"Error moving verified admin: {e}")
                flash("❌ Error finalizing verification. Please try again.", "error")
                return redirect(url_for("verification", email=email))

            finally:
                conn.close()

        else:
            conn.close()
            flash("❌ Invalid or expired verification code.", "error")
            return redirect(url_for("verification", email=email))

    # GET → Render verification page
    return render_template("verification.html", email=email)

#route for resending a code in the admin's email
@app.route('/resend-code', methods=['POST'])
def resend_code():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    email = request.form.get('email') or session.get('pending_email') or session.get('email')
    if not email:
        flash('No email specified for resending code.', 'warning')
        return redirect(url_for('create_account'))

    code = str(os.urandom(3).hex()).upper()

    if not cursor:
        flash('Database error. Try again later.', 'danger')
        return redirect(url_for('verification', email=email))

    try:
        cursor.execute('UPDATE admins SET verification_code = ? WHERE email = ?', (code, email))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Resend code error: {e}")
        flash('Failed to resend verification code.', 'danger')
    finally:
        conn.close()

    return redirect(url_for('verification', email=email))

# route to logOut
@app.route('/logout')
def logout():
    for k in ['loggedin', 'admin_id', 'email', 'first_name', 'last_name', 'pending_email', 'user_id']:
        session.pop(k, None)
    session.clear()  # ensures everything is wiped
    return redirect(url_for('login_page'))

# route to get admin account details
@app.route('/get_admin_account')
@login_required
def get_admin_account():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name, email FROM admins WHERE admin_id = ?", (session['admin_id'],))
    admin = cursor.fetchone()
    conn.close()

    if not admin:
        return jsonify(success=False, error="Admin not found.")
    
    return jsonify(success=True, first_name=admin[0], last_name=admin[1], email=admin[2])

# route to update admin account details
@app.route('/update_admin_account', methods=['POST'])
@login_required
def update_admin_account():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not name or not email or not current_password:
        return jsonify(success=False, error="All required fields must be filled.")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT password FROM admin WHERE admin_id = ?", (session['admin_id'],))
    admin = cursor.fetchone()

    if not admin:
        conn.close()
        return jsonify(success=False, error="Admin not found.")

    # Verify current password
    if not check_password_hash(admin[0], current_password):
        conn.close()
        return jsonify(success=False, error="Incorrect current password.")

    # Update information
    if new_password:
        hashed_pw = generate_password_hash(new_password)
        cursor.execute("""
            UPDATE admin SET name=?, email=?, password=? WHERE admin_id=?
        """, (name, email, hashed_pw, session['admin_id']))
    else:
        cursor.execute("""
            UPDATE admin SET name=?, email=? WHERE admin_id=?
        """, (name, email, session['admin_id']))

    conn.commit()
    conn.close()
    return jsonify(success=True)
#-------------------------------------------------
#Forgot Password Route
@app.route("/send_forgot_code", methods=["POST"])
def send_forgot_code():
    data = request.get_json()
    email = data.get("email")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM admins WHERE email=?", (email,))
    admin = cursor.fetchone()
    conn.close()

    if not admin:
        return jsonify(success=False, error="Email not registered")

    code = str(random.randint(100000,999999))
    save_verification_code(email, code)
    send_verification_email(email, code)
    return jsonify(success=True)
# route for resetting password
@app.route("/reset_password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("new_password")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT verification_code FROM admins WHERE email=?", (email,))
    admin = cursor.fetchone()

    if not admin or admin[0] != code:
        conn.close()
        return jsonify(success=False, error="Invalid or expired code")

    hashed_pw = generate_password_hash(new_password)
    cursor.execute("UPDATE admins SET password=?, verification_code=NULL WHERE email=?", (hashed_pw, email))
    conn.commit()
    conn.close()
    return jsonify(success=True)
# function to save verification code in the database
def save_verification_code(email, code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE admins SET verification_code=? WHERE email=?", (code, email))
    conn.commit()
    conn.close()
# function to send verification email
def send_verification_email(receiver_email, code):
    msg = MIMEText(f"Your verification code is: {code}")
    msg["Subject"] = "UMak LEBS Password Reset"
    msg["From"] = smtp_user
    msg["To"] = receiver_email
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [receiver_email], msg.as_string())

#-------------------------------------------------
#FUNCTION FOR KIOSK OR USER'S PAGE
#-------------------------------------------------
@app.route('/kiosk_page')
@login_required
def kiosk_page():
    if 'admin_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('KioskSelection.html')

@app.route("/kiosk_borrow")
@login_required
def kiosk_borrow_page():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        item_id, 
        item_name, 
        quantity, 
        borrowed, 
        CASE 
            WHEN (quantity - borrowed) < 0 THEN 0 
            ELSE (quantity - borrowed) 
        END AS available, 
        type
        FROM inventory
        ORDER BY item_name ASC
    """)
    items = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT type 
        FROM inventory 
        WHERE type IS NOT NULL AND type != '' 
        ORDER BY type ASC
    """)
    types = [row["type"] for row in cursor.fetchall()]
    conn.close()

    equipment = [
        {
            "id": item["item_id"],
            "name": item["item_name"],
            "all_quantity": item["quantity"],
            "on_borrowed": item["borrowed"],
            "available": item["available"],
            "type": item["type"],
        }
        for item in items
    ]

    return render_template("KioskBorrow.html", equipment=equipment, types=types)

# -----------------------------------------------------------------
# ROUTE 2: BORROW CONFIRMATION
# -----------------------------------------------------------------
@app.route("/kiosk_borrow_confirm", methods=["POST"])
@login_required
def kiosk_borrow_confirm():
    try:
        # --- RFID duplicate scan prevention ---
        last_rfid = session.get("last_rfid")
        last_time = session.get("last_time")
        

        rfid = request.form.get("rfid")
        if not rfid:
            flash("⚠️ RFID missing. Please scan again.", "warning")
            return redirect(url_for("kiosk_borrow_page"))

        if last_rfid == rfid and (datetime.now().timestamp() - last_time < 5):
            flash("⚠️ Please wait a moment before scanning again.", "warning")
            return redirect(url_for("kiosk_borrow_page"))

        session["last_rfid"] = rfid
        session["last_time"] = datetime.now(ZoneInfo("Asia/Manila")).timestamp()  # float

        # --- Retrieve form lists ---
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        before_condition_list = request.form.getlist("before_condition[]")
        subject = request.form.get("subject")
        room = request.form.get("room")
        instructor_rfid = request.form.get("instructor_rfid")

        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = ?", (session['admin_id'],))
        admin = cursor.fetchone()
        admin_full_name = f"{admin['first_name']} {admin['last_name']}" if admin else "Tool Room Admin"

        # --- Fetch borrower info ---
        cursor.execute("""
            SELECT user_id, borrower_id, first_name, last_name, department, course, umak_email
            FROM borrowers WHERE rfid = ?
        """, (rfid,))
        borrower = cursor.fetchone()

        if not borrower:
            flash("❌ RFID not recognized.", "error")
            conn.close()
            return redirect(url_for("kiosk_borrow_page"))

        user_id = borrower["user_id"]
        borrower_no = borrower["borrower_id"]
        full_name = f"{borrower['first_name']} {borrower['last_name']}"
        department = borrower["department"]
        course = borrower["course"]
        borrower_email = borrower["umak_email"]

        # --- Verify instructor RFID ---
        cursor.execute("""
            SELECT user_id, first_name, last_name, roles, umak_email
            FROM borrowers WHERE rfid = ?
        """, (instructor_rfid,))
        instructor = cursor.fetchone()

        if not instructor or instructor["roles"].lower() != "instructor":
            flash("❌ Invalid or unauthorized instructor RFID.", "error")
            conn.close()
            return redirect(url_for("kiosk_borrow_page"))

        instructor_id = instructor["user_id"]
        instructor_name = f"{instructor['first_name']} {instructor['last_name']}"
        instructor_email = instructor["umak_email"]

        # --- Loop through borrowed items ---
        items = []
        for eq_name, qty, cond in zip(equipment_list, quantity_list, before_condition_list):
            qty = int(qty) if qty.isdigit() else 0
            if qty <= 0:
                continue

            # ✅ Use correct column names
            cursor.execute("SELECT item_id, quantity, borrowed FROM inventory WHERE item_name = ?", (eq_name,))
            item = cursor.fetchone()
            if not item:
                flash(f"⚠️ Item '{eq_name}' not found in inventory.", "warning")
                continue

            item_id = item["item_id"]
            available = item["quantity"] - item["borrowed"]

            if available < qty:
                flash(f"⚠️ Not enough stock for {eq_name}. Only {available} available.", "warning")
                continue

            # Insert borrow record
            ph_time = datetime.now(ZoneInfo("Asia/Manila"))
            borrow_date = ph_time.strftime("%Y-%m-%d")
            borrow_time = ph_time.strftime("%H:%M:%S")

            cursor.execute("""
                INSERT INTO transactions 
                (user_id, instructor_id, instructor_rfid, subject, room, rfid, item_id, borrowed_qty, before_condition, borrow_date, borrow_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, instructor_id, instructor_rfid, subject, room, rfid, item_id, qty, cond, borrow_date, borrow_time))

            # Update inventory status
            cursor.execute("""
                UPDATE inventory 
                SET borrowed = borrowed + ?,
                    status = CASE WHEN borrowed + ? >= quantity THEN 'Borrowed' ELSE 'Available' END
                WHERE item_id = ?
            """, (qty, qty, item_id))

            items.append({"name": eq_name, "qty": qty, "condition": cond})

        # --- Get last borrow ID and format it ---
        cursor.execute("SELECT MAX(borrow_id) AS last_id FROM transactions")
        last_id = cursor.fetchone()["last_id"] or 1
        formatted_borrow_id = f"{last_id:07d}"

        cursor.execute("SELECT COUNT(*) FROM transactions")
        print("📊 Total transactions now:", cursor.fetchone()[0])

        conn.commit()
        conn.close()

        # --- Prepare transaction data for slip and email ---
        transaction = {
            "borrow_id": formatted_borrow_id,
            "name": full_name,
            "user_id": borrower_no,
            "department": department,
            "course": course,
            "instructor_name": instructor_name,
            "subject": subject,
            "room": room,
            "date": datetime.now(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d %H:%M:%S"),
            "time": datetime.now(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d %H:%M:%S"),
            "items": items,
            "admin_name": admin_full_name
        }

        # --- Generate and email borrow slip ---
        file_path = generate_borrow_slip(transaction)
        send_transaction_email(borrower_email, file_path, transaction)

        flash("✅ Borrow transaction successful.", "success")
        return redirect(url_for("kiosk_view_transaction", borrow_id=last_id))

    except Exception as e:
        import traceback
        print("❌ Error during kiosk_borrow_confirm:", e)
        print(traceback.format_exc())
        flash("❌ Error processing transaction.", "error")
        return redirect(url_for("kiosk_borrow_page"))

# -----------------------------------------------------------------
# RFID Scanner route
# -----------------------------------------------------------------
@app.route('/kiosk_rfid_scanner', methods=['POST'])
@login_required
def kiosk_rfid_scanner():
    try:
        # Retrieve all arrays from Borrow.html form
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        condition_list = request.form.getlist("before_condition[]")
        instructor_rfid = request.form.get("instructor_rfid")  
        subject = request.form.get("subject")
        room = request.form.get("room")

        if not equipment_list:
            flash("⚠️ No equipment data received.", "error")
            return redirect(url_for("kiosk_borrow_page"))

        # Pass arrays to the RFID scanner page
        return render_template(
            "RfidScanner.html",
            action_url=url_for("kiosk_borrow_confirm"),
            equipment_list=equipment_list,
            quantity_list=quantity_list,
            condition_list=condition_list,
            instructor_rfid=request.form.get("instructor_rfid"),
            subject=request.form.get("subject"),
            room=request.form.get("room"),
            zip=zip  # Pass zip function to template for iteration
        )

    except Exception as e:
        print("Error in /kiosk_rfid_scanner:", e)
        flash("An error occurred while preparing RFID scanning.", "error")
        return redirect(url_for("kiosk_borrow_page"))

# -----------------------------------------------------------------  
# route for transaction success page pop-up in admin panel
@app.route('/kiosk_success/<borrow_id>')
@login_required
def kiosk_view_transaction(borrow_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- Fetch main transaction info ---
    cursor.execute("""
        SELECT 
            t.borrow_id,
            t.borrow_date AS date,
            t.borrow_time AS time,
            t.subject,
            t.room,
            b.first_name,
            b.last_name,
            b.department,
            b.course,
            b.borrower_id AS user_id,
            i2.first_name AS instructor_first,
            i2.last_name AS instructor_last
        FROM transactions t
        JOIN borrowers b ON t.user_id = b.user_id
        JOIN borrowers i2 ON t.instructor_id = i2.user_id
        WHERE t.borrow_id = ?
        LIMIT 1
    """, (borrow_id,))
    main = cursor.fetchone()

    if not main:
        conn.close()
        flash("❌ Borrow transaction not found.", "error")
        return redirect(url_for("kiosk_page()"))

    # --- Fetch all items for this borrow_id ---
    cursor.execute("""
        SELECT i.item_name AS equipment, t.borrowed_qty AS quantity, t.before_condition AS condition
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.borrow_id = ?
    """, (borrow_id,))

    items = [
        {
            "equipment": row["equipment"],
            "quantity": row["quantity"],
            "condition": row["condition"]
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    # --- Build transaction dictionary ---
    transaction = {
        "transaction_number": f"{main['borrow_id']:07d}",
        "date": main["date"],
        "time": main["time"],
        "name": f"{main['first_name']} {main['last_name']}",
        "user_id": main["user_id"],
        "department": main["department"],
        "course": main["course"],
        "instructor_name": f"{main['instructor_first']} {main['instructor_last']}",
        "subject": main["subject"],
        "room": main["room"],
        "items": items
    }

    return render_template("KioskSuccess.html", transaction=transaction)
# ----------------------------------------------------------
# Kiosk Scanner Route
@app.route('/kiosk/return/scanner', methods=['GET', 'POST'])
def kiosk_scanner_return():
    if request.method == "GET":
        return render_template('KioskScannerReturn.html')

    rfid = request.form.get("rfid")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔹 Get borrower info
    cursor.execute("SELECT * FROM borrowers WHERE rfid = ?", (rfid,))
    borrower = cursor.fetchone()

    if not borrower:
        flash("❌ Borrower not found for this RFID.")
        conn.close()
        return redirect(url_for("kiosk_scanner_return"))

    # 🔹 Get borrowed items that are not yet fully returned
    cursor.execute("""
        SELECT 
            t.borrow_id,
            i.item_name,
            t.borrowed_qty,
            IFNULL(t.returned_qty, 0) AS returned_qty,
            t.before_condition,
            t.after_condition,
            t.borrow_date,
            t.borrow_time
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.rfid = ? 
        AND (t.returned_qty < t.borrowed_qty OR t.returned_qty IS NULL)
    """, (rfid,))
    items = cursor.fetchall()

    # Close DB connection early
    conn.close()

    # 🔹 If all items have been returned
    if not items:
        flash("✅ All items for this borrower have already been returned.")
        return redirect(url_for("kiosk_scanner_return"))

    # 🔹 Prepare borrower info for ReturnForm.html
    borrower_info = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",  # formatted borrow_id
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower["image"],
        "date": items[0]['borrow_date'],  
        "time": items[0]['borrow_time']
    }

    # 🔹 Render ReturnForm.html with all borrowed items
    return render_template("KioskReturnForm.html", borrower=borrower_info, items=items)

# Process RFID Scan for Return
@app.route('/return/confirm', methods=['POST'])
@login_required
def return_kiosk_confirm():
    rfid = request.form.get('rfid')
    
    if not rfid:
        # No RFID scanned, go back to scanner page
        return redirect(url_for('kiosk_scanner_return'))
    
    conn = get_db_connection()
    
    # Check if borrower exists
    borrower = conn.execute(
        'SELECT * FROM borrowers WHERE rfid = ?', (rfid,)
    ).fetchone()
    
    if not borrower:
        conn.close()
        # Instead of going back to KioskSelection, show form with message
        return render_template('KioskReturnForm.html',
                               borrower=None,
                               items=[],
                               error="Borrower not found. Please check your RFID card.")  # ✅ Changed
    
    # Get active transactions with pending returns for this user
    transactions = conn.execute('''
        SELECT DISTINCT t.borrow_id as transaction_no, 
            t.borrow_date as date,
            t.borrow_time as time,
            t.instructor_id,
            t.subject,
            t.room
        FROM transactions t
        WHERE t.rfid = ? AND (t.returned_qty IS NULL OR t.returned_qty < t.borrowed_qty)
        ORDER BY t.borrow_date DESC, t.borrow_time DESC
    ''', (rfid,)).fetchall()
    
    if not transactions:
        conn.close()
        # Instead of redirecting, show the form with no items
        return render_template('KioskReturnForm.html',
                               borrower={
                                   'rfid': rfid,
                                   'name': f"{borrower['first_name']} {borrower['last_name']}",
                                   'department': borrower['department'],
                                   'course': borrower['course'],
                                   'image': borrower['image']
                               },
                               items=[],
                               error="✅ No pending returns for this borrower.")  # ✅ Changed
    
    # Take the most recent transaction
    transaction = transactions[0]
    
    # Get items for this transaction that haven't been fully returned
    items = conn.execute('''
        SELECT t.borrow_id, t.item_id, i.item_name, 
            t.borrowed_qty as quantity_borrowed, 
            COALESCE(t.returned_qty, 0) as quantity_returned,
            t.before_condition as condition_borrowed
        FROM transactions t
        JOIN inventory i ON t.item_id = i.item_id
        WHERE t.rfid = ? AND t.borrow_id = ? 
        AND (t.returned_qty IS NULL OR t.returned_qty < t.borrowed_qty)
    ''', (rfid, transaction['transaction_no'])).fetchall()
        
    conn.close()
    
    # Prepare borrower data for template
    borrower_data = {
        'transaction_no': transaction['transaction_no'],
        'date': transaction['date'],
        'time': transaction['time'],
        'name': f"{borrower['first_name']} {borrower['last_name']}",
        'department': borrower['department'],
        'course': borrower['course'],
        'image': borrower['image'],
        'rfid': rfid
    }
    
    # Store in session for later use in processing
    session['return_rfid'] = rfid
    session['return_transaction_no'] = transaction['transaction_no']
    session['return_user_id'] = borrower['user_id']
    
    # Render the return form with items (empty if none pending)
    return render_template('KioskReturnForm.html', 
                           borrower=borrower_data,
                           items=items,
                           error=None)  
#----------------------------------------------------------------
# Process Return Form Submission
@app.route('/kiosk_process_return', methods=['POST'])
@login_required
def kiosk_process_return():
    rfid = session.get('return_rfid')
    transaction_no = session.get('return_transaction_no')
    user_id = session.get('return_user_id')
    
    if not rfid or not transaction_no:
        return redirect(url_for('kiosk_page'))
    
    # Get form data
    item_names = request.form.getlist('item_name[]')
    quantities_returned = request.form.getlist('quantity_returned[]')
    conditions_returned = request.form.getlist('condition_returned[]')
    
    conn = get_db_connection()

    try:
        current_time = datetime.now()
        return_details = []

        # ✅ 1. Build all return details first (no DB insert yet)
        for i in range(len(item_names)):
            return_details.append({
                'equipment': item_names[i],
                'quantity': int(quantities_returned[i]),
                'condition': conditions_returned[i]
            })

        # ✅ 2. Store pending return once (not inside the loop)
        conn.execute('''
            INSERT INTO pending_returns 
            (borrow_id, user_id, return_data, created_at)
            VALUES (?, ?, ?, ?)
        ''', (transaction_no, user_id, json.dumps(return_details), current_time))
        
        conn.commit()  # ✅ Commit after insert

        # ✅ 3. Fetch borrower info AFTER all commits, before closing
        borrower = conn.execute(
            'SELECT first_name, last_name, borrower_id, department, course, image FROM borrowers WHERE user_id = ?',
            (user_id,)
        ).fetchone()

        conn.close()  # ✅ Close once only, after all DB work

        # ✅ 4. Prepare success data (no DB work after closing)
        success_data = {
            'transaction_number': transaction_no,
            'name': f"{borrower['first_name']} {borrower['last_name']}",
            'user_id': borrower['borrower_id'],
            'department': borrower['department'],
            'course': borrower['course'],
            'date': current_time.strftime('%Y-%m-%d'),
            'time': current_time.strftime('%H:%M:%S'),
            'image': borrower['image'],
            'items': return_details
        }

        session['return_success_data'] = success_data
        
        # ✅ Redirect to success page (KioskReturnSuccess.html)
        return redirect(url_for('return_success'))
    
    except Exception as e:
        # ✅ Only rollback and close if connection still open
        try:
            conn.rollback()
        except:
            pass
        try:
            conn.close()
        except:
            pass

        return render_template('KioskReturnForm.html', error=f"Error processing return: {str(e)}")

#----------------------------------------------------------------
# Return Success Page
@app.route('/return/success')
@login_required
def return_success():
    success_data = session.get('return_success_data')

    # 🔹 If there is no success data in session, go back to kiosk page
    if not success_data:
        return redirect(url_for('kiosk_page'))

    # 🔹 Ensure items is always a list
    if 'items' not in success_data or not isinstance(success_data['items'], list):
        success_data['items'] = []  # empty list if missing or corrupted

    # 🔹 Ensure each item has proper keys (equipment, quantity, condition)
    for item in success_data['items']:
        item.setdefault('equipment', 'Unknown')
        item.setdefault('quantity', 0)
        item.setdefault('condition', 'N/A')

    # 🔹 Clear session data after using it
    session.pop('return_success_data', None)
    session.pop('return_rfid', None)
    session.pop('return_transaction_no', None)
    session.pop('return_user_id', None)

    # 🔹 Render the same KioskReturnSuccess.html template without changing layout
    return render_template('KioskReturnSuccess.html', transaction=success_data)

# ----------------------------------------------------------------- 
# main function to RUN APP
# -----------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    fill_inventory()
    socketio.run(app, debug=True)
    #socketio.run(app, host="0.0.0.0", port=5000, debug=True) #to run in local network