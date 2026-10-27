import math

import frappe
from frappe import _
from frappe.utils import flt

# Stitching and Finishing - the last workstation after Long Hemming
# (2026-09-26). ("Stitching & Finishing" in your spec - Frappe doesn't
# allow "&" in a DocType name, so it's "Stitching and Finishing".)
#
# Flow: submitted Long Hemming -> Create > Stitching and Finishing (or
# Get Items From > Long Hemming on a new one) -> draft prefilled with:
#   Items   - one row per Long Hemming row: Finish Item, Color, A/B Qty,
#             Color Batch; Finish Weight + Weight UOM from the Towel Costing
#             Sheet's Finish Item row; Pcs per Pack / Pack Per Ctn from the
#             Sales Order Item; Total Ctn = (A+B) / (Pcs per Pack x Pack
#             Per Ctn).
#   Trims   - the TCS Trims table rows for each Finish Item (Item, Qty,
#             Consumption Unit) + Qty Required from the Items rows' A+B:
#               Per Pcs  -> Qty x (A+B)
#               Per Pack -> Qty x (A+B) / Pcs per Pack
#               Per Ctn  -> Qty x Total Ctn
#             Trims in a whole-number UOM (Nos etc.) are rounded UP per
#             Items row, since each row is consumed in its own entry.
#   Waste   - same "Hemming Wastage" table as Long Hemming (entered by hand).
#
# On submit:
#   - one Manufacture Stock Entry PER ITEMS ROW (= per item + color batch,
#     so each color keeps its own cost instead of being averaged):
#     consumes that row's hemmed towels (A+B, Color Batch) from Source
#     Warehouse (B Qty from B Qty Source Warehouse if set) + that row's
#     share of the trims from Trims Warehouse, produces the same item /
#     Color Batch into Target Warehouse. Trims value (and the hemming
#     charge already in the towels' value) rolls into the finished stock.
#   - one Material Receipt for the Waste Items (same as Long Hemming).
# On cancel all of them are cancelled.


# ---------------------------------------------------------------------------
# Create from Long Hemming
# ---------------------------------------------------------------------------


@frappe.whitelist()
def create_stitching_and_finishing_from_long_hemming(long_hemming):
	lh = frappe.get_doc("Long Hemming", long_hemming)
	if lh.docstatus != 1:
		frappe.throw(_("Long Hemming must be submitted first."))

	doc = frappe.new_doc("Stitching and Finishing")
	fill_from_long_hemming(doc, lh)
	return doc


def check_not_already_used(doc):
	"""Only one (non-cancelled) Stitching and Finishing per Long Hemming."""
	if not doc.get("long_hemming"):
		return
	filters = {"long_hemming": doc.long_hemming, "docstatus": ["!=", 2]}
	if doc.name and not doc.is_new():
		filters["name"] = ["!=", doc.name]
	existing = frappe.db.get_value("Stitching and Finishing", filters, "name")
	if existing:
		frappe.throw(
			_("Long Hemming {0} already has a Stitching and Finishing ({1}) - open/amend that one instead.").format(
				doc.long_hemming, existing
			)
		)


def fill_from_long_hemming(doc, lh):
	doc.long_hemming = lh.name
	check_not_already_used(doc)

	# Normal (A, or A+B combined) towels are in the Long Hemming's target;
	# with Transfer B Qty the B towels went to its B Qty Warehouse.
	doc.source_warehouse = lh.target_warehouse
	doc.b_qty_source_warehouse = lh.b_qty_warehouse if lh.transfer_b_qty else None
	doc.set("items", [])

	for row in lh.items or []:
		a_qty, b_qty = flt(row.a_qty), flt(row.b_qty)
		if not (a_qty or b_qty):
			continue

		so_item = _get_sales_order_item(row.sales_order, row.item, row.color)
		tcs = so_item.get("custom_towel_costing_sheet") if so_item else None
		finish = _get_tcs_finish_row(tcs, row.item)

		doc.append(
			"items",
			{
				"finish_item": row.item,
				"color": row.color,
				"finish_weight": flt(finish.get("finish_weight")) if finish else 0,
				"weight_uom": finish.get("uom") if finish else None,
				"a_qty": a_qty,
				"b_qty": b_qty,
				"pcs_per_pack": flt(so_item.get("custom_pcs_per_pack")) if so_item else 0,
				"pack_per_ctn": flt(so_item.get("custom_pack_per_ctn")) if so_item else 0,
				"sales_order": row.sales_order,
				"sales_order_item": so_item.get("name") if so_item else None,
				"towel_costing_sheet": tcs,
				"color_batch": row.color_batch,
				"long_hemming_item": row.name,
			},
		)

	if not doc.items:
		frappe.throw(_("{0} has no rows with A Qty / B Qty - nothing to stitch.").format(lh.name))

	fetch_trims_from_tcs(doc)
	recalculate(doc)


