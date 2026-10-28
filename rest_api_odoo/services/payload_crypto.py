# -*- coding: utf-8 -*-
"""Dekripsi payload terenkripsi dari frontend POS (endpoint /api/pos/v2/*).

Amplop yang dikirim FE (body JSON):

    {"iv": "<base64, 12 byte>", "ct": "<base64, ciphertext+tag>", "ts": <epoch ms>}

Cipher AES-256-GCM (format keluaran WebCrypto: tag 16 byte menempel di ujung
ciphertext). AAD = "<ts>|<path>", sehingga timestamp dan endpoint ikut
terautentikasi: amplop untuk /order tidak bisa dipakai ulang ke /membership,
dan ts tidak bisa diubah tanpa merusak tag.

Kunci: ir.config_parameter `pos_payload_key` (base64 dari 32 byte acak).
Jendela waktu: `pos_payload_ttl` detik (default 300).

Anti-replay: IV setiap amplop dicatat di `pos.payload.nonce`; amplop yang sama
ditolak (409) kalau dikirim ulang. FE harus mengenkripsi ulang (IV + ts baru)
untuk setiap percobaan, termasuk retry setelah timeout.
"""
import base64
import binascii
import json
import random
import time
from datetime import timedelta

import psycopg2
from odoo import fields

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_PARAM = "pos_payload_key"
TTL_PARAM = "pos_payload_ttl"
DEFAULT_TTL = 300


class PayloadError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _load_key(env):
    raw = env["ir.config_parameter"].sudo().get_param(KEY_PARAM)
    if not raw:
        raise PayloadError("Encrypted payload is not configured on the server", 500)
    try:
        key = base64.b64decode(raw)
    except (binascii.Error, ValueError):
        raise PayloadError("Server payload key is invalid", 500)
    if len(key) != 32:
        raise PayloadError("Server payload key must be 32 bytes", 500)
    return key


def _b64(value, name):
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise PayloadError("Invalid encrypted payload: '%s' is not base64" % name)


def decrypt_body(env, raw, path):
    """raw: bytes body request. -> dict hasil dekripsi. Raise PayloadError."""
    try:
        envelope = json.loads((raw or b"").decode("utf-8"))
    except Exception:
        raise PayloadError("Invalid JSON body")
    if not isinstance(envelope, dict):
        raise PayloadError("Invalid encrypted payload")

    iv, ct, ts = envelope.get("iv"), envelope.get("ct"), envelope.get("ts")
    if not iv or not ct or ts is None:
        raise PayloadError("Encrypted payload requires 'iv', 'ct' and 'ts'")
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        raise PayloadError("Invalid 'ts'")

    key = _load_key(env)

    try:
        ttl = int(env["ir.config_parameter"].sudo().get_param(TTL_PARAM) or DEFAULT_TTL)
    except ValueError:
        ttl = DEFAULT_TTL
    if abs(time.time() - ts / 1000.0) > ttl:
        raise PayloadError("Encrypted payload expired", 400)

    iv_bytes = _b64(iv, "iv")
    if len(iv_bytes) != 12:
        raise PayloadError("Invalid encrypted payload: 'iv' must be 12 bytes")

    aad = ("%d|%s" % (ts, path)).encode("utf-8")
    try:
        plain = AESGCM(key).decrypt(iv_bytes, _b64(ct, "ct"), aad)
    except InvalidTag:
        # kunci salah, data diubah, atau ts/path tidak cocok -- sengaja tidak dibedakan
        raise PayloadError("Unable to decrypt payload", 400)

    try:
        body = json.loads(plain.decode("utf-8"))
    except Exception:
        raise PayloadError("Decrypted payload is not valid JSON")
    if not isinstance(body, dict):
        raise PayloadError("Decrypted payload must be a JSON object")

    # Terakhir: nonce baru dicatat setelah amplop terbukti asli, supaya
    # amplop sampah tidak memenuhi tabel.
    _consume_nonce(env, iv, ttl)
    return body


def _consume_nonce(env, iv, ttl):
    """Satu amplop hanya boleh dipakai sekali. Dicatat di transaksi request
    yang sama: kalau request gagal dan di-rollback, amplopnya belum "terpakai"."""
    Nonce = env["pos.payload.nonce"].sudo()
    try:
        with env.cr.savepoint():
            Nonce.create({"iv": iv})
    except psycopg2.IntegrityError:
        raise PayloadError("Encrypted payload already used", 409)

    # Bersihkan baris lama sesekali (amplop lebih tua dari 2x TTL sudah pasti
    # ditolak karena kedaluwarsa, jadi nonce-nya tidak perlu disimpan lagi).
    if random.random() < 0.02:
        cutoff = fields.Datetime.now() - timedelta(seconds=2 * ttl)
        env.cr.execute("DELETE FROM pos_payload_nonce WHERE ts < %s", (cutoff,))
