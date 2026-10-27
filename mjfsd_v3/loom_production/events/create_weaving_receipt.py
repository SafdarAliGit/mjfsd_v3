import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_weaving_contracts_for_selection():
	"""Feeds the "Get Items From > Weaving Contract" popup. Lists every
	submitted Weaving Contract that still has balance pcs left to receive.

	2026-09-28 fix - "I have entered order qty 50000 in Weaving Contract, I
	created one Weaving Receipt of 9000, but now when I'm going to create
	more another receipt of same weaving contract, it doesn't list that
	Weaving Contract that already has 41000 balance pcs" (your words). The
	old version excluded a contract entirely the moment ANY non-cancelled
	Weaving Receipt referenced it, regardless of how much was actually
	received. Now it sums Pcs (Actual) already received across every
	non-cancelled Weaving Receipt for that contract and only excludes it
	once that total reaches the contract's Order Qty (fabric_qty) - so
	partial receipts keep showing up with whatever balance is left.
	"""
	received = frappe.db.sql(
		"""
		select wri.weaving_contract, sum(wri.pcs_actual) as received
		from `tabWeaving Receipt Item` wri
		inner join `tabWeaving Receipt` wr on wr.name = wri.parent
		where wri.weaving_contract is not null and wr.docstatus != 2
		group by wri.weaving_contract
		""",
		as_dict=True,
	)
	received_by_contract = {r.weaving_contract: flt(r.received) for r in received}

	contracts = frappe.get_all(
		"Weaving Contract",
		filters={"docstatus": 1},
		fields=["name", "construction as finish_item", "sales_order", "fabric_qty", "weaver"],
	)

	result = []
	for contract in contracts:
		already_received = received_by_contract.get(contract.name, 0)
		balance = flt(contract.fabric_qty) - already_received
		if balance <= 0.0001:
			continue
		contract["balance_qty"] = balance
		contract["weaver_hint"] = contract.get("weaver") or _get_weaver_hint(contract)
		result.append(contract)

	return result


def _get_weaver_hint(contract):
	"""Best-effort display hint only (shown as an extra column in the
	popup, not used to filter/restrict selection) - Weaving Contract has
	no field of its own identifying who wove it, so this reads the
	Customer off the linked Sales Order instead, same fallback used in
	create_sizing_program_from_weaving_contract.py.
	"""
	if not contract.get("sales_order"):
		return None
	return frappe.db.get_value("Sales Order", contract["sales_order"], "customer")


@frappe.whitelist()
def get_weaving_contract_items(weaving_contracts):
	"""Called once the user picks one or more contracts and clicks Fetch.
	One Weaving Contract -> one Weaving Receipt Item row (a contract only
	ever has a single Finish Item, unlike Towel Costing Sheet).
	"""
	if isinstance(weaving_contracts, str):
		weaving_contracts = frappe.parse_json(weaving_contracts)

	result = []
	for wc_name in weaving_contracts:
		wc = frappe.get_doc("Weaving Contract", wc_name)
		result.append(
			{
				"finish_item": wc.construction,
				"gross_weight": wc.gross_weight,
				"finish_weight": wc.finish_weight,
				"order_qty": wc.fabric_qty,
				"weaving_contract": wc.name,
				"sales_order": wc.sales_order,
				"towel_costing_sheet": _get_towel_costing_sheet(wc),
				# 2026-09-28 (feature v3) - "when user gets item from Weaving
				# Contract, the weaver should be automatically fetched and
				# set to read only" (your words) - set on the Weaving Receipt
				# header in weaving_receipt.js, not per-row.
				"weaver": wc.weaver,
			}
		)
	return result


def _get_towel_costing_sheet(wc):
	if not wc.get("sales_order_item"):
		return None
	return frappe.db.get_value(
		"Sales Order Item", wc.sales_order_item, "custom_towel_costing_sheet"
	)
