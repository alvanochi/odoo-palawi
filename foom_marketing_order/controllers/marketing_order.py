# -*- coding: utf-8 -*-

# from odoo import http
# from odoo.http import request, Response
# import json

# class MarketingOrderController(http.Controller):

#     @http.route('/api/marketing_order', type='json', auth='public', methods=['POST'], csrf=False)
#     def create_marketing_order(self, **kw):
#         try:
#             # Parse the incoming JSON data
#             data = request.jsonrequest

#             # Create a new marketing order record
#             marketing_order = request.env['marketing.order'].sudo().create(data)

#             # Return the ID of the newly created record
#             return {'id': marketing_order.id, 'status': 'success'}

#         except Exception as e:
#             return {'error': str(e), 'status': 'error'}
