#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Smoke test manual untuk endpoint publik foom_attendance.
#
# Dipakai untuk memastikan instance yang SUDAH JALAN berperilaku benar —
# misalnya setelah deploy ke staging, atau setelah mengubah setting di layar
# Settings. Test otomatis ada di folder `tests/` (jalankan dengan
# `--test-enable --test-tags /foom_attendance`); skrip ini melengkapinya,
# bukan menggantikannya.
#
# Pakai:
#   ./smoke_test.sh https://odoo.foom.id F100001 482913 -6.1753924 106.8271528
#
# Argumen 4 & 5 adalah koordinat yang dianggap DI DALAM radius lokasi kerja
# employee tersebut. Kalau dikosongkan, koordinat lokasi harus diisi manual
# di bawah.
#
# PERINGATAN: skrip ini MEMBUAT ABSENSI SUNGGUHAN. Jangan dijalankan di
# database produksi dengan employee sungguhan.
# ---------------------------------------------------------------------------
set -u

BASE_URL="${1:?URL dasar wajib diisi, mis. https://odoo.foom.id}"
CODE="${2:?kode karyawan wajib diisi}"
PIN="${3:?PIN wajib diisi}"
LAT="${4:-}"
LON="${5:-}"

API="${BASE_URL%/}/foom/attendance/api"
PASS=0
FAIL=0

c_ok()   { printf '\033[32m  PASS\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
c_bad()  { printf '\033[31m  FAIL\033[0m %s\n' "$1"; printf '        %s\n' "$2"; FAIL=$((FAIL + 1)); }
head1()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

post() {  # post <path> <json>
  curl -sS -X POST "$API/$1" -H 'Content-Type: application/json' -d "$2"
}

field() { # field <json> <key>
  printf '%s' "$1" | python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print(''); raise SystemExit
v=d
for k in '$2'.split('.'):
    v = v.get(k) if isinstance(v, dict) else None
print('' if v is None else v)"
}

expect_error() { # expect_error <label> <json> <expected error code>
  local got; got=$(field "$2" error)
  if [ "$got" = "$3" ]; then c_ok "$1"; else c_bad "$1" "error='$got' (harusnya '$3') :: $2"; fi
}

expect_ok() { # expect_ok <label> <json>
  local got; got=$(field "$2" ok)
  if [ "$got" = "True" ]; then c_ok "$1"; else c_bad "$1" "$2"; fi
}

# ---------------------------------------------------------------------------
head1 "0. Halaman publik"
CODE_HTTP=$(curl -sS -o /tmp/fa_page.html -w '%{http_code}' "${BASE_URL%/}/foom/attendance")
if [ "$CODE_HTTP" = "200" ] && grep -q 'fa-login-form' /tmp/fa_page.html; then
  c_ok "halaman termuat (HTTP 200, form login ada)"
else
  c_bad "halaman termuat" "HTTP $CODE_HTTP — cek setting 'Halaman Absensi Publik'"
fi
case "$BASE_URL" in
  https://*) c_ok "pakai HTTPS (GPS browser butuh secure origin)" ;;
  *) printf '\033[33m  WARN\033[0m bukan HTTPS — navigator.geolocation tidak akan jalan di HP\n' ;;
esac

head1 "1. Login harus menolak yang salah, dan menolaknya secara seragam"
R_BADPIN=$(post login "{\"code\":\"$CODE\",\"pin\":\"00000000\"}")
expect_error "PIN salah ditolak" "$R_BADPIN" invalid
R_NOCODE=$(post login '{"code":"ZZ_TIDAK_ADA","pin":"00000000"}')
expect_error "kode tidak dikenal ditolak" "$R_NOCODE" invalid
if [ "$R_BADPIN" = "$R_NOCODE" ]; then
  c_ok "kedua respons identik (kode karyawan tidak bisa dienumerasi)"
else
  c_bad "kedua respons identik" "beda respons membocorkan kode mana yang nyata"
fi
R_WILD=$(post login "{\"code\":\"%\",\"pin\":\"$PIN\"}")
expect_error "wildcard '%' tidak cocok ke siapa pun" "$R_WILD" invalid

head1 "2. Login benar"
R_LOGIN=$(post login "{\"code\":\"$CODE\",\"pin\":\"$PIN\"}")
TOKEN=$(field "$R_LOGIN" token)
if [ -n "$TOKEN" ]; then
  c_ok "dapat token ($(printf '%s' "$TOKEN" | wc -c) karakter)"
else
  c_bad "dapat token" "$R_LOGIN"
  printf '\nTidak bisa lanjut tanpa token. Kalau errornya "throttled", tunggu\nmasa kunci habis atau tekan "Buka Kunci" di form employee.\n'
  exit 1
