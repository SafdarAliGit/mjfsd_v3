import frappe
from frappe.utils import cint, flt, nowtime

# Round 14 Part B (2026-09-09): original Daily Towel Production events file -
# see claude/daily-towel-production.md for the full spec this was built
# against (Kabeer's original spec, the four clarifying questions he
# answered, and the resulting design).
#
# Round 18 (2026-09-16): rewritten to fold in three changes Kabeer asked
# for while amending this doctype for the Weaving/Dyeing/Sizing workflow
# changes made elsewhere this session. NOTE: unlike most files touched
# this session, Kabeer did not paste his current live copy of this
# specific events file (he pasted daily_towel_production.py/.js and both
# doctype JSONs, but not this one) - so this is rebuilt fresh from the
# documented round 14 spec plus the three round 18 changes below, not a
# patch of a pasted original. The three changes themselves are the parts
# you actually asked for; the rest (query method, formulas, error
# handling) should match what's already live - flag anything that's
# drifted from your real file so it can be reconciled.
#
# Round 18 changes:
#   1. Stock Entry reference fields - every Manufacture Stock Entry this
#      creates now sets custom_sales_order and a new custom_
#      daily_towel_production (mjfsd_v3/custom/stock_entry.json), matching
#      the reference-field convention every other Stock-Entry-creating
#      flow in this project adopted this session.
#   2. Raw material lookup - the Beam-item Sizing Receipt lookup now
#      prefers matching on Weaving Contract (via the Sales Order Item's
#      linked Weaving Contract) instead of Sales Order + Yarn Item alone,
#      per your answer: "there can be multiple sizing receipts against
#      same sizing program, sales order, weaving contract" - narrowing by
#      Weaving Contract first cuts down the candidate pool, most-recent-
#      submitted is still the tie-breaker since even that isn't always
#      unique. Falls back to the old Sales Order + Yarn Item match if no
#      Weaving Contract can be resolved, so older data keeps working.
#   3. Greige Batch - the finished towel item row now carries batch_no,
#      read from the Sales Order Item's own custom_greige_batch field
#      ("the batch is already created and saved in sales order item
#      table in custom_greige_batch field", your words) - not created or
#      picked here, just consumed.
#
# Round 19 (2026-09-16): two changes.
#   1. get_raw_materials_for_row now also returns default_warehouse per
#      raw material (Beam Items -> the resolved Sizing Receipt's own
#      Target Warehouse, Yarn Items -> YARN_DEFAULT_WAREHOUSE below) so
#      the Raw Material Selection dialog can pre-fill the warehouse field
#      instead of leaving it blank - still editable, this is a default,
#      not a lock, per Kabeer: "yarn item warehouse will be Stores - PT
#      by default but editable."
#   2. Beam Items now also carry an explicit rate. Kabeer: "In Daily
#      Towel Production stock entry, qty is calculated correctly but
#      rates of source items are incorrect" - screenshot showed Beam item
#      consumption rows at implausibly low rates (Rs 1.42, Rs 2.71),
#      while the loose Yarn Item row was correct (Rs 350, matching
#      Item.valuation_rate). Working theory, confirmed by Kabeer: Beam -
#      PT's warehouse-ledger valuation is polluted by Sizing Receipts
#      submitted before round 17/19's set_basic_rate_manually fixes -
#      that bad history is now baked into the moving average and won't
#      self-correct just because the Sizing Receipt code is fixed going
#      forward. Kabeer chose to make this deterministic rather than
#      depend on ledger history (or a one-off data cleanup): Beam item
#      rows now get basic_rate set explicitly from the same Sizing
#      Receipt used to resolve them (Final Cost Of Beam / Beem Length,
#      same formula as create_stock_entry_from_sizing_receipt.py). See
#      create_manufacture_stock_entry_for_row below for how this is
#      threaded through without needing a new persisted field on the
#      child doctype - get_raw_materials_for_row is simply called again
#      at submit time to rebuild the item_code -> rate map, since neither
#      the resolved Sizing Receipt nor a rate was ever persisted from the
#      dialog (only item_code/qty/warehouse are, via the three existing
#      Data fields).
YARN_DEFAULT_WAREHOUSE = "Stores - PT"

