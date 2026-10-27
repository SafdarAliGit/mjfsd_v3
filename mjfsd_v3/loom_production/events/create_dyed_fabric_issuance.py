import frappe
from frappe import _
from frappe.utils import flt

# "Create" button on a submitted Dyeing Receipt seeds a new Dyed Fabric
# Issuance from that one receipt's rows. The new (unsaved) Dyed Fabric
# Issuance also gets its own "Get Items From > Dyeing Receipt" popup (same
# pattern as Dyeing Receipt's own "Get Items From > Dyeing Contract") so
# you can pull in MORE rows from other submitted Dyeing Receipts too -
# "Multiple dyeing receipts can also be fetched in this issuance" (your
# words). Both paths share _build_rows_for_receipts so the row-shape and
# balance logic only lives in one place.
#
# Balance discipline: each Dyeing Receipt Item row tracks how much of its
# own Received Qty/Rolls/Weight has already gone out on a Dyed Fabric
# Issuance (fabric_issuance_pcs/rolls/weight_kg - new hidden fields on
# Dyeing Receipt Item). Rows already fully issued are skipped when
# fetching; rows partially issued default to their remaining balance, not
# their full dyed amount, so re-fetching the same receipt twice won't
# double-offer stock that's already spoken for.


def _build_rows_for_receipts(receipt_names):
	rows = []
	for dr_name in receipt_names:
		dr = frappe.get_doc("Dyeing Receipt", dr_name)
		if dr.docstatus != 1:
			continue
		for row in dr.items:
			remaining_pcs = flt(row.received_qty) - flt(row.fabric_issuance_pcs)
			remaining_rolls = flt(row.rolls_received) - flt(row.fabric_issuance_rolls)
			remaining_weight = flt(row.weight_received_kg) - flt(row.fabric_issuance_weight_kg)
			if remaining_pcs <= 0.0001 and remaining_rolls <= 0.0001 and remaining_weight <= 0.0001:
				# Fully issued already - nothing left on this row to send
				# to a Dyed Fabric Issuance.
				continue
			rows.append(
				{
					"item": row.item,
					"color": row.color,
					"rolls": remaining_rolls,
					"weight_kg": remaining_weight,
					"pcs": remaining_pcs,
					"sales_order": row.sales_order,
					"dyeing_receipt": dr.name,
					"dyeing_contract": row.dyeing_contract,
					"dyed_rolls": row.rolls_received,
					"dyed_pcs": row.received_qty,
					"dyed_weight": row.weight_received_kg,
					"dyeing_receipt_item": row.name,
					"color_batch": row.color_batch,
				}
			)
	return rows


@frappe.whitelist()
def create_dyed_fabric_issuance_from_dyeing_receipt(dyeing_receipt):
	dr = frappe.get_doc("Dyeing Receipt", dyeing_receipt)
	if dr.docstatus != 1:
		frappe.throw(_("Dyeing Receipt must be submitted first."))

	dfi = frappe.new_doc("Dyed Fabric Issuance")
	dfi.source_warehouse = dr.target_warehouse

	for data in _build_rows_for_receipts([dr.name]):
		dfi.append("items", data)

	if not dfi.items:
		frappe.throw(
			_(
				"Every row on {0} has already been fully sent to a Dyed Fabric Issuance - nothing left to issue."
			).format(dr.name)
		)

	return dfi


@frappe.whitelist()
def get_dyeing_receipts_for_selection():
	return frappe.get_all(
		"Dyeing Receipt",
		filters={"docstatus": 1},
		fields=["name", "supplier", "date"],
		order_by="creation desc",
	)


@frappe.whitelist()
def get_dyeing_receipt_items(dyeing_receipts):
	import json

	if isinstance(dyeing_receipts, str):
		dyeing_receipts = json.loads(dyeing_receipts)

	return _build_rows_for_receipts(dyeing_receipts)
