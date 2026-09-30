# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, AccessError, ValidationError

# Sumber antrean dapur. 'pos_order' adalah pesanan yang sudah lewat checkout;
# 'bill' adalah open bill yang belum menjadi pos.order sama sekali. Keduanya
# dimasak dapur yang sama, jadi keduanya default-nya ikut terkirim dan setiap
# pesanan/baris membawa flag 'source'.
ORDER_SOURCES = ['pos_order', 'bill']


class GetPosOrdersUseCase:
    def __init__(self, pos_order_repo, bill_repo=None):
        self.pos_order_repo = pos_order_repo
        self.bill_repo = bill_repo

    def execute(self, session_id=None, pos_config_id=None, states=None,
                table_id=None, limit=100, offset=0, kitchen_states=None,
                sources=None, bill_states=None):
        if not session_id and not pos_config_id:
            return {
                "success": False,
                "error": "Missing required parameter 'pos_session_id' (or 'pos_config_id')",
                "status": 400,
            }

        sources = [s for s in (sources or ORDER_SOURCES) if s in ORDER_SOURCES]
        if not sources:
            return {
                "success": False,
                "error": "Invalid 'source'. Expected one or more of: %s" % ", ".join(ORDER_SOURCES),
                "status": 400,
            }

        try:
            entities = []

            if 'pos_order' in sources:
                entities += self.pos_order_repo.find_orders(
                    session_id=session_id,
                    pos_config_id=pos_config_id,
                    states=states,
                    table_id=table_id,
                    limit=limit,
                    offset=offset,
                    kitchen_states=kitchen_states,
                )

            if 'bill' in sources and self.bill_repo and self.bill_repo.is_available():
                # Open bill tidak terikat pos.session -- ia dibuat sebelum
                # checkout dan bisa melewati pergantian session -- jadi ia
                # selalu dicari lewat config, termasuk ketika pemanggil hanya
                # menyebut session.
                config_id = pos_config_id or self.pos_order_repo.config_id_for_session(session_id)
                entities += self.bill_repo.find_bills(
                    pos_config_id=config_id,
                    states=bill_states,
                    table_id=table_id,
                    limit=limit,
                    offset=offset,
                    kitchen_states=kitchen_states,
                )

            # Paging dijalankan per sumber lalu hasilnya digabung: keduanya
            # tabel terpisah, sehingga satu offset gabungan tidak bisa dijamin
            # stabil. Untuk layar dapur ini tidak menjadi masalah -- antreannya
            # jauh lebih pendek dari limit -- tetapi pemanggil yang benar-benar
            # mem-paging sebaiknya meminta satu 'source' saja.
            entities.sort(key=lambda entity: (entity.date_order or "", entity.source, entity.id))
            if limit:
                entities = entities[:limit]

            return {"success": True, "data": [entity.to_dict() for entity in entities]}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 400}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class GetPosOrderDetailUseCase:
    def __init__(self, pos_order_repo):
        self.pos_order_repo = pos_order_repo

    def execute(self, order_id):
        try:
            order = self.pos_order_repo.find_order(order_id)
            return {"success": True, "data": order.to_dict()}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 404}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


class GetBillOrderDetailUseCase:
    """Satu open bill, dalam bentuk yang sama dengan detail pos.order."""

    def __init__(self, bill_repo):
        self.bill_repo = bill_repo

    def execute(self, bill_id):
        try:
            bill = self.bill_repo.find_bill(bill_id)
            return {"success": True, "data": bill.to_dict()}
        except (UserError, AccessError, ValidationError) as e:
            return {"success": False, "error": str(e), "status": 404}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}
