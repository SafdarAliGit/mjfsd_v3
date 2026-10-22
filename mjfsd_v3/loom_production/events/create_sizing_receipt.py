import frappe
from frappe import _

# Same field list as the Sizing Program Item child table (minus the
# implicit parent/idx/name bookkeeping fields) - copied 1:1 onto each new
# Sizing Receipt.
FIELDS_TO_COPY = [
	"type",
	"item",
	"set_no",
	"w_set",
	"sizing_name",
	"yarn_count",
	"remarks",
	"actual_yarn_count",
	"waste_account",
	"actual_yarn_rate",
	"yarn_wastage_qty",
	"wastage_amount",
	"no_of_width",
	"beam_no",
	"beem_length",
	"ends",
	"length",
	"lbs",
	"wastage_percentage",
	"yarn_consumption_per_meter",
	"yarn_item",
	"target_warehouse",
	"fabric_construction",
	"panna",
	"warp_weight",
	"yarn_item_rate",
	"beem_rate",
	"expense_account",
	"sizing_rate",
	"sizing_amount",
	"beem_rate_per_meter",
	"value_of_yarn",
	"value_of_actual_yarn",
]


@frappe.whitelist()
def create_sizing_receipts(sizing_program):
	"""Create one Sizing Receipt per row in this Sizing Program's Items
	table. Idempotent - a row that already has a Sizing Receipt (matched by
	the row's own name, stored on the receipt as sizing_program_item) is
	skipped rather than duplicated, same convention as the Beam Item
	auto-creation on Weaving Contract submit.
	"""
	sp = frappe.get_doc("Sizing Program", sizing_program)

	created = []
	existing = []
	for row in sp.items or []:
		if frappe.db.exists("Sizing Receipt", {"sizing_program_item": row.name}):
			existing.append(row.name)
			continue

		receipt = frappe.new_doc("Sizing Receipt")
		receipt.sizing_program = sp.name
		receipt.sizing_program_item = row.name
		receipt.source_warehouse = sp.source_warehouse
		receipt.weaving_contract = sp.get("weaving_contract")
		for fieldname in FIELDS_TO_COPY:
			receipt.set(fieldname, row.get(fieldname))
		receipt.insert(ignore_permissions=True)
		created.append(receipt.name)

	if not created and not existing:
		frappe.throw(_("Sizing Program {0} has no rows in its Items table to create Sizing Receipts from.").format(sp.name))

	if existing:
		frappe.msgprint(
			_("{0} row(s) already had a Sizing Receipt - skipped.").format(len(existing))
		)

	return created