fi

head1 "3. State"
R_STATE=$(post state "{\"token\":\"$TOKEN\"}")
expect_ok "state terbaca" "$R_STATE"
printf '        employee : %s\n' "$(field "$R_STATE" employee.name)"
printf '        status   : %s\n' "$(field "$R_STATE" state)"
printf '        shift    : %s (%s - %s)\n' \
  "$(field "$R_STATE" schedule.shift_name)" \
  "$(field "$R_STATE" schedule.planned_in)" \
  "$(field "$R_STATE" schedule.planned_out)"
printf '        kebijakan: %s\n' "$(field "$R_STATE" geofence.policy)"
printf '        zona     : %s | jam server: %s\n' \
  "$(field "$R_STATE" timezone)" "$(field "$R_STATE" server_time)"

R_BADTOK=$(post state '{"token":"xxxxxxxxxxxxxxxxxxxxxxxx"}')
expect_error "token palsu ditolak" "$R_BADTOK" unauthorized

head1 "4. Geofence"
POLICY=$(field "$R_STATE" geofence.policy)
if [ "$POLICY" = "off" ]; then
  printf '\033[33m  SKIP\033[0m kebijakan employee ini "off" — uji geofence dilewati\n'
else
  R_FAR=$(post punch "{\"token\":\"$TOKEN\",\"action\":\"in\",\"latitude\":-7.797068,\"longitude\":110.370529,\"accuracy\":10}")
  E_FAR=$(field "$R_FAR" error)
  case "$E_FAR" in
    outside_geofence) c_ok "titik jauh (Yogyakarta) ditolak" ;;
    reason_required)  c_ok "titik jauh minta alasan (kebijakan 'warn')" ;;
    *) c_bad "titik jauh ditolak" "error='$E_FAR' :: $R_FAR" ;;
  esac

  R_NOACC=$(post punch "{\"token\":\"$TOKEN\",\"action\":\"in\",\"latitude\":${LAT:-0},\"longitude\":${LON:-0}}")
  E_NOACC=$(field "$R_NOACC" error)
  if [ "$E_NOACC" = "bad_accuracy" ] || [ "$E_NOACC" = "no_location" ]; then
    c_ok "request tanpa 'accuracy' ditolak (ambang tidak bisa dilewati)"
  else
    c_bad "request tanpa 'accuracy' ditolak" "error='$E_NOACC' :: $R_NOACC"
  fi

  R_NULL=$(post punch "{\"token\":\"$TOKEN\",\"action\":\"in\",\"latitude\":0,\"longitude\":0,\"accuracy\":10}")
  expect_error "koordinat 0,0 ditolak" "$R_NULL" no_location
fi

head1 "5. Clock in / clock out sungguhan"
if [ -z "$LAT" ] || [ -z "$LON" ]; then
  printf '\033[33m  SKIP\033[0m koordinat tidak diberikan — jalankan ulang dengan argumen 4 & 5\n'
else
  R_IN=$(post punch "{\"token\":\"$TOKEN\",\"action\":\"in\",\"latitude\":$LAT,\"longitude\":$LON,\"accuracy\":10}")
  if [ "$(field "$R_IN" ok)" = "True" ]; then
    c_ok "clock in ($(field "$R_IN" message), jarak $(field "$R_IN" distance_m) m)"
    ATT_ID=$(field "$R_IN" attendance_id)

    R_DUP=$(post punch "{\"token\":\"$TOKEN\",\"action\":\"in\",\"latitude\":$LAT,\"longitude\":$LON,\"accuracy\":10}")
    expect_error "clock in kedua ditolak" "$R_DUP" state_mismatch

    printf '        menunggu jeda antar punch...\n'
    sleep 62
    R_OUT=$(post punch "{\"token\":\"$TOKEN\",\"action\":\"out\",\"latitude\":$LAT,\"longitude\":$LON,\"accuracy\":10}")
    if [ "$(field "$R_OUT" ok)" = "True" ]; then
      c_ok "clock out ($(field "$R_OUT" message))"
      printf '        Periksa Attendances > Overview, baris id=%s:\n' "$ATT_ID"
      printf '        jarak masuk/pulang, Telat, Posisi Terukur, dan koordinat harus terisi.\n'
    else
      c_bad "clock out" "$R_OUT"
    fi
  else
    c_bad "clock in" "$R_IN — pastikan koordinat memang di dalam radius"
  fi
fi

head1 "6. Logout"
post logout "{\"token\":\"$TOKEN\"}" >/dev/null
expect_error "token mati setelah logout" "$(post state "{\"token\":\"$TOKEN\"}")" unauthorized

# ---------------------------------------------------------------------------
printf '\n\033[1mHasil: %d pass, %d fail\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
