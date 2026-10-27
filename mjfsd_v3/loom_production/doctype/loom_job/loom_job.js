// Copyright (c) 2023, Tech Ventures and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loom Job", {
    refresh(frm) {

        if (frm.doc.docstatus === 1 && frm.doc.status !== 'Closed') {
            frm.add_custom_button(__('Yarn Received'), function () {
                frm.trigger("new_stock_entry");
            });

             frm.add_custom_button(__('Beam Construction'), function () {
                frm.trigger("new_beam_construction");
            });
        }




    },
    new_stock_entry: function(frm) {
            frappe.call({
                method: 'mjfsd_v3.loom_production.doctype.loom_job.loom_job.new_stock_entry',
                args: {
                    'source_name': frm.doc.name
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.model.sync(r.message);
                        frappe.set_route("Form", r.message.doctype, r.message.name);
                    }
                }
            });
        },
        new_beam_construction: function(frm) {
            frappe.call({
                method: 'mjfsd_v3.loom_production.doctype.loom_job.loom_job.new_beam_construction',
                args: {
                    'source_name': frm.doc.name
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.model.sync(r.message);
                        frappe.set_route("Form", r.message.doctype, r.message.name);
                    }
                }
            });
        }
    });


frappe.ui.form.on("Loom Job Items", {
    ratio: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (frm.doc.lbs <= 0) {
            frappe.msgprint("Enter LBS for Required Item");
        } else {
            var ratio = row.ratio;
            var lbs = (flt(frm.doc.lbs) * flt(ratio / 100));
            frappe.model.set_value(cdt, cdn, "lbs", lbs);

            var bags = (flt(row.lbs) / flt(row.lbs_per_bag));
            frappe.model.set_value(cdt, cdn, "bags", bags);

        }

    },
    lbs_per_bag: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        var bags = (flt(row.lbs) / flt(row.lbs_per_bag));
        frappe.model.set_value(cdt, cdn, "bags", bags);
    },


});









