import frappe

# 2026-09-16 fix, second correction: your screenshot showed the actual
# source - "Valuation Rate" is a plain field directly on the Item doctype
# itself (350.00 for 12/S Ring Spun, sitting right next to Maintain
# Stock/Is Fixed Asset), not a warehouse-scoped figure on Bin at all. The
# previous Bin.valuation_rate version was coming back empty because there
# was apparently no Bin record for this item in whatever `source_warehouse`
# resolved to - a plain Item field read has no such dependency.
#
# `warehouse` is kept as an argument only so the existing call in
# sizing_receipt.js (`args: { item_code, warehouse }`) doesn't need a
# matching change - it's accepted but no longer used for anything.


@frappe.whitelist()
def fetch_current_rate(item_code, warehouse=None):
	try:
		return frappe.db.get_value("Item", item_code, "valuation_rate")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Error in fetching rate")
		return None