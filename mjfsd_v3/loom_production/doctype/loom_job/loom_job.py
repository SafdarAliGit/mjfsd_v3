# Copyright (c) 2023, Tech Ventures and contributors
# For license information, please see license.txt
import frappe
# import frappe
from frappe.model.document import Document


class LoomJob(Document):
	pass

@frappe.whitelist()
def new_stock_entry(source_name):
	source_name = frappe.get_doc("Loom Job", source_name)
	doc = frappe.new_doc("Stock Entry")
	doc.stock_entry_type = 'Material Receipt'
	doc.loom_job_yarn_received = source_name.name

	for items in source_name.loom_job_items:
		it = doc.append("items", {})
		it.item_code = items.item_name
		it.qty = items.lbs
		it.uom = items.uom
		it.stock_uom = items.stock_uom

	return doc

@frappe.whitelist()
def new_beam_construction(source_name):
	source_name = frappe.get_doc("Loom Job", source_name)
	doc = frappe.new_doc("Stock Entry")
	doc.stock_entry_type = 'Manufacture'
	doc.loom_job_yarn_received = source_name.name

	for items in source_name.loom_job_items:
		it = doc.append("items", {})
		it.item_code = items.item_name
		it.qty = items.lbs
		it.uom = items.uom
		it.stock_uom = items.stock_uom
	beam_items = frappe.get_list("Item", filters={'include_item_in_manufacturing':1,'has_serial_no':1,'item_group':'Beam'}, fields=["item_code", "stock_uom"])
	for item in beam_items:
		bi = doc.append("items", {})
		bi.item_code = item.item_code
		bi.uom = item.stock_uom
		bi.stock_uom = item.stock_uom
		bi.is_finished_item = 1
	return doc