# DELIMITER matches the parent daily_towel_production.js's RM_DELIMITER -
# keep both in sync if this ever changes.
DELIMITER = " | "


@frappe.whitelist()
def get_sales_order_items(doctype, txt, searchfield, start, page_len, filters):
	"""Link-query for the Items child table's `item` field, wired via
	frm.set_query('item', 'items', ...) in daily_towel_production.js -
	restricts the dropdown to items actually listed on the row's own
	Sales Order, per Kabeer's original spec ("drop-down of item(s) listed
	in sales order")."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	sales_order = filters.get("sales_order")
	if not sales_order:
		return []

	return frappe.db.sql(
		"""
		SELECT item_code, item_name
		FROM `tabSales Order Item`
		WHERE parent = %(sales_order)s
		AND item_code LIKE %(txt)s
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"sales_order": sales_order,
			"txt": "%{}%".format(txt or ""),
			"start": start,
			"page_len": page_len,
		},
	)


def _get_sales_order_item_row(sales_order, item_code):
	"""Resolve the one Sales Order Item row this Daily Towel Production row
	is producing. Used for the Towel Costing Sheet lookup (round 14,
	unchanged) and, as of round 18, also for the Weaving Contract match
	and the Greige Batch - all three live on this same row, so it's
	fetched once and reused rather than three separate queries."""
	row = frappe.db.get_value(
		"Sales Order Item",
		{"parent": sales_order, "item_code": item_code},
		["name", "custom_towel_costing_sheet", "custom_greige_batch"],
		as_dict=True,
	)
	if not row:
		frappe.throw(
			"No Sales Order Item found for Item {} on Sales Order {}.".format(item_code, sales_order)
		)
	return row


@frappe.whitelist()
def get_greige_weight(sales_order=None, item_code=None, weaving_contract=None):
	"""2026-09-28 (feature v3) - "Fetch ... greige weight (from TCS finish
	table)(New Field)" (your words), for Daily Loom Production Item's new
	Greige Weight field. Same Sales Order Item -> custom_towel_costing_sheet
	lookup as get_raw_materials_for_row above, then the Finish Item Towel
	Costing row (already on Towel Costing Sheet - Greige Weight already
	exists there, nothing new needed on that side) whose Article matches
	this row's Item. Returns 0 (not an error) when nothing resolves, since
	this is a live-preview convenience fetch, not a hard requirement."""
	# Commercial rows: Greige Weight is the Weaving Contract's own Gross
	# Weight (same value the Sales Order flow copies onto the contract from
	# the Towel Costing Sheet), no Sales Order / TCS involved.
	if weaving_contract:
		return flt(frappe.db.get_value("Weaving Contract", weaving_contract, "gross_weight"))

	if not (sales_order and item_code):
		return 0

	tcs_name = frappe.db.get_value(
		"Sales Order Item",
		{"parent": sales_order, "item_code": item_code},
		"custom_towel_costing_sheet",
	)
	if not tcs_name:
		return 0

	return flt(
		frappe.db.get_value(
			"Finish Item Towel Costing",
			{"parent": tcs_name, "article": item_code},
			"greige_weight",
		)
	)


def _get_weaving_contract(sales_order, sales_order_item_name):
	"""Round 18: resolve 'the' Weaving Contract governing this Sales Order
	Item's Article. Weaving Contract's own sales_order_item field is plain
	Data (stores the Sales Order Item row's `name`), not a Link - matched
	as a string here for exactly that reason. Returns None (not an error)
	if nothing matches, so callers can fall back to the pre-round-18
	Sales Order + Yarn Item match for older data that predates this
	field."""
	return frappe.db.get_value(
		"Weaving Contract",
		{
			"sales_order": sales_order,
			"sales_order_item": sales_order_item_name,
			"docstatus": ["!=", 2],
		},
		"name",
	)


