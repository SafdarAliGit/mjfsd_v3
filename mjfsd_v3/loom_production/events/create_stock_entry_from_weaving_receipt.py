import frappe
from frappe import _
from frappe.utils import flt


def create_manufacture_stock_entry(weaving_receipt):
	"""Called from Weaving Receipt's on_submit. Raises ONE Manufacture
	Stock Entry for the whole document: one raw-material consumption row
	per (Weaving Receipt Item row x matching Towel Costing Sheet Materials
	row), plus one finished-item row per Weaving Receipt Item row.

	Per Kabeer's choice when asked: raw materials are taken literally from
	the Towel Costing Sheet's own Materials table (the raw yarn item, no
	Beam-item substitution for Pile/Ground - unlike Daily Towel
	Production), and ratio/weaving-wastage% are read fresh from that same
	Towel Costing Sheet rather than from the Weaving Contract's BOM Items.

	2026-09-15 (feature v3) update:
	- Consumed qty now uses Weight Actual (Lbs) instead of Weight (Actual)
	  kg ("yarn consumed qty is incorrect, just use the weight actual
	  (Lbs) now instead of weight actual" - your words).
	- The finished item row's basic_rate is now set explicitly:
	  (Total Outgoing Value + (Weight Actual (Lbs) x Rate)) / Finish Qty,
	  where Rate = the Weaving Contract's Weaving Rate Per Lbs.
	- The finished item row also gets the new Per LBS Rate custom field:
	  (Total Outgoing Value / Weight Actual (Lbs)) + Rate.
	  "Total Outgoing Value" is this Weaving Receipt Item row's own
	  attributable raw-material consumption value (self-contained per
	  row, not a blended total shared across unrelated finish items in
	  the same Stock Entry).

	2026-09-15 fix #1: restored the finished row's `batch_no` (= Greige
	Batch from the matching Sales Order Item, only when the Finish Item
	is batch-tracked) - this had been dropped by a rebuild from a stale
	local copy. Without it, submitting against a batch-tracked Finish
	Item fails with "Serial No / Batch No are mandatory for Item ...".

	2026-09-15 fix #2 (this fix): "Total Outgoing Value" used to be
	computed independently here via a Bin valuation-rate lookup at the
	time each raw-material row was appended. That guess can diverge from
	the rate Frappe's own valuation engine actually posts onto those rows
	during validate() (moving-average/FIFO timing, precision, etc.) -
	which is exactly what caused the Basic Rate / Per LBS Rate mismatch
	you reported (your worked example: 19965.40/100 + 55.115x45/100 =
	224.4, but the posted values didn't match that).

	Fixed by NOT setting any rate on the raw-material rows and letting
	Frappe compute them itself during se.insert(). Frappe mutates the
	same Python row objects in place, so right after insert() we read
	back each row's real `.amount` (this IS what "Total Outgoing Value"
	shows on the Stock Entry) and use THAT - not a separate guess - to
	compute the finished row's basic_rate and Per LBS Rate.

	2026-09-15 fix #3: fix #2 above then called se.save() (a second,
	separate validate pass) to bake the finished row's real basic_rate in
	before submit - and that's what you hit next ("total incoming value
	is 0"). Rather than trust that second validate() to also rewrite
	`amount`/`basic_amount` from the new `basic_rate` on its own,
	`amount`/`basic_amount` are now set explicitly ourselves right next to
	`basic_rate`, and the redundant se.save() is dropped entirely -
	se.submit() is called directly (submit() runs validate() itself, so
	nothing is lost, there's just one fewer round trip that could silently
	leave amount stale).

	2026-09-15 fix #4: the Stock Entry itself now also gets
	`custom_weaving_receipt` set (new parent-level Stock Entry custom
	field, see mjfsd_v3/custom/stock_entry.json) - "why are there no
	references of documents in stock entry" - so opening the Stock Entry
	on its own shows which Weaving Receipt created it, not just the
	per-row plumbing fields.
	"""
	wr = weaving_receipt

	if not wr.source_warehouse or not wr.target_warehouse:
		frappe.throw(_("Set both Source Warehouse and Target Warehouse before submitting."))

	company = frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw(
			_("No default Company is set for this site - required to raise the Manufacture Stock Entry.")
		)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Manufacture"
	se.purpose = "Manufacture"
	se.company = company
	se.custom_weaving_receipt = wr.name

	tcs_cache = {}
	# One entry per Weaving Receipt Item row: tracks the raw-material rows
	# we appended for it (to read back their authoritative .amount after
	# insert) and the finish row (to write basic_rate / custom_per_lbs_rate
	# onto once we know the real Total Outgoing Value).
	tracking = []

	for item_row in wr.items or []:
		if not item_row.finish_item:
			frappe.throw(_("Row #{0}: Finish Item is not set.").format(item_row.idx))
		if not item_row.towel_costing_sheet:
			frappe.throw(
				_("Row #{0} ({1}): TCS Reference is not set - can't work out raw materials without it.").format(
					item_row.idx, item_row.finish_item
				)
			)

		tcs = tcs_cache.get(item_row.towel_costing_sheet)
		if tcs is None:
			tcs = frappe.get_doc("Towel Costing Sheet", item_row.towel_costing_sheet)
			tcs_cache[item_row.towel_costing_sheet] = tcs

		wastage_percent = _get_weaving_wastage_percent(tcs, item_row.finish_item)
		weight_actual_lbs = flt(item_row.weight_actual_lbs)

		matched_any = False
		material_rows = []
		for material in tcs.materials or []:
			if material.item != item_row.finish_item:
				continue
			matched_any = True

			consumed_qty = weight_actual_lbs * (1 + wastage_percent / 100) * (flt(material.ratio) / 100)
			if consumed_qty <= 0:
				continue

			# No rate is set here on purpose - Frappe computes the real
			# valuation rate for this row during se.insert() below, and
			# that authoritative rate/amount is what we read back.
			material_row = se.append(
				"items",
				{
					"item_code": material.raw_material,
					"qty": consumed_qty,
					"uom": _stock_uom(material.raw_material),
					"s_warehouse": wr.source_warehouse,
				},
			)
			material_rows.append(material_row)

		if not matched_any:
			frappe.throw(
				_("Row #{0}: no Materials rows found on Towel Costing Sheet {1} for Finish Item {2}.").format(
					item_row.idx, item_row.towel_costing_sheet, item_row.finish_item
				)
			)

		finish_item_data = {
			"item_code": item_row.finish_item,
			"qty": flt(item_row.pcs_actual),
			"uom": _stock_uom(item_row.finish_item),
			"t_warehouse": wr.target_warehouse,
			"is_finished_item": 1,
			# Placeholder - overwritten below once the raw-material rows'
			# real amounts are known (after insert()). set_basic_rate_manually
			# stops ERPNext's own Manufacture rate calculator from
			# recomputing/overwriting basic_rate from the consumed rows.
			"basic_rate": 0.0,
			"set_basic_rate_manually": 1,
		}

		if frappe.db.get_value("Item", item_row.finish_item, "has_batch_no"):
			greige_batch = _get_greige_batch(item_row)
			if not greige_batch:
				frappe.throw(
					_(
						"Row #{0}: Finish Item {1} is batch-tracked but no Greige Batch was found "
						"on the matching Sales Order Item (item {1} on Sales Order {2})."
					).format(item_row.idx, item_row.finish_item, item_row.sales_order)
				)
			finish_item_data["batch_no"] = greige_batch
			# Required in this ERPNext version whenever batch_no is set
			# directly via API - see the 2026-09-15 hotfix in
			# claude/dyeing-workflow.md for the full "Serial and Batch
			# Bundle ... has already created" story.
			finish_item_data["use_serial_batch_fields"] = 1

		finish_row = se.append("items", finish_item_data)

		tracking.append(
			{
				"item_row": item_row,
				"material_rows": material_rows,
				"finish_row": finish_row,
				"weight_actual_lbs": weight_actual_lbs,
			}
		)

	# insert() runs validate(), which is what actually computes each
	# raw-material row's real basic_rate/amount via Frappe's own
	# valuation engine. It mutates the same row objects we already hold
	# references to in `tracking`, so we can read the real numbers back
	# below rather than trusting an independent guess.
	se.insert(ignore_permissions=True)

	for entry in tracking:
		row_outgoing_value = sum(flt(r.amount) for r in entry["material_rows"])
		weaving_rate_per_lbs = flt(_get_weaving_rate_per_lbs(entry["item_row"].weaving_contract))
		weight_actual_lbs = entry["weight_actual_lbs"]
		finish_row = entry["finish_row"]
		finish_qty = flt(finish_row.qty)

		basic_rate = 0.0
		if finish_qty:
			basic_rate = (row_outgoing_value + (weight_actual_lbs * weaving_rate_per_lbs)) / finish_qty
		finish_row.basic_rate = basic_rate
		# Set explicitly rather than left for a later validate() pass to
		# derive from basic_rate on its own - see fix #3 in the docstring
		# above (this is what was landing as 0 / "total incoming value is
		# 0").
		finish_row.basic_amount = basic_rate * finish_qty
		finish_row.amount = basic_rate * finish_qty

		if weight_actual_lbs:
			finish_row.custom_per_lbs_rate = (row_outgoing_value / weight_actual_lbs) + weaving_rate_per_lbs

		# New 2026-09-16 - "Total LBS" (Stock Entry Detail custom field,
		# see mjfsd_v3/custom/stock_entry_detail.json) = same value as this
		# Weaving Receipt Item row's own Weight Actual (Lbs), copied onto
		# the finish row so it's visible directly on the Stock Entry.
		finish_row.custom_total_lbs = weight_actual_lbs

	# submit() runs validate() itself (which will recompute amount from
	# basic_rate x qty again and land on the same number, since basic_rate
	# is already correct and set_basic_rate_manually stops it being
	# touched) - no separate se.save() round trip needed first.
	se.submit()

	frappe.db.set_value("Weaving Receipt", wr.name, "manufacture_stock_entry", se.name)

	return se.name


