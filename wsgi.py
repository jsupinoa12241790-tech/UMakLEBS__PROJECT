import os
import sys

# Make sure project root is on sys.path
project_home = os.path.dirname(__file__)
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# If app resides in nested subfolders (as in this repo), add them too
subfolder = os.path.join(project_home, "(11- 24) Umak-Lebs Project", "(11- 24) Umak-Lebs Project", "(11- 24) Umak-Lebs Project")
if os.path.isdir(subfolder) and subfolder not in sys.path:
    sys.path.insert(0, subfolder)

# Import the application object for WSGI servers
try:
    from app import application
except Exception:
    # Fallback: try importing app and exposing app variable
    from app import app as application
