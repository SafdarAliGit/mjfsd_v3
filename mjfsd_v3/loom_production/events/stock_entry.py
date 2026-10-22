import frappe
def custom_on_submit(doc, method):
    if doc.custom_sizing_program_stock_entry:
        sp = frappe.get_doc("Sizing Program", doc.custom_sizing_program_stock_entry)
        sp.db_set("stock_return_entry", doc.name)
        
    