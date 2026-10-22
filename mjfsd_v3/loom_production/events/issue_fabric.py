import json

import frappe
from frappe import _
from frappe.utils import flt

# "Issue Fabric" button (shown once Dyeing Contract is submitted) - asks
# for item(s)/qty, creates ONE Material Transfer Stock Entry covering
# every item picked (per spec: "there can be multiple items ... in single
# Material Transfer entry"). Each row is tagged with that item's Greige
# Batch - this is the "same batch will be issued in Issuance of Dyeing
# Contract" part of your spec. Source Warehouse -> Target Warehouse per
# Dyeing Contract's own fields (our warehouse -> the dyer's warehouse -
# flagged assumption, see CHANGES.md).
#
# 2026-09-14 update: each row can also carry No. of Rolls / Weight (Kgs) -
# recorded on the Stock Entry's item row as custom_no_of_rolls /
# custom_weight_kgs (new custom fields, see custom/stock_entry_detail.json).
#
# 2026-09-14 (batch 2) update: those same No. of Rolls / Weight (Kgs)
# values now also accumulate into the Dyeing Contract Item's own
# rolls_issued / weight_issued_kg fields (mirroring how issued_qty already
# accumulated), and roll further up into the Dyeing Contract's parent
# totals + balance fields.
#
# 2026-09-15 hotfix:
# - Each Stock Entry item row is now tagged with custom_dyeing_contract_item
#   (new hidden field on Stock Entry Detail) so it can trace back to the
#   Dyeing Contract Item row it came from.
# - use_serial_batch_fields=1 is set on the row - required in this ERPNext
#   version when setting batch_no directly via API, otherwise a second
#   stock movement of the same batch can fail with "Serial and Batch
#   Bundle ... has already created" (hit on Dyed Fabric Issuance, which
#   moves the same Color Batch a second time after the Dyeing Receipt's
#   Repack entry already moved it once).
# - reverse_issued_qty() (new) is wired as a Stock Entry on_cancel
#   doc_event in hooks.py - whenever a Stock Entry created here gets
#   cancelled, however that happens (Dyeing Contract cancel cascading
#   into it via cancel_issued_stock_entries() below, or a user cancelling
#   the Stock Entry directly from the Stock Entry list), the matching
#   Dyeing Contract Item's issued_qty/rolls_issued/weight_issued_kg get
#   decremented back down and the Dyeing Contract's totals/balance
#   recompute.
#
# 2026-09-15 (feature v3) - Issue Fabric UX change: "upon clicking issue
# data gets filled in stock entry and stock entry form gets opened in
# Stock Entry and he submits it manually" (your words). issue_fabric() no
# longer submits the Stock Entry itself - it only inserts a draft and
# hands the whole doc back so the browser can route to it (dyeing_contract.js
# does frappe.model.sync + frappe.set_route, same pattern already used by
# every other "create and open" button in this project). Because
# submission is now in the user's hands, Issued Qty/Rolls/Weight can no
# longer be accumulated at draft-creation time - a draft the user abandons
# or deletes without submitting would leave those numbers permanently
# overstated with nothing to reverse them (reverse_issued_qty only fires
# on a *cancel*, not on discarding a draft). So that accumulation moved to
# a new apply_issued_qty(), wired as a Stock Entry on_submit hook
# (mirroring reverse_issued_qty's on_cancel hook) - it only fires once the
# user actually submits the Stock Entry themselves from its own form.
#
# 2026-09-16 - "again same error, dyeing contract not getting updated
# upon submitting material transfer entry" (your words, twice now). The
# custom_dyeing_contract reference field on the Stock Entry itself IS
# landing correctly (confirmed from your screenshot) - that's set
# directly in issue_fabric() above, no hooks.py involved. Issued Qty
# staying at 0 specifically points at apply_issued_qty not actually
# firing, which can only mean the Stock Entry on_submit entry never made
# it into mjfsd_v3's hooks.py doc_events (still haven't seen that file to
# confirm/fix directly).
#
# Rather than keep guessing at a file I can't see, added a second,
# hooks.py-independent path: sync_issued_totals() below recomputes
# Issued Qty/Rolls/Weight for every row on a Dyeing Contract straight
# from a live query against submitted Stock Entries (tagged via
# custom_dyeing_contract_item), instead of trusting the incremental
# accumulator apply_issued_qty/reverse_issued_qty maintain. Wired to run
# every time the Dyeing Contract form is opened (dyeing_contract.js
# refresh()) - self-heals on its own, no Save click needed, and doesn't
# care whether the on_submit hook is wired or not. The hooks.py entries
# are still worth fixing for true real-time updates without reopening
# the page, but this closes the actual gap you're blocked on right now.


