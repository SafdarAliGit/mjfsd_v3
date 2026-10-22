import frappe
from frappe import _
from frappe.utils import flt

# 2026-09-28 fix - "Sizing Program Gate Pass (Material Transfer Stock
# Entry) Source Warehouse = Stores - PT, Target Warehouse = Supplier - PT,
# Qty not calculated correctly. Qty = bags_issue (from sizing program) *
# 100" (your words). This was leftover scaffolding (its own comments said
# "simplified example" / "or appropriate type") - it only ever set
# t_warehouse (to sp.source_warehouse, the wrong field entirely), never
# set s_warehouse at all, and used sp.lbs as qty instead of the Bags
# Issue formula. Fixed to the fixed Source/Target pair below (same
# pattern as Issue Yarn's own SOURCE_WAREHOUSE/TARGET_WAREHOUSE) and the
# qty formula given.

SOURCE_WAREHOUSE = "Stores - PT"
TARGET_WAREHOUSE = "Supplier - PT"


@frappe.whitelist()
def open_stock_entry(sizing_program_name):
	"""Creates the "Gate Pass" (a Material Transfer Stock Entry) for a
	given Sizing Program. Draft only - user reviews and submits it
	himself, same pattern as every other "prefill, open the form" button
	in this project."""
	for wh in (SOURCE_WAREHOUSE, TARGET_WAREHOUSE):
		if not frappe.db.exists("Warehouse", wh):
			frappe.throw(_("Warehouse {0} doesn't exist - check the exact name/spelling.").format(wh))

	sp = frappe.get_doc("Sizing Program", sizing_program_name)
	item = frappe.get_doc("Item", sp.item)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.custom_sizing_program_gate_pass = sp.name
	se.purpose = "Material Transfer"
	se.set_posting_time = 1
	se.posting_date = sp.date

	se.append("items", {
		"item_code": sp.item,
		"qty": flt(sp.bags_issue) * 100,
		"s_warehouse": SOURCE_WAREHOUSE,
		"t_warehouse": TARGET_WAREHOUSE,
		"uom": item.stock_uom,
		"stock_uom": item.stock_uom,
	})

	return se
