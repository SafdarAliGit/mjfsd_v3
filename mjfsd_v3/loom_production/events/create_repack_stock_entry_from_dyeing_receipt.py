import frappe
from frappe import _
from frappe.utils import flt, rounded

# On Dyeing Receipt submit: one Repack Stock Entry, consuming each row's
# Greige batch and producing the same Item under its Color batch - "finish
# will be color batch item" / "finish qty will be received qty and finish
# rate will be valuation rate of greige + rate" (your words).
#
# 2026-09-14 update: also enforces "the received values shouldn't be
# greater than the issued values" (your words) for Pcs, Rolls AND Weight -
# checked against the matching Dyeing Contract Item's accumulated Issued
# totals, right before the Repack entry is created (so a violation blocks
# the whole submit, nothing partially posts). Also rolls up Rolls/Weight
# Received into the Dyeing Contract Item + Dyeing Contract, alongside the
# existing Pcs rollup.
#
# 2026-09-15 (feature v3) update: also sets the new Per LBS Rate custom
# field on the finish (Color Batch) row - (Total Outgoing Value / Weight
# Actual (Lbs)) + Rate. "Total Outgoing Value" is this row's own Greige
# consumption (received_qty x greige rate) - each Dyeing Receipt Item row
# is a self-contained Greige-in/Color-out pair, so that's the value
# actually attributable to that row's own finish output, not a blended
# total shared across unrelated rows in the same Stock Entry. Flag this
# interpretation to Kabeer if he meant the whole Stock Entry's total
# instead.
#
# 2026-09-15 fix (same class of bug reported on Weaving Receipt's
# Manufacture Stock Entry): the greige row's basic_rate used to be set
# here via an independent Bin valuation-rate lookup, and that guess can
# diverge from the rate Frappe's own valuation engine actually posts onto
# the row during validate() (moving-average/FIFO timing, precision,
# etc.) - even though set_basic_rate_manually wasn't set on that row, so
# Frappe could silently recompute/overwrite it anyway, leaving the finish
# row's "greige_rate + Rate" built on a number that no longer matched what
# actually posted. Fixed the same way: the greige row is now appended
# with NO rate set, se.insert() lets Frappe compute its real basic_rate,
# and only THEN do we read that back to work out the finish row's
# basic_rate and Per LBS Rate - not a separate guess.
#
# 2026-09-15 fix #2 (same day, applied proactively after the equivalent
# bug was actually reported on Weaving Receipt - "total incoming value is
# 0"): amount/basic_amount on the finish row are now set explicitly right
# alongside basic_rate, and the redundant se.save() before submit was
# dropped in favour of calling se.submit() directly (it runs validate()
# itself). Also tags the Stock Entry itself with custom_dyeing_receipt /
# custom_dyeing_contract (new parent-level Stock Entry custom fields, see
# mjfsd_v3/custom/stock_entry.json) so the Stock Entry shows what created it
# without having to dig into its row-level plumbing fields.
#
# 2026-09-16 fix: the finish row's basic_rate used to be
# `greige_rate + row.rate` - but row.rate is a rate PER LBS (fetched from
# the Dyeing Contract), so that was adding a per-lbs currency figure
# straight onto a per-piece rate ("rates mentioned in dyeing contract are
# rate per LBS, I don't want that exact value to be added in items value"
# - your words). Fixed to convert it to a per-piece figure first:
# (Weight (kg) (Received) x 2.2046 x Rate) / Received Qty, added onto the
# greige rate. Also now copies Rolls (Received) / Weight (kg) (Received) /
# Weight (Lbs) onto the finish row's custom_no_of_rolls / custom_weight_kgs
# / custom_total_lbs (Stock Entry Detail custom fields) - these were being
# computed but never actually written onto the Stock Entry's own rows.


