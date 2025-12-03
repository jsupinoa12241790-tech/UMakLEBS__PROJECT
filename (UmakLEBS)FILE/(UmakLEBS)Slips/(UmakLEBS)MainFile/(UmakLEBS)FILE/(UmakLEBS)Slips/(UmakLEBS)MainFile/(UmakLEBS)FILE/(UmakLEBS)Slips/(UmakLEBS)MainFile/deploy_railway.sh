#!/usr/bin/env bash
# Deployment helper for Railway (local use) - edit before running
# Requires: railway cli (https://railway.app/cli)

# 1) login
# railway login

# 2) init project (choose existing or create new)
# railway init

# 3) add MySQL plugin if you want from CLI (or add via web console)
# railway add plugin mysql

# 4) set environment variables (change values or use 'railway variables set' in script)
# railway variables set SECRET_KEY=yourkey MYSQL_HOST=... MYSQL_USER=... MYSQL_PASS=... MYSQL_DB=... EMAIL_USER=... EMAIL_PASS=

# 5) deploy
# railway up

echo "Script created. Run commands manually or edit this file to auto-run the railway CLI steps." 
