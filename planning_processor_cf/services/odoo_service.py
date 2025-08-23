# services/odoo_service.py
import xmlrpc.client
import pandas as pd
from typing import List, Dict, Any, Optional
from config.settings import settings
from utils.exceptions import OdooConnectionError, OdooOperationError
import logging

logger = logging.getLogger(__name__)

class OdooService:
    def __init__(self):
        self._common = None
        self._uid = None
        self._models = None
        self._connected = False

    def connect(self):
        if self._connected:
            return
        try:
            self._common = xmlrpc.client.ServerProxy(f'{settings.odoo_url}/xmlrpc/2/common')
            self._common.version()
            self._uid = self._common.authenticate(settings.odoo_db, settings.odoo_username, settings.odoo_password, {})
            if not self._uid:
                raise OdooConnectionError("Odoo authentication failed")
            self._models = xmlrpc.client.ServerProxy(f'{settings.odoo_url}/xmlrpc/2/object')
            self._connected = True
            logger.info("Odoo connection established successfully")
        except Exception as e:
            raise OdooConnectionError(f"Failed to connect to Odoo: {str(e)}")

    def execute_method(self, model_name: str, method_name: str, *args, **kwargs) -> Any:
        if not self._connected:
            self.connect()
        try:
            return self._models.execute_kw(
                settings.odoo_db, self._uid, settings.odoo_password,
                model_name, method_name, list(args), kwargs
            )
        except xmlrpc.client.Fault as e:
            raise OdooOperationError(f"Odoo API error for {model_name}.{method_name}: {e.faultString}")

    def find_record_id(self, model_name: str, field_name: str, value: Any) -> Optional[int]:
        ids = self.execute_method(model_name, 'search', [[field_name, '=', value]], limit=1)
        return ids[0] if ids else None

    def search_and_read(self, model_name: str, domain: List, fields: List[str]) -> List[Dict]:
        logger.info(f"Searching '{model_name}' with domain {domain}")
        return self.execute_method(model_name, 'search_read', domain, fields=fields)

    def get_production_orders(self, domain: List) -> List[Dict]:
        fields = ['display_name', 'x_planned_order_id', 'date_start', 'state']
        orders = self.search_and_read('mrp.production', domain, fields)
        for order in orders:
            order['type'] = 'Make'
            order['schedule_date'] = order.get('date_start')
        return orders

    def get_purchase_orders(self, domain: List) -> List[Dict]:
        fields = ['display_name', 'x_planned_order_id', 'date_planned', 'state']
        orders = self.search_and_read('purchase.order', domain, fields)
        for order in orders:
            order['type'] = 'Buy'
            order['schedule_date'] = order.get('date_planned')
        return orders

    def create_purchase_order(self, order_data: Dict) -> Dict:
        try:
            item_id = order_data.get('item_id')
            supplier_name = order_data.get('supplier_name_for_odoo')
            if not supplier_name or pd.isna(supplier_name):
                return {"status": "failed", "message": f"Supplier name not found for {item_id}"}
            
            product_id = self.find_record_id('product.product', 'default_code', item_id)
            if not product_id: return {"status": "failed", "message": f"Product '{item_id}' not found"}
            
            supplier_id = self.find_record_id('res.partner', 'name', supplier_name)
            if not supplier_id: return {"status": "failed", "message": f"Supplier '{supplier_name}' not found"}
            
            po_vals = {
                'partner_id': supplier_id,
                'date_planned': order_data.get('suggested_due_date'),
                'x_planned_order_id': order_data['planned_order_id'],
                'order_line': [(0, 0, {
                    'product_id': product_id,
                    'product_qty': order_data.get('quantity'),
                    'date_planned': order_data.get('suggested_due_date')
                })]
            }
            po_id = self.execute_method('purchase.order', 'create', po_vals)
            self.execute_method('purchase.order', 'button_confirm', [po_id])
            return {"status": "success", "odoo_id": po_id, "message": f"PO {po_id} created"}
        except Exception as e:
            raise OdooOperationError(f"Failed to create PO: {str(e)}")

    def create_manufacturing_order(self, order_data: Dict) -> Dict:
        try:
            item_id = order_data.get('item_id')
            product_id = self.find_record_id('product.product', 'default_code', item_id)
            if not product_id: return {"status": "failed", "message": f"Product '{item_id}' not found"}

            product_info = self.execute_method('product.product', 'read', [product_id], ['product_tmpl_id'])
            product_tmpl_id = product_info[0]['product_tmpl_id'][0]
            bom_ids = self.execute_method('mrp.bom', 'search', [['product_tmpl_id', '=', product_tmpl_id]], limit=1)
            if not bom_ids: return {"status": "failed", "message": f"BOM not found for {item_id}"}

            uom_id = self.find_record_id('uom.uom', 'name', 'Units')
            if not uom_id: return {"status": "failed", "message": "UoM 'Units' not found"}

            mo_vals = {
                'product_id': product_id,
                'product_qty': order_data.get('quantity'),
                'date_start': order_data.get('suggested_due_date'),
                'bom_id': bom_ids[0],
                'product_uom_id': uom_id,
                'x_planned_order_id': order_data['planned_order_id']
            }
            mo_id = self.execute_method('mrp.production', 'create', mo_vals)
            self.execute_method('mrp.production', 'action_confirm', [mo_id])
            return {"status": "success", "odoo_id": mo_id, "message": f"MO {mo_id} created"}
        except Exception as e:
            raise OdooOperationError(f"Failed to create MO: {str(e)}")