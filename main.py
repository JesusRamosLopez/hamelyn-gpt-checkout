from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
import stripe
import os
import numpy as np

# -----------------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------------

app = FastAPI(title="Hamelyn GPT Checkout API", version="1.0.0")

# Permitir peticiones desde ChatGPT y tu dominio
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chat.openai.com",  # ChatGPT
        "https://tienda.hamelyn.com",  # tu tienda
        "http://localhost:3000",  # entorno local
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------
# VARIABLES DE ENTORNO STRIPE
# -----------------------------------------------------

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_xxxxxxxxxxxxxxxxxxxxx")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_xxxxxxxxxxxxxxxxxxxxx")

# -----------------------------------------------------
# CARGA DE PRODUCTOS CSV
# -----------------------------------------------------

CSV_FILE = "uploadts-1760618195-sec_top_music.csv"

try:
    df = pd.read_csv(CSV_FILE)
    df = df.replace({np.nan: None})
    print(f"✅ {len(df)} productos cargados correctamente desde {CSV_FILE}")
except Exception as e:
    print(f"❌ Error al leer el CSV: {e}")
    df = pd.DataFrame(columns=["id", "title", "price", "link", "image link"])

# -----------------------------------------------------
# ENDPOINT PRINCIPAL
# -----------------------------------------------------

@app.get("/")
async def root():
    return {"message": "Hamelyn GPT Checkout API está viva 🚀"}

# -----------------------------------------------------
# LISTAR PRODUCTOS
# -----------------------------------------------------

@app.get("/productos")
async def listar_productos(limit: int = 10):
    """Devuelve los productos del CSV (limitado por parámetro)."""
    try:
        productos = df.head(limit).to_dict(orient="records")
        return JSONResponse(content=productos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------
# CREAR SESIÓN DE CHECKOUT
# -----------------------------------------------------

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    try:
        data = await request.json()
        product_id = data.get("id")

        if not product_id:
            raise HTTPException(status_code=400, detail="Falta el ID del producto.")

        # Buscar producto
        producto = df[df["id"] == int(product_id)] if product_id.isdigit() else df[df["id"] == product_id]

        if producto.empty:
            raise HTTPException(status_code=404, detail="Producto no encontrado.")

        row = producto.iloc[0]
        title = row["title"]
        price_str = str(row["price"]).replace(" EUR", "").replace(",", ".")
        price = int(float(price_str) * 100)  # convertir a céntimos
        image_url = row["image link"]
        link = row["link"]

        # Crear sesión de Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": title,
                            "images": [image_url],
                            "metadata": {"product_id": str(row["id"])},
                        },
                        "unit_amount": price,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url="https://tienda.hamelyn.com/gracias?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=link,
            metadata={"product_id": str(row["id"]), "product_title": title},
        )

        return {"url": session.url}

    except Exception as e:
        print("❌ Error creando sesión de checkout:", e)
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------
# WEBHOOK STRIPE
# -----------------------------------------------------

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma del webhook inválida")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        print(f"✅ Pago completado: {session.get('id')}")
        # Aquí podrías registrar la venta en una base de datos o Google Sheets

    elif event_type == "checkout.session.expired":
        session = event["data"]["object"]
        print(f"⚠️ Sesión expirada: {session.get('id')}")

    else:
        print(f"Evento recibido: {event_type}")

    return {"status": "success"}

# -----------------------------------------------------
# EJECUCIÓN LOCAL
# -----------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