def _find_sizing_receipt(sales_order, yarn_item, weaving_contract=None):
	"""Beam-item source lookup for a Pile/Ground raw material. Round 18:
	prefers narrowing by weaving_contract when one was resolved above,
	falling back to the original Sales Order + Yarn Item match if that
	comes up empty (receipt predates the weaving_contract field, or no
	Weaving Contract could be resolved at all). Most-recent-submitted is
	the tie-breaker either way - per Kabeer, even Sales Order + Weaving
	Contract + Yarn Item isn't guaranteed unique."""
	base_filters = {
		"yarn_item": yarn_item,
		"docstatus": 1,
	}
	# Commercial rows have no Sales Order - the Weaving Contract alone
	# identifies the receipt.
	if sales_order:
		base_filters["sales_order"] = sales_order

	# Round 19: target_warehouse fetched so the caller can default the
	# Beam Items warehouse field to where this Beam actually is (see
	# YARN_DEFAULT_WAREHOUSE above); final_cost_of_beam/beem_length
	# fetched so the caller can compute this Beam's rate the same way
	# create_stock_entry_from_sizing_receipt.py does.
	fields = ["name", "item", "lbs", "length", "target_warehouse", "final_cost_of_beam", "beem_length"]

	if weaving_contract:
		receipt = frappe.db.get_value(
			"Sizing Receipt",
			dict(base_filters, weaving_contract=weaving_contract),
			fields,
			as_dict=True,
			order_by="creation desc",
		)
		if receipt:
			return receipt
		if not sales_order:
			return None

	return frappe.db.get_value(
		"Sizing Receipt",
		base_filters,
		fields,
		as_dict=True,
		order_by="creation desc",
	)


@frappe.whitelist()
def get_raw_materials_for_row(sales_order=None, item_code=None, finish_qty=0, weaving_contract=None):
	"""Popup data source for the Raw Material Selection button. Returns
	[{item_code, group, qty, reference}, ...] - see
	claude/daily-towel-production.md for the full formula/grouping spec
	this implements (Pile/Ground -> Beam Items via Sizing Receipt,
	Weft/Fancy -> Yarn Items directly)."""
	finish_qty = flt(finish_qty)

	# Commercial: everything comes from the Weaving Contract, not the
	# Sales Order / Towel Costing Sheet.
	if weaving_contract:
		return _get_contract_raw_materials(weaving_contract, finish_qty)

	so_item = _get_sales_order_item_row(sales_order, item_code)

	if not so_item.custom_towel_costing_sheet:
		frappe.throw(
			"Sales Order Item {} on {} has no Towel Costing Sheet set "
			"(custom_towel_costing_sheet) - can't work out raw materials without it.".format(
				item_code, sales_order
			)
		)

	# Round 18: resolved once here, threaded into every Sizing Receipt
	# lookup below rather than re-resolved per raw-material row.
	weaving_contract = _get_weaving_contract(sales_order, so_item.name)

	materials = frappe.get_all(
		"Towel Costing Sheet Raw Material",
		filters={"parent": so_item.custom_towel_costing_sheet, "item": item_code},
		fields=["`for`", "raw_material", "yarn_required_in_lbs", "ratio"],
	)

	# Weaving Wastage % of this Finish Item on the Towel Costing Sheet
	weaving_wastage = flt(
		frappe.db.get_value(
			"Finish Item Towel Costing",
			{"parent": so_item.custom_towel_costing_sheet, "article": item_code},
			"weaving_wastage_percet",
		)
	)

	result = []
	for m in materials:
		yarn_required_per_lbs = flt(m.yarn_required_in_lbs)

		if m.get("for") in ("Pile", "Ground"):
			receipt = _find_sizing_receipt(sales_order, m.raw_material, weaving_contract)
			if not receipt:
				frappe.throw(
					"No submitted Sizing Receipt found for Sales Order {} / Yarn Item {} - "
					"can't resolve a Beam item for the {} raw material.".format(
						sales_order, m.raw_material, m.get("for")
					)
				)
			# Length (Beam No x Beem Length - ALL beams' meters), not
			# Beem Length alone - same reasoning as the parallel note on
			# Sizing Receipt's own Stock Entry rate (round 14 item 3, see
			# claude/sizing-receipt.md): lbs on a Sizing Receipt is the
			# total yarn for every beam on it, so the meters side of the
			# ratio has to match.
			ratio = flt(receipt.lbs) / flt(receipt.length) if flt(receipt.length) else 0
			qty = (yarn_required_per_lbs / ratio) * finish_qty if ratio else 0
			# Round 19: same formula as create_manufacture_stock_entry in
			# create_stock_entry_from_sizing_receipt.py - this Beam's own
			# per-meter cost, used to set an explicit rate on the DTP
			# consumption row below instead of trusting Beam - PT's
			# warehouse-ledger valuation.
			beem_length = flt(receipt.beem_length)
			rate = flt(receipt.final_cost_of_beam) / beem_length if beem_length else 0
			result.append({
				"item_code": receipt.item,
				"group": "Beam Items",
				"qty": qty,
				"reference": receipt.name,
				# Round 19: default warehouse for the dialog - see
				# YARN_DEFAULT_WAREHOUSE above.
				"default_warehouse": receipt.target_warehouse,
				"rate": rate,
				"ratio": flt(m.get("ratio")),
				"weaving_wastage": weaving_wastage,
			})
		else:
			qty = yarn_required_per_lbs * finish_qty
			result.append({
				"item_code": m.raw_material,
				"group": "Yarn Items",
				"qty": qty,
				"reference": None,
				"default_warehouse": YARN_DEFAULT_WAREHOUSE,
				"ratio": flt(m.get("ratio")),
				"weaving_wastage": weaving_wastage,
				# Round 19: not set for the Yarn Items group - Kabeer's
				# screenshot showed this row's rate was already correct
				# (matches Item.valuation_rate), only the Beam Items group
				# was reported wrong, so left to Frappe's own valuation
				# here rather than changing something that already works.
				"rate": None,
			})

	return result


