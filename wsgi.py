import os
import sys

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
    from lebs_database import init_db, fill_inventory
    try:
        print("Initializing DB tables from wsgi.py...")
        init_db()
        print("Filling default inventory from wsgi.py...")
        fill_inventory()
    except Exception as inner_e:
        print("Warning: DB init/fill failed during wsgi startup:", inner_e)
except Exception as e:
    # If lebs_database isn't importable here (e.g., race condition), ignore gracefully
    print("Warning: Could not import lebs_database in wsgi.py:", e)

# Import the application object for Gunicorn
try:
    from app import application  # type: ignore
except ImportError:
    from app import app as application  # type: ignore