@frappe.whitelist()
def issue_fabric(dyeing_contract, rows):
	"""rows: JSON list of {"row_name": <Dyeing Contract Item name>, "qty": <float>,
	"no_of_rolls": <float>, "weight_kgs": <float>}. Returns the inserted
	(not yet submitted) Stock Entry doc, for the browser to route to."""
	if isinstance(rows, str):
		rows = json.loads(rows)

	dc = frappe.get_doc("Dyeing Contract", dyeing_contract)
	if dc.docstatus != 1:
		frappe.throw(_("Dyeing Contract must be submitted before fabric can be issued."))

	dc_rows_by_name = {r.name: r for r in dc.items}

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = frappe.defaults.get_global_default("company")
	# New parent-level Stock Entry custom fields (mjfsd_v3/custom/stock_entry.json)
	# - "why are there no references of documents in stock entry" - so
	# opening this Stock Entry shows which Dyeing Contract/Sales Order it
	# came from, not just the per-row custom_dyeing_contract_item tag.
	se.custom_dyeing_contract = dc.name
	if dc.sales_order:
		se.custom_sales_order = dc.sales_order

	issued_any = False
	for entry in rows:
		qty = flt(entry.get("qty"))
		if not qty:
			continue

		row_name = entry.get("row_name")
		dc_row = dc_rows_by_name.get(row_name)
		if not dc_row:
			frappe.throw(_("Row {0} not found on Dyeing Contract {1}").format(row_name, dc.name))
		if not dc_row.greige_batch:
			frappe.throw(_("Row for Item {0} has no Greige Batch - can't issue.").format(dc_row.item))

		no_of_rolls = flt(entry.get("no_of_rolls"))
		weight_kgs = flt(entry.get("weight_kgs"))

		se.append(
			"items",
			{
				"s_warehouse": dc.source_warehouse,
				"t_warehouse": dc.target_warehouse,
				"item_code": dc_row.item,
				"qty": qty,
				"batch_no": dc_row.greige_batch,
				"use_serial_batch_fields": 1,
				"uom": frappe.db.get_value("Item", dc_row.item, "stock_uom"),
				"custom_no_of_rolls": no_of_rolls,
				"custom_weight_kgs": weight_kgs,
				"custom_dyeing_contract_item": row_name,
			},
		)
		issued_any = True

	if not issued_any:
		frappe.throw(_("Enter a qty to issue for at least one item."))

	se.insert(ignore_permissions=True)

	if not frappe.db.get_value("Dyeing Contract", dc.name, "status"):
		frappe.db.set_value("Dyeing Contract", dc.name, "status", "Fabric Issued")

	return se


def cancel_issued_stock_entries(doc):
	"""Dyeing Contract on_cancel. Refuses to cancel if anything has already
	been received back on a Dyeing Receipt against this contract (that
	Received Qty would otherwise be left pointing at a cancelled contract
	with no way to reconcile it) - cancel/amend those Dyeing Receipts
	first. Otherwise finds every Stock Entry Issue Fabric created against
	this contract (via the custom_dyeing_contract_item tag on Stock Entry
	Detail rows) and cancels each one still submitted - which itself
	triggers reverse_issued_qty() below via the Stock Entry on_cancel
	hook, so the accumulators end up correct without duplicating that
	logic here. A draft (never submitted) Stock Entry left over from an
	abandoned Issue Fabric is simply skipped - issued_qty was never
	incremented for it in the first place."""
	if flt(doc.total_received_qty) or flt(doc.total_rolls_received) or flt(doc.total_weight_received_kg):
		frappe.throw(
			_(
				"Can't cancel {0} - {1} Pcs / {2} Rolls / {3} kg have already been received "
				"against it on a Dyeing Receipt. Cancel/amend those Dyeing Receipts first."
			).format(
				doc.name, doc.total_received_qty, doc.total_rolls_received, doc.total_weight_received_kg
			)
		)

	item_rows = [row.name for row in doc.items or []]
	if not item_rows:
		return

	se_names = set(
		frappe.get_all(
			"Stock Entry Detail",
			filters={"custom_dyeing_contract_item": ["in", item_rows]},
			pluck="parent",
		)
	)
	for se_name in se_names:
		se = frappe.get_doc("Stock Entry", se_name)
		if se.docstatus == 1:
			se.cancel()