def _get_contract_raw_materials(weaving_contract, finish_qty):
	"""Commercial version of get_raw_materials_for_row: one entry per BOM
	Items row of the Weaving Contract. Yarn per piece = the contract's own
	Yarn Qty / Order Qty (already worked out from Gross Weight, Ratio % and
	Weaving Wastage % on the contract). Pile/Ground rows are consumed as
	the Beam from their Sizing Receipt (matched on this Weaving Contract +
	yarn); Weft/Fancy rows as loose yarn."""
	wc = frappe.get_doc("Weaving Contract", weaving_contract)
	if wc.docstatus != 1:
		frappe.throw("Weaving Contract {} is not submitted.".format(weaving_contract))
	order_qty = flt(wc.fabric_qty)
	if not order_qty:
		frappe.throw("Weaving Contract {} has no Order Qty - can't work out yarn per piece.".format(weaving_contract))

	result = []
	for m in wc.bom_items or []:
		if not m.yarn_count:
			continue
		yarn_required_per_pc = flt(m.yarn_qty) / order_qty

		if m.get("for") in ("Pile", "Ground"):
			receipt = _find_sizing_receipt(None, m.yarn_count, weaving_contract)
			if not receipt:
				frappe.throw(
					"No submitted Sizing Receipt found for Weaving Contract {} / Yarn Item {} - "
					"can't resolve a Beam item for the {} raw material.".format(
						weaving_contract, m.yarn_count, m.get("for")
					)
				)
			ratio = flt(receipt.lbs) / flt(receipt.length) if flt(receipt.length) else 0
			qty = (yarn_required_per_pc / ratio) * finish_qty if ratio else 0
			beem_length = flt(receipt.beem_length)
			rate = flt(receipt.final_cost_of_beam) / beem_length if beem_length else 0
			result.append({
				"item_code": receipt.item,
				"group": "Beam Items",
				"qty": qty,
				"reference": receipt.name,
				"default_warehouse": receipt.target_warehouse,
				"rate": rate,
				"ratio": flt(m.ratio),
				"weaving_wastage": flt(m.get("weaving_wastage")),
			})
		else:
			result.append({
				"item_code": m.yarn_count,
				"group": "Yarn Items",
				"qty": yarn_required_per_pc * finish_qty,
				"reference": None,
				"default_warehouse": YARN_DEFAULT_WAREHOUSE,
				"rate": None,
				"ratio": flt(m.ratio),
				"weaving_wastage": flt(m.get("weaving_wastage")),
			})

	return result


