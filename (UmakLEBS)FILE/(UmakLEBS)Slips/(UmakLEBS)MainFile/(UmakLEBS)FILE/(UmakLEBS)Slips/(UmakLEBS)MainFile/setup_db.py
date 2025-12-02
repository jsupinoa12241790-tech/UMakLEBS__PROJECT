from lebs_database import init_db, fill_inventory, get_db_connection
import bcrypt

init_db()
fill_inventory()

# Seed initial admin account (if it doesn't exist)
def seed_admin():
	conn = get_db_connection()
	if not conn:
		print("❌ Unable to seed admin: database connection failed.")
		return
	cursor = conn.cursor()
	try:
		cursor.execute("SELECT COUNT(*) FROM admins WHERE email = %s", ("jsupino.a12241790@umak.edu.ph",))
		if cursor.fetchone()[0] == 0:
			hashed_pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
			cursor.execute(
				"""
				INSERT INTO admins (first_name, last_name, email, password, is_verified)
				VALUES (%s, %s, %s, %s, %s)
				""",
				("JS", "Upino", "jsupino.a12241790@umak.edu.ph", hashed_pw, 1)
			)
			conn.commit()
			print("✅ Admin account seeded.")
		else:
			print("ℹ️ Admin account already exists.")
	except Exception as e:
		print(f"❌ Failed to seed admin: {e}")
	finally:
		cursor.close()
		conn.close()

seed_admin()