def apply_issued_qty(doc, method=None):
	"""Stock Entry on_submit hook - wire in mjfsd_v3's hooks.py alongside the
	existing on_cancel entry:
	doc_events = {"Stock Entry": {
		"on_submit": "mjfsd_v3.loom_production.events.issue_fabric.apply_issued_qty",
		"on_cancel": "mjfsd_v3.loom_production.events.issue_fabric.reverse_issued_qty",
	}}
	Mirrors reverse_issued_qty() below. Only acts on rows tagged with
	custom_dyeing_contract_item - every other Stock Entry in the system is
	untouched. Fires once the user manually submits an Issue Fabric draft
	from its own Stock Entry form (issue_fabric() above only inserts it).

	2026-09-28 - weight_issued_kg (label now says LBS) is no longer
	accumulated from custom_weight_kgs (a manual entry on the Stock
	Entry row) - it's derived from Issued Qty and the TCS Finish Weight
	(see calc_weight_lbs/_get_tcs_finish_weight below, same formula
	dyeing_contract.py's own recalculate_totals uses), recomputed here
	each time issued_qty changes so it doesn't go stale between form
	saves. Amount follows the same way: Rate x weight_issued_kg (lbs)."""
	contracts_touched = set()
	for row in doc.items or []:
		dci_name = row.get("custom_dyeing_contract_item")
		if not dci_name:
			continue
		current = frappe.db.get_value(
			"Dyeing Contract Item",
			dci_name,
			["issued_qty", "rolls_issued", "rate", "towel_costing_sheet", "item", "parent"],
			as_dict=True,
		)
		if not current:
			continue
		_set_issued_qty(dci_name, current, flt(current.issued_qty) + flt(row.qty), current.rolls_issued)
		contracts_touched.add(current.parent)

	for dc_name in contracts_touched:
		_recompute_dyeing_contract_issue_totals(dc_name)


def reverse_issued_qty(doc, method=None):
	"""Stock Entry on_cancel hook - wire in mjfsd_v3's hooks.py:
	doc_events = {"Stock Entry": {"on_cancel": "mjfsd_v3.loom_production.events.issue_fabric.reverse_issued_qty"}}
	Only acts on rows tagged with custom_dyeing_contract_item - every other
	Stock Entry in the system (including Dyed Fabric Issuance's and Long
	Hemming's own transfers, and anything unrelated to this app) is
	untouched. See apply_issued_qty above re: weight_issued_kg/amount."""
	contracts_touched = set()
	for row in doc.items or []:
		dci_name = row.get("custom_dyeing_contract_item")
		if not dci_name:
			continue
		current = frappe.db.get_value(
			"Dyeing Contract Item",
			dci_name,
			["issued_qty", "rolls_issued", "rate", "towel_costing_sheet", "item", "parent"],
			as_dict=True,
		)
		if not current:
			continue
		new_issued_qty = max(0, flt(current.issued_qty) - flt(row.qty))
		new_rolls_issued = max(0, flt(current.rolls_issued) - flt(row.get("custom_no_of_rolls")))
		_set_issued_qty(dci_name, current, new_issued_qty, new_rolls_issued)
		contracts_touched.add(current.parent)

	for dc_name in contracts_touched:
		_recompute_dyeing_contract_issue_totals(dc_name)


