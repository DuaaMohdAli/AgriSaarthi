import os
import tempfile
import datetime
import mysql.connector
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from ml.disease_detector import predict_disease
from db_handler import save_disease_history, get_disease_history

app = FastAPI(title="AgriSaarthi API", docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://agrisaarti.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── MySQL config ─────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "",           # your MySQL password
    "database": "dbmsproject"
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

# ── Season mapping (month → Kharif/Rabi) ────────────────────────────────────
def get_season():
    month = datetime.datetime.now().month
    if month in [6, 7, 8, 9, 10]:
        return "Kharif"       # Monsoon/Rainy
    elif month in [11, 12, 1, 2, 3]:
        return "Rabi"         # Winter
    else:
        return "Kharif"       # Summer → fallback to Kharif

# ── Water mapping (frontend value → DB value) ────────────────────────────────
def map_water(water: str) -> list:
    """If user selects Low, also include Medium as fallback"""
    water = water.strip().capitalize()
    if water == "Low":
        return ["Low", "Medium"]
    elif water == "Medium":
        return ["Medium", "High"]
    else:
        return ["High"]

class CropRequest(BaseModel):
    state: str
    climate_zone: str
    soil_ph: float
    water: str
    lang: str = "en"

@app.post("/api/recommend_crop")
def recommend_crop(req: CropRequest):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        season = get_season()
        water_options = map_water(req.water)
        water_placeholders = ", ".join(["%s"] * len(water_options))

        # ── Main query joining all tables ────────────────────────────────────
        query = f"""
            SELECT 
                cs.crop_name,
                cr.soil_type,
                cr.profit_range,
                cr.water_recommendation,
                mp.current_price,
                mp.price_trend,
                s.season_name
            FROM crop_recommendation cr
            JOIN crop_season cs2 
                ON cs2.season = %s
            JOIN crop_soil cs 
                ON cs.crop_name = cs2.crop_name
                AND cs.soil_type = cr.soil_type
            JOIN season s 
                ON s.crop_id = cr.crop_id
                AND s.season_name = %s
            JOIN market_price mp 
                ON mp.market_id = cr.market_id
            WHERE cr.water_recommendation IN ({water_placeholders})
            LIMIT 10
        """

        params = [season, season] + water_options
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # ── Fallback: ignore season if empty ────────────────────────────────
        if not rows:
            query_fallback = f"""
                SELECT 
                    cs.crop_name,
                    cr.soil_type,
                    cr.profit_range,
                    cr.water_recommendation,
                    mp.current_price,
                    mp.price_trend
                FROM crop_recommendation cr
                JOIN crop_soil cs 
                    ON cs.soil_type = cr.soil_type
                JOIN market_price mp 
                    ON mp.market_id = cr.market_id
                WHERE cr.water_recommendation IN ({water_placeholders})
                LIMIT 10
            """
            cursor.execute(query_fallback, water_options)
            rows = cursor.fetchall()

        cursor.close()
        conn.close()

        if not rows:
            return {"success": False, "message": "No matching crops found", "crops": []}

        # ── Sort by profit and return top 3 ─────────────────────────────────
        rows.sort(key=lambda x: x["profit_range"], reverse=True)
        top3 = rows[:3]

        recommended = []
        for row in top3:
            recommended.append({
                "crop":          row["crop_name"],
                "profit_index":  float(row["profit_range"]),
                "water_need":    row["water_recommendation"],
                "price":         float(row["current_price"]),
                "price_trend":   row.get("price_trend", "N/A"),
                "sowing_months": "See local calendar",
                "fertilizer":    "Consult local agronomist"
            })

        return {"success": True, "crops": recommended}

    except Exception as e:
        return {"success": False, "message": str(e), "crops": []}


# ── Disease detection (unchanged) ────────────────────────────────────────────
@app.post("/api/detect_disease")
async def detect_disease(
    farmer_name: str = Form(...),
    lang: str = Form("en"),
    file: UploadFile = File(...)
):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = predict_disease(tmp_path, lang=lang)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if lang in ["hi", "ta", "te", "ml"]:
        disease_display    = result.get(f"disease_{lang}", result["disease"]).replace("_", " ")
        crop_display       = result.get(f"crop_{lang}", result["crop"])
        remedy_display     = result.get(f"remedy_{lang}", result["remedy"])
        precautions_display = result.get(f"precautions_{lang}", result["precautions"])
    else:
        disease_display    = result["disease"].replace("_", " ")
        crop_display       = result["crop"]
        remedy_display     = result["remedy"]
        precautions_display = result["precautions"]

    save_disease_history(
        farmer_name, crop_display, disease_display,
        result.get("remedy_en", ""),      result.get("precautions_en", ""),
        result.get("remedy_hi", ""),      result.get("precautions_hi", ""),
        result.get("remedy_ta", ""),      result.get("precautions_ta", ""),
        result.get("remedy_te", ""),      result.get("precautions_te", ""),
        result.get("remedy_ml", ""),      result.get("precautions_ml", ""),
    )

    return {
        "success":    True,
        "disease":    disease_display,
        "crop":       crop_display,
        "remedy":     remedy_display,
        "precautions": precautions_display,
        "confidence": result.get("confidence", 0)
    }


# ── History ──────────────────────────────────────────────────────────────────
@app.get("/api/history")
def get_history():
    try:
        df = get_disease_history()
        return {"success": True, "history": df.fillna("").to_dict(orient="records")}
    except Exception as e:
        return {"success": False, "message": str(e), "history": []}

@app.get("/")
def read_root():
    return {"status": "ok", "message": "AgriSaarthi API is running"}