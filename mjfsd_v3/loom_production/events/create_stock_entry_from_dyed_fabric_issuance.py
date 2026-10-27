import frappe
from frappe import _
from frappe.utils import flt

# On Dyed Fabric Issuance submit: one Material Transfer Stock Entry
# (Source -> Target Warehouse), one row per Issuance Details row, qty =
# that row's PCs, tagged with the Color Batch carried through from the
# Dyeing Receipt Item it was fetched from - "The user will submit this
# entry, and stock will be transferred" (your words).
#
# Re-validates the dyed balance fresh from the DB right before creating
# the entry (not trusting whatever the client fetched earlier) and
# hard-throws if this row would take the total issued past what was
# actually received on the source Dyeing Receipt row - guards against two
# Dyed Fabric Issuances racing to issue the same dyed batch, mirroring the
# Weaving Contract's own balance-allocation safeguard.


def create_transfer_stock_entry(dfi):
	_validate_against_dyed_balance(dfi)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = frappe.defaults.get_global_default("company")

	any_row = False
	for row in dfi.items or []:
		if not flt(row.pcs):
			continue
		if not row.color_batch:
			frappe.throw(_("Row for Item {0} / Color {1} has no Color Batch.").format(row.item, row.color))

		se.append(
			"items",
			{
				"s_warehouse": dfi.source_warehouse,
				"t_warehouse": dfi.target_warehouse,
				"item_code": row.item,
				"qty": row.pcs,
				"batch_no": row.color_batch,
				# Required in this ERPNext version when setting batch_no
				# directly via API - without it, moving a batch a second
				# time (it was already moved once by the Dyeing Receipt's
				# own Repack entry) fails with "Serial and Batch Bundle
				# ... has already created." (2026-09-15 hotfix.)
				"use_serial_batch_fields": 1,
				"uom": frappe.db.get_value("Item", row.item, "stock_uom"),
				"custom_no_of_rolls": flt(row.rolls),
				"custom_weight_kgs": flt(row.weight_kg),
			},
		)
		any_row = True

	if not any_row:
		frappe.throw(_("No Items have a PCs qty - nothing to issue."))

	se.insert(ignore_permissions=True)
	se.submit()

	frappe.db.set_value("Dyed Fabric Issuance", dfi.name, "transfer_stock_entry", se.name)
	_rollup_fabric_issuance(dfi, sign=1)


def cancel_linked_stock_entry(dfi):
	if not dfi.transfer_stock_entry:
		return
	se = frappe.get_doc("Stock Entry", dfi.transfer_stock_entry)
	if se.docstatus == 1:
		se.cancel()
	_rollup_fabric_issuance(dfi, sign=-1)


def _validate_against_dyed_balance(dfi):
	for row in dfi.items or []:
		if not row.dyeing_receipt_item:
			continue
		dri = frappe.db.get_value(
			"Dyeing Receipt Item",
			row.dyeing_receipt_item,
			[
				"item",
				"color",
				"received_qty",
				"rolls_received",
				"weight_received_kg",
				"fabric_issuance_pcs",
				"fabric_issuance_rolls",
				"fabric_issuance_weight_kg",
			],
			as_dict=True,
		)
		if not dri:
			continue

		new_pcs = flt(dri.fabric_issuance_pcs) + flt(row.pcs)
		new_rolls = flt(dri.fabric_issuance_rolls) + flt(row.rolls)
		new_weight = flt(dri.fabric_issuance_weight_kg) + flt(row.weight_kg)

		if new_pcs - flt(dri.received_qty) > 0.0001:
			frappe.throw(
				_(
					"Item {0} / Color {1}: PCs on this Dyed Fabric Issuance would take the total "
					"issued from this Dyeing Receipt row to {2}, more than the {3} Pcs actually "
					"received (someone else may have issued part of it since you fetched it)."
				).format(dri.item, dri.color, new_pcs, dri.received_qty)
			)
		if new_rolls - flt(dri.rolls_received) > 0.0001:
			frappe.throw(
				_(
					"Item {0} / Color {1}: Rolls on this Dyed Fabric Issuance would exceed the {2} "
					"Rolls actually received."
				).format(dri.item, dri.color, dri.rolls_received)
			)
		if new_weight - flt(dri.weight_received_kg) > 0.0001:
			frappe.throw(
				_(
					"Item {0} / Color {1}: Weight (kg) on this Dyed Fabric Issuance would exceed "
					"the {2} kg actually received."
				).format(dri.item, dri.color, dri.weight_received_kg)
			)


def _rollup_fabric_issuance(dfi, sign):
	for row in dfi.items or []:
		if not row.dyeing_receipt_item:
			continue
		current = frappe.db.get_value(
			"Dyeing Receipt Item",
			row.dyeing_receipt_item,
			["fabric_issuance_pcs", "fabric_issuance_rolls", "fabric_issuance_weight_kg"],
			as_dict=True,
		)
		if not current:
			continue
		frappe.db.set_value(
			"Dyeing Receipt Item",
			row.dyeing_receipt_item,
			{
				"fabric_issuance_pcs": flt(current.fabric_issuance_pcs) + sign * flt(row.pcs),
				"fabric_issuance_rolls": flt(current.fabric_issuance_rolls) + sign * flt(row.rolls),
				"fabric_issuance_weight_kg": flt(current.fabric_issuance_weight_kg)
				+ sign * flt(row.weight_kg),
			},
		)
