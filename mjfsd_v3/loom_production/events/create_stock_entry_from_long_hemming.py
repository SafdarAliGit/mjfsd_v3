import frappe
from frappe import _
from frappe.utils import flt

# On Long Hemming submit:
#
# 1. One Material Transfer Stock Entry. Per row: if Transfer B Qty is
#    UNCHECKED (default), one line of qty = A Qty + B Qty, Source ->
#    Target Warehouse - "A Qty + B Qty combined by default" (your
#    confirmed answer). If CHECKED, two lines instead: A Qty Source ->
#    Target Warehouse, and (only if B Qty > 0) B Qty Source -> B Qty
#    Warehouse. Both lines for a row carry that row's Color Batch
#    (carried through from Dyed Fabric Issuance / Dyeing Receipt).
#
# 2. Separately, if the Hemming Wastage table has any rows, one Material
#    Receipt Stock Entry - "qty as weight" (your own words): qty = that
#    row's Weight, uom = that row's UOM, into that row's Warehouse. No
#    source warehouse/batch needed for a Material Receipt.


def create_transfer_stock_entries(lh):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = frappe.defaults.get_global_default("company")

	any_row = False
	for row in lh.items or []:
		if not (flt(row.a_qty) or flt(row.b_qty)):
			continue
		if not row.color_batch:
			frappe.throw(_("Row for Item {0} / Color {1} has no Color Batch.").format(row.item, row.color))

		stock_uom = frappe.db.get_value("Item", row.item, "stock_uom")

		if lh.transfer_b_qty:
			if flt(row.a_qty):
				se.append(
					"items",
					{
						"s_warehouse": lh.source_warehouse,
						"t_warehouse": lh.target_warehouse,
						"item_code": row.item,
						"qty": row.a_qty,
						"batch_no": row.color_batch,
						# See create_stock_entry_from_dyed_fabric_issuance.py -
						# required whenever batch_no is set directly via API
						# in this ERPNext version (2026-09-15 hotfix).
						"use_serial_batch_fields": 1,
						"uom": stock_uom,
					},
				)
				any_row = True
			if flt(row.b_qty):
				if not lh.b_qty_warehouse:
					frappe.throw(_("B Qty Warehouse is required when Transfer B Qty is checked."))
				se.append(
					"items",
					{
						"s_warehouse": lh.source_warehouse,
						"t_warehouse": lh.b_qty_warehouse,
						"item_code": row.item,
						"qty": row.b_qty,
						"batch_no": row.color_batch,
						"use_serial_batch_fields": 1,
						"uom": stock_uom,
					},
				)
				any_row = True
		else:
			combined = flt(row.a_qty) + flt(row.b_qty)
			if combined:
				se.append(
					"items",
					{
						"s_warehouse": lh.source_warehouse,
						"t_warehouse": lh.target_warehouse,
						"item_code": row.item,
						"qty": combined,
						"batch_no": row.color_batch,
						"use_serial_batch_fields": 1,
						"uom": stock_uom,
					},
				)
				any_row = True

	if not any_row:
		frappe.throw(_("No Items have an A Qty / B Qty - nothing to transfer."))

	add_hemming_cost(lh, se)

	se.insert(ignore_permissions=True)
	se.submit()
	frappe.db.set_value("Long Hemming", lh.name, "transfer_stock_entry", se.name)


def create_wastage_receipt_entry(lh):
	if not lh.hemming_wastage:
		return

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.purpose = "Material Receipt"
	se.company = frappe.defaults.get_global_default("company")

	for row in lh.hemming_wastage:
		if not flt(row.weight):
			continue
		se.append(
			"items",
			{
				"item_code": row.item,
				"qty": row.weight,
				"t_warehouse": row.warehouse,
				"uom": row.uom,
			},
		)

	if not se.items:
		return

	se.insert(ignore_permissions=True)
	se.submit()
	frappe.db.set_value("Long Hemming", lh.name, "wastage_stock_entry", se.name)


def cancel_linked_stock_entries(lh):
	for fieldname in ("transfer_stock_entry", "wastage_stock_entry"):
		se_name = lh.get(fieldname)
		if not se_name:
			continue
		se = frappe.get_doc("Stock Entry", se_name)
		if se.docstatus == 1:
			se.cancel()


def add_hemming_cost(lh, se):
	"""2026-09-26 - Hemming Rate x (A Qty + B Qty) posted as an additional
	cost on the transfer entry, so the hemming charge goes into the value
	of the towels arriving at Stitching & Finishing (ERPNext spreads it
	over the incoming rows). Credited to the company's "Expenses Included
	In Valuation" account - the supplier's Purchase Invoice for hemming
	should be booked against that same account to clear it."""
	rate = flt(lh.get("hemming_rate"))
	if not rate:
		return

	total_qty = sum(flt(d.qty) for d in se.items)
	amount = rate * total_qty
	if not amount:
		return

	account = frappe.get_cached_value("Company", se.company, "expenses_included_in_valuation")
	if not account:
		frappe.throw(
			_("Set 'Expenses Included In Valuation' on Company {0} - the hemming charge is booked against it.").format(
				se.company
			)
		)

	se.append(
		"additional_costs",
		{
			"expense_account": account,
			"description": _("Hemming charges - {0} ({1} pcs @ {2}) - {3}").format(
				lh.get("supplier") or _("no supplier"), total_qty, rate, lh.name
			),
			"amount": amount,
		},
	)
