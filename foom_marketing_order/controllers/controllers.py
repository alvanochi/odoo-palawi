# -*- coding: utf-8 -*-
# from odoo import http


# class FoomMarketingOrder(http.Controller):
#     @http.route('/foom_marketing_order/foom_marketing_order', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/foom_marketing_order/foom_marketing_order/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('foom_marketing_order.listing', {
#             'root': '/foom_marketing_order/foom_marketing_order',
#             'objects': http.request.env['foom_marketing_order.foom_marketing_order'].search([]),
#         })

#     @http.route('/foom_marketing_order/foom_marketing_order/objects/<model("foom_marketing_order.foom_marketing_order"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('foom_marketing_order.object', {
#             'object': obj
#         })

from odoo import http
from odoo.http import request, Response
import json

class MarketingOrderController(http.Controller):

    @http.route('/api/marketing_order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_marketing_order(self, **kw):
        try:
            # Parse the incoming JSON data
            data = request.jsonrequest

            # Create a new marketing order record
            marketing_order = request.env['marketing.order'].sudo().create(data)

            # Return the ID of the newly created record
            return {'id': marketing_order.id, 'status': 'success'}

        except Exception as e:
            return {'error': str(e), 'status': 'error'}
