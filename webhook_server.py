from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os

app = FastAPI()

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "clio-autotrading-hooks")


@app.post("/hooks/whatsapp_outbound")
async def whatsapp_outbound(request: Request):
    """Webhook endpoint to receive WhatsApp notifications.

    Expected:
      - Query param: ?token=WEBHOOK_TOKEN
      - JSON body: {"to": "628170090022", "message": "text"}
    """
    # 1) Auth by token
    token = request.query_params.get("token")
    if not token or token != WEBHOOK_TOKEN:
        # Jangan log tokennya
        raise HTTPException(status_code=401, detail="Invalid token")

    # 2) Parse JSON body
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    to = payload.get("to")
    message = payload.get("message")

    if not to or not message:
        raise HTTPException(status_code=400, detail="'to' and 'message' are required")

    # 3) TODO: kirim via OpenClaw / WhatsApp.
    # Untuk sekarang, kita log ke stdout dulu sebagai placeholder.
    print(f"[WEBHOOK WHATSAPP] to={to} message={message!r}")

    # Di langkah berikutnya, fungsi ini akan dipasangi integrasi ke OpenClaw
    # (misalnya lewat CLI atau HTTP API lokal) untuk benar-benar mengirim WhatsApp.

    return JSONResponse({"status": "ok"})