def _get_requirements(sales_order, item_code, weaving_contract=None):
	"""Yarn needed per finished piece of this item, one dict per BOM line:
	{"for", "yarn_count", "per_pc" (lbs), "ratio", "weaving_wastage"}.
	Commercial rows read the Weaving Contract (only the lines of this Finish
	Item on a Multi Item contract); others read the Towel Costing Sheet."""
	if weaving_contract:
		wc = frappe.get_doc("Weaving Contract", weaving_contract)
		if wc.get("multi_item_weaving_contract") and wc.get("finish_items"):
			source = next((r for r in wc.finish_items if r.finish_item == item_code), None)
			order_qty = flt(source.order_qty) if source else 0
			lines = [r for r in wc.bom_items or [] if r.get("finish_item") == item_code]
		else:
			order_qty = flt(wc.fabric_qty)
			lines = list(wc.bom_items or [])
		if not order_qty:
			frappe.throw("Weaving Contract {} has no Order Qty for {} - can't work out yarn per piece.".format(weaving_contract, item_code))
		return [
			{
				"for": r.get("for"),
				"yarn_count": r.yarn_count,
				"per_pc": flt(r.yarn_qty) / order_qty,
				"ratio": flt(r.ratio),
				"weaving_wastage": flt(r.get("weaving_wastage")),
			}
			for r in lines
			if r.yarn_count
		]

	so_item = _get_sales_order_item_row(sales_order, item_code)
	if not so_item.custom_towel_costing_sheet:
		frappe.throw(
			"Sales Order Item {} on {} has no Towel Costing Sheet set "
			"(custom_towel_costing_sheet) - can't work out raw materials without it.".format(item_code, sales_order)
		)
	wastage = flt(
		frappe.db.get_value(
			"Finish Item Towel Costing",
			{"parent": so_item.custom_towel_costing_sheet, "article": item_code},
			"weaving_wastage_percet",
		)
	)
	materials = frappe.get_all(
		"Towel Costing Sheet Raw Material",
		filters={"parent": so_item.custom_towel_costing_sheet, "item": item_code},
		fields=["`for`", "raw_material", "yarn_required_in_lbs", "ratio"],
	)
	return [
		{
			"for": m.get("for"),
			"yarn_count": m.raw_material,
			"per_pc": flt(m.yarn_required_in_lbs),
			"ratio": flt(m.ratio),
			"weaving_wastage": wastage,
		}
		for m in materials
	]


@frappe.whitelist()
def get_row_material_types(sales_order=None, item_code=None, weaving_contract=None):
	"""Which yarn types (Pile / Ground / Weft / Fancy) this row's finished item
	uses, so the row only shows the warehouse / beam fields it needs."""
	types = {"pile": 0, "ground": 0, "weft": 0, "fancy": 0}
	if not item_code or not (sales_order or weaving_contract):
		return types
	try:
		for r in _get_requirements(sales_order, item_code, weaving_contract):
			key = (r.get("for") or "").strip().lower()
			if key in types:
				types[key] = 1
	except Exception:
		frappe.clear_last_message()
	return types


@frappe.whitelist()
def get_beam_batch_info(batch):
	"""Where a Pile / Ground beam batch lives, to default the row's warehouse."""
	data = frappe.db.get_value("Batch", batch, ["item", "batch_qty", "reference_doctype", "reference_name"], as_dict=True)
	if not data:
		return {}
	if data.reference_doctype == "Sizing Receipt":
		data["target_warehouse"] = frappe.db.get_value("Sizing Receipt", data.reference_name, "target_warehouse")
	return data


@frappe.whitelist()
def get_beam_batches(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for Pile Beam / Ground Beam: every enabled Batch of that Beam
	Type that still has stock. Not limited to any Weaving Contract or Sales
	Order."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	return frappe.db.sql(
		"""
		select b.name, b.item, b.batch_qty
		from `tabBatch` b
		where b.disabled = 0
			and ifnull(b.batch_qty, 0) > 0
			and b.beam_type = %(beam_type)s
			and (b.name like %(txt)s or b.item like %(txt)s)
		order by b.creation desc
		limit %(page_len)s offset %(start)s
		""",
		{
			"beam_type": filters.get("beam_type"),
			"txt": "%{}%".format(txt or ""),
			"start": cint(start),
			"page_len": cint(page_len),
		},
	)


