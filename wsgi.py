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
    from lebs_database import init_db, fill_inventory, get_db_connection
    # Wait for DB to become ready (useful in containers where MySQL starts slower)
    max_checks = 10
    for attempt in range(1, max_checks + 1):
        try:
            conn = get_db_connection()
            if conn is not None:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                conn.close()
                print("Database connection verified, proceeding with init_db().")
                break
            else:
                raise Exception("get_db_connection returned None")
        except Exception as inner_e:
            print(f"DB not ready (attempt {attempt}/{max_checks}): {inner_e}")
            if attempt == max_checks:
                print("DB did not become ready; proceeding to call init_db() anyway (it may fail).")
                break
            time.sleep(attempt)  # linear backoff

    try:
        print("Initializing DB tables from wsgi.py...")
        init_db()
        print("Filling default inventory from wsgi.py...")
        fill_inventory()
    except Exception as init_e:
        print("Warning: DB init/fill failed during wsgi startup:", init_e)
except Exception as e:
    # If lebs_database isn't importable here (e.g., path/race condition), ignore gracefully
    print("Warning: Could not import lebs_database in wsgi.py:", e)

# Import the application object for Gunicorn
try:
    from app import application  # type: ignore
except ImportError:
    from app import app as application  # type: ignore