def _get_sales_order_item(sales_order, item_code, color):
	if not (sales_order and item_code):
		return None
	fields = ["name", "custom_towel_costing_sheet", "custom_pcs_per_pack", "custom_pack_per_ctn"]
	filters = {"parent": sales_order, "item_code": item_code}
	if color:
		row = frappe.db.get_value("Sales Order Item", dict(filters, custom_color=color), fields, as_dict=True)
		if row:
			return row
	return frappe.db.get_value("Sales Order Item", filters, fields, as_dict=True)


def _get_tcs_finish_row(towel_costing_sheet, item_code):
	if not towel_costing_sheet:
		return None
	tcs = frappe.get_cached_doc("Towel Costing Sheet", towel_costing_sheet)
	for r in tcs.get("finish_item_towel_costing") or []:
		if r.article == item_code:
			return r
	return None


# ---------------------------------------------------------------------------
# Trims
# ---------------------------------------------------------------------------


def fetch_trims_from_tcs(doc):
	"""(Re)build the Trims Consumption table from each Items row's Towel
	Costing Sheet: every TCS Trims row for that Finish Item (a TCS trim with
	no Finish Item applies to every Finish Item on that sheet). One set of
	rows per (TCS, Finish Item)."""
	doc.set("trims", [])
	seen = set()
	for row in doc.items or []:
		key = (row.towel_costing_sheet, row.finish_item)
		if not row.towel_costing_sheet or key in seen:
			continue
		seen.add(key)

		tcs = frappe.get_cached_doc("Towel Costing Sheet", row.towel_costing_sheet)
		merged = {}
		for t in tcs.get("trims") or []:
			if not t.item_code:
				continue
			if t.finish_item and t.finish_item != row.finish_item:
				continue
			k = (t.item_code, (t.consumption_unit or "").strip())
			merged[k] = merged.get(k, 0) + flt(t.consumed_qty)

		for (item_code, unit), consumed in merged.items():
			doc.append(
				"trims",
				{
					"finish_item": row.finish_item,
					"item_code": item_code,
					"consumption_unit": unit,
					"consumed_qty": consumed,
					"uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
					"towel_costing_sheet": row.towel_costing_sheet,
				},
			)


def get_total_ctn(qty, pcs_per_pack, pack_per_ctn):
	per_ctn = flt(pcs_per_pack) * flt(pack_per_ctn)
	return flt(qty) / per_ctn if per_ctn else 0


def trim_applies(trim, row):
	"""A trim row belongs to an Items row with the same Finish Item and -
	when both carry one - the same Towel Costing Sheet (so an item coming
	from two Sales Orders / TCS doesn't get both trim sets)."""
	if trim.finish_item != row.finish_item:
		return False
	if trim.get("towel_costing_sheet") and row.get("towel_costing_sheet"):
		return trim.towel_costing_sheet == row.towel_costing_sheet
	return True


def trim_qty_for_row(trim, item_row):
	"""Qty of one trim for one Items row -> (qty, problem). Rounded up for a
	whole-number UOM (each row is its own Stock Entry)."""
	total = flt(item_row.a_qty) + flt(item_row.b_qty)
	unit = (trim.consumption_unit or "").strip()
	consumed = flt(trim.consumed_qty)

	if unit == "Per Pcs":
		qty = consumed * total
	elif unit == "Per Pack":
		if not flt(item_row.pcs_per_pack):
			return 0, _("Items row {0} ({1}): Pcs per Pack is empty").format(item_row.idx, item_row.finish_item)
		qty = consumed * total / flt(item_row.pcs_per_pack)
	elif unit == "Per Ctn":
		if not (flt(item_row.pcs_per_pack) and flt(item_row.pack_per_ctn)):
			return 0, _("Items row {0} ({1}): Pcs per Pack / Pack Per Ctn is empty").format(
				item_row.idx, item_row.finish_item
			)
		qty = consumed * get_total_ctn(total, item_row.pcs_per_pack, item_row.pack_per_ctn)
	else:
		return 0, _("Trim {0}: no Consumption Unit").format(trim.item_code)

	uom = trim.get("uom") or frappe.get_cached_value("Item", trim.item_code, "stock_uom")
	if qty and uom and frappe.get_cached_value("UOM", uom, "must_be_whole_number"):
		qty = math.ceil(qty - 0.0001)
	return qty, None


