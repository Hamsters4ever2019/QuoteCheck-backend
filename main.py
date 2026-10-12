from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from datetime import datetime
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "quotecheck.db")

app = FastAPI(title="QuoteCheck API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- DB ----------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema) as f:
        sql = f.read()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(sql)
    conn.commit()
    conn.close()


# ---------- Engine ----------

D = Decimal


def q2(value) -> Decimal:
    return D(str(value)).quantize(D("0.01"), ROUND_HALF_UP)


def calculate_quote(
    estimated_hours: Decimal,
    materials_cost: Decimal,
    travel_distance: Decimal,
    hourly_rate: Decimal,
    vehicle_cost_per_mile: Decimal,
    overhead_pct: Decimal,
    target_margin_pct: Decimal,
    quote_price: Decimal,
) -> dict:
    labour = q2(estimated_hours * hourly_rate)
    materials = q2(materials_cost)
    travel = q2(travel_distance * vehicle_cost_per_mile)
    subtotal = labour + materials + travel
    overhead = q2(subtotal * overhead_pct / D("100"))
    total_cost = subtotal + overhead

    margin_factor = D("1") - (target_margin_pct / D("100"))
    if margin_factor <= 0:
        raise ValueError("Target margin must be less than 100%")

    required_quote = q2(total_cost / margin_factor)
    profit = q2(quote_price - total_cost)

    if quote_price > 0:
        actual_margin = q2((profit / quote_price) * D("100"))
    else:
        actual_margin = D("0.00")

    shortfall = q2(required_quote - quote_price)

    if actual_margin < 0:
        verdict = "LOSS"
    elif actual_margin < target_margin_pct:
        verdict = "THIN"
    else:
        verdict = "GOOD"

    # Headroom = how much you're above target (positive) or below (negative)
    headroom = q2(quote_price - required_quote)

    workings = [
        f"Labour: {estimated_hours} hrs x £{hourly_rate} = £{labour}",
        f"Materials: £{materials}",
        f"Travel: {travel_distance} miles x £{vehicle_cost_per_mile} = £{travel}",
        f"Subtotal: £{subtotal}",
        f"Overhead: {overhead_pct}% x £{subtotal} = £{overhead}",
        f"Total cost: £{total_cost}",
        f"Required quote for {target_margin_pct}% margin: £{required_quote}",
        f"Your quote: £{quote_price}",
        f"Profit: £{profit}",
        f"Actual margin: {actual_margin}%",
        f"Shortfall: £{shortfall}" if shortfall > 0 else "No shortfall — quote is profitable",
    ]

    return {
        "labour_cost": float(labour),
        "materials_cost": float(materials),
        "travel_cost": float(travel),
        "subtotal": float(subtotal),
        "overhead": float(overhead),
        "total_cost": float(total_cost),
        "required_quote": float(required_quote),
        "profit": float(profit),
        "actual_margin": float(actual_margin),
        "verdict": verdict,
        "shortfall": float(shortfall) if shortfall > 0 else 0.0,
        "headroom": float(headroom) if headroom > 0 else 0.0,
        "workings": workings,
    }


# ---------- Models ----------

class QuoteRequest(BaseModel):
    customer_id: Optional[int] = None
    job_type_id: Optional[int] = None
    estimated_hours: Decimal = Field(..., gt=0)
    materials_cost: Decimal = Field(..., ge=0)
    travel_distance: Decimal = Field(..., ge=0)
    hourly_rate: Decimal = Field(..., gt=0)
    vehicle_cost_per_mile: Decimal = Field(..., gt=0)
    overhead_pct: Decimal = Field(..., ge=0, lt=100)
    target_margin_pct: Decimal = Field(..., ge=0, lt=100)
    quote_price: Decimal = Field(..., gt=0)


class ActualRequest(BaseModel):
    actual_hours: Decimal = Field(..., ge=0)
    actual_materials: Decimal = Field(..., ge=0)
    actual_travel: Decimal = Field(..., ge=0)


# ---------- Routes ----------

@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/v1/settings")
def get_settings(db=Depends(get_db)):
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: float(r["value"]) for r in rows}


