# -----------------------------------------------------------------
# IMPORTS
# -----------------------------------------------------------------
# Flask framework and extensions

from flask import (
    Flask, flash, render_template, request,
    session, redirect, url_for, jsonify, send_file
)
from flask_socketio import SocketIO  # Real-time communication (for notifications, etc.)
import bcrypt  # Secure password hashing
from werkzeug.utils import secure_filename  # For safe file uploads
from werkzeug.security import check_password_hash as werk_check_password_hash
from functools import wraps  # Used for login-required decorators

# ----------------------------------------------
# 
# -------------------
# SYSTEM UTILITIES
# -----------------------------------------------------------------
import os, re, random, json, io, calendar
import time as time_module
from io import BytesIO
from datetime import datetime, timedelta, timezone, date, time  # Time handling
from zoneinfo import ZoneInfo  # More modern timezone handling in Python 3.9+
import base64  # Encoding binary data (e.g., images) into text

# -----------------------------------------------------------------
# EMAIL FUNCTIONALITY
# -----------------------------------------------------------------
import smtplib  # For sending emails
from email.mime.multipart import MIMEMultipart  # Build complex email messages
from email.mime.text import MIMEText  # Add plain text or HTML parts
from email.mime.application import MIMEApplication  # For attachments (PDF, DOCX, etc.)
from email.message import EmailMessage  # Alternative for simple email construction

# -----------------------------------------------------------------
# DOCUMENT GENERATION (DOCX + PDF)
# -----------------------------------------------------------------
from docx import Document  # Generate Microsoft Word documents
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend (for servers)
import matplotlib.pyplot as plt  # For plotting charts
from builtins import zip

# ReportLab (used for generating PDF reports)
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader

# -----------------------------------------------------------------
# ENVIRONMENT VARIABLES
# -----------------------------------------------------------------
from dotenv import load_dotenv  # Load credentials from .env file (for security)
load_dotenv()  # This reads your .env file and makes EMAIL_USER, EMAIL_PASS

# -----------------------------------------------------------------
# DATABASE CONNECTION (MySQL)
# -----------------------------------------------------------------
import mysql.connector  # MySQL connector for Python
from mysql.connector import Error  # Error handling for MySQL
from lebs_database import get_db_connection, fill_inventory, init_db  # Import helper function from external file

# -----------------------------------------------------------------
# FLASK APP INITIALIZATION
# -----------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_default_secret')  # Use env var in production
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow SocketIO for live updates
# Expose WSGI callable expected by hosts (e.g. Railway / WSGI loaders)
application = app
# -----------------------------------------------------------------
# IMAGE UPLOAD SETTINGS
# -----------------------------------------------------------------
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#--------------------------------------------------------------
# PROTECTED LOGIN FORM
#-------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admins_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


# Password verification helper (support bcrypt and Werkzeug hashed formats)
def verify_password(plain_password, stored_hash):
    if not stored_hash:
        return False
    try:
        # bcrypt hashed passwords start with $2a$, $2b$, or $2y$
        if isinstance(stored_hash, str) and (stored_hash.startswith("$2a$") or stored_hash.startswith("$2b$") or stored_hash.startswith("$2y$")):
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception:
        pass
    # Fallback to werkzeug's check (supports scrypt and others)
    try:
        return werk_check_password_hash(stored_hash, plain_password)
    except Exception:
        # Last resort try bcrypt again
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_hash.encode('utf-8'))
        except Exception:
            return False
#-----------------------------------------------------------------
# DEFAULT IMAGE IN INVENTORY
#-----------------------------------------------------------------
DEFAULT_IMAGE = "static/Icons/tool_default.jpg"

# -----------------------------------
# Landing Page
# -----------------------------------
@app.route("/")
def landing_page():
    return render_template('Landing.html')
# -----------------------------------------------------------------
# LOGIN ROUTES
# -----------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login_page():
    """
    Main login page for adminsistrators.
    Step 1: Verify email and password.
    Step 2: Generate OTP and send to registered email.
    Step 3: Wait for OTP input to complete authentication.
    """
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Connect to MySQL
        conn = get_db_connection()
        if not conn:
            flash("⚠️ Database connection failed. Please ensure your MySQL credentials are set in .env or the environment.", "error")
            return redirect(url_for("login_page"))
        cursor = conn.cursor()

        # Fetch admins record based on email
        cursor.execute(
            "SELECT admin_id, password, first_name, last_name FROM admins WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()
        conn.close()

        # Check credentials
        if not user or not verify_password(password, user[1]):
            flash("❌ Invalid credentials", "error")
            return redirect(url_for("login_page"))

        # Generate OTP (valid for 10 minutes)
        otp = str(random.randint(100000, 999999))
        expiry = (datetime.now() + timedelta(minutes=10)).isoformat()

        # Store OTP in the database
        conn = get_db_connection()
        if not conn:
            flash("⚠️ Database connection failed. Please ensure your MySQL credentials are set in .env or the environment.", "error")
            return redirect(url_for("login_page"))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE admins SET otp = %s, otp_expiry = %s WHERE admin_id = %s",
            (otp, expiry, user[0])
        )
        conn.commit()
        conn.close()

        # Send OTP via email
        send_verification_email(email, otp)

        # Temporarily store email in session for the OTP step
        session["pending_email"] = email

        # Return the same page but show OTP modal
        return render_template("LogIn.html", show_otp_modal=True, email=email)

    # Render normal login page for GET requests
    return render_template("LogIn.html")


# -----------------------------------------------------------------
# 🧾 STEP 1: EMAIL + PASSWORD VALIDATION (AJAX version)
# -----------------------------------------------------------------
@app.route('/login_step1', methods=['POST'])
def login_step1():
    """
    First AJAX-based login step:
    - Checks if email & password match.
    - Sends OTP to registered email.
    """
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection failed. Please contact the administrator.'})

    cur = None
    otp_code = None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM admins WHERE email = %s", (email,))
        admins = cur.fetchone()

        # Validation
        if not admins:
            return jsonify({'success': False, 'error': 'Account not found. Please create an account.'})
        if not verify_password(password, admins['password']):
            return jsonify({'success': False, 'error': 'Incorrect password.'})

        # Generate OTP and expiry (UTC+8)
        otp_code = str(random.randint(100000, 999999))
        expiry_time = datetime.now() + timedelta(minutes=10)
        expiry_iso = expiry_time.strftime('%Y-%m-%d %H:%M:%S')

        # Store OTP and expiry
        cur.execute(
            "UPDATE admins SET otp = %s, otp_expiry = %s WHERE admin_id = %s",
            (otp_code, expiry_iso, admins['admin_id'])
        )
        conn.commit()

    except Exception as e:
        print(f"[ERROR] login_step1 DB error: {e}")
        return jsonify({'success': False, 'error': 'Internal server error.'})
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # Send OTP email
    try:
        send_verification_email(email, otp_code)
    except Exception as e:
        print(f"[ERROR] Failed to send OTP: {e}")
        return jsonify({'success': False, 'error': 'Failed to send verification email.'})

    return jsonify({'success': True, 'message': 'OTP sent to your email.'})


# -----------------------------------------------------------------
# 🧾 STEP 2: OTP VERIFICATION → COMPLETE LOGIN
# -----------------------------------------------------------------
@app.route('/login_step2', methods=['POST'])
def login_step2():
    """
    Second AJAX-based login step:
    - Validates OTP from user.
    - Starts admins session if OTP is correct.
    """
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM admins WHERE email = %s", (email,))
    admins = cur.fetchone()

    if not admins:
        conn.close()
        return jsonify({'success': False, 'error': 'Account not found.'})

    otp_stored = admins['otp']
    otp_expiry = admins['otp_expiry']

    # Check OTP match
    if not otp_stored or otp_stored != code:
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid verification code.'})

    # Check expiration (handle MySQL DATETIME or string formats)
    try:
        otp_expiry_str = str(otp_expiry)
        if '.' in otp_expiry_str:  # handles microseconds
            otp_expiry_dt = datetime.strptime(otp_expiry_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        elif 'T' in otp_expiry_str:  # handles ISO format like 2025-10-31T20:15:43
            otp_expiry_dt = datetime.fromisoformat(otp_expiry_str)
        else:
            otp_expiry_dt = datetime.strptime(otp_expiry_str, '%Y-%m-%d %H:%M:%S')

        # 🕒 Make it timezone-aware (Philippine Time)
        otp_expiry_dt = otp_expiry_dt.replace(tzinfo=timezone(timedelta(hours=8)))

    except Exception as e:
        print(f"[DEBUG] OTP expiry format error: {otp_expiry} ({e})")
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid OTP expiry format.'})

    now_ph = datetime.now(timezone(timedelta(hours=8)))  # aware datetime (PH Time)

    # ✅ Compare both aware datetimes safely
    if otp_expiry_dt < now_ph:
        conn.close()
        return jsonify({'success': False, 'error': 'OTP expired. Please log in again.'})

    # ✅ OTP valid → start session
    session['admins_id'] = admins['admin_id']
    session['email'] = admins['email']
    session['first_name'] = admins['first_name']
    session['last_name'] = admins['last_name']
    session['loggedin'] = True

    # Clear OTP (for security)
    cur.execute("UPDATE admins SET otp = NULL, otp_expiry = NULL WHERE admin_id = %s", (admins['admin_id'],))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'redirect_url': url_for('dashboard')})

