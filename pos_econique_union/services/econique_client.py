# -*- coding: utf-8 -*-
"""HTTP client for the Union Kuliner Econique API (login + transaction).

Does not import odoo. Never logs request bodies, passwords or tokens.
"""
import logging

import requests

_logger = logging.getLogger(__name__)

LOGIN_PATH = "/api/kuliner/login"
TRANSACTION_PATH = "/api/kuliner/transaction"


class EconiqueError(Exception):
    pass


class EconiqueNetworkError(EconiqueError):
    """Timeout / connection failure: safe to retry."""


class EconiqueLoginError(EconiqueError):
    pass


class EconiqueClient:
    def __init__(self, base_url, username, password, basic_auth=None, timeout=20):
        """basic_auth: (user, password) tuple for the Basic header on login, or None."""
        self.base_url = (base_url or "").rstrip("/")
        self.username = username
        self.password = password
        self.basic_auth = basic_auth
        self.timeout = timeout

    def _post(self, path, json, headers=None, auth=None):
        """-> (http_status, data dict, text). Raises EconiqueNetworkError."""
        url = self.base_url + path
        try:
            res = requests.post(
                url, json=json, headers=headers, auth=auth, timeout=self.timeout)
        except requests.RequestException as e:
            _logger.warning("Econique %s connection failed: %s", path, type(e).__name__)
            raise EconiqueNetworkError("%s: %s" % (type(e).__name__, e))
        try:
            data = res.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return res.status_code, data, res.text or ""

    def login(self):
        """-> access_token. Raises EconiqueLoginError / EconiqueNetworkError."""
        status, data, text = self._post(
            LOGIN_PATH,
            json={"username": self.username, "password": self.password},
            auth=self.basic_auth,
        )
        token = data.get("access_token")
        ok = 200 <= status < 300 and str(data.get("status", "")).lower() == "success"
        if not (ok and token):
            raise EconiqueLoginError(
                "Login failed (HTTP %s): %s" % (status, data.get("message") or text[:200]))
        return token

    def post_transaction(self, token, payload):
        """-> (http_status, data dict, text)."""
        return self._post(
            TRANSACTION_PATH,
            json=payload,
            headers={"Authorization": "Bearer %s" % token, "Accept": "application/json"},
        )
