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

@app.head("/")
async def root_head():
    """Responde al método HEAD para los monitores (200 OK)."""
    return JSONResponse(status_code=200, content=None)


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
# CREAR SESIÓN DE CHECKOUT (DINÁMICA)
# -----------------------------------------------------

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    try:
        data = await request.json()
        product_id = data.get("id") or data.get("product_id")

        if not product_id:
            raise HTTPException(status_code=400, detail="Falta el ID del producto.")

        # Buscar producto en el CSV (id puede ser string o número)
        producto = df[df["id"].astype(str) == str(product_id)]

        if producto.empty:
            raise HTTPException(status_code=404, detail="Producto no encontrado.")

        row = producto.iloc[0]
        title = str(row["title"])
        link = str(row["link"])
        image_url = str(row["image link"])
        price_str = str(row["price"]).replace("EUR", "").replace("€", "").replace(",", ".").strip()

        # Validar precio
        try:
            price_value = int(float(price_str) * 100)  # céntimos
        except Exception:
            raise HTTPException(status_code=400, detail=f"Precio inválido: {price_str}")

        # Crear sesión de Stripe SIN depender del catálogo
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": price_value,
                        "product_data": {
                            "name": title,
                            "images": [image_url],
                            "metadata": {"product_id": str(product_id), "link": link},
                        },
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url="https://tienda.hamelyn.com/gracias?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=link,
            metadata={"product_id": str(product_id), "product_title": title},
        )

        print(f"✅ Sesión de checkout creada correctamente para {title} ({product_id})")
        return {"url": session.url}

    except Exception as e:
        print("❌ Error creando sesión de checkout:", str(e))
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
        print(f"✅ Pago completado: {session.get('id')} | Producto: {session.get('metadata', {}).get('product_title')}")

    elif event_type == "checkout.session.expired":
        session = event["data"]["object"]
        print(f"⚠️ Sesión expirada: {session.get('id')}")

    else:
        print(f"ℹ️ Evento recibido: {event_type}")

    return {"status": "success"}

# -----------------------------------------------------
# EJECUCIÓN LOCAL
# -----------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))