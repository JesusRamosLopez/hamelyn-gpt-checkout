import os
import stripe
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 🔑 Cargar clave de Stripe desde variable de entorno
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    raise RuntimeError("⚠️ La variable STRIPE_SECRET_KEY no está configurada")
print("🔍 Stripe key cargada:", stripe.api_key[:10] + "..." if stripe.api_key else "⚠️ No detectada")

# 🌐 Dominio principal y archivo CSV
DOMAIN = "https://tienda.hamelyn.com"
CSV_FILE = "uploadts-1760618195-sec_top_music.csv"

# 🚀 Inicializar FastAPI
app = FastAPI(title="Hamelyn Checkout API")

# 🔓 CORS para permitir acceso desde cualquier origen (ChatGPT, frontends, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 📦 Cargar catálogo de productos
try:
    df = pd.read_csv(CSV_FILE)
except Exception as e:
    raise RuntimeError(f"Error al leer el CSV: {e}")

# 🧹 Normalizar columnas
df.columns = [c.strip().lower() for c in df.columns]
df["price_value"] = df["price"].str.extract(r"([\d\.,]+)").astype(float)
df["currency"] = df["price"].str.extract(r"([A-Z]{3})")
productos = df.to_dict(orient="records")

# 🏁 Endpoint raíz
@app.get("/")
def root():
    return {"status": "Hamelyn Checkout API running", "total_products": len(productos)}

# 🧾 Listar productos
@app.get("/productos")
def listar_productos(limit: int = 10):
    """Devuelve los primeros productos del catálogo."""
    return productos[:limit]

# 💳 Crear sesión de Stripe Checkout
@app.post("/checkout/{product_id}")
def crear_checkout(product_id: str):
    """Crea una sesión real de Stripe Checkout (modo test)."""
    producto = next((p for p in productos if str(p.get("id")) == product_id), None)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # 🧠 Validaciones y fallback
    nombre = str(producto.get("title") or "Producto Hamelyn")
    precio = float(producto.get("price_value") or 1.0)
    moneda = (producto.get("currency") or "eur").lower()
    imagen = producto.get("image link")

    # Validar imagen
    if not isinstance(imagen, str) or not imagen.startswith("http"):
        imagen = "https://tienda.hamelyn.com/assets/img/default-product.jpg"

    try:
        # 🧾 Crear sesión de checkout
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": moneda,
                        "product_data": {
                            "name": nombre,
                            "images": [imagen],
                        },
                        "unit_amount": int(precio * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{DOMAIN}/gracias?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/cancelado",
        )

        print(f"✅ Sesión creada correctamente para {nombre} → {session.url}")
        return {"checkout_url": session.url}

    except Exception as e:
        print(f"❌ Error creando checkout para {product_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
