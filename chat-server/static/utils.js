//  Copyright (c) 2023 Fuka Narita.
//  This source code is licensed under the MIT license found in the
//  LICENSE file in the root directory of this source tree.

//  Copyright (c) 2020 Kurohashi-Chu-Murawaki lab, Kyoto University.
//  Licensed under the MIT license.
//  https://opensource.org/licenses/mit-license.php

var entityMap = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
  '/': '&#x2F;',
  '`': '&#x60;',
  '=': '&#x3D;'
};

function escapeHtml (string) {
    return String(string).replace(/[&<>"'`=\/]/g, function (s) {
        return entityMap[s];
    });
}

function showSimpleDialog(title, msg, elementToHighlight, callback) {
    if (elementToHighlight)
        elementToHighlight.effect('highlight', { color: 'yellow' }, 3000);

    var simpleDialog = $('#dialog-simple');
    simpleDialog.attr('title', title);
    simpleDialog.text(msg);
    simpleDialog.dialog({
        modal: true,
        width: 430,
        buttons: {
            'OK': function() {
                $(this).dialog('close');
                if (callback)
                    callback();
            }
        }
    });
}

