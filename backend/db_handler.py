import mysql.connector
import pandas as pd

# ── MySQL connection config ──────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",        # change if different
    "password": "dua143UMMA@/",            # your MySQL root password
    "database": "dbmsproject"  # your existing database name
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def save_disease_history(
    farmer_name,
    crop,
    disease,
    remedy_en, precautions_en,
    remedy_hi, precautions_hi,
    remedy_ta, precautions_ta,
    remedy_te, precautions_te,
    remedy_ml, precautions_ml
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disease_history (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            farmer_name VARCHAR(255),
            crop        VARCHAR(255),
            disease     VARCHAR(255),
            remedy_en       TEXT, precautions_en TEXT,
            remedy_hi       TEXT, precautions_hi TEXT,
            remedy_ta       TEXT, precautions_ta TEXT,
            remedy_te       TEXT, precautions_te TEXT,
            remedy_ml       TEXT, precautions_ml TEXT,
            timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        INSERT INTO disease_history (
            farmer_name, crop, disease,
            remedy_en, precautions_en,
            remedy_hi, precautions_hi,
            remedy_ta, precautions_ta,
            remedy_te, precautions_te,
            remedy_ml, precautions_ml
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        farmer_name, crop, disease,
        remedy_en, precautions_en,
        remedy_hi, precautions_hi,
        remedy_ta, precautions_ta,
        remedy_te, precautions_te,
        remedy_ml, precautions_ml
    ))

    conn.commit()
    cursor.close()
    conn.close()


def get_disease_history():
    conn = get_connection()
    query = "SELECT * FROM disease_history ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df