def create_repack_stock_entry(dyeing_receipt):
	dr = dyeing_receipt

	_validate_against_issued_balance(dr)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Repack"
	se.purpose = "Repack"
	se.company = frappe.defaults.get_global_default("company")
	se.custom_dyeing_receipt = dr.name
	# Best-effort - a Dyeing Receipt's rows can technically come from more
	# than one Dyeing Contract (multi-select popup); this just carries the
	# first one found so the common single-contract case still shows a
	# reference on the Stock Entry.
	for row in dr.items or []:
		if row.dyeing_contract:
			se.custom_dyeing_contract = row.dyeing_contract
			break

	# One entry per Dyeing Receipt Item row: tracks the greige (source)
	# row we appended for it (to read back its authoritative basic_rate /
	# amount after insert) and the finish row (to write basic_rate /
	# custom_per_lbs_rate onto once the real greige rate is known).
	tracking = []

	for row in dr.items or []:
		if not flt(row.received_qty):
			continue
		if not row.greige_batch:
			frappe.throw(_("Row for Item {0} has no Greige Batch - can't repack.").format(row.item))
		if not row.color_batch:
			frappe.throw(
				_(
					"Row for Item {0} / Color {1} has no Color Batch - check the Sales Order "
					"Item still has that Color and was submitted (batches are created on Sales "
					"Order submit)."
				).format(row.item, row.color)
			)

		stock_uom = frappe.db.get_value("Item", row.item, "stock_uom")

		# No rate set here on purpose - Frappe computes the real
		# valuation rate for this row during se.insert() below, and that
		# authoritative rate/amount is what we read back.
		# Greige consumed = Actual Qty + the Dyeing Wastage % of the contract,
		# rounded to a whole number (the item is counted in Pcs / Nos)
		greige_qty = rounded(flt(row.received_qty) * (1 + flt(row.dyeing_wastage_percent) / 100), 0)

		greige_row = se.append(
			"items",
			{
				"item_code": row.item,
				"qty": greige_qty,
				"s_warehouse": dr.source_warehouse,
				"batch_no": row.greige_batch,
				"use_serial_batch_fields": 1,
				"uom": stock_uom,
			},
		)

		finish_row = se.append(
			"items",
			{
				"item_code": row.item,
				"qty": row.received_qty,
				"t_warehouse": dr.target_warehouse,
				"batch_no": row.color_batch,
				"use_serial_batch_fields": 1,
				# Placeholder - overwritten below once the greige row's
				# real basic_rate is known (after insert()).
				"basic_rate": 0.0,
				# Without this, ERPNext's own Repack/Manufacture rate
				# calculator recomputes the finished row's rate from the
				# consumed row(s) and silently overwrites whatever we set
				# above - dropping the dyeing Rate we just added on top of
				# the greige valuation rate. This tells it to trust our
				# basic_rate instead. (2026-09-15 hotfix - "the stock
				# entry is not adding the dyeing rate in finish rate of
				# item".)
				"set_basic_rate_manually": 1,
				"is_finished_item": 1,
				"uom": stock_uom,
			},
		)

		tracking.append(
			{
				"row": row,
				"greige_row": greige_row,
				"finish_row": finish_row,
			}
		)

	if not tracking:
		frappe.throw(_("No Items have a Received Qty - nothing to repack."))

	# insert() runs validate(), which is what actually computes the
	# greige row's real basic_rate/amount via Frappe's own valuation
	# engine. It mutates the same row objects we already hold references
	# to in `tracking`, so we can read the real numbers back below rather
	# than trusting an independent Bin-lookup guess.
	se.insert(ignore_permissions=True)

	for entry in tracking:
		row = entry["row"]
		greige_row = entry["greige_row"]
		finish_row = entry["finish_row"]

		greige_rate = flt(greige_row.basic_rate)
		row_outgoing_value = flt(greige_row.amount)
		finish_qty = flt(finish_row.qty)
		# Recomputed directly from Weight (kg) (Received) rather than read
		# from the stored weight_received_lbs field, so this doesn't depend
		# on Dyeing Receipt's own validate() having already run in this
		# same request.
		# Actual Weight is entered in LBS
		weight_lbs = flt(row.weight_received_kg)

		# 2026-09-16 fix: Rate (fetched from the Dyeing Contract) is a rate
		# PER LBS, not per piece. Adding it straight onto greige_rate (a
		# per-piece rate) - as this used to do - silently treated it as a
		# per-piece rate, which is a unit mismatch, not just an off number
		# ("I don't want that exact value to be added in items value" -
		# your words). The per-piece value this row's dyeing actually
		# contributes is (Weight (kg) (Received) x 2.2046 x Rate) /
		# Received Qty - THAT per-piece figure is what gets added on top of
		# the greige (item's original) rate.
		dyeing_value_per_pc = 0.0
		if finish_qty:
			dyeing_value_per_pc = (weight_lbs * flt(row.rate)) / finish_qty

		# The Greige actually consumed includes the wastage, so the finished
		# pieces carry the whole Greige value plus the dyeing charge.
		finish_row.basic_rate = (row_outgoing_value / finish_qty + dyeing_value_per_pc) if finish_qty else greige_rate
		finish_row.basic_amount = finish_row.basic_rate * finish_qty
		finish_row.amount = finish_row.basic_rate * finish_qty

		if weight_lbs:
			finish_row.custom_per_lbs_rate = (row_outgoing_value / weight_lbs) + flt(row.rate)

		# 2026-09-16 - "not fetching rolls, weight kg and total lbs in
		# stock entry table" - these were already known here but never
		# copied onto the Stock Entry's own row (Stock Entry Detail custom
		# fields, see mjfsd_v3/custom/stock_entry_detail.json).
		finish_row.custom_no_of_rolls = flt(row.rolls_received)
		# the Stock Entry's own weight field is in Kgs
		finish_row.custom_weight_kgs = weight_lbs / 2.2046
		finish_row.custom_total_lbs = weight_lbs

	# submit() runs validate() itself (which will recompute amount from
	# basic_rate x qty again and land on the same number, since basic_rate
	# is already correct and set_basic_rate_manually stops it being
	# touched) - no separate se.save() round trip needed first.
	se.submit()

	frappe.db.set_value("Dyeing Receipt", dr.name, "repack_stock_entry", se.name)
	_rollup_received_qty(dr, sign=1)