# -----------------------------------------------------------------
# VERIFY OTP (Form Submission Route)
# -----------------------------------------------------------------
@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    code = request.form.get("otp_code")
    email = session.get("pending_email")

    if not email or not code:
        flash("❌ Missing OTP or session expired.", "error")
        return redirect(url_for("login_page"))

    conn = get_db_connection()
    if not conn:
        flash("⚠️ Database connection failed. Please ensure your MySQL service is running and credentials are set.", "error")
        return redirect(url_for("login_page"))
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id, otp, otp_expiry, first_name, last_name FROM admins WHERE email=%s", (email,))
    user = cursor.fetchone()

    if not user or user[1] != code:
        conn.close()
        flash("❌ Invalid OTP", "error")
        return redirect(url_for("login_page"))

    try:
        otp_expiry = datetime.strptime(user[2], "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        conn.close()
        flash("❌ Invalid OTP expiry format.", "error")
        print(f"⚠️ Failed to parse OTP expiry: {user[2]} ({e})")
        return redirect(url_for("login_page"))

    # Check expiration
    if otp_expiry < datetime.now():
        conn.close()
        flash("❌ OTP expired", "error")
        return redirect(url_for("login_page"))

    cursor.execute("UPDATE admins SET otp=NULL, otp_expiry=NULL WHERE admin_id=%s", (user[0],))
    conn.commit()
    conn.close()

    session["admins_id"] = user[0]
    session["email"] = email
    session["first_name"] = user[3]
    session["last_name"] = user[4]
    session["loggedin"] = True
    session.pop("pending_email", None)

    flash("✅ Login successful!", "success")
    return redirect(url_for("dashboard"))

# -----------------------------------------------------------------
# SEND VERIFICATION EMAIL
# -----------------------------------------------------------------
def send_verification_email(receiver_email, code):
    smtp_user = os.getenv("EMAIL_USER")
    smtp_pass = os.getenv("EMAIL_PASS")

    message_body = f"""
    Dear User,

    We received a request to verify your account for the University of Makati Laboratory Equipment Borrowing System (UMak-LEBS).

    Your verification code is: {code}

    Please enter this code in the verification field to proceed. 
    For your security, do not share this code with anyone.

    Best regards,
    UMak-LEBS Support Team
    University of Makati
    """
    msg = MIMEText(message_body.strip())
    msg["Subject"] = "UMak-LEBS Account Verification Code"
    msg["From"] = smtp_user
    msg["To"] = receiver_email

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [receiver_email], msg.as_string())
            print("✅ Verification email sent successfully")
            return True
        except Exception as e:
            print(f"❌ Error sending email (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time_module.sleep(1 * attempt)  # backoff
            else:
                return False

# -----------------------------------------------------------------
# GENERATE 6-DIGIT CODE
# -----------------------------------------------------------------
def generate_code():
    return str(random.randint(100000, 999999))

# -----------------------------------------------------------------
# SAVE VERIFICATION CODE TO DATABASE (MySQL version)
# -----------------------------------------------------------------
def save_verification_code(email, code):
    conn = get_db_connection()
    if conn is None:
        print("❌ Database connection failed.")
        return

    try:
        cursor = conn.cursor()
        query = """
            UPDATE admins
            SET verification_code = %s
            WHERE email = %s
        """
        cursor.execute(query, (code, email))
        conn.commit()
        print("✅ Verification code saved successfully.")
    except Error as e:
        print(f"❌ Error saving verification code: {e}")
    finally:
        cursor.close()
        conn.close()
#-----------------------------------------------------
# ROUTE: LOGOUT
#----------------------------------------------------
@app.route('/logout')
def logout():
    for k in ['loggedin', 'admins_id', 'email', 'first_name', 'last_name', 'pending_email', 'user_id']:
        session.pop(k, None)
    session.clear()  # ensures everything is wiped
    return redirect(url_for('login_page'))

# -------------------------------------------------
# ROUTE: Create Account
# -------------------------------------------------
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
            return render_template('CreateAccount.html', fname=fname, lname=lname, email=email)
        
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

        conn = get_db_connection()
        if conn is None:
            flash('Database connection failed.', 'danger')
            return render_template('CreateAccount.html')

        cursor = conn.cursor()

        try:
            cursor.execute('SELECT admin_id FROM admins WHERE email = %s', (email,))
            if cursor.fetchone():
                flash('Account already exists. Please log in.', 'warning')
                conn.close()
                return redirect(url_for('login_page'))

            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            code = str(os.urandom(3).hex()).upper()
            ph_time = timezone(timedelta(hours=8))
            now = datetime.now(ph_time).strftime("%Y-%m-%d %H:%M:%S")

            try:
                cursor.execute("SELECT pending_id FROM pending_admins WHERE email = %s", (email,))
                pending_row = cursor.fetchone()
                if pending_row:
                    cursor.execute(
                        "UPDATE pending_admins SET password=%s, verification_code=%s, created_at=%s WHERE email=%s",
                        (hashed, code, now, email)
                    )
                else:
                    cursor.execute("""
                        INSERT INTO pending_admins (first_name, last_name, email, password, verification_code, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (fname, lname, email, hashed, code, now))
                conn.commit()
            except Error as e:
                # Table missing => attempt to initialize DB and retry once
                if getattr(e, 'errno', None) == 1146 or ('Table' in str(e) and "doesn't exist" in str(e)):
                    print('⚠️ Table missing during account creation, attempting to initialize DB...')
                    try:
                        init_db()
                        cursor.execute("""
                            INSERT INTO pending_admins (first_name, last_name, email, password, verification_code, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (fname, lname, email, hashed, code, now))
                        conn.commit()
                    except Exception as e2:
                        conn.rollback()
                        raise
                else:
                    conn.rollback()
                    raise

            # ✅ Send email
            send_verification_email(email, code)

            session['pending_email'] = email
            flash('Verification code has been sent to your email.', 'success')
            return redirect(url_for('verification', email=email))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Create account error: {e}")
            flash('An error occurred while creating the account.', 'danger')
            return render_template('CreateAccount.html')
        finally:
            cursor.close()
            conn.close()

    return render_template('CreateAccount.html')

# -------------------------------------------------
# ROUTE: Verification Page
# -------------------------------------------------
@app.route("/verification/<email>", methods=["GET", "POST"])
def verification(email):
    if request.method == "POST":
        code = request.form.get("verification_code", "").strip()

        conn = get_db_connection()
        if conn is None:
            flash('Database connection failed.', 'danger')
            return redirect(url_for('create_account'))
        cursor = conn.cursor()

        # Check pending_admins for matching email + code
        try:
            cursor.execute("""
                SELECT pending_id, first_name, last_name, email, password, verification_code, created_at
                FROM pending_admins
                WHERE email = %s AND verification_code = %s
            """, (email, code))
        except Error as e:
            if getattr(e, 'errno', None) == 1146 or ('Table' in str(e) and "doesn't exist" in str(e)):
                print('⚠️ pending_admins table missing, attempting to initialize schema...')
                init_db()
                # Try again
                cursor.execute("""
                    SELECT pending_id, first_name, last_name, email, password, verification_code, created_at
                    FROM pending_admins
                    WHERE email = %s AND verification_code = %s
                """, (email, code))
            else:
                raise
        pending = cursor.fetchone()

        if pending:
            try:
                # Move verified user to admins table
                cursor.execute("""
                    INSERT INTO admins (first_name, last_name, email, password, is_verified, created_at)
                    VALUES (%s, %s, %s, %s, 1, %s)
                """, (pending[1], pending[2], pending[3], pending[4], pending[6]))

                # Remove from pending_admins
                cursor.execute("DELETE FROM pending_admins WHERE email = %s", (email,))
                conn.commit()

                flash("✅ Verification successful! You can now log in.", "success")
                return redirect(url_for("login_page"))

            except Exception as e:
                conn.rollback()
                print(f"❌ Error moving verified admins: {e}")
                flash("Error finalizing verification. Please try again.", "error")
                return redirect(url_for("verification", email=email))

            finally:
                cursor.close()
                conn.close()

        else:
            conn.close()
            flash("❌ Invalid or expired verification code.", "error")
            return redirect(url_for("verification", email=email))

    return render_template("Verification.html", email=email)

# -------------------------------------------------
# ROUTE: Resend Verification Code
# -------------------------------------------------
@app.route('/resend-code', methods=['POST'])
def resend_code():
    conn = get_db_connection()
    if conn is None:
        flash('Database connection failed.', 'danger')
        return redirect(url_for('create_account'))

    cursor = conn.cursor()
    email = request.form.get('email') or session.get('pending_email') or session.get('email')
    if not email:
        flash('No email specified for resending code.', 'warning')
        return redirect(url_for('create_account'))

    code = str(os.urandom(3).hex()).upper()

    try:
        cursor.execute('UPDATE admins SET verification_code = %s WHERE email = %s', (code, email))
        conn.commit()

        # ✅ Send updated code
        send_verification_email(email, code)
        flash('Verification code resent successfully.', 'success')

    except Exception as e:
        conn.rollback()
        print(f"❌ Resend code error: {e}")
        flash('Failed to resend verification code.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('verification', email=email))
# -----------------------------------------------------------------
# DASHBOARD ROUTE (MySQL Version)
# -----------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ====== STATS ======
    cursor.execute("SELECT COUNT(*) AS total FROM borrowers")
    users = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM transactions")
    borrowed_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(returned_qty) AS total FROM transactions")
    total_returned = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM inventory")
    total_items = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM transactions WHERE return_date IS NOT NULL")
    returned = cursor.fetchone()["total"]

    # ====== PENDING RETURNS COUNT ======
    cursor.execute("SELECT COUNT(*) AS total FROM pending_returns WHERE status = 'pending'")
    pending_returns_count = cursor.fetchone()["total"]

    # ====== NEW: PENDING RETURNS DATA ======
    cursor.execute("""
        SELECT 
            r.id AS pending_id,
            r.borrow_id,
            r.user_id,
            r.return_data,
            r.created_at,
            CONCAT(b.first_name, ' ', b.last_name) AS borrower_name,
            b.department,
            b.course,
            t.borrow_date,
            t.borrow_time
        FROM pending_returns r
        JOIN borrowers b ON r.user_id = b.user_id
        JOIN transactions t ON r.borrow_id = t.borrow_id
        WHERE r.status = 'pending'
        ORDER BY r.created_at DESC
    """)
    pending_returns = cursor.fetchall()

    # ✅ Decode return_data JSON and format Return ID
    for pr in pending_returns:
        try:
            pr["return_data"] = json.loads(pr["return_data"])
        except:
            pr["return_data"] = []
        pr["formatted_id"] = f"{pr['pending_id']:07d}"  # Same format as ReturnSuccess.html

    # ====== TRANSACTION HISTORY ======
    cursor.execute("""
        SELECT 
            b.borrow_date, 
            b.borrow_time, 
            i.item_name, 
            CONCAT(s.first_name, ' ', s.last_name) AS borrower, 
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
        borrow_date = row['borrow_date']
        borrow_time = row['borrow_time']
        item_name = row['item_name']
        borrower = row['borrower']
        quantity = int(row['borrowed_qty']) if row['borrowed_qty'] else 0
        returned_qty = int(row['returned_qty']) if row['returned_qty'] else 0
        status = row['status']

        history.setdefault(borrow_date, []).append({
            "time": borrow_time,
            "tool": item_name,
            "user": borrower,
            "quantity": quantity,
            "returned_qty": returned_qty,
            "status": status
        })
        total_returned_qty += returned_qty
        status_counts[status] = status_counts.get(status, 0) + 1

    stats = {
        "users": users,
        "borrowed": borrowed_count,
        "total_trans": borrowed_count,
        "total_returned": total_returned,
        "status_counts": status_counts,
        "pending_returns": pending_returns_count
    }

    # ====== WEEKLY CHART (Mon–Sun) ======
    conn2 = get_db_connection()
    cursor2 = conn2.cursor()
    weekly_chart = []
    today_dt = datetime.now()
    monday = (today_dt - timedelta(days=today_dt.weekday())).date()

    for i in range(7):
        day = monday + timedelta(days=i)
        cursor2.execute("""
            SELECT SUM(borrowed_qty) 
            FROM transactions 
            WHERE DATE(borrow_date) = %s
        """, (day.strftime('%Y-%m-%d'),))
        weekly_chart.append(cursor2.fetchone()[0] or 0)
    conn2.close()

    # ====== MONTHLY CHART ======
    conn3 = get_db_connection()
    cursor3 = conn3.cursor()
    today = datetime.now().date()
    year, month = today.year, today.month
    first_day = datetime(year, month, 1).date()
    if month == 12:
        next_month_first = datetime(year + 1, 1, 1).date()
    else:
        next_month_first = datetime(year, month + 1, 1).date()
    last_day = next_month_first - timedelta(days=1)
    num_weeks = ((last_day.day - 1) // 7) + 1

    monthly_chart = []
    monthly_labels = []

    for week in range(1, num_weeks + 1):
        week_start = first_day + timedelta(days=(week - 1) * 7)
        week_end = week_start + timedelta(days=6)
        if week_end > last_day:
            week_end = last_day

        cursor3.execute("""
            SELECT SUM(borrowed_qty)
            FROM transactions
            WHERE DATE(borrow_date) BETWEEN %s AND %s
        """, (week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
        weekly_total = cursor3.fetchone()[0] or 0
        monthly_chart.append(weekly_total)

        start_label = week_start.strftime("%b %d").lstrip("0").replace(" 0", " ")
        end_label = week_end.strftime("%d").lstrip("0").replace(" 0", " ")
        monthly_labels.append(f"Week {week} ({start_label}–{end_label})")

    conn3.close()

    # ====== YEARLY CHART (Jan–Dec) ======
    conn4 = get_db_connection()
    cursor4 = conn4.cursor()
    yearly_chart = []
    yearly_labels = []

    for m in range(1, 13):
        cursor4.execute("""
            SELECT SUM(borrowed_qty)
            FROM transactions
            WHERE YEAR(borrow_date) = %s AND MONTH(borrow_date) = %s
        """, (str(year), str(m)))
        yearly_chart.append(cursor4.fetchone()[0] or 0)
        yearly_labels.append(calendar.month_abbr[m])
    conn4.close()

    # ====== RENDER DASHBOARD ======
    return render_template(
        "Dashboard.html",
        stats=stats,
        history=history,
        pending_returns=pending_returns,
        weekly_chart=weekly_chart,
        weekly_labels=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        monthly_chart=monthly_chart,
        monthly_labels=monthly_labels,
        yearly_chart=yearly_chart,
        yearly_labels=yearly_labels
    )
# -----------------------------------------------------------------
# ROUTE 1: BORROW PAGE
# -----------------------------------------------------------------
@app.route("/borrow")
def borrow_page():
    if 'admins_id' not in session:
        flash("Session expired. Please log in again.")
        return redirect('/login')

    admins_id = session['admins_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch admins info
        cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = %s", (admins_id,))
        admins = cursor.fetchone()
        if not admins:
            flash("admins not found.")
            return redirect('/login')

        # Fetch inventory data
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
                type,
                image_path
            FROM inventory
            ORDER BY item_name ASC
        """)
        items = cursor.fetchall()

        for item in items:
            img_path = item.get("image_path")

            if not img_path:
                item["image_path"] = "Icons/tool_default.jpg"
            else:
                img_path = img_path.replace("\\", "/")
                if img_path.startswith("static/"):
                    img_path = img_path[len("static/"):]
                
                full_path = os.path.join(app.root_path, "static", img_path)
                if not os.path.exists(full_path):
                    img_path = f"Icons/{os.path.basename(img_path)}"

                item["image_path"] = img_path

        # ✅ Get distinct item types
        cursor.execute("""
            SELECT DISTINCT type 
            FROM inventory 
            WHERE type IS NOT NULL AND type != '' 
            ORDER BY type ASC
        """)
        types = [row["type"] for row in cursor.fetchall()]

        conn.close()

        # ✅ Prepare equipment data
        equipment = [
            {
                "id": item["item_id"],
                "name": item["item_name"],
                "all_quantity": item["quantity"],
                "on_borrowed": item["borrowed"],
                "available": item["available"],
                "type": item["type"],
                "image_path": item["image_path"]
            }
            for item in items
        ]
        return render_template(
            "Borrow.html",
            equipment=equipment,
            types=types,
            admins_name=f"{admins['first_name']} {admins['last_name']}"
        )

    except Exception as e:
        print(f"❌ Error during borrow_page: {e}")
        flash("An error occurred while loading the borrow page.")
        return redirect('/dashboard')

# -----------------------------------------------------------------
# ROUTE 2: RFID Scanner Route (MySQL version)
# -----------------------------------------------------------------
@app.route('/rfid_scanner', methods=['POST'])
@login_required
def rfid_scanner():
    try:
        # Retrieve form data arrays from Borrow.html
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        condition_list = request.form.getlist("before_condition[]")
        instructor_rfid = request.form.get("instructor_rfid")
        subject = request.form.get("subject")
        room = request.form.get("room")

        if not equipment_list:
            flash("⚠️ No equipment data received.", "error")
            return redirect(url_for("borrow_page"))

        # Pass arrays to RFID Scanner page
        return render_template(
            "RfidScanner.html",
            action_url=url_for("borrow_confirm"),
            equipment_list=equipment_list,
            quantity_list=quantity_list,
            condition_list=condition_list,
            instructor_rfid=instructor_rfid,
            subject=subject,
            room=room,
            zip=zip
        )

    except Exception as e:
        print("Error in /rfid_scanner:", e)
        flash("An error occurred while preparing RFID scanning.", "error")
        return redirect(url_for("borrow_page"))

# -----------------------------------------------------------------
# ROUTE 3: BORROW CONFIRM
# -----------------------------------------------------------------
@app.route("/borrow_confirm", methods=["POST"])
@login_required
def borrow_confirm():
    try:
        if "admins_id" not in session:
            flash("Session expired. Please log in again.")
            return redirect("/login")

        admins_id = session["admins_id"]

        # ✅ Form data
        rfid = request.form.get("rfid")
        subject = request.form.get("subject", "").strip()
        room = request.form.get("room", "").strip()
        instructor_rfid = request.form.get("instructor_rfid")
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        condition_list = request.form.getlist("before_condition[]")

        if not rfid or not equipment_list:
            flash("Missing RFID or equipment data.")
            return redirect("/borrow")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ✅ Lookup borrower
        cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
        borrower = cursor.fetchone()
        if not borrower:
            flash("No borrower found for this RFID.")
            conn.close()
            return redirect("/borrow")

        # ✅ Lookup instructor
        cursor.execute("SELECT user_id, first_name, last_name FROM borrowers WHERE rfid = %s", (instructor_rfid,))
        instructor = cursor.fetchone()
        if not instructor:
            flash("Instructor not found.")
            conn.close()
            return redirect("/borrow")

        instructor_id = instructor["user_id"]

        # ✅ Current date/time
        now = datetime.now(ZoneInfo("Asia/Manila"))
        borrow_date = now.date()   # Python date object
        borrow_time = now.time()   # Python time object

        borrow_ids = []  # track all transaction rows

        # ✅ Loop through all equipment entries
        for eq, qty, cond in zip(equipment_list, quantity_list, condition_list):
            cursor.execute("SELECT item_id, quantity, borrowed FROM inventory WHERE item_name = %s", (eq,))
            item = cursor.fetchone()
            if not item:
                print(f"⚠️ Item not found: {eq}")
                continue

            available = item["quantity"] - item["borrowed"]
            if int(qty) > available:
                print(f"⚠️ Not enough stock for {eq}. Available: {available}, Requested: {qty}")
                continue

            # ✅ Insert transaction with proper date/time objects
            cursor.execute("""
                    INSERT INTO transactions (
                        user_id, admin_id, instructor_id, instructor_rfid,
                    subject, room, rfid, item_id, borrowed_qty,
                    borrow_date, borrow_time, before_condition
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                borrower["user_id"], admins_id, instructor_id, instructor_rfid,
                subject, room, rfid, item["item_id"], int(qty),
                borrow_date, borrow_time, cond
            ))

            borrow_ids.append(cursor.lastrowid)

            # ✅ Update inventory count
            cursor.execute("UPDATE inventory SET borrowed = borrowed + %s WHERE item_id = %s",
                           (int(qty), item["item_id"]))

        conn.commit()

        # ✅ Fetch admins details
        cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = %s", (admins_id,))
        admins = cursor.fetchone()

        # ✅ Prepare summary for PDF/email slip
        transaction = {
            "transaction_number": f"{borrow_ids[0]:07d}" if borrow_ids else "N/A",
            "name": f"{borrower['first_name']} {borrower['last_name']}",
            "user_id": borrower["borrower_id"],
            "department": borrower["department"],
            "course": borrower["course"],
            "instructor_name": f"{instructor['first_name']} {instructor['last_name']}",
            "subject": subject,
            "room": room,
            "date": borrow_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
            "time": borrow_time.strftime("%I:%M %p").lstrip("0"),
            "admins_name": f"{admins['first_name']} {admins['last_name']}",
            "items": [
                {"equipment": eq, "quantity": qty, "condition": cond}
                for eq, qty, cond in zip(equipment_list, quantity_list, condition_list)
            ]
        }

        # ✅ Generate PDF slip
        pdf_path = generate_borrow_slip(transaction)

        # ✅ Send via email (optional)
        if borrower.get("umak_email"):
            send_transaction_email(borrower["umak_email"], pdf_path, transaction)

        flash("✅ Borrow confirmed! Borrow slip generated and sent via email.")
        return redirect(url_for("view_transaction", borrow_id=borrow_ids[0] if borrow_ids else 0))

    except Exception as e:
        print("❌ Error during borrow_confirm:", e)
        flash("An error occurred during borrowing confirmation.")
        return redirect("/borrow")

    finally:
        cursor.close()
        conn.close()

#------------------------------------------------------------------------------  
# ROUTE 4: COMPLETED TRANSACTION  
#------------------------------------------------------------------------------  
@app.route('/transaction_success/<int:borrow_id>')  
@login_required  
def view_transaction(borrow_id):  
    conn = get_db_connection()  
    cursor = conn.cursor(dictionary=True)  

    try:  
        cursor.execute("""
        SELECT
            t.borrow_id,
            t.borrow_date,
            t.borrow_time,
            t.subject,
            t.room,
            b.first_name,
            b.last_name,
            b.department,
            b.course,
            b.image,
            b.borrower_id AS user_id,
            i2.first_name AS instructor_first,
            i2.last_name AS instructor_last,
            inv.item_name AS equipment,
            t.borrowed_qty AS quantity,
            t.before_condition AS `condition`
        FROM transactions t
        JOIN borrowers b ON t.user_id = b.user_id
        JOIN borrowers i2 ON t.instructor_id = i2.user_id
        JOIN inventory inv ON t.item_id = inv.item_id
        WHERE t.user_id = (
            SELECT user_id FROM transactions WHERE borrow_id = %s
        )
        AND t.borrow_date = (
            SELECT borrow_date FROM transactions WHERE borrow_id = %s
        )
        AND t.borrow_time = (
            SELECT borrow_time FROM transactions WHERE borrow_id = %s
        )
        ORDER BY t.borrow_id
    """, (borrow_id, borrow_id, borrow_id))  
        rows = cursor.fetchall()

        if not rows:  
            flash("❌ Borrow transaction not found.", "error")  
            return redirect(url_for("kiosk_page"))  

        main = rows[0]  

        # Format borrow_id with 7-digit zero padding  
        transaction_number = f"{main['borrow_id']:07d}"  

        # Safely format date  
        display_date = ""  
        if main["borrow_date"]:  
            if isinstance(main["borrow_date"], (datetime, date)):  
                display_date = main["borrow_date"].strftime("%m/%d/%Y").lstrip("0").replace("/0", "/")  
            else:  
                display_date = str(main["borrow_date"])  

        # Safely format time  
        display_time = ""  
        if main["borrow_time"]:  
            if isinstance(main["borrow_time"], (datetime, time)):  
                display_time = main["borrow_time"].strftime("%I:%M %p").lstrip("0")  
            else:  
                display_time = str(main["borrow_time"])  

        # Build transaction dictionary  
        transaction = {  
            "transaction_number": transaction_number,  
            "date": display_date,  
            "time": display_time,  
            "name": f"{main['first_name']} {main['last_name']}",  
            "user_id": main["user_id"],  
            "department": main["department"],  
            "course": main["course"],  
            "instructor_name": f"{main['instructor_first']} {main['instructor_last']}",  
            "subject": main["subject"],  
            "room": main["room"],  
            "image": main["image"],  
            "items": []  
        }  

        for r in rows:  
            transaction["items"].append({  
                "equipment": r["equipment"],  
                "quantity": r["quantity"],  
                "condition": r["condition"]  
            })  

        return render_template("transaction_success.html", transaction=transaction)    

    except Exception as e:  
        print("Error loading transaction:", e)  
        flash("⚠️ Failed to load transaction details.", "error")  
        return redirect(url_for("dashboard"))  

    finally:  
        cursor.close()  
        conn.close()  

# Borrower's Image
@app.route('/register_borrower', methods=['POST'])
def register_borrower():
    try:
        rfid = request.form['rfid']
        borrower_id = request.form['borrower_id']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        department = request.form['department']
        course = request.form['course']
        email = request.form['umak_email']

        image_file = request.files.get('image')

        image_path = None
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            image_save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(image_save_path)

            # ✅ Store relative path for Flask
            image_path = f"uploads/{filename}"

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO borrowers (rfid, borrower_id, first_name, last_name, department, course, image, umak_email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (rfid, borrower_id, first_name, last_name, department, course, image_path, email))

        conn.commit()
        flash("✅ Borrower registered successfully!", "success")

    except Exception as e:
        print("Error registering borrower:", e)
        flash("⚠️ Failed to register borrower.", "error")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('borrow_page'))


@app.route("/hello")
def hello():
    return "Hello, your Flask app is working!"

# -----------------------------------------------------------------
# FUNCTION: Generate Borrow Slip PDF
# -----------------------------------------------------------------
def generate_borrow_slip(transaction):
    folder = "generated_slips"
    os.makedirs(folder, exist_ok=True)

    filename = f"borrow_slip_{transaction['transaction_number']}.pdf"
    file_path = os.path.join(folder, filename)

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # --- Header ---
    elements.append(Paragraph("<b>UNIVERSITY OF MAKATI</b>", styles["Title"]))
    elements.append(Paragraph("Laboratory Equipment Borrow Slip", styles["Heading2"]))
    elements.append(Spacer(1, 18))

    # --- Borrower & Transaction Info ---
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
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 18))

    # --- Borrowed Items ---
    elements.append(Paragraph("<b>Borrowed Items</b>", styles["Heading3"]))
    item_data = [["Item Name", "Quantity", "Condition Before Borrowing"]]
    for item in transaction["items"]:
        item_data.append([
            item["equipment"],
            str(item["quantity"]),
            item["condition"]
        ])

    item_table = Table(item_data, colWidths=[220, 70, 200])
    item_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 30))

    # --- Footer ---
    elements.append(Paragraph("<b>Approved by:</b>", styles["Normal"]))
    elements.append(Paragraph(transaction.get("admins_name", "____________________"), styles["Normal"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<i>Please return borrowed items in good condition and on time.</i>", styles["Italic"]))

    doc.build(elements)
    return file_path

# -----------------------------------------------------------------
# FUNCTION: SEND TRANSACTION EMAIL
# -----------------------------------------------------------------
def send_transaction_email(recipient, file_path, transaction):
    """Send an email with the borrow slip PDF attached."""
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")

    if not sender_email or not sender_password:
        print("❌ Missing EMAIL_USER or EMAIL_PASS in .env")
        return

    subject = f"Borrow Slip - {transaction['transaction_number']}"
    body = f"""
Dear {transaction['name']},

Attached is your borrow slip for your recent laboratory borrowing transaction.

Borrow ID: {transaction['transaction_number']}
Date: {transaction['date']}
Subject: {transaction['subject']}
Room: {transaction['room']}

Thank you,
University of Makati - LEBS
"""

    try:
        msg = EmailMessage()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        # Attach the PDF
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="application",
                    subtype="pdf",
                    filename=os.path.basename(file_path)
                )
        else:
            print(f"⚠️ PDF file not found: {file_path}")

        print("📧 Sending borrow slip to:", recipient)
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        print("✅ Borrow slip email sent successfully")

    except Exception as e:
        print("❌ Error sending borrow slip email:", e)

# ----------------------------------------------------------------- 
# ROUTE 1: RFID SCANNER RETURN
# -----------------------------------------------------------------
@app.route("/rfid_scanner_return", methods=["GET", "POST"])
@login_required
def rfid_scanner_return():
    if request.method == "GET":
        return render_template("RfidScannerReturn.html")

    rfid = request.form.get("rfid")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 Get borrower info
    cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
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
        WHERE t.rfid = %s
          AND IFNULL(t.returned_qty, 0) < t.borrowed_qty
        ORDER BY t.borrow_id ASC
    """, (rfid,))
    items = cursor.fetchall()

    conn.close()

    if not items:
        flash("✅ All items for this borrower have already been returned.")
        return redirect(url_for("rfid_scanner_return"))

    borrower_info = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower.get("image"),
        "date": items[0]['borrow_date'],
        "time": items[0]['borrow_time']
    }

    return render_template("ReturnForm.html", borrower=borrower_info, items=items)

# -----------------------------------------------------------------
# ROUTE 2: RETURN CONFIRM ROUTE
# -----------------------------------------------------------------
@app.route("/return_confirm", methods=["POST"])
@login_required
def return_confirm():
    rfid = request.form.get("rfid")

    if not rfid:
        flash("❌ No RFID received. Please try again.")
        return redirect(url_for("rfid_scanner_return"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Verify borrower
    cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
    borrower = cursor.fetchone()
    if not borrower:
        flash("⚠️ RFID not found in the system.")
        conn.close()
        return redirect(url_for("rfid_scanner_return"))

    # Fetch unreturned items
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
        WHERE t.rfid = %s 
        AND (t.returned_qty < t.borrowed_qty OR t.returned_qty IS NULL)
    """, (rfid,))
    items = cursor.fetchall()
    conn.close()

    if not items:
        flash("✅ All items for this borrower are already returned.")
        return redirect(url_for("rfid_scanner_return"))

    # Prepare borrower data with image
    borrower_data = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower["image"] if borrower.get("image") else None,
        "date": items[0]["borrow_date"],
        "time": items[0]["borrow_time"]
    }

    # Prepare items data with remaining quantity to return
    items_data = [
        {
            "borrow_id": f"{item['borrow_id']:07d}",
            "item_name": item["item_name"],
            "quantity_borrowed": item["borrowed_qty"],
            "quantity_returned": item["returned_qty"],
            "condition_borrowed": item["before_condition"],
            "quantity_remaining": item["borrowed_qty"] - item["returned_qty"]
        }
        for item in items
    ]

    return render_template("ReturnForm.html", borrower=borrower_data, items=items_data)

# -----------------------------------------------------------------
# ROUTE 3: PROCESS RETURN
# -----------------------------------------------------------------
@app.route("/process_return", methods=["POST"])
@login_required
def process_return():
    try:
        rfid = request.form.get("rfid")
        transaction_no = request.form.get("transaction_no")
        item_names = request.form.getlist("item_name[]")
        returned_now = request.form.getlist("quantity_returned[]")
        condition_returned = request.form.getlist("condition_returned[]")

        # Get admins info from session
        admins_id = session.get("admins_id")
        if not admins_id:
            session["admins_name"] = "admins unknown"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch borrower info
        cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
        borrower = cursor.fetchone()
        if not borrower:
            flash("⚠️ Borrower not found.")
            return redirect(url_for("rfid_scanner_return"))

        now = datetime.now(ZoneInfo("Asia/Manila"))
        return_date = now.date()
        return_time = now.time()

        returned_items = []
        returned_borrow_ids = []

        # Loop through items to process return
        for i in range(len(item_names)):
            item_name = item_names[i]
            qty_now = returned_now[i] if i < len(returned_now) else "0"
            cond_returned = condition_returned[i] if i < len(condition_returned) else ""

            if not qty_now.strip() or not cond_returned.strip():
                continue

            try:
                qty_now = int(qty_now)
                if qty_now <= 0:
                    continue
            except ValueError:
                continue

            # Get all pending transactions for this item
            cursor.execute("""
                SELECT t.borrow_id, t.item_id, t.returned_qty, t.borrowed_qty
                FROM transactions t
                JOIN inventory i ON t.item_id = i.item_id
                WHERE t.rfid = %s AND i.item_name = %s AND t.returned_qty < t.borrowed_qty
                ORDER BY t.borrow_id ASC
            """, (rfid, item_name))
            transactions = cursor.fetchall()
            if not transactions:
                continue

            remaining_qty = qty_now
            for transaction in transactions:
                still_to_return = transaction["borrowed_qty"] - transaction["returned_qty"]
                to_return = min(remaining_qty, still_to_return)
                new_returned_qty = transaction["returned_qty"] + to_return

                # Update transaction
                cursor.execute("""
                    UPDATE transactions
                    SET returned_qty = %s,
                        after_condition = %s,
                        return_date = %s,
                        return_time = %s
                    WHERE borrow_id = %s
                """, (new_returned_qty, cond_returned, return_date, return_time, transaction["borrow_id"]))

                returned_borrow_ids.append(str(transaction["borrow_id"]))
                returned_items.append({
                    "item_name": item_name,
                    "quantity": to_return,
                    "condition": cond_returned
                })

                remaining_qty -= to_return
                if remaining_qty <= 0:
                    break

            # Update inventory status
            cursor.execute("""
                UPDATE inventory i
                JOIN (
                    SELECT item_id, GREATEST(SUM(borrowed_qty - returned_qty), 0) AS still_borrowed
                    FROM transactions
                    WHERE item_id = %s
                    GROUP BY item_id
                ) t ON i.item_id = t.item_id
                SET i.borrowed = t.still_borrowed,
                    i.status = CASE 
                        WHEN t.still_borrowed < i.quantity THEN 'Available'
                        ELSE 'Unavailable'
                    END
            """, (transactions[0]["item_id"],))

        if not returned_items:
            flash("⚠️ No items were returned. Please input at least one valid quantity.")
            return redirect(url_for("rfid_scanner_return"))

        conn.commit()

        # Fetch admins details if available
        if admins_id:
            cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = %s", (admins_id,))
            admins = cursor.fetchone()
            admins_name = f"{admins['first_name']} {admins['last_name']}" if admins else "admins unknown"
        else:
            admins_name = "admins unknown"

        # After all items have been processed
        borrow_ids_str = ",".join(returned_borrow_ids)

        # Use first borrow_id of returned items as Return ID
        return_id = f"{int(returned_borrow_ids[0]):07d}" if returned_borrow_ids else "N/A"

        # Prepare transaction summary for PDF/email
        transaction_summary = {
            "transaction_number": return_id,
            "name": f"{borrower['first_name']} {borrower['last_name']}",
            "borrower_id": borrower["borrower_id"],
            "rfid": rfid,
            "department": borrower["department"],
            "course": borrower["course"],
            "image": borrower.get("image") or None,
            "date": return_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
            "time": return_time.strftime("%I:%M %p").lstrip("0"),
            "items": returned_items,
            "admins_name": admins_name
        }

        # Generate PDF and send email
        pdf_path = generate_return_slip(transaction_summary)
        if borrower.get("umak_email"):
            send_return_email(borrower["umak_email"], pdf_path, transaction_summary)

        flash("✅ Return recorded successfully. Partial returns saved if applicable.")

        # Redirect to success page
        borrow_ids_str = ",".join(returned_borrow_ids)
        qty_str = ",".join([str(item["quantity"]) for item in returned_items])
        return redirect(url_for('return_success') + f"?borrow_ids={borrow_ids_str}&qty={qty_str}")

    except Exception as e:
        print("❌ Error processing return:", e)
        flash("An error occurred while processing the return.")
        return redirect(url_for("rfid_scanner_return"))

    finally:
        cursor.close()
        conn.close()

# -----------------------------------------------------------------
# ROUTE 4: RETURN SUCCESS PAGE
# -----------------------------------------------------------------
@app.route("/return_success")
@login_required
def return_success():
    borrow_ids_str = request.args.get("borrow_ids")
    qty_str = request.args.get("qty")

    if not borrow_ids_str or not qty_str:
        flash("⚠️ No transaction data provided.")
        return redirect(url_for("dashboard"))

    borrow_ids = borrow_ids_str.split(",")
    qty_list = [int(q) for q in qty_str.split(",") if q.isdigit()]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get borrower info
        cursor.execute("""
            SELECT b.first_name, b.last_name, b.department, b.course, b.borrower_id, b.image
            FROM transactions t
            JOIN borrowers b ON t.rfid = b.rfid
            WHERE t.borrow_id = %s
            LIMIT 1
        """, (borrow_ids[0],))
        borrower = cursor.fetchone()
        if not borrower:
            flash("⚠️ Borrower not found.")
            return redirect(url_for("dashboard"))

        # ✅ Fetch ALL items for the given borrow_ids
        format_strings = ",".join(["%s"] * len(borrow_ids))
        cursor.execute(f"""
            SELECT i.item_name, t.after_condition AS `condition`, t.returned_qty
            FROM transactions t
            JOIN inventory i ON t.item_id = i.item_id
            WHERE t.borrow_id IN ({format_strings})
        """, tuple(borrow_ids))
        items_db = cursor.fetchall()

        # ✅ Always show all items, even if mismatch in qty length
        items = []
        for i, item in enumerate(items_db):
            qty = qty_list[i] if i < len(qty_list) else item.get("returned_qty", 1)
            items.append({
                "item_name": item["item_name"],
                "quantity": qty,
                "condition": item["condition"] or "Good Condition"
            })

        # Get return date/time
        cursor.execute("""
            SELECT return_date, return_time
            FROM transactions
            WHERE borrow_id = %s
            LIMIT 1
        """, (borrow_ids[0],))
        dt = cursor.fetchone()
        return_date = dt.get("return_date") if dt else None
        return_time = dt.get("return_time") if dt else None

        transaction = {
            "transaction_number": f"{int(borrow_ids[0]):07d}",
            "date": (
                return_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/")
                if isinstance(return_date, (datetime, date))
                else str(return_date or "")
            ),
            "time": (
                return_time.strftime("%I:%M %p").lstrip("0")
                if isinstance(return_time, (datetime, time))
                else str(return_time or "")
            ),
            "name": f"{borrower['first_name']} {borrower['last_name']}",
            "borrower_id": borrower["borrower_id"],
            "department": borrower["department"],
            "course": borrower["course"],
            "image": borrower.get("image"),
            "items": items
        }

        return render_template("SuccessReturn.html", transaction=transaction)

    except Exception as e:
        print("❌ Error loading return success page:", e)
        flash("An error occurred while loading the return summary.")
        return redirect(url_for("dashboard"))

    finally:
        cursor.close()
        conn.close()

# -----------------------------------------------------------------
# FUNCTION: GENERATE RETURN SLIP
# -----------------------------------------------------------------
def generate_return_slip(transaction):
    folder = "generated_slips"
    os.makedirs(folder, exist_ok=True)

    filename = f"return_slip_{transaction['transaction_number']}.pdf"
    file_path = os.path.join(folder, filename)

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # --- Header ---
    elements.append(Paragraph("<b>UNIVERSITY OF MAKATI</b>", styles["Title"]))
    elements.append(Paragraph("Laboratory Equipment Return Slip", styles["Heading2"]))
    elements.append(Spacer(1, 18))

    # --- Borrower & Transaction Info ---
    info_data = [
        ["Return ID:", transaction["transaction_number"]],
        ["Name:", transaction["name"]],
        ["Borrower ID:", transaction["borrower_id"]],
        ["Department:", transaction["department"]],
        ["Course:", transaction["course"]],
        ["Processed By (admins):", transaction.get("admins_name", "____________________")],
        ["Date:", transaction["date"]],
        ["Time:", transaction["time"]],
    ]

    info_table = Table(info_data, colWidths=[150, 270])
    info_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 18))

    # --- Returned Items ---
    elements.append(Paragraph("<b>Returned Items</b>", styles["Heading3"]))
    item_data = [["Item Name", "Quantity", "Condition After Return"]]
    for item in transaction["items"]:
        item_data.append([
            item["item_name"],
            str(item["quantity"]),
            item["condition"]
        ])

    item_table = Table(item_data, colWidths=[220, 70, 200])
    item_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 30))

    # --- Footer ---
    elements.append(Paragraph("<b>Approved by:</b>", styles["Normal"]))
    elements.append(Paragraph(transaction.get("admins_name", "____________________"), styles["Normal"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<i>Please ensure returned items are in good condition. Thank you.</i>", styles["Italic"]))

    doc.build(elements)
    return file_path

# -----------------------------------------------------------------
# FUNCTION: SEND RETURN EMAIL
# -----------------------------------------------------------------
def send_return_email(recipient, file_path, transaction):
    """Send an email with the return slip PDF attached."""
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")

    if not sender_email or not sender_password:
        print("❌ Missing EMAIL_USER or EMAIL_PASS in .env")
        return

    subject = f"Return Slip - {transaction['transaction_number']}"
    body = f"""
Dear {transaction['name']},

Attached is your return slip for your recent laboratory equipment return transaction.

Return ID: {transaction['transaction_number']}
Date: {transaction['date']}

Thank you,
University of Makati - LEBS
"""

    try:
        msg = EmailMessage()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        # Attach the PDF
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="application",
                    subtype="pdf",
                    filename=os.path.basename(file_path)
                )
        else:
            print(f"⚠️ PDF file not found: {file_path}")

        print("📧 Sending return slip to:", recipient)
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        print("✅ Return slip email sent successfully")

    except Exception as e:
        print("❌ Error sending return slip email:", e)

# -------------------------------
# ROUTE: INVENTORY PAGE (MySQL Version)
# -------------------------------
@app.route("/inventory")
@login_required
def inventory_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    cursor.execute(
        "SELECT item_id, item_name, type, quantity, borrowed, status, image_path FROM inventory"
    )
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    for item in items:
        img_path = item.get("image_path")

        # If no image path, use default
        if not img_path:
            img_path = "Icons/tool_default.jpg"
        else:
            # Normalize slashes
            img_path = img_path.replace("\\", "/")
            # Construct full path in the static folder
            full_path = os.path.join(app.root_path, "static", img_path)

            # If file doesn't exist, use default
            if not os.path.isfile(full_path):
                img_path = "Icons/tool_default.jpg"

        # Final image path relative to /static/
        item["image_path"] = img_path

    return render_template("Inventory.html", items=items)

# -------------------------------
# ROUTE: ADD ITEM ROUTE
# -------------------------------
@app.route("/add", methods=["POST"])
@login_required
def add_item():
    name = request.form.get("name")
    item_type = request.form.get("type")
    quantity = request.form.get("quantity")
    borrowed = request.form.get("borrowed")
    status = request.form.get("status")
    image = request.files.get("image")

    image_path = None
    # Save the uploaded image inside your project's static/uploads folder
    if image and image.filename != "":
        filename = secure_filename(image.filename)
        
        # Full path using the correct uploads folder inside your project
        full_path = os.path.join(app.root_path, "static", "uploads", filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        image.save(full_path)

        # Store relative path for database (matches your /static structure)
        image_path = os.path.join("uploads", filename).replace("\\", "/")

    else:
        # ✅ Default image relative to static/
        image_path = "Icons/tool_default.jpg"

    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    cursor.execute("""
        INSERT INTO inventory (item_name, type, quantity, borrowed, status, image_path)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, item_type, quantity, borrowed, status, image_path))
    conn.commit()
    cursor.close()
    conn.close()

    return "Item added successfully", 200

# -------------------------------
# ROUTE: EDIT ITEM ROUTE
# -------------------------------
@app.route("/edit", methods=["POST"])
@login_required
def edit_item():
    item_id = request.form.get("id")
    name = request.form.get("name")
    item_type = request.form.get("type")
    quantity = request.form.get("quantity")
    borrowed = request.form.get("borrowed")
    status = request.form.get("status")
    image = request.files.get("image")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT image_path FROM inventory WHERE item_id=%s", (item_id,))
    row = cursor.fetchone()

    # If a record exists, use the stored image_path; otherwise use default
    current_image = row["image_path"] if row else "Icons/tool_default.jpg"

    # Save the uploaded image inside your project's static/uploads folder
    if image and image.filename != "":
        filename = secure_filename(image.filename)
        
        # Full path using the correct uploads folder inside your project
        full_path = os.path.join(app.root_path, "static", "uploads", filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        image.save(full_path)

        # Store relative path for database (matches your /static structure)
        image_path = os.path.join("uploads", filename).replace("\\", "/")

    else:
        # ✅ Keep current image, ensure clean path
        image_path = current_image.replace("\\", "/").replace("static/", "")

    cursor.execute("""
        UPDATE inventory
        SET item_name=%s, type=%s, quantity=%s, borrowed=%s, status=%s, image_path=%s
        WHERE item_id=%s
    """, (name, item_type, quantity, borrowed, status, image_path, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    return "Item updated successfully", 200

# -------------------------------
# ROUTE: DELETE ITEM ROUTE
# -------------------------------
@app.route("/archive_equipment", methods=["POST"])
@login_required
def archive_equipment():
    data = request.get_json()
    ids = data.get("ids", [])

    if not ids:
        return jsonify({"success": False, "error": "No equipment IDs provided"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1️⃣ Copy selected records to archive table
        format_strings = ','.join(['%s'] * len(ids))
        cursor.execute(f"""
            INSERT INTO inventory_archive (item_id, item_name, type, quantity, borrowed, status, image_path)
            SELECT item_id, item_name, type, quantity, borrowed, status, image_path
            FROM inventory
            WHERE item_id IN ({format_strings})
        """, tuple(ids))

        # 2️⃣ Delete them from the main inventory
        cursor.execute(f"DELETE FROM inventory WHERE item_id IN ({format_strings})", tuple(ids))

        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()
#------------------------------------------------------------------
# ROUTE: RECENTLY DELETED ITEMS IN INVENTORY
#------------------------------------------------------------------
@app.route("/view_archive")
@login_required
def view_archive():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM inventory_archive")
    archived_items = cursor.fetchall()

    cursor.close()
    conn.close()

    # Fix image path if stored inside static folder
    for item in archived_items:
        img_path = item.get("image_path")
        if not img_path:
            item["image_path"] = "Icons/tool_default.jpg"
        else:
            img_path = img_path.replace("\\", "/")
            if img_path.startswith("static/"):
                img_path = img_path[len("static/"):]
            item["image_path"] = img_path

    return render_template("InventoryArchive.html", items=archived_items)
#--------------------------------------------------------------
# ROUTE: RESTORE ARCHIVE ITEMS
#---------------------------------------------------------------
@app.route('/restore_item/<int:item_id>', methods=['POST'])
@login_required
def restore_item(item_id):
    try:
        cursor = mysql.connection.cursor(dictionary=True)

        # 🟡 1. Fetch the archived item
        cursor.execute("SELECT * FROM archive_inventory WHERE item_id = %s", (item_id,))
        item = cursor.fetchone()

        if item:
            # 🟢 2. Insert back into main inventory table
            cursor.execute("""
                INSERT INTO inventory (item_name, type, quantity, borrowed, status, image_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (item['item_name'], item['type'], item['quantity'], item['borrowed'], 'Available', item['image_path']))

            # 🔴 3. Delete from archive table
            cursor.execute("DELETE FROM archive_inventory WHERE item_id = %s", (item_id,))
            mysql.connection.commit()

        cursor.close()
        flash("Item successfully restored!", "success")
    except Exception as e:
        print("Error restoring item:", e)
        flash("Error restoring item.", "danger")

    return redirect(url_for('view_archive'))

# ------------------------------
# USERS MANAGEMENT ROUTES (MySQL Version)
# ------------------------------
@app.route("/users")
@login_required
def users_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

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
            CONCAT(u.last_name, ', ', u.first_name) AS name,
            (
                SELECT COUNT(*) 
                FROM transactions b 
                WHERE b.user_id = u.user_id
            ) AS transactions
        FROM borrowers u
        ORDER BY u.user_id DESC
    """)

    users = cursor.fetchall()
    conn.close()
    return render_template("UsersPage.html", users=users)
#-------------------------------------------------------------
# ROUTE: Get Transactions of a Specific User (VIEW BUTTON IN USERS PAGE)
#-------------------------------------------------------------
@app.route("/user_transactions/<int:user_id>")
@login_required
def user_transactions(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            b.borrow_id AS transaction_id,
            b.item_id,
            i.item_name,
            b.borrowed_qty,
            b.returned_qty,
            b.before_condition,
            b.after_condition,
            b.borrow_date,
            b.borrow_time,
            b.return_date,
            b.return_time
        FROM transactions b
        JOIN inventory i ON b.item_id = i.item_id
        WHERE b.user_id = %s
        ORDER BY b.borrow_date DESC
    """, (user_id,))

    transactions = cursor.fetchall()
    cursor.close()
    conn.close()

    # Convert date/time/timedelta fields to strings
    for tx in transactions:
        if tx['borrow_date']:
            tx['borrow_date'] = tx['borrow_date'].strftime("%Y-%m-%d")
        if tx['borrow_time']:
            tx['borrow_time'] = str(tx['borrow_time'])
        if tx['return_date']:
            tx['return_date'] = tx['return_date'].strftime("%Y-%m-%d")
        if tx['return_time']:
            tx['return_time'] = str(tx['return_time'])

    return jsonify({"transactions": transactions})

# -----------------------------------------------------------------
# ROUTE: Add User with image upload
# -----------------------------------------------------------------
@app.route("/add_user", methods=["POST"])
@login_required
def add_user():
    rfid = request.form.get("rfid")
    last_name = request.form.get("lastName")
    first_name = request.form.get("firstName")
    stud_no = request.form.get("stud_no")
    college = request.form.get("college")
    course = request.form.get("course")
    roles = request.form.get("roles")
    umak_email = request.form.get("umakEmail")

    # Handle image file
    image_file = request.files.get("image")
    image_path = None
    if image_file and image_file.filename != "":
        filename = secure_filename(image_file.filename)
        upload_folder = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_folder, exist_ok=True)  # ensure folder exists
        upload_path = os.path.join(upload_folder, filename)
        image_file.save(upload_path)
        # Store relative path for database
        image_path = f"uploads/{filename}"

    if not (rfid and last_name and first_name and stud_no):
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify(success=False, error="Database connection failed")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO borrowers (rfid, borrower_id, last_name, first_name, department, course, roles, umak_email, image)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (rfid, stud_no, last_name, first_name, college, course, roles, umak_email, image_path))
        conn.commit()
        return jsonify({"status": "success", "message": "User added successfully"})
    except mysql.connector.IntegrityError as e:
        error_msg = str(e)
        if "Duplicate entry" in error_msg and "rfid" in error_msg:
            return jsonify({"status": "error", "message": "RFID already exists"}), 400
        elif "Duplicate entry" in error_msg and "borrower_id" in error_msg:
            return jsonify({"status": "error", "message": "Student number already exists"}), 400
        else:
            return jsonify({"status": "error", "message": "Database error: " + error_msg}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": "Server error: " + str(e)}), 500
    finally:
        conn.close()

# -----------------------------------------------------------------
# ROUTE: UPLOAD AND PREVIEW BORROWER'S IMAGE
@app.route("/upload_user_image/<int:user_id>", methods=["POST"])
def upload_user_image(user_id):
    if "image" not in request.files:
        return jsonify({"status": "error", "message": "No image file found"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No selected file"}), 400

    # Save to static/uploads
    filename = secure_filename(file.filename)
    upload_path = os.path.join(app.root_path, "static", "uploads", filename)
    file.save(upload_path)

    # Update database (relative path)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE borrowers SET image=%s WHERE user_id=%s", (f"uploads/{filename}", user_id))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

# -----------------------------------------------------------------
# ROUTE: Edit User (MySQL Version)
# -----------------------------------------------------------------
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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE borrowers
        SET last_name=%s, first_name=%s, department=%s, course=%s, roles=%s, umak_email=%s
        WHERE user_id=%s
    """, (last_name, first_name, college, course, roles, umak_email, user_id))

    # Keep transactions linked to same user_id
    cursor.execute("""
        UPDATE transactions
        SET rfid = rfid
        WHERE user_id = %s
    """, (user_id,))

    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

# -----------------------------------------------------------------
# ROUTE: Archive (Delete) User Instead of Permanent Delete
# -----------------------------------------------------------------
@app.route("/delete_user/<int:user_id>", methods=["DELETE"])
@login_required
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1️⃣ Fetch the user data first
        cursor.execute("SELECT * FROM borrowers WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            conn.close()
            return jsonify({"status": "error", "message": "User not found"}), 404

        # 2️⃣ Insert into archive_borrowers table
        cursor.execute("""
            INSERT INTO archive_borrowers (
                rfid, borrower_id, last_name, first_name, department,
                course, image, roles, umak_email, archived_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            user["rfid"], user["borrower_id"], user["last_name"], user["first_name"],
            user["department"], user["course"], user["image"],
            user["roles"], user["umak_email"]
        ))

        # 3️⃣ Delete related records (transactions + main borrowers)
        cursor.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM borrowers WHERE user_id = %s", (user_id,))

        conn.commit()
        return jsonify({"status": "success", "message": "User archived successfully"})

    except Exception as e:
        conn.rollback()
        print("Error archiving user:", e)
        return jsonify({"status": "error", "message": "Failed to archive user"})

    finally:
        cursor.close()
        conn.close()
# -----------------------------------------------------------------
# ROUTE: Fetch Archived Users (For "Recently Deleted" Modal)
# -----------------------------------------------------------------
@app.route("/archived_users")
@login_required
def archived_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                archive_id AS user_id, 
                rfid, 
                borrower_id, 
                last_name, 
                first_name, 
                department, 
                course, 
                roles, 
                umak_email, 
                archived_at 
            FROM archive_borrowers 
            ORDER BY archived_at DESC
        """)
        users = cursor.fetchall()
        return jsonify({"users": users})
    except Exception as e:
        print("Error fetching archived users:", e)
        return jsonify({"users": []})
    finally:
        cursor.close()
        conn.close()

# -----------------------------------------------------------------
# ROUTE: Restore Archived User
# -----------------------------------------------------------------
@app.route("/restore_user/<int:user_id>", methods=["PUT"])
@login_required
def restore_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1️⃣ Fetch user from archive
        cursor.execute("SELECT * FROM archive_borrowers WHERE archive_id = %s", (user_id,))
        archived_user = cursor.fetchone()

        if not archived_user:
            conn.close()
            return jsonify({"status": "error", "message": "User not found in archive"}), 404

        # 2️⃣ Insert back to borrowers table
        cursor.execute("""
            INSERT INTO borrowers (
                rfid, borrower_id, last_name, first_name, department,
                course, image, roles, umak_email
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            archived_user["rfid"], archived_user["borrower_id"],
            archived_user["last_name"], archived_user["first_name"],
            archived_user["department"], archived_user["course"],
            archived_user["image"], archived_user["roles"],
            archived_user["umak_email"]
        ))

        # 3️⃣ Remove from archive table
        cursor.execute("DELETE FROM archive_borrowers WHERE archive_id = %s", (user_id,))

        conn.commit()
        return jsonify({"status": "success", "message": "User restored successfully"})

    except Exception as e:
        conn.rollback()
        print("Error restoring user:", e)
        return jsonify({"status": "error", "message": "Failed to restore user"})

    finally:
        cursor.close()
        conn.close()

# ----------------------------------------------------------
# ROUTE: History Page (MySQL Version)
# ----------------------------------------------------------
@app.route("/history")
@login_required
def history_page():
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    cursor = conn.cursor(dictionary=True)
    selected_date = request.args.get("date")

    base_query = """
        SELECT 
            b.borrow_date, 
            b.borrow_time, 
            i.item_name, 
            CONCAT(s.first_name, ' ', s.last_name) AS borrower,
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
    """

    try:
        if selected_date:
            cursor.execute(
                base_query + " WHERE b.borrow_date = %s ORDER BY b.borrow_date DESC, b.borrow_time DESC",
                (selected_date,)
            )
        else:
            cursor.execute(base_query + " ORDER BY b.borrow_date DESC, b.borrow_time DESC")

        rows = cursor.fetchall()

        # Group by date only (NOT by transaction)
        history = {}
        for row in rows:
            borrow_date = row["borrow_date"]
            if borrow_date not in history:
                history[borrow_date] = []
            history[borrow_date].append({
                "time": row["borrow_time"],
                "tool": row["item_name"],
                "user": row["borrower"],
                "quantity": row["borrowed_qty"],
                "returned_qty": row["returned_qty"],
                "status": row["status"]
            })

        return render_template("History.html", history=history or {})

    except Exception as e:
        print(f"History route error: {e}")
        return "Server error", 500

    finally:
        cursor.close()
        conn.close()

# ----------------------------------------------------------
# ROUTE: Report Page (MySQL Version)
# ----------------------------------------------------------
@app.route("/report")
@login_required
def report_page():
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500
    cursor = conn.cursor(dictionary=True)

    # Total borrows
    cursor.execute("SELECT COUNT(*) AS total FROM transactions")
    total_borrows = cursor.fetchone()["total"]

    # Items currently borrowed
    cursor.execute("""
        SELECT SUM(
            CASE 
                WHEN (borrowed_qty - returned_qty) > 0 
                THEN (borrowed_qty - returned_qty)
                ELSE 0
            END
        ) AS total
        FROM transactions
    """)
    currently_borrowed = cursor.fetchone()["total"] or 0

    # Available items
    cursor.execute("SELECT SUM(quantity - borrowed) AS total FROM inventory")
    available_items = cursor.fetchone()["total"] or 0

    # Items needing attention
    cursor.execute("SELECT COUNT(*) AS total FROM inventory WHERE status != 'Available'")
    items_attention = cursor.fetchone()["total"]

    # Most borrowed items
    cursor.execute("""
        SELECT i.item_name, i.type, SUM(b.borrowed_qty) AS 'total_borrowed'
        FROM transactions b
        JOIN inventory i ON b.item_id = i.item_id
        GROUP BY b.item_id
        ORDER BY total_borrowed DESC
        LIMIT 5
    """)
    most_borrowed = cursor.fetchall()

    # Items in poor condition (latest transaction per item)
    cursor.execute("""
        SELECT i.item_name, i.type, t.after_condition AS 'condition'
        FROM inventory i
        JOIN transactions t ON i.item_id = t.item_id
        WHERE t.borrow_id IN (
            SELECT MAX(borrow_id)
            FROM transactions
            GROUP BY item_id
        )
        AND t.after_condition IS NOT NULL
        AND (
            LOWER(t.after_condition) LIKE '%fair%'
            OR LOWER(t.after_condition) LIKE '%poor%'
            OR LOWER(t.after_condition) LIKE '%bad%'
            OR LOWER(t.after_condition) LIKE '%Retired%'
            OR LOWER(t.after_condition) LIKE '%Needs Repair%'
            OR LOWER(t.after_condition) LIKE '%For Replacement / Retired%'
        )
    """)
    poor_condition_items = cursor.fetchall()
    print("Poor condition items:", poor_condition_items)
    if not poor_condition_items:
        poor_condition_items = [{"message": "All items are in good condition"}]

    # Unavailable items (borrowed_qty > returned_qty)
    cursor.execute("""
        SELECT i.item_name, i.type, (t.borrowed_qty - t.returned_qty) AS unavailable_qty
        FROM inventory i
        JOIN transactions t ON i.item_id = t.item_id
        WHERE (t.borrowed_qty - t.returned_qty) > 0
    """)
    unavailable_items = cursor.fetchall()

    if not unavailable_items:
        unavailable_items = [{"message": "All items are available"}]

    for row in cursor.fetchall():
        try:
            days = int(float(row["status"])) if row["status"] is not None else 0
        except (ValueError, TypeError):
            days = 0
        unavailable_items.append({
            "name": row["item_name"],
            "type": row["type"],
            "days_unavailable": days
        })

    # ---------------- Chart Data ----------------
    today = datetime.now().date()

    # Daily chart
    slot_hours = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    daily_chart = []
    today_str = today.strftime('%Y-%m-%d')
    for h in slot_hours:
        start_time = f"{h:02d}:00:00"
        end_time = f"{h+1:02d}:59:59" if h < 22 else "23:59:59"
        cursor.execute("""
            SELECT SUM(borrowed_qty) AS total
            FROM transactions
            WHERE DATE(borrow_date) = %s AND TIME(borrow_time) BETWEEN %s AND %s
        """, (today_str, start_time, end_time))
        daily_chart.append(cursor.fetchone()["total"] or 0)

    # Weekly chart
    today_dt = datetime.now()
    today_day = today_dt.weekday()  # 0=Monday
    monday = (today_dt - timedelta(days=today_day)).date()
    weekly_chart = []
    for i in range(7):
        day = monday + timedelta(days=i)
        cursor.execute("""
            SELECT SUM(borrowed_qty) AS total
            FROM transactions
            WHERE DATE(borrow_date) = %s
        """, (day.strftime('%Y-%m-%d'),))
        weekly_chart.append(cursor.fetchone()["total"] or 0)

    # Monthly chart
    monthly_chart = []
    year, month = today.year, today.month
    first_day = datetime(year, month, 1).date()
    next_month_first = datetime(year + (month // 12), (month % 12) + 1, 1).date()
    last_day = next_month_first - timedelta(days=1)
    num_weeks = ((last_day.day - 1) // 7) + 1

    for week in range(1, num_weeks + 1):
        week_start = first_day + timedelta(days=(week - 1) * 7)
        week_end = min(week_start + timedelta(days=6), last_day)
        cursor.execute("""
            SELECT SUM(borrowed_qty) AS total
            FROM transactions
            WHERE DATE(borrow_date) BETWEEN %s AND %s
        """, (week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
        monthly_chart.append(cursor.fetchone()["total"] or 0)

    # ----- Summary data for donut chart -----
    cursor.execute("""
        SELECT status, SUM(quantity) AS total
        FROM inventory
        GROUP BY status
    """)
    status_data = cursor.fetchall()
    
    # Convert to lists for Chart.js
    labels = [row['status'] for row in status_data]
    values = [row['total'] for row in status_data]

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
        monthly_chart=monthly_chart,
        donut_labels=labels,
        donut_values=values
    )

# ---------------------------------------------------
# ROUTE: GENERATE REPORT (PDF FORMAT)
# ---------------------------------------------------
@app.route("/generate_report_pdf")
@login_required
def generate_report_pdf():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # -----------------------------------------------------
    # SUMMARY DATA
    # -----------------------------------------------------
    cursor.execute("SELECT COUNT(*) AS total FROM transactions")
    total_borrows = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT SUM(
            CASE 
                WHEN (borrowed_qty - returned_qty) > 0 
                THEN (borrowed_qty - returned_qty)
                ELSE 0
            END
        ) AS current
        FROM transactions
    """)
    currently_borrowed = cursor.fetchone()["current"] or 0

    cursor.execute("SELECT SUM(quantity - borrowed) AS available FROM inventory")
    available_items = cursor.fetchone()["available"] or 0

    cursor.execute("SELECT COUNT(*) AS attention FROM inventory WHERE status != 'Available'")
    items_attention = cursor.fetchone()["attention"]

    cursor.execute("SELECT item_name, type, quantity, borrowed, status FROM inventory")
    inventory_data = cursor.fetchall()

    # -----------------------------------------------------
    # CHART DATA (FROM REPORTS ROUTE)
    # -----------------------------------------------------
    today = datetime.now().date()

    # 1. DAILY CHART (6am–11pm)
    slot_hours = [6,8,10,12,14,16,18,20,22]
    daily_values = []
    today_str = today.strftime('%Y-%m-%d')

    for h in slot_hours:
        start_time = f"{h:02d}:00:00"
        end_time = f"{h+1:02d}:59:59" if h < 22 else "23:59:59"
        cursor.execute("""
            SELECT SUM(borrowed_qty) AS total
            FROM transactions
            WHERE DATE(borrow_date) = %s AND TIME(borrow_time) BETWEEN %s AND %s
        """, (today_str, start_time, end_time))
        daily_values.append(cursor.fetchone()["total"] or 0)

    daily_labels = [f"{h}:00" for h in slot_hours]

    # 2. WEEKLY CHART (Mon–Sun)
    today_dt = datetime.now()
    monday = (today_dt - timedelta(days=today_dt.weekday())).date()
    weekly_values = []
    weekly_labels = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

    for i in range(7):
        day = monday + timedelta(days=i)
        cursor.execute("""
            SELECT SUM(borrowed_qty) AS total
            FROM transactions
            WHERE DATE(borrow_date) = %s
        """, (day.strftime('%Y-%m-%d'),))
        weekly_values.append(cursor.fetchone()["total"] or 0)

    # 3. MONTHLY CHART (Week 1–5)
    year, month = today.year, today.month
    first_day = datetime(year, month, 1).date()
    next_month = datetime(year + (month // 12), (month % 12) + 1, 1).date()
    last_day = next_month - timedelta(days=1)
    total_weeks = ((last_day.day - 1) // 7) + 1

    monthly_values = []
    monthly_labels = [f"Week {i}" for i in range(1, total_weeks+1)]

    for i in range(1, total_weeks+1):
        week_start = first_day + timedelta(days=(i - 1) * 7)
        week_end = min(week_start + timedelta(days=6), last_day)
        cursor.execute("""
            SELECT SUM(borrowed_qty) AS total
            FROM transactions
            WHERE DATE(borrow_date) BETWEEN %s AND %s
        """, (week_start, week_end))
        monthly_values.append(cursor.fetchone()["total"] or 0)

    # 4. DONUT CHART (Equipment Status)
    cursor.execute("""
        SELECT status, COUNT(*) AS total
        FROM inventory
        GROUP BY status
    """)
    status_raw = cursor.fetchall()
    status_labels = [row["status"] for row in status_raw]
    status_values = [row["total"] for row in status_raw]

    conn.close()

    # -----------------------------------------------------
    # GENERATE CHART IMAGES
    # -----------------------------------------------------
    charts = []

    def build_bar(labels, values, title):
        plt.figure(figsize=(5,3))
        plt.bar(labels, values)
        plt.title(title)
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        charts.append(buf)
        plt.close()

    # Daily - Weekly - Monthly
    build_bar(daily_labels, daily_values, "Daily Borrow Count")
    build_bar(weekly_labels, weekly_values, "Weekly Borrow Count")
    build_bar(monthly_labels, monthly_values, "Monthly Borrow Count")

    # Donut Chart
    plt.figure(figsize=(4,4))
    plt.pie(status_values, labels=status_labels, autopct='%1.1f%%')
    circle = plt.Circle((0,0), 0.70, color='white')
    fig = plt.gcf()
    fig.gca().add_artist(circle)
    plt.title("Equipment Status Distribution")
    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    charts.append(buf)
    plt.close()

    # -----------------------------------------------------
    # BUILD PDF
    # -----------------------------------------------------
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph("<b>Laboratory Equipment Borrowing System Report</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Date Generated: {datetime.now().strftime('%B %d, %Y')}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Summary table
    summary_data = [
        ["Total Borrows", total_borrows],
        ["Currently Borrowed", currently_borrowed],
        ["Available Items", available_items],
        ["Items Needing Attention", items_attention],
    ]

    summary_table = Table(summary_data, colWidths=[200, 150])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN', (1,0), (-1,-1), 'CENTER')
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Inventory table
    inv_headers = ["Item Name", "Type", "Qty", "Borrowed", "Status"]
    inv_rows = [
        [row["item_name"], row["type"], row["quantity"], row["borrowed"], row["status"]]
        for row in inventory_data
    ]

    inv_table = Table([inv_headers] + inv_rows, repeatRows=1)
    inv_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,-1), 9)
    ]))

    elements.append(Paragraph("<b>Inventory List</b>", styles["Heading2"]))
    elements.append(inv_table)
    elements.append(Spacer(1, 26))

    # Insert Charts
    for chart in charts:
        elements.append(Image(chart, width=400, height=220))
        elements.append(Spacer(1, 20))

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="UMAK_LEBS_Report.pdf",
                     mimetype="application/pdf")

# ----------------------------------------------------------
# ROUTE: Update admins Account (MySQL Version)
# ----------------------------------------------------------
@app.route('/update_admins_account', methods=['POST'])
@login_required
def update_admins_account():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not name or not email or not current_password:
        return jsonify(success=False, error="All required fields must be filled.")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Use %s instead of ? for MySQL
    try:
        cursor.execute("SELECT password FROM admins WHERE admin_id = %s", (session['admins_id'],))
    except mysql.connector.errors.ProgrammingError as e:
        print(f"⚠️ ProgrammingError in update_admins_account: {e}. Trying to init DB and retry.")
        init_db()
        cursor.execute("SELECT password FROM admins WHERE admin_id = %s", (session['admins_id'],))
    admins = cursor.fetchone()

    if not admins:
        conn.close()
        return jsonify(success=False, error="admins not found.")

    # Verify current password
    if not bcrypt.checkpw(current_password.encode('utf-8'), admins[0].encode('utf-8')):
        conn.close()
        return jsonify(success=False, error="Incorrect current password.")

    # Update information
    if new_password:
        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute("""
            UPDATE admins SET name=%s, email=%s, password=%s WHERE admin_id=%s
        """, (name, email, hashed_pw, session['admins_id']))
    else:
        cursor.execute("""
            UPDATE admins SET name=%s, email=%s WHERE admin_id=%s
        """, (name, email, session['admins_id']))

    conn.commit()
    conn.close()
    return jsonify(success=True)

# ----------------------------------------------------------
# ROUTE: Send Forgot Password Code
# ----------------------------------------------------------
@app.route("/send_forgot_code", methods=["POST"])
def send_forgot_code():
    data = request.get_json()
    email = data.get("email")
    conn = get_db_connection()
    if conn is None:
        return jsonify(success=False, error="Database connection failed")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM admins WHERE email=%s", (email,))
        admins = cursor.fetchone()
    except mysql.connector.errors.ProgrammingError as e:
        # Possibly table missing (first-run); try to create tables and retry
        print(f"⚠️ Database programming error while checking admins: {e}. Attempting to init DB and retry.")
        try:
            init_db()
        except Exception as ex:
            print(f"❌ init_db() failed: {ex}")
            conn.close()
            return jsonify(success=False, error="Database initialization failed")
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM admins WHERE email=%s", (email,))
        admins = cursor.fetchone()
    finally:
        conn.close()

    if not admins:
        return jsonify(success=False, error="Email not registered")

    code = str(random.randint(100000, 999999))
    try:
        save_verification_code(email, code)
    except Exception as e:
        print(f"❌ Error saving verification code: {e}")
        return jsonify(success=False, error="Failed to save verification code")

    try:
        sent = send_verification_email(email, code)
        if not sent:
            return jsonify(success=False, error="Failed to send verification email")
    except Exception as e:
        print(f"❌ Error while sending verification email: {e}")
        return jsonify(success=False, error="Email sending failed")

    return jsonify(success=True)

# ----------------------------------------------------------
# ROUTE: Reset Password
# ----------------------------------------------------------
@app.route("/reset_password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("new_password")

    conn = get_db_connection()
    if conn is None:
        return jsonify(success=False, error="Database connection failed")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT verification_code FROM admins WHERE email=%s", (email,))
        admins = cursor.fetchone()
    except mysql.connector.errors.ProgrammingError as e:
        print(f"⚠️ ProgrammingError on reset_password: {e}. Attempting init_db() and retry.")
        init_db()
        cursor = conn.cursor()
        cursor.execute("SELECT verification_code FROM admins WHERE email=%s", (email,))
        admins = cursor.fetchone()

    if not admins or admins[0] != code:
        conn.close()
        return jsonify(success=False, error="Invalid or expired code")

    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cursor.execute("UPDATE admins SET password=%s, verification_code=NULL WHERE email=%s", (hashed_pw, email))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# ----------------------------------------------------------
# ROUTE: Save Verification Code
# ----------------------------------------------------------
def save_verification_code(email, code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE admins SET verification_code=%s WHERE email=%s", (code, email))
    conn.commit()
    conn.close()
# -------------------------------------------------------------------------------------------------------
# FUNCTIONS FOR KIOSK OR USER'S PAGE
# -------------------------------------------------------------------------------------------------------
#------------------------------------------------------------
# ROUTE: KIOSK SELECTION
#------------------------------------------------------------
@app.route('/kiosk_page')
@login_required
def kiosk_page():
    if 'admins_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('KioskSelection.html')
#--------------------------------------------------
# ROUTE 1: KIOSK BORROW PAGE
#---------------------------------------------------
@app.route("/kiosk_borrow")
@login_required
def kiosk_borrow_page():
    if 'admins_id' not in session:
        flash("Session expired. Please log in again.")
        return redirect('/login')

    admins_id = session['admins_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch admins info
        cursor.execute("SELECT first_name, last_name FROM admins WHERE admins_id = %s", (admins_id,))
        admins = cursor.fetchone()
        if not admins:
            flash("admins not found.")
            return redirect('/login')

        # Fetch inventory data
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
                type,
                image_path
            FROM inventory
            ORDER BY item_name ASC
        """)
        items = cursor.fetchall()

        for item in items:
            img_path = item.get("image_path")

            if not img_path:
                item["image_path"] = "Icons/tool_default.jpg"
            else:
                img_path = img_path.replace("\\", "/")
                if img_path.startswith("static/"):
                    img_path = img_path[len("static/"):]
                
                full_path = os.path.join(app.root_path, "static", img_path)
                if not os.path.exists(full_path):
                    img_path = f"Icons/{os.path.basename(img_path)}"

                item["image_path"] = img_path

        # ✅ Get distinct item types
        cursor.execute("""
            SELECT DISTINCT type 
            FROM inventory 
            WHERE type IS NOT NULL AND type != '' 
            ORDER BY type ASC
        """)
        types = [row["type"] for row in cursor.fetchall()]

        conn.close()

        # ✅ Prepare equipment data
        equipment = [
            {
                "id": item["item_id"],
                "name": item["item_name"],
                "all_quantity": item["quantity"],
                "on_borrowed": item["borrowed"],
                "available": item["available"],
                "type": item["type"],
                "image_path": item["image_path"]
            }
            for item in items
        ]
        return render_template(
            "KioskBorrow.html",
            equipment=equipment,
            types=types,
            admins_name=f"{admins['first_name']} {admins['last_name']}"
        )
    except Exception as e:
        print(f"❌ Error during borrow_page: {e}")
        flash("An error occurred while loading the borrow page.")
        return redirect('/kiosk_page')
    
# -----------------------------------------------------------------
# ROUTE 2: RFID Scanner Route for Kiosk
# -----------------------------------------------------------------
@app.route('/kiosk_rfid_scanner', methods=['POST'])
@login_required
def kiosk_rfid_scanner():
    try:
        # Retrieve form data arrays from Borrow.html
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        condition_list = request.form.getlist("before_condition[]")
        instructor_rfid = request.form.get("instructor_rfid")
        subject = request.form.get("subject")
        room = request.form.get("room")

        if not equipment_list:
            flash("⚠️ No equipment data received.", "error")
            return redirect(url_for("kiosk_borrow_page"))

        # Pass arrays to RFID Scanner page
        return render_template(
            "RfidScanner.html",
            action_url=url_for("kiosk_borrow_confirm"),
            equipment_list=equipment_list,
            quantity_list=quantity_list,
            condition_list=condition_list,
            instructor_rfid=instructor_rfid,
            subject=subject,
            room=room,
            zip=zip
        )

    except Exception as e:
        print("Error in /rfid_scanner:", e)
        flash("An error occurred while preparing RFID scanning.", "error")
        return redirect(url_for("kiosk_borrow_page"))

# -------------------------------------------------
# ROUTE 3: BORROW CONFIRMATION
# -------------------------------------------------
@app.route("/kiosk_borrow_confirm", methods=["POST"])
@login_required
def kiosk_borrow_confirm():
    try:
        if "admins_id" not in session:
            flash("Session expired. Please log in again.")
            return redirect("/login")

        admins_id = session["admins_id"]

        # ✅ Form data
        rfid = request.form.get("rfid")
        subject = request.form.get("subject", "").strip()
        room = request.form.get("room", "").strip()
        instructor_rfid = request.form.get("instructor_rfid")
        equipment_list = request.form.getlist("equipment[]")
        quantity_list = request.form.getlist("quantity[]")
        condition_list = request.form.getlist("before_condition[]")

        if not rfid or not equipment_list:
            flash("Missing RFID or equipment data.")
            return redirect("/kiosk_borrow")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ✅ Lookup borrower
        cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
        borrower = cursor.fetchone()
        if not borrower:
            flash("No borrower found for this RFID.")
            conn.close()
            return redirect("/kiosk_borrow")

        # ✅ Lookup instructor
        cursor.execute("SELECT user_id, first_name, last_name FROM borrowers WHERE rfid = %s", (instructor_rfid,))
        instructor = cursor.fetchone()
        if not instructor:
            flash("Instructor not found.")
            conn.close()
            return redirect("/kiosk_borrow")

        instructor_id = instructor["user_id"]

        # ✅ Current date/time
        now = datetime.now(ZoneInfo("Asia/Manila"))
        borrow_date = now.date()   # Python date object
        borrow_time = now.time()   # Python time object

        borrow_ids = []  # track all transaction rows

        # ✅ Loop through all equipment entries
        for eq, qty, cond in zip(equipment_list, quantity_list, condition_list):
            cursor.execute("SELECT item_id, quantity, borrowed FROM inventory WHERE item_name = %s", (eq,))
            item = cursor.fetchone()
            if not item:
                print(f"⚠️ Item not found: {eq}")
                continue

            available = item["quantity"] - item["borrowed"]
            if int(qty) > available:
                print(f"⚠️ Not enough stock for {eq}. Available: {available}, Requested: {qty}")
                continue

            # ✅ Insert transaction with proper date/time objects
            cursor.execute("""
                INSERT INTO transactions (
                    user_id, admins_id, instructor_id, instructor_rfid,
                    subject, room, rfid, item_id, borrowed_qty,
                    borrow_date, borrow_time, before_condition
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                borrower["user_id"], admins_id, instructor_id, instructor_rfid,
                subject, room, rfid, item["item_id"], int(qty),
                borrow_date, borrow_time, cond
            ))

            borrow_ids.append(cursor.lastrowid)

            # ✅ Update inventory count
            cursor.execute("UPDATE inventory SET borrowed = borrowed + %s WHERE item_id = %s",
                           (int(qty), item["item_id"]))

        conn.commit()

        # ✅ Fetch admins details
        cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = %s", (admins_id,))
        admins = cursor.fetchone()

        # ✅ Prepare summary for PDF/email slip
        transaction = {
            "transaction_number": f"{borrow_ids[0]:07d}" if borrow_ids else "N/A",
            "name": f"{borrower['first_name']} {borrower['last_name']}",
            "user_id": borrower["borrower_id"],
            "department": borrower["department"],
            "course": borrower["course"],
            "instructor_name": f"{instructor['first_name']} {instructor['last_name']}",
            "subject": subject,
            "room": room,
            "date": borrow_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
            "time": borrow_time.strftime("%I:%M %p").lstrip("0"),
            "admins_name": f"{admins['first_name']} {admins['last_name']}",
            "items": [
                {"equipment": eq, "quantity": qty, "condition": cond}
                for eq, qty, cond in zip(equipment_list, quantity_list, condition_list)
            ]
        }

        # ✅ Generate PDF slip
        pdf_path = generate_borrow_slip(transaction)

        # ✅ Send via email (optional)
        if borrower.get("umak_email"):
            send_transaction_email(borrower["umak_email"], pdf_path, transaction)

        flash("✅ Borrow confirmed! Borrow slip generated and sent via email.")
        return redirect(url_for("kiosk_view_transaction", borrow_id=borrow_ids[0] if borrow_ids else 0))

    except Exception as e:
        print("❌ Error during borrow_confirm:", e)
        flash("An error occurred during borrowing confirmation.")
        return redirect("/kiosk_borrow")

    finally:
        cursor.close()
        conn.close()

# -------------------------------------------------
# ROUTE 4: KIOSK TRANSACTION SUCCESS PAGE
# -------------------------------------------------
@app.route('/kiosk_success/<borrow_id>')
@login_required
def kiosk_view_transaction(borrow_id):
    conn = get_db_connection()  
    cursor = conn.cursor(dictionary=True)  

    try:  
        cursor.execute("""
        SELECT
            t.borrow_id,
            t.borrow_date,
            t.borrow_time,
            t.subject,
            t.room,
            b.first_name,
            b.last_name,
            b.department,
            b.course,
            b.image,
            b.borrower_id AS user_id,
            i2.first_name AS instructor_first,
            i2.last_name AS instructor_last,
            inv.item_name AS equipment,
            t.borrowed_qty AS quantity,
            t.before_condition AS `condition`
        FROM transactions t
        JOIN borrowers b ON t.user_id = b.user_id
        JOIN borrowers i2 ON t.instructor_id = i2.user_id
        JOIN inventory inv ON t.item_id = inv.item_id
        WHERE t.user_id = (
            SELECT user_id FROM transactions WHERE borrow_id = %s
        )
        AND t.borrow_date = (
            SELECT borrow_date FROM transactions WHERE borrow_id = %s
        )
        AND t.borrow_time = (
            SELECT borrow_time FROM transactions WHERE borrow_id = %s
        )
        ORDER BY t.borrow_id
    """, (borrow_id, borrow_id, borrow_id))  
        rows = cursor.fetchall()

        if not rows:  
            flash("❌ Borrow transaction not found.", "error")  
            return redirect(url_for("kiosk_page"))  

        main = rows[0]  

        # Format borrow_id with 7-digit zero padding  
        transaction_number = f"{main['borrow_id']:07d}"  

        # Safely format date  
        display_date = ""  
        if main["borrow_date"]:  
            if isinstance(main["borrow_date"], (datetime, date)):  
                display_date = main["borrow_date"].strftime("%m/%d/%Y").lstrip("0").replace("/0", "/")  
            else:  
                display_date = str(main["borrow_date"])  

        # Safely format time  
        display_time = ""  
        if main["borrow_time"]:  
            if isinstance(main["borrow_time"], (datetime, time)):  
                display_time = main["borrow_time"].strftime("%I:%M %p").lstrip("0")  
            else:  
                display_time = str(main["borrow_time"])  

        # Build transaction dictionary  
        transaction = {  
            "transaction_number": transaction_number,  
            "date": display_date,  
            "time": display_time,  
            "name": f"{main['first_name']} {main['last_name']}",  
            "user_id": main["user_id"],  
            "department": main["department"],  
            "course": main["course"],  
            "instructor_name": f"{main['instructor_first']} {main['instructor_last']}",  
            "subject": main["subject"],  
            "room": main["room"],  
            "image": main["image"],  
            "items": []  
        }  

        for r in rows:  
            transaction["items"].append({  
                "equipment": r["equipment"],  
                "quantity": r["quantity"],  
                "condition": r["condition"]  
            })  

        return render_template("KioskSuccess.html", transaction=transaction)  

    except Exception as e:  
        print("Error loading transaction:", e)  
        flash("⚠️ Failed to load transaction details.", "error")  
        return redirect(url_for("kiosk_page"))  

    finally:  
        cursor.close()  
        conn.close()

# -------------------------------------------------
# STEP 1: SCAN RFID -> SHOW RETURN FORM
# ------------------------------------------------
@app.route("/kiosk_return_scanner", methods=["GET", "POST"])
@login_required
def kiosk_return_scanner():
    if request.method == "GET":
        return render_template("KioskScannerReturn.html")

    rfid = request.form.get("rfid")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 Get borrower info
    cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
    borrower = cursor.fetchone()

    if not borrower:
        flash("❌ Borrower not found for this RFID.")
        conn.close()
        return redirect(url_for("kiosk_return_scanner"))

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
        WHERE t.rfid = %s
          AND IFNULL(t.returned_qty, 0) < t.borrowed_qty
        ORDER BY t.borrow_id ASC
    """, (rfid,))
    items = cursor.fetchall()

    conn.close()

    if not items:
        flash("✅ All items for this borrower have already been returned.")
        return redirect(url_for("kiosk_return_scanner"))

    borrower_info = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower.get("image"),
        "date": items[0]['borrow_date'],
        "time": items[0]['borrow_time']
    }

    return render_template("KioskReturnForm.html", borrower=borrower_info, items=items)

# -----------------------------------------------------------------
# STEP 2: CONFIRM ITEMS TO BE RETURNED
# -----------------------------------------------------------------
@app.route("/kiosk_return_confirm", methods=["POST"])
@login_required
def kiosk_return_confirm():
    rfid = request.form.get("rfid")

    if not rfid:
        flash("❌ No RFID received. Please try again.")
        return redirect(url_for("kiosk_return_scanner"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Verify borrower
    cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
    borrower = cursor.fetchone()
    if not borrower:
        flash("⚠️ RFID not found in the system.")
        conn.close()
        return redirect(url_for("kiosk_return_scanner"))

    # Fetch unreturned items
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
    WHERE t.rfid = %s 
    AND (t.returned_qty < t.borrowed_qty OR t.returned_qty IS NULL)
    """, (rfid,))
    items = cursor.fetchall()
    conn.close()

    if not items:
        flash("✅ All items for this borrower are already returned.")
        return redirect(url_for("kiosk_return_scanner"))

    # Prepare borrower data with image
    borrower_data = {
        "transaction_no": f"{items[0]['borrow_id']:07d}",
        "rfid": rfid,
        "name": f"{borrower['first_name']} {borrower['last_name']}",
        "department": borrower["department"],
        "course": borrower["course"],
        "image": borrower["image"] if borrower.get("image") else None,
        "date": items[0]["borrow_date"],
        "time": items[0]["borrow_time"]
    }

    # Prepare items data with remaining quantity to return
    items_data = [
        {
            "borrow_id": f"{item.get('borrow_id', 0):07d}",
            "item_name": item.get("item_name", "Unknown"),
            "quantity_borrowed": item.get("borrowed_qty") or 0,
            "quantity_returned": item.get("returned_qty") or 0,
            "condition_borrowed": item.get("before_condition") or "N/A",
            "quantity_remaining": (item.get("borrowed_qty") or 0) - (item.get("returned_qty") or 0)
        }
        for item in items
    ]
    print("DEBUG items_data:", items_data)

    return render_template("KioskReturnForm.html", borrower=borrower_data, items=items_data)

# -------------------------------------------------
# STEP 3: SUBMIT RETURN FORM
# -------------------------------------------------
@app.route("/kiosk_process_return", methods=["POST"])
@login_required
def kiosk_process_return():
    try:
        rfid = request.form.get("rfid")
        transaction_no = request.form.get("transaction_no")
        item_names = request.form.getlist("item_name[]")
        returned_now = request.form.getlist("quantity_returned[]")
        condition_returned = request.form.getlist("condition_returned[]")

        # Get admins info from session
        admins_id = session.get("admins_id")
        if not admins_id:
            session["admins_name"] = "admins unknown"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch borrower info
        cursor.execute("SELECT * FROM borrowers WHERE rfid = %s", (rfid,))
        borrower = cursor.fetchone()
        if not borrower:
            flash("⚠️ Borrower not found.")
            return redirect(url_for("kiosk_return_scanner"))

        now = datetime.now(ZoneInfo("Asia/Manila"))
        return_date = now.date()
        return_time = now.time()

        returned_items = []
        returned_borrow_ids = []

        # Loop through items to process return
        for i in range(len(item_names)):
            item_name = item_names[i]
            qty_now = returned_now[i] if i < len(returned_now) else "0"
            cond_returned = condition_returned[i] if i < len(condition_returned) else ""

            if not qty_now.strip() or not cond_returned.strip():
                continue

            try:
                qty_now = int(qty_now)
                if qty_now <= 0:
                    continue
            except ValueError:
                continue

            # Get all pending transactions for this item
            cursor.execute("""
                SELECT t.borrow_id, t.item_id, t.returned_qty, t.borrowed_qty
                FROM transactions t
                JOIN inventory i ON t.item_id = i.item_id
                WHERE t.rfid = %s AND i.item_name = %s AND t.returned_qty < t.borrowed_qty
                ORDER BY t.borrow_id ASC
            """, (rfid, item_name))
            transactions = cursor.fetchall()
            if not transactions:
                continue

            remaining_qty = qty_now
            for transaction in transactions:
                still_to_return = transaction["borrowed_qty"] - transaction["returned_qty"]
                to_return = min(remaining_qty, still_to_return)
                new_returned_qty = transaction["returned_qty"] + to_return

                # Update transaction
                cursor.execute("""
                    UPDATE transactions
                    SET returned_qty = %s,
                        after_condition = %s,
                        return_date = %s,
                        return_time = %s
                    WHERE borrow_id = %s
                """, (new_returned_qty, cond_returned, return_date, return_time, transaction["borrow_id"]))

                returned_borrow_ids.append(str(transaction["borrow_id"]))
                returned_items.append({
                    "item_name": item_name,
                    "quantity": to_return,
                    "condition": cond_returned
                })

                remaining_qty -= to_return
                if remaining_qty <= 0:
                    break

            # Update inventory status
            cursor.execute("""
                UPDATE inventory i
                JOIN (
                    SELECT item_id, GREATEST(SUM(borrowed_qty - returned_qty), 0) AS still_borrowed
                    FROM transactions
                    WHERE item_id = %s
                    GROUP BY item_id
                ) t ON i.item_id = t.item_id
                SET i.borrowed = t.still_borrowed,
                    i.status = CASE 
                        WHEN t.still_borrowed < i.quantity THEN 'Available'
                        ELSE 'Unavailable'
                    END
            """, (transactions[0]["item_id"],))

        if not returned_items:
            flash("⚠️ No items were returned. Please input at least one valid quantity.")
            return redirect(url_for("kiosk_return_scanner"))

        conn.commit()

        # Fetch admins details if available
        if admins_id:
            cursor.execute("SELECT first_name, last_name FROM admins WHERE admin_id = %s", (admins_id,))
            admins = cursor.fetchone()
            admins_name = f"{admins['first_name']} {admins['last_name']}" if admins else "admins unknown"
        else:
            admins_name = "admins unknown"

        # After all items have been processed
        borrow_ids_str = ",".join(returned_borrow_ids)

        # Use first borrow_id of returned items as Return ID
        return_id = f"{int(returned_borrow_ids[0]):07d}" if returned_borrow_ids else "N/A"

        # Prepare transaction summary for PDF/email
        transaction_summary = {
            "transaction_number": return_id,
            "name": f"{borrower['first_name']} {borrower['last_name']}",
            "borrower_id": borrower["borrower_id"],
            "rfid": rfid,
            "department": borrower["department"],
            "course": borrower["course"],
            "image": borrower.get("image") or None,
            "date": return_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
            "time": return_time.strftime("%I:%M %p").lstrip("0"),
            "items": returned_items,
            "admins_name": admins_name
        }

        # Generate PDF and send email
        pdf_path = generate_return_slip(transaction_summary)
        if borrower.get("umak_email"):
            send_return_email(borrower["umak_email"], pdf_path, transaction_summary)

        flash("✅ Return recorded successfully. Partial returns saved if applicable.")

        # Redirect to success page
        borrow_ids_str = ",".join(returned_borrow_ids)
        qty_str = ",".join([str(item["quantity"]) for item in returned_items])
        return redirect(url_for('kiosk_return_success') + f"?borrow_ids={borrow_ids_str}&qty={qty_str}")

    except Exception as e:
        print("❌ Error processing return:", e)
        flash("An error occurred while processing the return.")
        return redirect(url_for("kiosk_return_scanner"))

    finally:
        cursor.close()
        conn.close()

# -------------------------------------------------
# STEP 5: DISPLAY THE RETURN DETAILS
# -------------------------------------------------
@app.route("/kiosk_return_success")
@login_required
def kiosk_return_success():
    borrow_ids_str = request.args.get("borrow_ids")
    qty_str = request.args.get("qty")

    if not borrow_ids_str or not qty_str:
        flash("⚠️ No transaction data provided.")
        return redirect(url_for("kiosk_return_scanner"))

    borrow_ids = borrow_ids_str.split(",")
    qty_list = [int(q) for q in qty_str.split(",") if q.isdigit()]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get borrower info
        cursor.execute("""
            SELECT b.first_name, b.last_name, b.department, b.course, b.borrower_id, b.image
            FROM transactions t
            JOIN borrowers b ON t.rfid = b.rfid
            WHERE t.borrow_id = %s
            LIMIT 1
        """, (borrow_ids[0],))
        borrower = cursor.fetchone()
        if not borrower:
            flash("⚠️ Borrower not found.")
            return redirect(url_for("kiosk_page"))

        # ✅ Fetch ALL items for the given borrow_ids
        format_strings = ",".join(["%s"] * len(borrow_ids))
        cursor.execute(f"""
            SELECT i.item_name, t.after_condition AS `condition`, t.returned_qty
            FROM transactions t
            JOIN inventory i ON t.item_id = i.item_id
            WHERE t.borrow_id IN ({format_strings})
        """, tuple(borrow_ids))
        items_db = cursor.fetchall()

        # ✅ Always show all items, even if mismatch in qty length
        items = []
        for i, item in enumerate(items_db):
            qty = qty_list[i] if i < len(qty_list) else item.get("returned_qty", 1)
            items.append({
                "item_name": item["item_name"],
                "quantity": qty,
                "condition": item["condition"] or "Good Condition"
            })

        # Get return date/time
        cursor.execute("""
            SELECT return_date, return_time
            FROM transactions
            WHERE borrow_id = %s
            LIMIT 1
        """, (borrow_ids[0],))
        dt = cursor.fetchone()
        return_date = dt.get("return_date") if dt else None
        return_time = dt.get("return_time") if dt else None

        transaction = {
            "transaction_number": f"{int(borrow_ids[0]):07d}",
            "date": (
                return_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/")
                if isinstance(return_date, (datetime, date))
                else str(return_date or "")
            ),
            "time": (
                return_time.strftime("%I:%M %p").lstrip("0")
                if isinstance(return_time, (datetime, time))
                else str(return_time or "")
            ),
            "name": f"{borrower['first_name']} {borrower['last_name']}",
            "borrower_id": borrower["borrower_id"],
            "department": borrower["department"],
            "course": borrower["course"],
            "image": borrower.get("image"),
            "items": items
        }

        return render_template("KioskReturnSuccess.html", transaction=transaction)

    except Exception as e:
        print("❌ Error loading return success page:", e)
        flash("An error occurred while loading the return summary.")
        return redirect(url_for("kiosk_page"))

    finally:
        cursor.close()
        conn.close()

# -----------------------------------------------------------------
# MAIN ENTRY POINT
# -----------------------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8080)




