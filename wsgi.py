import os
import sys
import time

# Get the project root
project_home = os.path.dirname(__file__)
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Add nested folder to sys.path manually
nested_path = os.path.join(project_home, "(UmakLEBS)FILE", "(UmakLEBS)Slips", "(UmakLEBS)MainFile")
if os.path.isdir(nested_path) and nested_path not in sys.path:
    sys.path.insert(0, nested_path)

# Run DB initialization once at app startup to ensure tables exist
try:
    from lebs_database import init_db, fill_inventory, get_db_connection, is_db_ready
    # Wait for DB to become ready (useful in containers where MySQL starts slower)
    # Use connection.is_connected() / conn.ping() to check readiness safely
    max_checks = int(os.getenv('DB_READY_CHECKS', 10))
    for attempt in range(1, max_checks + 1):
        try:
            # Prefer using our helper to avoid leaving unread results
            if is_db_ready():
                print("Database connection verified, proceeding with init_db().")
                break
            else:
                raise Exception("DB not ready yet")
        except Exception as inner_e:
            print(f"DB not ready (attempt {attempt}/{max_checks}): {inner_e}")
            if attempt == max_checks:
                print("DB did not become ready; proceeding to call init_db() anyway (it may fail).")
                break
            time.sleep(min(5, attempt))  # small backoff to avoid long blocking

    # Optionally run init_db on startup only if env var allows it - prevents blocking during container restarts
    init_on_start = os.getenv('INIT_DB_ON_STARTUP', 'true').lower() in ('true', '1', 'yes')
    if init_on_start:
        try:
            print("Initializing DB tables from wsgi.py...")
            # Optionally run init in a background thread to avoid blocking Gunicorn master/workers
            run_in_thread = os.getenv('RUN_INIT_IN_THREAD', 'true').lower() in ('true', '1', 'yes')
            if run_in_thread:
                import threading
                t = threading.Thread(target=init_db, daemon=True)
                t.start()
                t2 = threading.Thread(target=fill_inventory, daemon=True)
                t2.start()
                print("init_db() and fill_inventory() started in background threads.")
            else:
                init_db()
                fill_inventory()
        except Exception as init_e:
            print("Warning: DB init/fill failed during wsgi startup:", init_e)
    else:
        print("INIT_DB_ON_STARTUP is disabled; skipping init_db/fill_inventory during wsgi startup.")
except Exception as e:
    # If lebs_database isn't importable here (e.g., path/race condition), ignore gracefully
    print("Warning: Could not import lebs_database in wsgi.py:", e)

# Import the application object for Gunicorn
try:
    from app import application  # type: ignore
except ImportError:
    from app import app as application  # type: ignore

