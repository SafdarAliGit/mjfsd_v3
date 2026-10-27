import frappe
import json
from frappe import _
from frappe.model.document import Document


def abbr():
    company = frappe.defaults.get_user_default("Company")
    abbr = frappe.get_cached_value("Company", company, "abbr")
    return str(abbr)


@frappe.whitelist()
def create_stock_entry_from_sizing_program(sizing_program):
    # Fetch the Weaving Contract document
    sp = frappe.get_doc("Sizing Program", sizing_program)
    se = frappe.db.get_value("Stock Entry", {"sizing_program": sizing_program}, "name")
    se_doc = None
    if se:
        se_doc = frappe.get_doc("Stock Entry", se)
    if se_doc and se_doc.docstatus != 2:
        frappe.throw(f"Stock Entry already created for {sp.name} Sizing Program")
    # Create a new Stock Entry
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = "Manufacture"  # Change as needed
    stock_entry.purpose = "Manufacture"
    stock_entry.sizing_program = sizing_program  # Link back to Weaving Contract

    # Loop through child items (bom_items) and add them to Stock Entry items
    valuation = 0
    if sp.conversion == 1:
        valuation = 1
    else:
        valuation = 0

    stock_entry.append("items", {
        "item_code": sp.item,
        "qty": sp.lbs,
        "allow_zero_valuation_rate": valuation,
        "s_warehouse": sp.source_warehouse,
        "uom": sp.uom,
        "stock_uom": sp.uom
    })
    stock_entry.append("items", {
        "item_code": sp.item_returnable,
        "qty": sp.lbs,
        "allow_zero_valuation_rate": valuation,
        "is_finished_item": 1,
        "uom": sp.uom,
        "stock_uom": sp.uom
    })

    # Return the Stock Entry name to open in the form view
    return stock_entry



@frappe.whitelist()
def make_stock_entry_from_sizing_item(docname,s_warehouse, child_row):
    try:
        child_row = json.loads(child_row)

        sizing_program = frappe.get_doc("Sizing Program", docname)
        valuation = 0
        expense_account = None
        stock_entry_type = "Beem Receipt Entry"
        is_finished_item = 1
        if sizing_program.conversion == 1:
            valuation = 1
            stock_entry_type = "Repack"
            expense_account = "Sizing Expense - ET"
            # is_finished_item = 0

        else:
            # valuation = 0
            stock_entry_type = "Beem Receipt Entry"
            # is_finished_item = 1
        item = frappe.get_doc("Item", child_row.get("item"))
        if item.has_batch_no:
            # Create Batch for finished item
            batch = frappe.new_doc("Batch")
            batch.batch_id = str(child_row.get("set_no")) 
            batch.item = child_row.get("item")
            batch.stock_uom = "Meter"
            batch.custom_ends = child_row.get("ends")
            batch.custom_yarn_count = child_row.get("yarn_count")
            batch.custom_warp_weight = child_row.get("warp_weight")
            batch.custom_beem_rate = child_row.get("beem_rate")
            batch.save(ignore_permissions=True)
        
        item.custom_warp_weight = child_row.get("warp_weight","")
        item.custom_beem_rate = child_row.get("beem_rate_per_meter","")
        item.save(ignore_permissions=True)

        # Create Stock Entry
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = stock_entry_type
        se.purpose = stock_entry_type
        se.set_posting_time = 1
        se.posting_date = sizing_program.date
        se.sizing_program = sizing_program.name

        # Raw Material Entry (source)
        se.append("items", {
            "item_code": child_row.get("yarn_item"),
            "qty": child_row.get("lbs"),
            "uom":"Lbs",
            "s_warehouse": s_warehouse,
            "conversion_factor": 1
        })

        # Finished Item Entry (target)
        # Build the main item dictionary
        item_dict = {
            "item_code": child_row.get("item"),
            "qty": child_row.get("length"),
            "uom": "Meter",
            "t_warehouse": child_row.get("target_warehouse"),
            "allow_zero_valuation_rate": valuation,
            "is_finished_item": is_finished_item
        }

        # Add batch_no if the item has one
        if item.has_batch_no:
            item_dict["batch_no"] = batch.name

        # Append the complete dictionary to the child table
        se.append("items", item_dict)
        
        if sizing_program.conversion == 0:
            if child_row.get("expense_account") and child_row.get("sizing_amount") != 0:
                se.append("additional_costs", {
                    "expense_account": child_row.get("expense_account"),
                    "description":docname,
                    "amount": child_row.get("sizing_amount"),
            })
            if child_row.get("waste_account") and child_row.get("wastage_amount") != 0:
                se.append("additional_costs", {
                    "expense_account": child_row.get("waste_account"),
                    "description":docname,
                    "amount": child_row.get("wastage_amount"),
                })

        se.save(ignore_permissions=True)
        se.submit()
        
        

        if child_row.get("sizing_amount") and child_row.get("sizing_amount") != 0:
            je = frappe.new_doc("Journal Entry")
            je.voucher_type = "Journal Entry"
            je.posting_date = sizing_program.date
            je.user_remark = sizing_program.name
            je.custom_sizing_program = sizing_program.name
            je.append("accounts", {
                "account": expense_account if sizing_program.conversion == 1 else child_row.get("expense_account"),
                "debit_in_account_currency": child_row.get("sizing_amount")
            })
            je.append("accounts", {
                "account": f"Creditors - {abbr()}",
                "party_type": "Supplier",
                "party": child_row.get("sizing_name"),
                "credit_in_account_currency": child_row.get("sizing_amount")
            })
            je.save(ignore_permissions=True)
            je.submit()

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in make_stock_entry_from_sizing_item")
        frappe.throw(_("Failed to create Stock Entry. Error: {0}").format(str(e)))


@frappe.whitelist()
def make_stock_entry_for_stock_return_item(sizing_program):
    try:
        # Fetch the parent document
        sizing_program = frappe.get_doc("Sizing Program", sizing_program)

        # Create a new Stock Entry for Material Transfer
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer"
        se.purpose = "Material Transfer"
        se.set_posting_time = 1
        se.posting_date = sizing_program.date
        se.custom_sizing_program_stock_entry = sizing_program.name

        # Iterate over each row in the stock_return_item child table
        for row in sizing_program.stock_return_item:
            se.append("items", {
                "item_code": row.yarn_item,
                "qty": row.qty_lbs,
                "uom": "Lbs",
                "s_warehouse": sizing_program.source_warehouse,
                "t_warehouse": row.target_warehouse,
                "conversion_factor": 1,
                "stock_uom":"Lbs"
            })

        # Save and submit the Stock Entry

        return se

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in make_stock_entry_for_stock_return_item")
        frappe.throw(_("Failed to create Stock Entry. Error: {0}").format(str(e)))

