import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_balance_net_meter(sizing_program):
	"""A Sizing Program's Net Meter is drawn down by every Sizing Receipt
	created against it (a program can have many receipts over its life).
	Returns Net Meter minus the sum of Beam Length already recorded on this
	program's Sizing Receipts, computed fresh on every call rather than
	stored/cached, so it can never drift out of sync.
	"""
	net_meter = frappe.db.get_value("Sizing Program", sizing_program, "net_meter") or 0

	issued = frappe.db.get_all(
		"Sizing Receipt",
		filters={"sizing_program": sizing_program},
		pluck="beem_length",
	)
	total_issued = sum(flt(v) for v in issued)

	return flt(net_meter) - total_issued
