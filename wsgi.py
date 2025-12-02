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

# Import the application object for Gunicorn
try:
    from app import application
except ImportError:
    from app import app as application
