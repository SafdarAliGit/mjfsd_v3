// Copyright (c) 2025, Tech Ventures and contributors
// For license information, please see license.txt

frappe.ui.form.on('Fabric Weaving', {
    // refresh: function(frm) {

    // }
    const: function (frm) {
        calculate_read_space(frm);
    },
    panna: function (frm) {
        calculate_read_space(frm);
    },
    extra_add_first: function (frm) {
        calculate_ends(frm);
    },
    extra_add_second: function (frm) {
        calculate_ends(frm);
    },
    ends: function (frm) {
        calculate_bags(frm);
        calculate_warp_consumption(frm);
    },
    cones_per_bag: function (frm) {
        calculate_bags(frm);
        calculate_actual_cones(frm);
        calculate_bags_to_send(frm);
        calculate_beam_length(frm);
        calculate_warp_consumption(frm);
    },
    sizing_repeat: function (frm) {
        calculate_bags(frm);
    },
    weight_per_bag: function (frm) {
        calculate_actual_consumption(frm);
        calculate_bags_to_send(frm);
        calculate_beam_length(frm);
        calculate_warp_consumption(frm);
    },
    lbs_to_send: function (frm) {
        calculate_bags_to_send(frm);
        calculate_warp_consumption(frm);
    },
    warp: function (frm) {
        calculate_beam_length(frm);
        calculate_warp_consumption(frm);
    },
    reduce_: function (frm) {
        calculate_beam_length(frm);
        calculate_warp_consumption(frm);
    },
    repeat: function (frm) {
        calculate_beam_length(frm);
        calculate_warp_consumption(frm);
    },
    required_fabric: function (frm) {
        calculate_required_yarn(frm);
    },
    pick:function (frm){
        calculate_required_yarn(frm);
    },
    weft:function (frm){
      calculate_required_yarn(frm);
    }
});


function calculate_read_space(frm) {
    let read_space = 0;
    let panna = frm.doc.panna;
    let con = frm.doc.const;
    read_space = panna + con;
    frm.set_value("read_space", read_space);
}

function calculate_ends(frm) {
    let read_space = frm.doc.read_space || 0;
    let read_count = frm.doc.read_count || 0;
    let extra_add_first = frm.doc.extra_add_first || 0;
    let extra_add_second = frm.doc.extra_add_second || 0;
    let ends = frm.doc.ends || 0;
    ends = (read_space * read_count) + (extra_add_first + extra_add_second);
    frm.set_value("ends", ends);
}


function calculate_bags(frm) {
    let ends = frm.doc.ends || 0;
    let cones_per_bag = frm.doc.cones_per_bag || 0;
    let sizing_repeat = frm.doc.sizing_repeat || 0;
    let bags = ends / cones_per_bag / sizing_repeat;
    frm.set_value("bags", bags);
    calculate_actual_consumption(frm)
    calculate_actual_cones(frm)
}


function calculate_actual_consumption(frm) {
    let actual_consumption = 0;
    let bags = frm.doc.bags || 0;
    let weight_per_bag = frm.doc.weight_per_bag || 0;
    actual_consumption = bags * weight_per_bag;
    frm.set_value("actual_consumption", actual_consumption);
}

function calculate_actual_cones(frm) {
    let bags = frm.doc.bags || 0;
    let cones_per_bag = frm.doc.cones_per_bag || 0;
    let actual_cones = bags * cones_per_bag;
    frm.set_value("actual_cones", actual_cones);
}

function calculate_bags_to_send(frm) {
    let bags_to_send = 0;
    let lbs_to_send = frm.doc.lbs_to_send || 0;
    let weight_per_bag = frm.doc.weight_per_bag || 0;
    let cones_per_bag = frm.doc.cones_per_bag || 0;
    let cones_to_send = 0;
    let excess_cones = 0;
    let actual_cones = frm.doc.actual_cones || 0;
    if (weight_per_bag > 0) {
        bags_to_send = lbs_to_send / weight_per_bag
    }
    frm.set_value("bags_to_send", bags_to_send);
    cones_to_send = bags_to_send * cones_per_bag;
    frm.set_value("cones_to_send", cones_to_send);
    excess_cones = cones_to_send - actual_cones;
    frm.set_value("excess_cones", excess_cones);

}


function calculate_beam_length(frm) {
    let beam_length = 0;
    let warp = frm.doc.warp || 0;
    let weight_per_bag = frm.doc.weight_per_bag || 0;
    let cones_per_bag = frm.doc.cones_per_bag || 0;
    let reduce_ = frm.doc.reduce_ || 0;
    let repeat = frm.doc.repeat || 0;
    beam_length = ((warp * (weight_per_bag / cones_per_bag) * 768.1) * ((100 - reduce_) / 100)) / repeat;
    frm.set_value("beam_length", beam_length);

}


function calculate_warp_consumption(frm) {
    let warp_consumption = 0;
    let left_over_yarn = 0;
    let left_over_cones = 0;
    let ends = frm.doc.ends || 0;
    let beam_length = frm.doc.beam_length || 0;
    let warp = frm.doc.warp || 0;
    warp_consumption = ((ends * beam_length) / 768.1) / warp;
    frm.set_value("warp_consumption", warp_consumption);
    let lbs_to_send = frm.doc.lbs_to_send || 0;
    left_over_yarn = lbs_to_send - warp_consumption;
    frm.set_value("left_over_yarn", left_over_yarn);
    let weight_per_bag = frm.doc.weight_per_bag || 0;
    let cones_per_bag = frm.doc.cones_per_bag || 0;
    left_over_cones = left_over_yarn / (weight_per_bag / cones_per_bag);
    frm.set_value("left_over_cones", left_over_cones);
}


function calculate_required_yarn(frm) {
    let weft_consumption = 0;
    let required_yarn = 0;
    let pick = frm.doc.pick || 0;
    let read_space = frm.doc.read_space || 0;
    let weft = frm.doc.weft || 0;
    let required_fabric = frm.doc.required_fabric || 0;
    weft_consumption = ((pick * read_space) / 768.1) / weft;
    frm.set_value("weft_consumption", weft_consumption);
    required_yarn = weft_consumption * required_fabric;
    frm.set_value("required_yarn", required_yarn);

}