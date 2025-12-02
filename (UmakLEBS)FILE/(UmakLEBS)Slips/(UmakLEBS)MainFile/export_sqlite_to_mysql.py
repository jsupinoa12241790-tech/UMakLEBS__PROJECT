import sqlite3
import re

conn = sqlite3.connect("lebsData.db")
dump = "\n".join(conn.iterdump())
conn.close()

dump = re.sub(r"AUTOINCREMENT", "AUTO_INCREMENT", dump)
dump = re.sub(r"INTEGER PRIMARY KEY", "INT AUTO_INCREMENT PRIMARY KEY", dump)
dump = re.sub(r"BEGIN TRANSACTION;", "", dump)
dump = re.sub(r"COMMIT;", "", dump)
dump = re.sub(r"PRAGMA.*?;\n", "", dump)
dump = re.sub(r"sqlite_sequence.*?;\n", "", dump)
dump = re.sub(r"CREATE TABLE sqlite_sequence.*?;\n", "", dump)

with open("lebsData_mysql.sql", "w", encoding="utf-8") as f:
    f.write(dump)

print("✅ Export complete: lebsData_mysql.sql is ready for MySQL import.")
