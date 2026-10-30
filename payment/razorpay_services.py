import uuid

import requests

from django.conf import settings


class RazorpayAPIError(RuntimeError):
    """An error returned by the Razorpay Orders or Payments API."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class RazorpayService:
    BASE_URL = "https://api.razorpay.com/v1"

    @classmethod
    def _credentials(cls):
        key_id = str(getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
        key_secret = str(getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
        if not key_id or not key_secret:
            raise RazorpayAPIError("Razorpay test credentials are not configured.")
        return key_id, key_secret

    @classmethod
    def _request(cls, method, path, *, json=None):
        key_id, key_secret = cls._credentials()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
        }
        try:
            response = requests.request(
                method,
                f"{cls.BASE_URL}{path}",
                auth=(key_id, key_secret),
                headers=headers,
                json=json,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RazorpayAPIError("Razorpay is temporarily unavailable.") from exc

        try:
            response_body = response.json()
        except ValueError:
            response_body = {"detail": response.text[:500]}

        if not response.ok:
            raise RazorpayAPIError(
                "Razorpay rejected the payment request.",
                status_code=response.status_code,
                response_body=response_body,
            )
        return response_body

    @classmethod
    def create_order(cls, *, amount, currency, receipt, notes=None):
        return cls._request(
            "POST",
            "/orders",
            json={
                "amount": int(amount),
                "currency": currency,
                "receipt": str(receipt)[:40],
                "partial_payment": False,
                "notes": notes or {},
            },
        )

    @classmethod
    def fetch_payment(cls, payment_id):
        return cls._request("GET", f"/payments/{payment_id}")
