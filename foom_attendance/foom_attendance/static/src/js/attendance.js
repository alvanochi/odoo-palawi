/* Foom Attendance — halaman absensi publik.
 * Vanilla JS, tanpa dependency. Semua keputusan (geofence, telat, shift)
 * diputuskan ulang di server; kode di sini hanya untuk tampilan & UX.
 */
(function () {
    "use strict";

    var API = "/foom/attendance/api";
    var STORE_KEY = "foom_attendance_token";

    var state = {
        token: null,
        remember: true,
        data: null,
        position: null,
        positionError: null,
        watchId: null,
        photo: null,
        photoStatus: null,   // alasan kalau kamera gagal: denied / no_camera / ...
        stream: null,
        busy: false,
        clockOffsetMs: 0,
        tz: null,
    };

    // ---------------------------------------------------------------- utils
    function $(id) { return document.getElementById(id); }

    function show(el, visible) {
        if (!el) { return; }
        if (visible) { el.removeAttribute("hidden"); }
        else { el.setAttribute("hidden", "hidden"); }
    }

    function setText(id, text) {
        var el = $(id);
        if (el) { el.textContent = text == null ? "" : String(text); }
    }

    function alertBox(id, text, kind) {
        var el = $(id);
        if (!el) { return; }
        el.className = "fa-alert" + (kind ? " fa-alert-" + kind : "");
        el.textContent = text || "";
        show(el, !!text);
    }

    function readStoredToken() {
        try { return window.localStorage.getItem(STORE_KEY); }
        catch (e) { return null; }
    }

    function writeStoredToken(token) {
        try {
            if (token) { window.localStorage.setItem(STORE_KEY, token); }
            else { window.localStorage.removeItem(STORE_KEY); }
        } catch (e) { /* mode privat / storage diblokir — abaikan */ }
    }

    function post(path, payload) {
        return fetch(API + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload || {}),
            credentials: "same-origin",
        }).then(function (response) {
            return response.json().catch(function () {
                return { ok: false, error: "bad_response", message: "Server tidak merespons dengan benar." };
            });
        });
    }

    function haversine(lat1, lon1, lat2, lon2) {
        var R = 6371008.8;
        var toRad = Math.PI / 180;
        var dPhi = (lat2 - lat1) * toRad;
        var dLam = (lon2 - lon1) * toRad;
        var a = Math.sin(dPhi / 2) * Math.sin(dPhi / 2) +
            Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) *
            Math.sin(dLam / 2) * Math.sin(dLam / 2);
        return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
    }

    // ---------------------------------------------------------------- clock
    function startClock() {
        function tick() {
            var now = new Date(Date.now() + state.clockOffsetMs);
            var hh = String(now.getHours()).padStart(2, "0");
            var mm = String(now.getMinutes()).padStart(2, "0");
            var ss = String(now.getSeconds()).padStart(2, "0");
            setText("fa-time", hh + ":" + mm + ":" + ss);
            setText("fa-date", now.toLocaleDateString("id-ID", {
                weekday: "long", day: "numeric", month: "long", year: "numeric",
            }));
        }
        tick();
        window.setInterval(tick, 1000);
    }

    function syncClock(serverTimeString) {
        // "YYYY-MM-DD HH:MM:SS" sudah dalam zona waktu employee; kita hanya
        // memakainya untuk mengoreksi jam perangkat yang meleset.
        if (!serverTimeString) { return; }
        var parts = serverTimeString.replace(" ", "T");
        var parsed = new Date(parts);
        if (!isNaN(parsed.getTime())) {
            state.clockOffsetMs = parsed.getTime() - Date.now();
        }
    }

    // ------------------------------------------------------------- location
    function startWatch() {
        if (!navigator.geolocation) {
            state.positionError = "Perangkat ini tidak mendukung GPS.";
            renderGeo();
            return;
        }
        if (state.watchId !== null) { return; }
        state.watchId = navigator.geolocation.watchPosition(
            function (pos) {
                state.position = pos;
                state.positionError = null;
                renderGeo();
            },
            function (err) {
                var messages = {
                    1: "Akses lokasi ditolak. Izinkan lokasi di pengaturan browser.",
                    2: "Lokasi tidak terbaca. Pastikan GPS menyala.",
                    3: "Pencarian lokasi terlalu lama.",
                };
                state.positionError = messages[err.code] || "Lokasi tidak tersedia.";
                renderGeo();
            },
            { enableHighAccuracy: true, timeout: 20000, maximumAge: 5000 }
        );
    }

    function stopWatch() {
        if (state.watchId !== null && navigator.geolocation) {
            navigator.geolocation.clearWatch(state.watchId);
        }
        state.watchId = null;
        state.position = null;
    }

    function nearestLocation() {
        var data = state.data;
        if (!data || !data.geofence || !data.geofence.locations.length) { return null; }
        if (!state.position) { return { location: data.geofence.locations[0], distance: null }; }
        var coords = state.position.coords;
        var best = null;
        data.geofence.locations.forEach(function (loc) {
            var dist = haversine(coords.latitude, coords.longitude, loc.latitude, loc.longitude);
            if (!best || dist < best.distance) { best = { location: loc, distance: dist }; }
        });
        return best;
    }

    // ---------------------------------------------------------------- render
    // server memakai kebijakan lokasi TERDEKAT; ikuti supaya pesan di layar
    // tidak bertentangan dengan keputusan server saat tombol ditekan
    function effectivePolicy(near) {
        var data = state.data;
        if (!data) { return "off"; }
        return (near && near.location.policy) || data.geofence.policy;
    }

    function renderGeo() {
        var data = state.data;
        if (!data) { return; }
        var near = nearestLocation();
        var policy = effectivePolicy(near);

        setText("fa-location", near ? near.location.name : (policy === "off" ? "Bebas" : "Belum diatur"));

        if (policy === "off") {
            setText("fa-distance", "tidak dicek");
            alertBox("fa-geo-warn", "", null);
            show($("fa-extra"), false);
            updatePunchButton();
            return;
        }

        if (state.positionError) {
            setText("fa-distance", "—");
            alertBox("fa-geo-warn", state.positionError, "danger");
            updatePunchButton();
            return;
        }
        if (!state.position) {
            setText("fa-distance", "mengukur…");
            alertBox("fa-geo-warn", "", null);
            updatePunchButton();
            return;
        }

        var accuracy = Math.round(state.position.coords.accuracy || 0);
        var maxAcc = data.options.max_accuracy_m || 0;

        if (!near) {
            setText("fa-distance", "±" + accuracy + " m akurasi");
            alertBox("fa-geo-warn", "Belum ada lokasi kerja yang ditetapkan untuk kamu.", "warn");
            updatePunchButton();
            return;
        }

        var dist = Math.round(near.distance);
        var radius = near.location.radius_m;
        setText("fa-distance", dist + " m / " + radius + " m (±" + accuracy + " m)");

        var outside = dist > radius;
        if (maxAcc > 0 && accuracy > maxAcc) {
            alertBox("fa-geo-warn",
                "Akurasi GPS " + accuracy + " m terlalu rendah (maks " + maxAcc +
                " m). Pindah ke tempat terbuka.", "warn");
        } else if (outside && policy === "block") {
            alertBox("fa-geo-warn",
                "Kamu di luar radius " + near.location.name + ". Clock in/out akan ditolak.", "danger");
        } else if (outside) {
            alertBox("fa-geo-warn",
                "Kamu di luar radius " + near.location.name + ". Absensi tetap dicatat dan ditandai.", "warn");
        } else {
            alertBox("fa-geo-warn", "", null);
        }

        show($("fa-extra"), outside && data.options.require_reason_outside);
        updatePunchButton();
    }

    function updatePunchButton() {
        var btn = $("fa-punch");
        var data = state.data;
        if (!btn || !data) { return; }
        var checkedIn = data.state === "checked_in";

        if (data.day_done && !checkedIn) {
            btn.textContent = "Absensi hari ini selesai";
            btn.className = "fa-btn fa-btn-big fa-btn-done";
            btn.disabled = true;
            return;
        }

        btn.textContent = state.busy ? "Mengirim…" : (checkedIn ? "Clock Out" : "Clock In");
        btn.className = "fa-btn fa-btn-big " + (checkedIn ? "fa-btn-out" : "fa-btn-in");

        var blocked = state.busy;
        if (effectivePolicy(nearestLocation()) !== "off") {
            if (state.positionError || !state.position) { blocked = true; }
        }
        btn.disabled = blocked;
    }

    function checkedInNow() {
        return !!state.data && state.data.state === "checked_in";
    }

    function render() {
        var data = state.data;
        if (!data) { return; }
        show($("fa-login"), false);
        show($("fa-home"), true);

        setText("fa-name", data.employee.name);
        setText("fa-job", [data.employee.job, data.employee.department].filter(Boolean).join(" · "));
        var avatar = $("fa-avatar");
        if (avatar) {
            if (data.employee.avatar) { avatar.src = data.employee.avatar; }
            else { avatar.removeAttribute("src"); }
        }

        var pill = $("fa-state");
        if (pill) {
            var checkedIn = data.state === "checked_in";
            pill.textContent = checkedIn ? "Sedang bekerja" : "Belum masuk";
            pill.className = "fa-pill " + (checkedIn ? "fa-pill-in" : "fa-pill-out");
        }

        var sched = data.schedule;
        var shiftLabel = sched.day_off ? "Libur" : (sched.shift_name || "Tidak ada jadwal");
        if (!sched.day_off && sched.planned_in) {
            shiftLabel = sched.shift_name;
        }
        setText("fa-shift", shiftLabel);

        var wantPhoto = !!data.options.require_photo && !(data.day_done && !checkedInNow());
        show($("fa-photo-box"), wantPhoto);
        if (wantPhoto) { startCamera(); } else { stopCamera(); }

        var list = $("fa-today");
        if (list) {
            list.innerHTML = "";
            if (!data.today.length) {
                var empty = document.createElement("li");
                empty.className = "fa-muted";
                empty.textContent = "Belum ada catatan.";
                list.appendChild(empty);
            } else {
                data.today.forEach(function (line) {
                    var li = document.createElement("li");
                    var right = document.createElement("span");
                    var left = document.createElement("span");
                    left.textContent = line.check_in + " → " + (line.check_out || "…");
                    var bits = [];
                    if (line.worked_hours) { bits.push(line.worked_hours.toFixed(2) + " j"); }
                    if (line.late_minutes) { bits.push("telat " + line.late_minutes + "m"); }
                    if (line.outside) { bits.push("di luar radius"); }
                    right.className = "fa-muted";
                    right.textContent = bits.join(" · ");
                    li.appendChild(left);
                    li.appendChild(right);
                    list.appendChild(li);
                });
            }
        }

        renderGeo();
    }

    // ---------------------------------------------------------------- kamera
    //
    // Selfie diambil LANGSUNG dari kamera (getUserMedia), bukan lewat
    // <input type="file">. Atribut `capture` pada input file cuma saran — di
    // banyak browser employee tetap bisa memilih foto lama dari galeri.
    //
    // Kalau kamera tidak bisa dipakai, absensi tetap boleh jalan tetapi
    // alasannya dikirim ke server dan barisnya ditandai untuk audit HR.

    function camMessage(text) {
        var idle = $("fa-cam-idle");
        if (idle) { idle.textContent = text || ""; show(idle, !!text); }
    }

    function stopCamera() {
        if (state.stream) {
            state.stream.getTracks().forEach(function (track) { track.stop(); });
        }
        state.stream = null;
        var video = $("fa-cam");
        if (video) { video.srcObject = null; }
    }

    function cameraFailed(reason, message) {
        state.photoStatus = reason;
        stopCamera();
        show($("fa-cam"), false);
        camMessage("");
        show($("fa-shoot"), false);
        show($("fa-retake"), false);
        alertBox("fa-cam-error", message, "warn");
        updatePunchButton();
    }

    function startCamera() {
        if (!state.data || !state.data.options.require_photo) { return; }
        if (state.stream || state.photo) { return; }

        show($("fa-photo-preview"), false);
        show($("fa-cam"), true);
        show($("fa-shoot"), true);
        show($("fa-retake"), false);
        alertBox("fa-cam-error", "", null);
        camMessage("Menyalakan kamera…");

        if (!window.isSecureContext) {
            cameraFailed("insecure",
                "Kamera hanya bisa dipakai lewat HTTPS. Absensi tetap bisa dilanjutkan, " +
                "tapi akan ditandai tanpa foto.");
            return;
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            cameraFailed("no_camera",
                "Browser ini tidak mendukung kamera. Absensi ditandai tanpa foto.");
            return;
        }

        navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 720 } },
            audio: false,
        }).then(function (stream) {
            state.stream = stream;
            state.photoStatus = null;
            var video = $("fa-cam");
            video.srcObject = stream;
            video.play().catch(function () { /* autoplay diblokir — abaikan */ });
            camMessage("");
            updatePunchButton();
        }).catch(function (err) {
            var reason = "failed";
            var text = "Kamera tidak bisa dibuka. Absensi ditandai tanpa foto.";
            if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) {
                reason = "denied";
                text = "Izin kamera ditolak. Absensi tetap bisa dilanjutkan, tapi akan " +
                       "ditandai tanpa foto — HR bisa melihat tanda ini.";
            } else if (err && (err.name === "NotFoundError" || err.name === "OverconstrainedError")) {
                reason = "no_camera";
                text = "Tidak ada kamera yang terdeteksi. Absensi ditandai tanpa foto.";
            }
            cameraFailed(reason, text);
        });
    }

    function capturePhoto() {
        var video = $("fa-cam");
        if (!video || !video.videoWidth) {
            camMessage("Kamera belum siap, tunggu sebentar…");
            return;
        }
        var max = 720;
        var scale = Math.min(1, max / Math.max(video.videoWidth, video.videoHeight));
        var canvas = document.createElement("canvas");
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

        state.photo = canvas.toDataURL("image/jpeg", 0.7);
        state.photoStatus = null;
        stopCamera();

        var preview = $("fa-photo-preview");
        if (preview) { preview.src = state.photo; show(preview, true); }
        show($("fa-cam"), false);
        show($("fa-shoot"), false);
        show($("fa-retake"), true);
        camMessage("");
        updatePunchButton();
    }

    function retakePhoto() {
        state.photo = null;
        show($("fa-photo-preview"), false);
        startCamera();
    }

    // ---------------------------------------------------------------- flows
    function applyPayload(payload) {
        state.data = payload;
        syncClock(payload.server_time);
        render();
    }

    function doLogin(event) {
        event.preventDefault();
        var code = $("fa-code").value.trim();
        var pin = $("fa-pin").value.trim();
        state.remember = $("fa-remember").checked;
        alertBox("fa-login-error", "", null);
        var btn = $("fa-login-btn");
        btn.disabled = true;
        btn.textContent = "Memeriksa…";

        post("/login", { code: code, pin: pin }).then(function (res) {
            btn.disabled = false;
            btn.textContent = "Masuk";
            if (!res.ok) {
                alertBox("fa-login-error", res.message || "Gagal masuk.", "danger");
                return;
            }
            state.token = res.token;
            if (state.remember) { writeStoredToken(res.token); }
            $("fa-pin").value = "";
            applyPayload(res);
            startWatch();
        }).catch(function () {
            btn.disabled = false;
            btn.textContent = "Masuk";
            alertBox("fa-login-error", "Tidak bisa menghubungi server.", "danger");
        });
    }

    function doLogout() {
        var token = state.token;
        state.token = null;
        state.data = null;
        state.photo = null;
        state.photoStatus = null;
        writeStoredToken(null);
        stopWatch();
        stopCamera();
        show($("fa-home"), false);
        show($("fa-login"), true);
        if (token) { post("/logout", { token: token }); }
    }

    function refreshState() {
        if (!state.token) { return Promise.resolve(); }
        return post("/state", { token: state.token }).then(function (res) {
            if (!res.ok) {
                if (res.error === "unauthorized" || res.error === "disabled_employee") {
                    doLogout();
                    alertBox("fa-login-error", res.message || "Sesi berakhir.", "warn");
                }
                return;
            }
            applyPayload(res);
        });
    }

    function doPunch() {
        if (state.busy || !state.data) { return; }
        state.busy = true;
        updatePunchButton();
        alertBox("fa-msg", "", null);

        var payload = {
            token: state.token,
            action: state.data.state === "checked_in" ? "out" : "in",
            note: ($("fa-note") && $("fa-note").value) || "",
            photo: state.photo || null,
            photo_status: state.photo ? null : state.photoStatus,
        };
        if (state.position) {
            payload.latitude = state.position.coords.latitude;
            payload.longitude = state.position.coords.longitude;
            payload.accuracy = state.position.coords.accuracy;
        }

        post("/punch", payload).then(function (res) {
            state.busy = false;
            if (res.employee) { applyPayload(res); }
            if (res.ok) {
                alertBox("fa-msg", res.message, "ok");
                state.photo = null;
                if ($("fa-note")) { $("fa-note").value = ""; }
                show($("fa-photo-preview"), false);
                if (state.data && state.data.options.require_photo
                        && !(state.data.day_done && !checkedInNow())) {
                    startCamera();
                }
            } else if (res.error === "unauthorized") {
                doLogout();
            } else {
                alertBox("fa-msg", res.message || "Gagal menyimpan absensi.", "danger");
                if (res.need_reason) { show($("fa-extra"), true); }
            }
            updatePunchButton();
        }).catch(function () {
            state.busy = false;
            updatePunchButton();
            alertBox("fa-msg", "Tidak bisa menghubungi server.", "danger");
        });
    }

    // ------------------------------------------------------------------ init
    function init() {
        startClock();
        $("fa-login-form").addEventListener("submit", doLogin);
        $("fa-logout").addEventListener("click", doLogout);
        $("fa-punch").addEventListener("click", doPunch);
        $("fa-shoot").addEventListener("click", capturePhoto);
        $("fa-retake").addEventListener("click", retakePhoto);

        var stored = readStoredToken();
        if (stored) {
            state.token = stored;
            refreshState().then(function () {
                if (state.data) { startWatch(); }
            });
        }

        window.setInterval(function () {
            if (state.token && state.data && !state.busy) { refreshState(); }
        }, 60000);

        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                // lepaskan kamera saat halaman di-background: kalau tidak,
                // lampu kamera tetap menyala dan baterai terkuras
                if (!state.photo) { stopCamera(); }
                return;
            }
            if (state.token && !state.busy) { refreshState(); }
        });

        window.addEventListener("pagehide", stopCamera);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