def _consumption_rows(row, commercial):
	"""Raw material rows for one Daily Loom Production row: Pile / Ground are
	consumed from the Beam Batch picked on the row (rate from that batch's
	Sizing Receipt), Weft / Fancy as loose yarn from the row's warehouse."""
	reqs = _get_requirements(row.sales_order, row.item, row.weaving_contract if commercial else None)
	finish_qty = flt(row.finish_qty)
	out = []

	for beam_type in ("Pile", "Ground"):
		lines = [r for r in reqs if (r.get("for") or "").strip() == beam_type]
		if not lines:
			continue
		batch_name = row.get(f"{beam_type.lower()}_beam")
		if not batch_name:
			frappe.throw("Row {}: select the {} Beam batch.".format(row.idx, beam_type))
		batch = frappe.db.get_value("Batch", batch_name, ["item", "reference_doctype", "reference_name"], as_dict=True)
		receipt = (
			frappe.db.get_value(
				"Sizing Receipt",
				batch.reference_name,
				["lbs", "length", "target_warehouse", "final_cost_of_beam", "beem_length"],
				as_dict=True,
			)
			if batch and batch.reference_doctype == "Sizing Receipt"
			else None
		)
		if not receipt:
			frappe.throw("Row {}: Batch {} was not created from a Sizing Receipt.".format(row.idx, batch_name))

		ratio = flt(receipt.lbs) / flt(receipt.length) if flt(receipt.length) else 0
		per_pc = sum(r["per_pc"] for r in lines)
		qty = (per_pc / ratio) * finish_qty if ratio else 0
		rate = flt(receipt.final_cost_of_beam) / flt(receipt.beem_length) if flt(receipt.beem_length) else 0
		out.append({
			"item_code": batch.item,
			"qty": qty,
			"s_warehouse": row.get(f"{beam_type.lower()}_warehouse") or receipt.target_warehouse,
			"batch_no": batch_name,
			"rate": rate,
			"lbs_factor": sum(r["ratio"] / 100 * (1 + r["weaving_wastage"] / 100) for r in lines),
		})

	for r in reqs:
		beam_type = (r.get("for") or "").strip()
		if beam_type in ("Pile", "Ground"):
			continue
		out.append({
			"item_code": r["yarn_count"],
			"qty": r["per_pc"] * finish_qty,
			"s_warehouse": row.get(f"{beam_type.lower()}_warehouse") or YARN_DEFAULT_WAREHOUSE,
			"batch_no": None,
			"rate": None,
			"lbs_factor": r["ratio"] / 100 * (1 + r["weaving_wastage"] / 100),
		})
	return out


def _check_batch_stock(doc, row, consumption):
	"""Say clearly why a beam batch can't be consumed, before ERPNext's own
	"negative stock" message: the batch balance is read as of this document's
	date, then today, then in other warehouses."""
	try:
		from erpnext.stock.doctype.batch.batch import get_batch_qty
	except ImportError:
		return

	for c in consumption:
		if not c["batch_no"]:
			continue
		batch, warehouse, need = c["batch_no"], c["s_warehouse"], flt(c["qty"])
		as_of = flt(get_batch_qty(batch, warehouse, posting_date=doc.date, posting_time=nowtime()))
		if as_of + 0.0005 >= need:
			continue

		now_qty = flt(get_batch_qty(batch, warehouse))
		elsewhere = [
			"{} ({})".format(b.get("warehouse"), flt(b.get("qty")))
			for b in (get_batch_qty(batch_no=batch) or [])
			if b.get("warehouse") != warehouse and flt(b.get("qty")) > 0
		]
		if now_qty + 0.0005 >= need:
			reason = (
				"The stock is there now ({}) but not on {} - this document is dated before the "
				"Sizing Receipt's Beem Receipt entry that brought it in. Use a later date.".format(now_qty, doc.date)
			)
		elif elsewhere:
			reason = "That batch has stock in other warehouse(s): {}. Change the warehouse on the row.".format(
				", ".join(elsewhere)
			)
		else:
			reason = (
				"The batch holds {} in {} (needs {}). If the Sizing Receipt was split over several beams, "
				"each beam batch holds only its share of the receipt's length.".format(now_qty, warehouse, need)
			)
		frappe.throw(
			"Row {}: batch {} ({}) has {} available in {} as of {}, but {} is needed. {}".format(
				row.idx, batch, c["item_code"], as_of, warehouse, doc.date, need, reason
			)
		)