@app.post("/api/v1/quotes")
def create_quote(req: QuoteRequest, db=Depends(get_db)):
    try:
        result = calculate_quote(
            req.estimated_hours, req.materials_cost, req.travel_distance,
            req.hourly_rate, req.vehicle_cost_per_mile,
            req.overhead_pct, req.target_margin_pct, req.quote_price,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    message = build_message(result)

    cursor = db.execute("""
        INSERT INTO quotes (
            customer_id, job_type_id,
            estimated_hours, materials_cost, travel_distance,
            hourly_rate, vehicle_cost_per_mile,
            overhead_pct, target_margin_pct, quote_price,
            labour_cost, travel_cost, subtotal, overhead,
            total_cost, required_quote, profit, actual_margin,
            verdict, shortfall, headroom, workings
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        req.customer_id, req.job_type_id,
        float(req.estimated_hours), float(req.materials_cost), float(req.travel_distance),
        float(req.hourly_rate), float(req.vehicle_cost_per_mile),
        float(req.overhead_pct), float(req.target_margin_pct), float(req.quote_price),
        result["labour_cost"], result["travel_cost"], result["subtotal"], result["overhead"],
        result["total_cost"], result["required_quote"], result["profit"], result["actual_margin"],
        result["verdict"], result["shortfall"], result["headroom"], json.dumps(result["workings"]),
    ))
    db.commit()
  

    return {"id": cursor.lastrowid, "message": message, **result}


@app.get("/api/v1/quotes")
def list_quotes(db=Depends(get_db)):
    rows = db.execute("""
        SELECT q.id, q.quote_price, q.verdict, q.shortfall, q.actual_margin,
               q.created_at, q.estimated_hours, q.materials_cost, q.travel_distance,
               c.name AS customer_name, j.name AS job_type_name
        FROM quotes q
        LEFT JOIN customers c ON q.customer_id = c.id
        LEFT JOIN job_types j ON q.job_type_id = j.id
        ORDER BY q.created_at DESC
        LIMIT 50
    """).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/v1/quotes/{quote_id}")
def get_quote(quote_id: int, db=Depends(get_db)):
    row = db.execute("""
        SELECT q.*, c.name AS customer_name, j.name AS job_type_name
        FROM quotes q
        LEFT JOIN customers c ON q.customer_id = c.id
        LEFT JOIN job_types j ON q.job_type_id = j.id
        WHERE q.id = ?
    """, (quote_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Quote not found")
    d = dict(row)
    d["workings"] = json.loads(d["workings"])
    d["message"] = build_message(d)
    return d


@app.post("/api/v1/quotes/{quote_id}/actuals")
def log_actuals(quote_id: int, req: ActualRequest, db=Depends(get_db)):
    quote = db.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    if not quote:
        raise HTTPException(404, "Quote not found")

    hourly_rate = D(str(quote["hourly_rate"]))
    vehicle_cost = D(str(quote["vehicle_cost_per_mile"]))
    overhead_pct = D(str(quote["overhead_pct"]))
    quote_price = D(str(quote["quote_price"]))

    actual_labour = q2(req.actual_hours * hourly_rate)
    actual_travel = q2(req.actual_travel * vehicle_cost)
    actual_subtotal = actual_labour + req.actual_materials + actual_travel
    actual_overhead = q2(actual_subtotal * overhead_pct / D("100"))
    actual_cost = actual_subtotal + actual_overhead
    actual_profit = q2(quote_price - actual_cost)
    actual_margin = q2((actual_profit / quote_price) * D("100")) if quote_price > 0 else D("0")

    db.execute("""
        INSERT INTO actuals (
            quote_id, actual_hours, actual_materials, actual_travel,
            actual_cost, actual_profit, actual_margin
        ) VALUES (?,?,?,?,?,?,?)
    """, (
        quote_id, float(req.actual_hours), float(req.actual_materials), float(req.actual_travel),
        float(actual_cost), float(actual_profit), float(actual_margin),
    ))
    db.commit()

    quoted_margin = D(str(quote["actual_margin"]))
    delta = actual_margin - quoted_margin
    direction = "worse" if delta < 0 else "better"

    return {
        "quote_id": quote_id,
        "actual_cost": float(actual_cost),
        "actual_profit": float(actual_profit),
        "actual_margin": float(actual_margin),
        "quoted_margin": float(quoted_margin),
        "delta": float(delta),
        "engine_note": (
            f"Your actual margin is {actual_margin}%, {direction} than the "
            f"{quoted_margin}% you quoted. Adjusting future quotes."
        ),
    }


def build_message(result: dict) -> str:
    if result["verdict"] == "LOSS":
        return f"This quote will lose you £{result['shortfall']:.2f}."
    if result["verdict"] == "THIN":
        return f"This quote is thin. Increase price by £{result['shortfall']:.2f} to hit target."
    return f"This quote delivers {result['actual_margin']:.1f}% margin. £{result['headroom']:.2f} above target."