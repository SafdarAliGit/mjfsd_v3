import frappe
from frappe import _
from frappe.utils import flt

# Mirrors Weaving Receipt's own "Get Items From" popup pattern - not
# spelled out in your spec for Dyeing Receipt (unlike Dyeing Contract,
# which explicitly says "Create Dyeing Contract button in sales order"),
# but "Rate (fetch rates from dyeing contract)" on Dyeing Receipt Items
# implies pulling from an existing submitted Dyeing Contract, so built the
# same way as every other receipt-style doctype in this project. Flag if
# Dyeing Receipts should instead be entered from scratch by hand.
#
# 2026-09-15: added create_dyeing_receipt_from_dyeing_contract (the new
# "Dyeing Receipt" button on Dyeing Contract itself - reuses
# get_dyeing_contract_items below so both paths build rows identically)
# and get_tcs_finish_weight (live-preview helper for dyeing_receipt.js's
# new Finish Weight calc - see dyeing_receipt.py's own recalculate_totals
# for the authoritative server-side version of the same lookup).


@frappe.whitelist()
def get_dyeing_contracts_for_selection():
	contracts = frappe.get_all(
		"Dyeing Contract",
		filters={"docstatus": 1},
		fields=["name", "supplier", "source_warehouse", "target_warehouse"],
		order_by="creation desc",
	)
	return contracts


@frappe.whitelist()
def get_dyeing_contract_items(dyeing_contracts):
	import json

	if isinstance(dyeing_contracts, str):
		dyeing_contracts = json.loads(dyeing_contracts)

	rows = []
	for dc_name in dyeing_contracts:
		dc = frappe.get_doc("Dyeing Contract", dc_name)
		for row in dc.items:
			color_batch = _get_color_batch(row.sales_order, row.item, row.color)
			rows.append(
				{
					"item": row.item,
					"color": row.color,
					"received_qty": 0,
					"dyeing_wastage_percent": row.dyeing_wastage_percent,
					"rate": row.rate,
					"sales_order": row.sales_order,
					"towel_costing_sheet": row.towel_costing_sheet,
					"dyeing_contract": dc.name,
					"dyeing_contract_item": row.name,
					"greige_batch": row.greige_batch,
					"color_batch": color_batch,
					"source_warehouse": dc.target_warehouse,
					"target_warehouse": dc.source_warehouse,
					# 2026-09-28 - "user can select different supplier in
					# Dyeing Receipt" (your words) - fetched here so
					# dyeing_receipt.js can set+lock it, same fix as
					# Weaving Receipt's weaver.
					"supplier": dc.supplier,
				}
			)

	return rows


@frappe.whitelist()
def create_dyeing_receipt_from_dyeing_contract(dyeing_contract):
	"""'There should be a create dyeing receipt button in dyeing contract'
	(your words). Builds an unsaved Dyeing Receipt prefilled with this one
	Dyeing Contract's rows, via the exact same get_dyeing_contract_items()
	used by Dyeing Receipt's own 'Get Items From > Dyeing Contract' popup,
	then routes you to it (save/submit yourself) - same pattern as Weaving
	Contract's own 'Weaving Receipt' button."""
	dc = frappe.get_doc("Dyeing Contract", dyeing_contract)
	if dc.docstatus != 1:
		frappe.throw(_("Dyeing Contract must be submitted before a Dyeing Receipt can be created from it."))

	rows = get_dyeing_contract_items([dc.name])
	if not rows:
		frappe.throw(_("{0} has no items to receive.").format(dc.name))

	dr = frappe.new_doc("Dyeing Receipt")
	dr.supplier = dc.supplier
	dr.source_warehouse = rows[0].get("source_warehouse")
	dr.target_warehouse = rows[0].get("target_warehouse")
	for data in rows:
		dr.append("items", data)

	return dr


@frappe.whitelist()
def get_tcs_finish_weight(towel_costing_sheet, item_code):
	"""Live-preview helper for dyeing_receipt.js's Finish Weight calc -
	Dyeing Receipt's own validate() (recalculate_totals in
	dyeing_receipt.py) recomputes this authoritatively on every save
	regardless, same 'server is the source of truth' pattern as
	everywhere else in this project."""
	if not towel_costing_sheet or not item_code:
		return 0

	tcs = frappe.get_doc("Towel Costing Sheet", towel_costing_sheet)
	for row in tcs.finish_item_towel_costing or []:
		if row.article == item_code:
			return flt(row.finish_weight)
	return 0


def _get_color_batch(sales_order, item_code, color):
	if not (sales_order and item_code and color):
		return None
	return frappe.db.get_value(
		"Sales Order Item",
		{"parent": sales_order, "item_code": item_code, "custom_color": color},
		"custom_batch",
	)
