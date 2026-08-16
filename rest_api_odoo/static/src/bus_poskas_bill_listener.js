/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser";

const { busService } = registry.category("services").get("bus_service");

/**
 * Listener: notifikasi bill open per config_id
 * channel: ["poskas.bill", config_id]
 * type: "poskas_bill_open"
 * payload: { bill_id, table_id, table_ref, state, amount_total }
 */
export const poskasBillBusListener = {
    dependencies: ["bus_service", "user", "orm", "notification"],
    start(env, { bus_service, notification }) {
        // TODO: ganti cara ambil config_id sesuai kebutuhan kamu
        // kalau di POS, biasanya config_id bisa diambil dari env.services.pos?.config?.id
        const getConfigId = () => env.services?.pos?.config?.id;

        const subscribe = () => {
            const configId = getConfigId();
            if (!configId) return;

            const channel = ["poskas.bill", configId];
            bus_service.addChannel(channel);

            bus_service.addEventListener("notification", ({ detail: notifications }) => {
                for (const notif of notifications) {
                    // format umum: [channel, type, payload]
                    const [ch, type, payload] = notif;

                    if (type === "poskas_bill_open") {
                        // contoh aksi: tampil toast
                        notification.add(
                            `New open bill: table=${payload.table_ref} total=${payload.amount_total}`,
                            { type: "info" }
                        );

                        // TODO: trigger refresh list / fetch API / update state
                        // console.log("BILL EVENT:", payload);
                    }
                }
            });
        };

        // coba subscribe sekarang
        subscribe();

        // optional: resubscribe kalau POS/config_id muncul belakangan
        browser.setTimeout(subscribe, 1500);
    },
};

registry.category("services").add("poskas_bill_bus_listener", poskasBillBusListener);
