import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_dyeing_contract_from_sales_order(sales_order):
	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		frappe.throw(_("Sales Order must be submitted first - Color/Greige batches are only created on submit."))

	dc = frappe.new_doc("Dyeing Contract")
	dc.sales_order = so.name

	# 2026-09-26 - several dyers per Sales Order: each new contract is
	# prefilled with only what's still unassigned of each row's AB Qty
	# (AB Qty minus every submitted Dyeing Contract's Order Qty for that
	# row). Reduce Order Qty / delete rows to give this dyer only part of it.
	used = get_dyeing_used(so.name)
	has_color_rows = False

	for row in so.items:
		if not row.get("custom_color"):
			# Rows with no Color set aren't going through dyeing (e.g. a
			# Greige-only line) - skipped rather than forced in, since
			# there's nothing to dye and no Color batch to consume/produce.
			continue
		has_color_rows = True

		balance = flt(row.get("custom_ab_qty")) - flt(used.get(row.name))
		if balance <= 0.0001:
			continue

		tcs = row.get("custom_towel_costing_sheet")
		dc.append(
			"items",
			{
				"item": row.item_code,
				"color": row.custom_color,
				"order_qty": balance,
				"so_balance": balance,
				"dyeing_wastage_percent": _get_dyeing_wastage_percent(tcs, row.item_code),
				"sales_order": so.name,
				"sales_order_item": row.name,
				"towel_costing_sheet": tcs,
				"greige_batch": row.get("custom_greige_batch"),
			},
		)

	if not dc.items:
		if has_color_rows:
			frappe.throw(_("The full AB Qty of every row on {0} is already assigned to submitted Dyeing Contracts.").format(so.name))
		frappe.throw(_("No Sales Order Items have a Color set - nothing to send for dyeing."))

	return dc


def get_dyeing_used(sales_order, exclude_contract=None):
	"""{Sales Order Item row name: Order Qty on SUBMITTED Dyeing Contracts}.
	Always re-read, never stored - cancelling a contract frees its qty."""
	conditions = "dc.docstatus = 1 and dci.sales_order = %(so)s and ifnull(dci.sales_order_item, '') != ''"
	values = {"so": sales_order}
	if exclude_contract:
		conditions += " and dc.name != %(exclude)s"
		values["exclude"] = exclude_contract
	rows = frappe.db.sql(
		f"""
		select dci.sales_order_item, sum(dci.order_qty) as qty
		from `tabDyeing Contract Item` dci
		inner join `tabDyeing Contract` dc on dc.name = dci.parent and dci.parenttype = 'Dyeing Contract'
		where {conditions}
		group by dci.sales_order_item
		""",
		values,
		as_dict=True,
	)
	return {r.sales_order_item: flt(r.qty) for r in rows}


def validate_dyeing_balance(doc, hard=True):
	"""Order Qty per Sales Order row must fit inside that row's AB Qty minus
	what other submitted Dyeing Contracts already took."""
	so_rows = {}
	for row in doc.get("items") or []:
		if row.get("sales_order") and row.get("sales_order_item"):
			key = (row.sales_order, row.sales_order_item)
			so_rows[key] = so_rows.get(key, 0) + flt(row.order_qty)
	if not so_rows:
		return

	over = []
	used_by_so = {}
	for (sales_order, so_item), asked in so_rows.items():
		if sales_order not in used_by_so:
			used_by_so[sales_order] = get_dyeing_used(sales_order, exclude_contract=doc.name)
		ab_qty, item_code, color = frappe.db.get_value(
			"Sales Order Item", so_item, ["custom_ab_qty", "item_code", "custom_color"]
		) or (0, so_item, "")
		balance = flt(ab_qty) - flt(used_by_so[sales_order].get(so_item))
		if asked > balance + 0.001:
			over.append(
				_("{0} / {1}: {2} entered, only {3} of AB Qty {4} left").format(
					item_code, color or "-", asked, max(balance, 0), flt(ab_qty)
				)
			)

	if not over:
		return
	msg = _("Order Qty exceeds the Sales Order AB Qty still unassigned:") + "<br>" + "<br>".join(over)
	if hard:
		frappe.throw(msg, title=_("AB Qty Balance Exceeded"))
	frappe.msgprint(msg + "<br><br>" + _("You can save, but it will be blocked on submit."), indicator="orange", title=_("AB Qty Balance"))


def _get_dyeing_wastage_percent(towel_costing_sheet, item_code):
	"""Looks up Dyeing Wastage % from the Towel Costing Sheet's Finish Item
	Towel Costing row for this item. Doesn't hard-code that child table's
	fieldname on the parent - finds it via meta instead - since the exact
	fieldname wasn't confirmed; if it can't find a match it returns 0
	(non-blocking: this only pre-fills a suggested value, which you review
	before saving/submitting the Dyeing Contract, not a stock-posting
	number). Flag if this comes back 0 when it shouldn't.
	"""
	if not towel_costing_sheet:
		return 0

	table_fieldname = None
	for df in frappe.get_meta("Towel Costing Sheet").get_table_fields():
		if df.options == "Finish Item Towel Costing":
			table_fieldname = df.fieldname
			break
	if not table_fieldname:
		return 0

	tcs = frappe.get_doc("Towel Costing Sheet", towel_costing_sheet)
	for row in tcs.get(table_fieldname) or []:
		# "article" confirmed as the real fieldname (see
		# create_stock_entry_from_weaving_receipt.py's own
		# _get_weaving_wastage_percent) - item/finish_item kept as
		# fallbacks only.
		row_item = row.get("article") or row.get("item") or row.get("finish_item")
		if row_item == item_code:
			return flt(row.get("custom_dyeing_wastage_percent"))

	return 0
