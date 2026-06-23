import base64
import json
import os
import urllib.error
import urllib.request

TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY")


def confirm_payment(payment_key, order_id, amount):
    secret_key = f"{TOSS_SECRET_KEY}:"

    encoded_key = base64.b64encode(
        secret_key.encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {encoded_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "paymentKey": payment_key,
        "orderId": order_id,
        "amount": amount,
    }

    request = urllib.request.Request(
        "https://api.tosspayments.com/v1/payments/confirm",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            raise Exception(error_body) from exc
