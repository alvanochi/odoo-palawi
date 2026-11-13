# -*- coding: utf-8 -*-
"""Klien HTTP untuk API Union Kuliner Econique (login + transaction).

Tidak meng-import odoo. Tidak pernah men-log body, password, atau token.
"""
import logging

import requests

_logger = logging.getLogger(__name__)

LOGIN_PATH = "/api/kuliner/login"
TRANSACTION_PATH = "/api/kuliner/transaction"


class EconiqueError(Exception):
    pass


class EconiqueNetworkError(EconiqueError):
    """Timeout / koneksi gagal: aman untuk dicoba lagi."""


class EconiqueLoginError(EconiqueError):
    pass


class EconiqueClient:
    def __init__(self, base_url, username, password, basic_auth=None, timeout=20):
        """basic_auth: tuple (user, password) untuk header Basic pada login, atau None."""
        self.base_url = (base_url or "").rstrip("/")
        self.username = username
        self.password = password
        self.basic_auth = basic_auth
        self.timeout = timeout

    def _post(self, path, json, headers=None, auth=None):
        """-> (http_status, data dict, text). Raise EconiqueNetworkError."""
        url = self.base_url + path
        try:
            res = requests.post(
                url, json=json, headers=headers, auth=auth, timeout=self.timeout)
        except requests.RequestException as e:
            _logger.warning("Econique %s gagal terhubung: %s", path, type(e).__name__)
            raise EconiqueNetworkError("%s: %s" % (type(e).__name__, e))
        try:
            data = res.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return res.status_code, data, res.text or ""

    def login(self):
        """-> access_token. Raise EconiqueLoginError / EconiqueNetworkError."""
        status, data, text = self._post(
            LOGIN_PATH,
            json={"username": self.username, "password": self.password},
            auth=self.basic_auth,
        )
        token = data.get("access_token")
        ok = 200 <= status < 300 and str(data.get("status", "")).lower() == "success"
        if not (ok and token):
            raise EconiqueLoginError(
                "Login gagal (HTTP %s): %s" % (status, data.get("message") or text[:200]))
        return token

    def post_transaction(self, token, payload):
        """-> (http_status, data dict, text)."""
        return self._post(
            TRANSACTION_PATH,
            json=payload,
            headers={"Authorization": "Bearer %s" % token, "Accept": "application/json"},
        )
