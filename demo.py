import xmlrpc.client
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict

# -------------------------
# 1. Odoo Connection Setup
# -------------------------
url = "https://staunch-tec.odoo.com/"      # Odoo server URL
db = "staunch-tec"                # Database name
username = "seenumahesh045@gmail.com"     # Odoo login
password = "Staunch@123"         # Odoo password

try:
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    print("✅ Successfully connected to Odoo.")
except Exception as e:
    print(f"❌ Failed to connect to Odoo. Error: {e}")
    exit()

# -------------------
# Configuration
# -------------------
planned_date = datetime.today().date()
horizon_start_date = planned_date
horizon_end_date = planned_date + timedelta(days=30)
order_counter = 1
planned_orders = []

print(f"🗓️  Planning horizon: {horizon_start_date.strftime('%Y-%m-%d')} to {horizon_end_date.strftime('%Y-%m-%d')}")

# -------------------
# Step 1: Get Finished Goods Demand from Confirmed Sales Orders
# -------------------
print("\n🔍 Step 1: Fetching demand from confirmed Sales Orders...")

so_domain = [
    ['state', 'in', ['sale', 'done']],
    ['commitment_date', '>=', horizon_start_date.strftime('%Y-%m-%d %H:%M:%S')],
    ['commitment_date', '<=', horizon_end_date.strftime('%Y-%m-%d %H:%M:%S')]
]
sales_orders = models.execute_kw(db, uid, password, 'sale.order', 'search_read', [so_domain], {'fields': ['name', 'order_line', 'commitment_date']})

fg_demand = defaultdict(lambda: {'quantity': 0, 'earliest_due_date': horizon_end_date + timedelta(days=1)})

for so in sales_orders:
    order_lines = models.execute_kw(db, uid, password, 'sale.order.line', 'read', [so['order_line']], {'fields': ['product_id', 'product_uom_qty']})
    commitment_date = datetime.strptime(so['commitment_date'], '%Y-%m-%d %H:%M:%S').date()
    
    for line in order_lines:
        product_id = line['product_id'][0]
        fg_demand[product_id]['quantity'] += line['product_uom_qty']
        if commitment_date < fg_demand[product_id]['earliest_due_date']:
            fg_demand[product_id]['earliest_due_date'] = commitment_date

if not fg_demand:
    print("✅ No sales demand found within the next 30 days. No planning needed.")
    exit()

print(f"📊 Found demand for {len(fg_demand)} unique finished products.")

# -------------------
# Step 2 & 3: Calculate Net Requirements and Plan MOs
# -------------------
print("\n⚙️  Step 2 & 3: Calculating shortages and planning Manufacturing Orders (MOs)...")

for product_id, demand_info in fg_demand.items():
    total_demand = demand_info['quantity']
    earliest_due_date = demand_info['earliest_due_date']

    # Add 'default_code' to the list of fields to read
    fields_to_read = ['name', 'default_code', 'qty_available', 'x_studio_manufacturing_lead_time', 'product_tmpl_id']
    product_data = models.execute_kw(db, uid, password, 'product.product', 'read', [product_id], {'fields': fields_to_read})[0]
    
    # Construct the consistent item name format
    fg_code = product_data.get('default_code') or 'NOCODE'
    fg_name_only = product_data['name']
    fg_display_name = f"[{fg_code}] {fg_name_only}"
    
    on_hand = product_data['qty_available']
    
    to_produce = max(0, total_demand - on_hand)

    if to_produce > 0:
        mfg_lead_time = int(product_data.get('x_studio_manufacturing_lead_time', 0))
        mo_start_date = earliest_due_date - timedelta(days=mfg_lead_time)
        
        planned_id = f"PLN-MO-{order_counter:04d}"
        order_counter += 1

        planned_orders.append({
            "Order Type": "MO", "Planned ID": planned_id, "Item": fg_display_name,
            "Item Type": "Manufacture", "Quantity": to_produce, "Supplier": None,
            "Lead Time": mfg_lead_time, "Planned Date": planned_date.strftime("%Y-%m-%d"),
            "Due Date": earliest_due_date.strftime("%Y-%m-%d"),
        })
        print(f"  -> Shortage for '{fg_display_name}'. Planning MO: {planned_id} for {to_produce} units.")

        # -------------------
        # Step 4 & 5: Explode BOM and Plan POs
        # -------------------
        product_template_id = product_data['product_tmpl_id'][0]
        bom_ids = models.execute_kw(db, uid, password, 'mrp.bom', 'search', [[['product_tmpl_id', '=', product_template_id]]], {'limit': 1})
        
        if not bom_ids:
            # THIS IS THE CORRECTED LINE
            print(f"    ⚠️  Warning: No BOM found for '{fg_display_name}'. Cannot plan for raw materials.")
            continue

        bom_lines = models.execute_kw(db, uid, password, 'mrp.bom.line', 'search_read', [[['bom_id', '=', bom_ids[0]]]], {'fields': ['product_id', 'product_qty']})

        for line in bom_lines:
            rm_id, rm_name = line['product_id']
            rm_qty_per_fg = line['product_qty']
            total_rm_needed = rm_qty_per_fg * to_produce

            rm_data = models.execute_kw(db, uid, password, 'product.product', 'read', [rm_id], {'fields': ['qty_available', 'seller_ids']})[0]
            rm_on_hand = rm_data['qty_available']
            rm_shortage = max(0, total_rm_needed - rm_on_hand)

            if rm_shortage > 0:
                seller_ids = rm_data.get('seller_ids', [])
                
                supplier_name = "N/A"
                purchase_lead_time = 0

                if seller_ids:
                    first_supplier_id = seller_ids[0]
                    seller_info = models.execute_kw(db, uid, password, 'product.supplierinfo', 'read', [first_supplier_id], {'fields': ['partner_id', 'delay']})[0]
                    
                    supplier_name = seller_info.get('partner_id', [0, "N/A"])[1]
                    purchase_lead_time = seller_info.get('delay', 0)
                else:
                    print(f"    ⚠️  Warning: No supplier configured for raw material '{rm_name}'. Using 0 lead time.")

                po_due_date = mo_start_date - timedelta(days=1)
                
                planned_id = f"PLN-PO-{order_counter:04d}"
                order_counter += 1

                planned_orders.append({
                    "Order Type": "PO", "Planned ID": planned_id, "Item": rm_name,
                    "Item Type": "Purchase", "Quantity": rm_shortage, "Supplier": supplier_name,
                    "Lead Time": purchase_lead_time, "Planned Date": planned_date.strftime("%Y-%m-%d"),
                    "Due Date": po_due_date.strftime("%Y-%m-%d"),
                })
                print(f"    -> RM Shortage for '{rm_name}'. Planning PO: {planned_id} for {rm_shortage} units from '{supplier_name}'.")

# -------------------
# Step 6: Save Output
# -------------------
if planned_orders:
    df = pd.DataFrame(planned_orders)
    df = df.sort_values(by="Due Date").reset_index(drop=True)
    
    output_filename = "planned_orders.csv"
    df.to_csv(output_filename, index=False)
    print(f"\n✅ Process complete. Planned Orders saved to '{output_filename}'")
    print("\n--- Planned Orders Summary ---")
    print(df.to_string())
else:
    print("\n✅ Process complete. No shortages found, no planned orders generated.")