def recalculate(doc):
	"""Row totals, parent totals and every trim's Qty Required. Returns the
	list of problems (missing Pcs per Pack etc.) so submit can block on it."""
	total_a = total_b = total_ctn = 0.0
	for row in doc.items or []:
		row.total_qty = flt(row.a_qty) + flt(row.b_qty)
		row.total_ctn = get_total_ctn(row.total_qty, row.pcs_per_pack, row.pack_per_ctn)
		total_a += flt(row.a_qty)
		total_b += flt(row.b_qty)
		total_ctn += flt(row.total_ctn)

	doc.total_a_qty = total_a
	doc.total_b_qty = total_b
	doc.total_qty = total_a + total_b
	doc.total_ctn = total_ctn

	problems = []
	for trim in doc.trims or []:
		if trim.item_code and not trim.uom:
			trim.uom = frappe.get_cached_value("Item", trim.item_code, "stock_uom")
		qty = 0.0
		for row in doc.items or []:
			if not trim_applies(trim, row):
				continue
			row_qty, problem = trim_qty_for_row(trim, row)
			if problem:
				problems.append(problem)
			qty += row_qty
		trim.qty_required = qty
	return sorted(set(problems))


# ---------------------------------------------------------------------------
# Stock entries
# ---------------------------------------------------------------------------


def create_stock_entries(doc):
	company = frappe.get_cached_value("Warehouse", doc.source_warehouse, "company") or frappe.defaults.get_global_default(
		"company"
	)
	trims_warehouse = doc.trims_warehouse or doc.source_warehouse

	rows = [r for r in doc.items or [] if flt(r.total_qty) > 0]
	if not rows:
		frappe.throw(_("No Items have an A Qty / B Qty - nothing to finish."))

	se_names = []
	for row in rows:
		finish_item = row.finish_item
		stock_uom = frappe.get_cached_value("Item", finish_item, "stock_uom")
		has_batch = frappe.get_cached_value("Item", finish_item, "has_batch_no")
		if has_batch and not row.color_batch:
			frappe.throw(_("Items row {0} ({1} / {2}) has no Color Batch.").format(row.idx, finish_item, row.color))
		batch_no = row.color_batch if has_batch else None

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Manufacture"
		se.purpose = "Manufacture"
		se.company = company
		se.set_posting_time = 1
		se.posting_date = doc.date
		se.use_serial_batch_fields = 1
		se.remarks = _("Stitching and Finishing {0}, row {1}").format(doc.name, row.idx)
		if row.sales_order and se.meta.has_field("custom_sales_order"):
			se.custom_sales_order = row.sales_order

		# hemmed towels in (B Qty from its own warehouse if one is set)
		if doc.get("b_qty_source_warehouse"):
			legs = [(flt(row.a_qty), doc.source_warehouse), (flt(row.b_qty), doc.b_qty_source_warehouse)]
		else:
			legs = [(flt(row.total_qty), doc.source_warehouse)]
		for qty, warehouse in legs:
			if qty <= 0:
				continue
			se.append(
				"items",
				{
					"item_code": finish_item,
					"qty": qty,
					"uom": stock_uom,
					"stock_uom": stock_uom,
					"conversion_factor": 1,
					"s_warehouse": warehouse,
					"batch_no": batch_no,
					"use_serial_batch_fields": 1,
				},
			)

		# this row's share of the trims & accessories
		for trim in doc.trims or []:
			if not trim.item_code or not trim_applies(trim, row):
				continue
			qty, _problem = trim_qty_for_row(trim, row)
			if qty <= 0:
				continue
			trim_uom = frappe.get_cached_value("Item", trim.item_code, "stock_uom")
			se.append(
				"items",
				{
					"item_code": trim.item_code,
					"qty": qty,
					"uom": trim_uom,
					"stock_uom": trim_uom,
					"conversion_factor": 1,
					"s_warehouse": trims_warehouse,
				},
			)

		# finished towels out
		se.append(
			"items",
			{
				"item_code": finish_item,
				"qty": row.total_qty,
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1,
				"t_warehouse": doc.target_warehouse,
				"is_finished_item": 1,
				"batch_no": batch_no,
				"use_serial_batch_fields": 1,
			},
		)

		se.insert(ignore_permissions=True)
		se.submit()
		se_names.append(se.name)

	frappe.db.set_value("Stitching and Finishing", doc.name, "manufacture_stock_entries", "\n".join(se_names))


def create_waste_receipt_entry(doc):
	if not doc.get("waste_items"):
		return

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.purpose = "Material Receipt"
	se.company = frappe.get_cached_value("Warehouse", doc.source_warehouse, "company") or frappe.defaults.get_global_default(
		"company"
	)
	se.set_posting_time = 1
	se.posting_date = doc.date
	se.remarks = _("Waste from Stitching and Finishing {0}").format(doc.name)

	for row in doc.waste_items:
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
	frappe.db.set_value("Stitching and Finishing", doc.name, "waste_stock_entry", se.name)


def cancel_stock_entries(doc):
	names = [n.strip() for n in (doc.get("manufacture_stock_entries") or "").split("\n") if n.strip()]
	if doc.get("waste_stock_entry"):
		names.append(doc.waste_stock_entry)
	for name in reversed(names):
		if not frappe.db.exists("Stock Entry", name):
			continue
		se = frappe.get_doc("Stock Entry", name)
		if se.docstatus == 1:
			se.cancel()