def create_manufacture_stock_entry_for_row(doc, row):
	"""One Manufacture Stock Entry per child row - consumes that row's raw
	materials (Pile / Ground beam batches and loose Weft / Fancy yarn from the
	warehouses on the row), produces Finish Qty of the row's own Item into the
	parent's Target Warehouse."""
	commercial = bool(doc.get("commercial"))
	consumption = _consumption_rows(row, commercial)
	if not consumption:
		frappe.throw("Row {}: no raw materials found for {}.".format(row.idx, row.item))

	# Round 18: Greige Batch for the finished row - see module docstring.
	# Commercial rows have no Sales Order Item, so no Greige Batch is set.
	greige_batch = None
	if not commercial:
		so_item = _get_sales_order_item_row(row.sales_order, row.item)
		if not so_item.custom_greige_batch:
			frappe.throw(
				"Row {}: Sales Order Item {} on {} has no Greige Batch set "
				"(custom_greige_batch) - can't raise the Manufacture Stock Entry without one.".format(
					row.idx, row.item, row.sales_order
				)
			)
		greige_batch = so_item.custom_greige_batch

	_check_batch_stock(doc, row, consumption)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Manufacture"
	se.purpose = "Manufacture"
	se.set_posting_time = 1
	se.posting_date = doc.date
	if commercial:
		se.weaving_contract = row.weaving_contract
	else:
		se.custom_sales_order = row.sales_order
	se.custom_daily_towel_production = doc.name
	# required whenever batch_no is set directly via the API
	if greige_batch or any(c["batch_no"] for c in consumption):
		se.use_serial_batch_fields = 1

	total_lbs = 0.0
	for c in consumption:
		item_row = {
			"item_code": c["item_code"],
			"qty": c["qty"],
			"uom": frappe.db.get_value("Item", c["item_code"], "stock_uom"),
			"s_warehouse": c["s_warehouse"],
		}
		if c["batch_no"]:
			item_row["batch_no"] = c["batch_no"]
			# Must be set on the ROW: otherwise ERPNext auto-picks its own batch
			# for this outgoing row on submit and then rejects ours ("Serial and
			# Batch Bundle ... has already created").
			item_row["use_serial_batch_fields"] = 1
		if c["rate"]:
			item_row.update({
				"basic_rate": c["rate"],
				"basic_amount": c["rate"] * c["qty"],
				"set_basic_rate_manually": 1,
			})
		# Total LBS = Total Greige Weight (Scale) * 2.2046 * Ratio % * (1 + Weaving Wastage %)
		item_row["custom_total_lbs"] = flt(row.total_greige_weight_scale) * 2.2046 * c["lbs_factor"]
		total_lbs += item_row["custom_total_lbs"]
		se.append("items", item_row)

	finished_row = {
		"item_code": row.item,
		"qty": row.finish_qty,
		"uom": frappe.db.get_value("Item", row.item, "stock_uom"),
		"t_warehouse": doc.target_warehouse,
		"is_finished_item": 1,
	}
	# The finished row carries the sum of the raw material rows' Total LBS.
	finished_row["custom_total_lbs"] = total_lbs
	# Rolls and Weight (Kg) of this Daily Loom Production row, shown on the
	# finished row (Stock Entry Detail custom fields).
	finished_row["custom_no_of_rolls"] = flt(row.no_of_rolls)
	finished_row["custom_weight_kgs"] = flt(row.weight_kg)
	if greige_batch:
		finished_row["batch_no"] = greige_batch
		finished_row["use_serial_batch_fields"] = 1
	se.append("items", finished_row)

	se.save(ignore_permissions=True)
	se.submit()
	return se.name


def create_stock_entries(doc):
	"""Called from Daily Towel Production's on_submit. Loops every child
	row, creating and submitting one Manufacture Stock Entry each, and
	records the Stock Entry name back onto that row so on_cancel below
	knows exactly what to cancel."""
	for row in doc.items:
		se_name = create_manufacture_stock_entry_for_row(doc, row)
		row.db_set("stock_entry", se_name, update_modified=False)


def cancel_linked_stock_entries(doc):
	"""Called from Daily Towel Production's on_cancel. Cancels every
	row's tracked Stock Entry."""
	for row in doc.items:
		if row.stock_entry and frappe.db.exists("Stock Entry", row.stock_entry):
			se = frappe.get_doc("Stock Entry", row.stock_entry)
			if se.docstatus == 1:
				se.cancel()
