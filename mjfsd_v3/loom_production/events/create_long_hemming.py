import frappe
from frappe import _

# "Create" button on a submitted Dyed Fabric Issuance (your confirmed
# answer: "Manual Create button") seeds a new Long Hemming from that one
# Dyed Fabric Issuance's rows - unlike Dyed Fabric Issuance itself, there's
# no separate multi-select fetch dialog here, since your spec doesn't
# describe pulling multiple Dyed Fabric Issuances into one Long Hemming
# the way it does for Dyeing Receipts into a Dyed Fabric Issuance.
#
# Only one (non-cancelled) Long Hemming is allowed per Dyed Fabric
# Issuance - blocked with a clear message naming the existing one, rather
# than silently allowing the same issued fabric to be hemmed twice.


@frappe.whitelist()
def create_long_hemming_from_dyed_fabric_issuance(dyed_fabric_issuance):
	dfi = frappe.get_doc("Dyed Fabric Issuance", dyed_fabric_issuance)
	if dfi.docstatus != 1:
		frappe.throw(_("Dyed Fabric Issuance must be submitted first."))

	existing = frappe.db.get_value(
		"Long Hemming", {"dyed_fabric_issuance": dfi.name, "docstatus": ["!=", 2]}, "name"
	)
	if existing:
		frappe.throw(
			_(
				"Dyed Fabric Issuance {0} already has a Long Hemming ({1}) - open/amend that one "
				"instead of creating another."
			).format(dfi.name, existing)
		)

	lh = frappe.new_doc("Long Hemming")
	lh.dyed_fabric_issuance = dfi.name
	lh.source_warehouse = dfi.target_warehouse

	for row in dfi.items:
		lh.append(
			"items",
			{
				"item": row.item,
				"color": row.color,
				"issued_pcs": row.pcs,
				"issued_weight_kg": row.weight_kg,
				"sales_order": row.sales_order,
				"dyeing_receipt": row.dyeing_receipt,
				"dyeing_contract": row.dyeing_contract,
				"dyed_fabric_issuance_item": row.name,
				"color_batch": row.color_batch,
			},
		)

	if not lh.items:
		frappe.throw(_("{0} has no Issuance Details rows - nothing to hem.").format(dfi.name))

	return lh
