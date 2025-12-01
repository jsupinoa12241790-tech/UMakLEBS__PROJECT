# UMak-LEBS (Railway deployment guide)

This project is a Flask-based Laboratory Equipment Borrowing system with SocketIO and MySQL.

## Recommended deployment: Railway (free tier)

### Key points
- Use the `Procfile` or `Dockerfile` for Railway to deploy: `web: gunicorn -k eventlet -w 1 wsgi:application`.
- The app reads configuration from environment variables. See `.env.example`.
- Use a managed MySQL plugin in Railway (or PlanetScale/ClearDB) for your database.

---

## Files added for deployment
- `wsgi.py`: WSGI entrypoint; exposes `application`.
- `Dockerfile`: Optional container deployment; sets up environment and runs Gunicorn.
- `Procfile`: For `railway` simple deployments (Gunicorn + Eventlet).
- `.dockerignore`: Excludes files from the Docker context.
- `.env.example`: A template of environment variables to provide on Railway.
- `README.md`: Deployment instructions.

---

## Railway quick steps
1. Push your repo to GitHub (if not already). Make sure `requirements.txt`, `Procfile`, and `wsgi.py` are in the repo root.
2. Create a Railway account and click **New Project** → **Deploy from GitHub**.
3. Select your repository and branch. On the `Variables` panel, add the environment variables shown in `.env.example`.
4. Add a MySQL plugin from Railway (or connect to a managed MySQL/PlanetScale database).
5. Ensure `PORT` is configured by Railway automatically.
6. Deploy and open logs from Railway's console to monitor the deploy and startup.

### Railway CLI quick steps (optional)
If you prefer to use the Railway CLI (https://railway.app/), here are quick commands to create a project and add a managed MySQL plugin:

1. Login to Railway from the CLI:
	```bash
	railway login
	```
2. Initialize project inside your repo directory:
	```bash
	railway init
	```
3. Connect your project to GitHub if needed and push files.
4. Add MySQL plugin using the Railway console or CLI (the dashboard is easier), then add environment variables shown in `.env.example`.
5. Deploy with:
	```bash
	railway up
	```

Note: If using Docker on Railway with the `Dockerfile`, Railway will use your Docker setup to build the image. Alternatively, the `Procfile` will instruct Railway to build with a Python builder.

Notes:
- If your app uses websockets, ensure Railway supports eventlet; it does support websocket-like connections (check Log/Docs for Skyline/Transport behavior).
- If your app sends email (SMTP), set `EMAIL_USER` and `EMAIL_PASS` as environment variables (and configure the account to allow app connections).

---

## Database
- The `get_db_connection()` in `lebs_database.py` reads `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASS`, `MYSQL_DB`, and `MYSQL_PORT` from environment variables.
- First-time deploy: run the `init_db()` endpoint manually or run the app locally to initialize tables.

## Debugging
- Tail the logs on Railway if you see import errors or issues. If you see `ModuleNotFoundError`, re-check `requirements.txt`.
- If emails fail, confirm SMTP credentials and that less-secure app access is permitted for SMTP provider.

---

## Optional: Deploy using Docker on Railway or Fly.io
- If you want to deploy using Docker, the `Dockerfile` is configured to run Gunicorn + Eventlet. On Railway choose **Deploy using Docker** and it will build and run the image.

---

If you'd like, I can set up the GitHub repository to include these files and add a `railway.json` for Railways' `cli` — tell me if you'd like automation and I can add more config or help you connect the repo to Railway. 