@frappe.whitelist()
def sync_issued_totals(dyeing_contract):
	"""Self-healing recompute, hooks.py-independent - see the 2026-09-16
	note above. Queries actually-submitted Stock Entries directly (rather
	than trusting the incremental accumulator apply_issued_qty/
	reverse_issued_qty maintain) and overwrites each row's issued_qty/
	rolls_issued with the real number, then re-derives weight_issued_kg
	(lbs) and amount from that - same formula as everywhere else. Only
	writes (and only tells the caller to reload) when something was
	actually stale, so opening an already-correct Dyeing Contract is a
	no-op."""
	dc = frappe.get_doc("Dyeing Contract", dyeing_contract)
	row_names = [row.name for row in dc.items or []]
	if not row_names:
		return {"changed": False}

	totals = frappe.db.sql(
		"""
		select sed.custom_dyeing_contract_item as row_name,
		       sum(sed.qty) as issued_qty,
		       sum(sed.custom_no_of_rolls) as rolls_issued
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1
		  and sed.custom_dyeing_contract_item in %(row_names)s
		group by sed.custom_dyeing_contract_item
		""",
		{"row_names": row_names},
		as_dict=True,
	)
	totals_by_row = {t.row_name: t for t in totals}

	changed = False
	tcs_cache = {}
	for row in dc.items or []:
		t = totals_by_row.get(row.name)
		real_issued_qty = flt(t.issued_qty) if t else 0.0
		real_rolls_issued = flt(t.rolls_issued) if t else 0.0
		tcs_finish_weight = _get_tcs_finish_weight(tcs_cache, row.towel_costing_sheet, row.item)
		real_weight_issued_kg = calc_weight_lbs(real_issued_qty, tcs_finish_weight)
		real_amount = flt(row.rate) * real_weight_issued_kg

		if (
			abs(real_issued_qty - flt(row.issued_qty)) > 0.0001
			or abs(real_rolls_issued - flt(row.rolls_issued)) > 0.0001
			or abs(real_weight_issued_kg - flt(row.weight_issued_kg)) > 0.0001
		):
			frappe.db.set_value(
				"Dyeing Contract Item",
				row.name,
				{
					"issued_qty": real_issued_qty,
					"rolls_issued": real_rolls_issued,
					"weight_issued_kg": real_weight_issued_kg,
					"amount": real_amount,
				},
			)
			changed = True

	if changed:
		_recompute_dyeing_contract_issue_totals(dc.name)

	return {"changed": changed}


def _set_issued_qty(dci_name, current, new_issued_qty, new_rolls_issued):
	tcs_finish_weight = _get_tcs_finish_weight({}, current.towel_costing_sheet, current.item)
	weight_issued_kg = calc_weight_lbs(new_issued_qty, tcs_finish_weight)
	frappe.db.set_value(
		"Dyeing Contract Item",
		dci_name,
		{
			"issued_qty": new_issued_qty,
			"rolls_issued": new_rolls_issued,
			"weight_issued_kg": weight_issued_kg,
			"amount": flt(current.rate) * weight_issued_kg,
		},
	)


def calc_weight_lbs(pcs, tcs_finish_weight):
	"""2026-09-28 (feature v3) - "((Pcs * finish weight mentioned in TCS)
	/1000)*2.2046" (your words). TCS Finish Weight is grams per piece;
	/1000 -> kg, x2.2046 -> lbs. Duplicated from dyeing_contract.py (same
	formula, kept local per this codebase's usual per-file convention)."""
	return (flt(tcs_finish_weight) / 1000) * flt(pcs) * 2.2046


def _get_tcs_finish_weight(tcs_cache, towel_costing_sheet, item_code):
	if not (towel_costing_sheet and item_code):
		return 0.0
	tcs = tcs_cache.get(towel_costing_sheet)
	if tcs is None:
		tcs = frappe.get_doc("Towel Costing Sheet", towel_costing_sheet)
		tcs_cache[towel_costing_sheet] = tcs
	for row in tcs.finish_item_towel_costing or []:
		if row.article == item_code:
			return flt(row.finish_weight)
	return 0.0


def _recompute_dyeing_contract_issue_totals(dc_name):
	totals = frappe.db.sql(
		"select sum(issued_qty), sum(rolls_issued), sum(weight_issued_kg) "
		"from `tabDyeing Contract Item` where parent=%s",
		dc_name,
	)[0]
	total_issue_qty = flt(totals[0])
	total_rolls_issued = flt(totals[1])
	total_weight_issued_kg = flt(totals[2])

	received_totals = frappe.db.get_value(
		"Dyeing Contract",
		dc_name,
		["total_received_qty", "total_rolls_received", "total_weight_received_kg"],
		as_dict=True,
	)
	frappe.db.set_value(
		"Dyeing Contract",
		dc_name,
		{
			"total_issue_qty": total_issue_qty,
			"total_rolls_issued": total_rolls_issued,
			"total_weight_issued_kg": total_weight_issued_kg,
			"balance_qty": total_issue_qty - flt(received_totals.total_received_qty),
			"balance_rolls": total_rolls_issued - flt(received_totals.total_rolls_received),
			"balance_weight_kg": total_weight_issued_kg - flt(received_totals.total_weight_received_kg),
		},
	)