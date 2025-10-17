import os
import stripe
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Cargar clave de Stripe desde variable de entorno
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    raise RuntimeError("⚠️ La variable STRIPE_SECRET_KEY no está configurada")

DOMAIN = "https://tienda.hamelyn.com"
CSV_FILE = "uploadts-1760618195-sec_top_music.csv"

app = FastAPI(title="Hamelyn Checkout API")

# Permitir llamadas desde cualquier origen (útil para ChatGPT y pruebas locales)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Leer productos del Merchant Center
try:
    df = pd.read_csv(CSV_FILE)
except Exception as e:
    raise RuntimeError(f"Error al leer el CSV: {e}")

# Normalizar y extraer campos clave
df.columns = [c.strip().lower() for c in df.columns]
df["price_value"] = df["price"].str.extract(r"([\d\.,]+)").astype(float)
df["currency"] = df["price"].str.extract(r"([A-Z]{3})")
productos = df.to_dict(orient="records")

@app.get("/")
def root():
    return {"status": "Hamelyn Checkout API running", "total_products": len(productos)}

@app.get("/productos")
def listar_productos(limit: int = 10):
    """Devuelve los primeros productos del catálogo."""
    return productos[:limit]

@app.post("/checkout/{product_id}")
def crear_checkout(product_id: str):
    """Crea una sesión real de Stripe Checkout (modo test)."""
    producto = next((p for p in productos if str(p.get("id")) == product_id), None)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": producto["currency"] or "EUR",
                        "product_data": {
                            "name": producto["title"],
                            "images": [producto.get("image link")],
                        },
                        "unit_amount": int(float(producto["price_value"]) * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{DOMAIN}/gracias?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/cancelado",
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
