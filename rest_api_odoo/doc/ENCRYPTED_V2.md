# Endpoint terenkripsi (v2)

| v1 | v2 (body POST terenkripsi) |
|---|---|
| `/api/pos/membership` | `/api/pos/v2/membership` |
| `/api/pos/order` | `/api/pos/v2/order` |
| `/api/pos/order/pay` | `/api/pos/v2/order/pay` |
| `/api/pos/coupons/validate` | `/api/pos/v2/coupons/validate` |

Proses, validasi, dan response sama dengan v1 (logikanya dipakai bersama).
`GET` pada v2 tidak punya body, jadi parameternya tetap query string biasa.
`/coupons/validate` tetap butuh header `api-key` seperti v1.

## Perbedaan `/api/pos/v2/order/pay`

- **id order ada di body terenkripsi** (`{"id": 123, "session_id": ..., "amount": ...}`),
  bukan `?id=`. Di v1 id ada di query string sehingga bisa diubah bebas;
  query string v2 diabaikan.
- Hanya order **draft** yang bisa dibayar (409 `ORDER_NOT_DRAFT` selain itu).
  v1 membiarkan order yang sudah paid dibayar lagi.
- `bill_id` harus milik POS yang sama dengan order dan belum terhubung ke order
  lain (409 `BILL_MISMATCH`).

## Anti-replay

Satu amplop hanya diproses sekali (IV dicatat di `pos.payload.nonce`); kirim
ulang amplop yang sama menjawab 409. **FE harus mengenkripsi ulang (IV + ts
baru) pada setiap percobaan**, termasuk retry setelah timeout.

## Setup server

Buat kunci 32 byte, simpan base64-nya di *Settings → Technical → System Parameters*:

```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

| Key | Isi |
|---|---|
| `pos_payload_key` | base64 dari 32 byte (wajib) |
| `pos_payload_ttl` | jendela waktu detik (opsional, default 300) |

## Amplop

```json
{"iv": "<base64 12 byte>", "ct": "<base64 ciphertext+tag>", "ts": 1730000000000}
```

AES-256-GCM. AAD = `"<ts>|<path>"` (path persis, mis. `/api/pos/v2/order`).

## Contoh FE (WebCrypto)

```js
const KEY_B64 = "...";  // sama dengan pos_payload_key

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function encryptPayload(path, payload) {
  const key = await crypto.subtle.importKey(
    "raw", unb64(KEY_B64), "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ts = Date.now();
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: new TextEncoder().encode(`${ts}|${path}`) },
    key,
    new TextEncoder().encode(JSON.stringify(payload)),
  );
  return { iv: b64(iv), ct: b64(ct), ts };
}

const path = "/api/pos/v2/order";
const res = await fetch(BASE_URL + path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(await encryptPayload(path, orderBody)),
});
```

WebCrypto hanya tersedia di konteks aman (HTTPS atau localhost).
