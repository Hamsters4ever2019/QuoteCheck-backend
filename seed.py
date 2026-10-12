"""Seed the database with realistic electrician quotes."""
import sqlite3
import json
import os
from main import calculate_quote, DB_PATH, init_db

D = __import__("decimal").Decimal


def seed():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Settings
    conn.executemany(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        [
            ("hourly_rate", "45"),
            ("vehicle_cost_per_mile", "0.45"),
            ("overhead_pct", "15"),
            ("target_margin_pct", "25"),
        ],
    )

    # Customers
    customers = [
        ("Mrs Smith", "07700 900123", "smith@example.com", "SW1A 1AA"),
        ("Mr Jones", "07700 900456", "jones@example.com", "M1 1AE"),
        ("Mrs Patel", "07700 900789", "patel@example.com", "B1 1AA"),
        ("Mr O'Brien", "07700 900321", "obrien@example.com", "EH1 1YZ"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO customers (name, phone, email, postcode) VALUES (?,?,?,?)",
        customers,
    )

    # Job types
    job_types = [
        ("Rewire", 16, 450, 24),
        ("Consumer Unit", 4, 120, 12),
        ("EICR", 3, 0, 12),
        ("Fault Finding", 2, 0, 12),
        ("Lighting Install", 6, 200, 12),
        ("EV Charger", 5, 600, 16),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO job_types (name, default_hours, default_materials, default_travel) VALUES (?,?,?,?)",
        job_types,
    )

    # Realistic quotes
    quotes = [
        # (customer_id, job_type_id, hours, materials, travel, quote_price)
        (1, 1, 16, 450, 24, 1500),   # Rewire — THIN (margin 9.5%, under target)
        (2, 2, 4, 120, 12, 550),      # Consumer Unit — GOOD (margin 36%)
        (3, 3, 3, 0, 12, 250),        # EICR — GOOD (margin 35%)
        (4, 4, 2, 0, 12, 160),        # Fault Finding — GOOD (margin 31%)
        (1, 5, 6, 200, 12, 800),      # Lighting — GOOD (margin 32%)
        (2, 6, 5, 600, 16, 950),      # EV Charger — LOSS (margin -0.7%)
    ]

    for cust_id, job_id, hours, mats, travel, price in quotes:
        result = calculate_quote(
            D(str(hours)), D(str(mats)), D(str(travel)),
            D("45"), D("0.45"), D("15"), D("25"), D(str(price)),
        )
        conn.execute("""
            INSERT INTO quotes (
                customer_id, job_type_id,
                estimated_hours, materials_cost, travel_distance,
                hourly_rate, vehicle_cost_per_mile,
                overhead_pct, target_margin_pct, quote_price,
                labour_cost, travel_cost, subtotal, overhead,
                total_cost, required_quote, profit, actual_margin,
                verdict, shortfall, workings
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cust_id, job_id,
            hours, mats, travel,
            45, 0.45, 15, 25, price,
            result["labour_cost"], result["travel_cost"], result["subtotal"], result["overhead"],
            result["total_cost"], result["required_quote"], result["profit"], result["actual_margin"],
            result["verdict"], result["shortfall"], json.dumps(result["workings"]),
        ))

    # One actual logged (the rewire went worse than quoted)
    conn.execute("""
        INSERT INTO actuals (
            quote_id, actual_hours, actual_materials, actual_travel,
            actual_cost, actual_profit, actual_margin
        ) VALUES (?,?,?,?,?,?,?)
    """, (1, 18, 480, 28, 1540.20, -40.20, -2.68))

    conn.commit()
    conn.close()
    print(f"Seeded {len(quotes)} quotes, {len(customers)} customers, {len(job_types)} job types.")


if __name__ == "__main__":
    seed()