def cancel_linked_stock_entry(weaving_receipt):
	se_name = weaving_receipt.get("manufacture_stock_entry")
	if not se_name:
		return
	se = frappe.get_doc("Stock Entry", se_name)
	if se.docstatus == 1:
		se.cancel()


def _get_weaving_wastage_percent(tcs, finish_item):
	for row in tcs.finish_item_towel_costing or []:
		if row.article == finish_item:
			return flt(row.weaving_wastage_percet)
	return 0.0


def _get_weaving_rate_per_lbs(weaving_contract):
	if not weaving_contract:
		return 0.0
	return flt(frappe.db.get_value("Weaving Contract", weaving_contract, "weaving_rate_per_lbs"))


def _get_greige_batch(item_row):
	"""Mirrors the same lookup Dyeing Receipt uses for its own Color
	Batch - the Greige Batch is shared across every row of the same Item
	regardless of Color (see claude/dyeing-workflow.md), so this matches
	on Sales Order + Item Code only, not Color."""
	if not item_row.sales_order:
		return None
	return frappe.db.get_value(
		"Sales Order Item",
		{"parent": item_row.sales_order, "item_code": item_row.finish_item},
		"custom_greige_batch",
	)


def _stock_uom(item_code):
	return frappe.db.get_value("Item", item_code, "stock_uom")