def cancel_linked_stock_entry(dyeing_receipt):
	dr = dyeing_receipt
	if not dr.repack_stock_entry:
		return
	se = frappe.get_doc("Stock Entry", dr.repack_stock_entry)
	if se.docstatus == 1:
		se.cancel()
	_rollup_received_qty(dr, sign=-1)


def _validate_against_issued_balance(dr):
	"""'The received values shouldn't be greater than the issued values' -
	checked per row against the matching Dyeing Contract Item's Issued
	totals (Pcs/Rolls/Weight), including whatever was already received on
	earlier Dyeing Receipts against that same row. Hard-throws naming the
	item/color and both numbers, rather than silently capping - matches
	this project's existing 'surface it, don't silently under/over-post'
	pattern."""
	for row in dr.items or []:
		if not row.dyeing_contract_item:
			continue
		dci = frappe.db.get_value(
			"Dyeing Contract Item",
			row.dyeing_contract_item,
			["item", "color", "issued_qty", "received_qty", "rolls_issued", "rolls_received",
				"weight_issued_kg", "weight_received_kg"],
			as_dict=True,
		)
		if not dci:
			continue

		new_received_qty = flt(dci.received_qty) + flt(row.received_qty)
		new_rolls_received = flt(dci.rolls_received) + flt(row.rolls_received)
		new_weight_received = flt(dci.weight_received_kg) + flt(row.weight_received_kg)

		if new_received_qty - flt(dci.issued_qty) > 0.0001:
			frappe.throw(
				_(
					"Item {0} / Color {1}: Received Qty would total {2} Pcs, more than the {3} "
					"Pcs issued against this Dyeing Contract row."
				).format(dci.item, dci.color, new_received_qty, dci.issued_qty)
			)
		if new_rolls_received - flt(dci.rolls_issued) > 0.0001:
			frappe.throw(
				_(
					"Item {0} / Color {1}: Rolls (Received) would total {2}, more than the {3} "
					"Rolls (Issued) against this Dyeing Contract row."
				).format(dci.item, dci.color, new_rolls_received, dci.rolls_issued)
			)
		if new_weight_received - flt(dci.weight_issued_kg) > 0.0001:
			frappe.throw(
				_(
					"Item {0} / Color {1}: Weight (kg) (Received) would total {2} kg, more than "
					"the {3} kg issued against this Dyeing Contract row."
				).format(dci.item, dci.color, new_weight_received, dci.weight_issued_kg)
			)


def _rollup_received_qty(dr, sign):
	contracts_touched = set()
	for row in dr.items or []:
		if not row.dyeing_contract_item:
			continue
		if not (flt(row.received_qty) or flt(row.rolls_received) or flt(row.weight_received_kg)):
			continue

		current = frappe.db.get_value(
			"Dyeing Contract Item",
			row.dyeing_contract_item,
			["received_qty", "rolls_received", "weight_received_kg"],
			as_dict=True,
		)
		frappe.db.set_value(
			"Dyeing Contract Item",
			row.dyeing_contract_item,
			{
				"received_qty": flt(current.received_qty) + sign * flt(row.received_qty),
				"rolls_received": flt(current.rolls_received) + sign * flt(row.rolls_received),
				"weight_received_kg": flt(current.weight_received_kg) + sign * flt(row.weight_received_kg),
			},
		)
		if row.dyeing_contract:
			contracts_touched.add(row.dyeing_contract)

	for dc_name in contracts_touched:
		totals = frappe.db.sql(
			"select sum(received_qty), sum(rolls_received), sum(weight_received_kg) "
			"from `tabDyeing Contract Item` where parent=%s",
			dc_name,
		)[0]
		total_received_qty = flt(totals[0])
		total_rolls_received = flt(totals[1])
		total_weight_received_kg = flt(totals[2])

		issued_totals = frappe.db.get_value(
			"Dyeing Contract",
			dc_name,
			["total_issue_qty", "total_rolls_issued", "total_weight_issued_kg"],
			as_dict=True,
		)
		frappe.db.set_value(
			"Dyeing Contract",
			dc_name,
			{
				"total_received_qty": total_received_qty,
				"total_rolls_received": total_rolls_received,
				"total_weight_received_kg": total_weight_received_kg,
				"balance_qty": flt(issued_totals.total_issue_qty) - total_received_qty,
				"balance_rolls": flt(issued_totals.total_rolls_issued) - total_rolls_received,
				"balance_weight_kg": flt(issued_totals.total_weight_issued_kg) - total_weight_received_kg,
			},
		)