

frappe.ui.form.on('Loom Production', {
    refresh(frm) {
        
        frm.set_query('sizing_name', 'loom_production_items', function (doc, cdt, cdn) {
            return {
                filters: [
                    ["Item", "item_group", "in", ["Fabric"]]
                ]
            };
        });
    }
})

frappe.ui.form.on('Loom Production Items', {
    actual_reading: function (frm, cdt, cdn) {
        var d = locals[cdt][cdn];
        var unit_per_rpm = Math.round((d.rpm* (0.72/ 12) * frm.doc.shift_working_hours),0);
        frappe.model.set_value(cdt, cdn, "unit_per_rpm", unit_per_rpm);
        var actual_reading = d.actual_reading;
        var effeciency = Math.round((actual_reading/unit_per_rpm)*100,2);
        frappe.model.set_value(cdt, cdn, "effeciency", effeciency);
        calculate_meters_in_row(frm, cdt, cdn);
    },



});



function calculate_meters_in_row(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row.actual_reading || !row.pick || !row.panna) {
        frm.fields_dict['items'].grid.refresh();
        return;
    }

    const meters = ((row.actual_reading * 25.4) / row.pick) * row.panna;
    frappe.model.set_value(cdt, cdn, 'meters', flt(meters, 2));
}