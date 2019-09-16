var $ = require('jquery'),
    moment = require('moment');

require('../../vendor/jquery-date-range-picker/jquery.daterangepicker');
require('selectize');

var timeFormat = 'hh:mmA dddd, MMM DD, YYYY',
    dateFormat = 'dddd, MMM DD, YYYY';

function datePicker(selector, format, options) {
    var datePickerParams = $.extend({
        format: format,
        singleDate: true,
        showTopBar: false
    }, options);

    var $picker = $(selector);
    if($picker.length) {
        $picker.dateRangePicker(datePickerParams);
    }

    return $picker;
}

function textAreaResizer(i, el) {
    // via http://www.impressivewebs.com/textarea-auto-resize/
    var txt = $(el),
        hiddenDiv = $(document.createElement('div')),
        content = null;

    txt.addClass('txtstuff');
    hiddenDiv.addClass('hiddendiv common form-control');

    txt.after(hiddenDiv);

    function autosize() {
        content = txt.val();
        content = content.replace(/\n/g, '<br>');
        hiddenDiv.html(content + '<br class="lbr">');
        txt.css('height', hiddenDiv.height() + 20);
    }

    autosize();
    txt.on('keyup', autosize);
}

function amountVis() {
  var status = $('#id_status input:checked').val();
  $('#amounts').toggle(['relatg', 'relagc'].indexOf(status) !== -1);
}


$(function() {
    datePicker('input[name*="-scheduled_time"]', timeFormat, {
        startDate: moment().format(timeFormat),
        setValue: function(s) {
            var t = moment(s, timeFormat).hour(10).minute(0);
            $(this).val(t.format(timeFormat));
    	}
    });
    datePicker('#id_update_date', dateFormat);
    datePicker('#id_sent', dateFormat);

    $('textarea').each(textAreaResizer);

    $('#id_recipients').selectize({
        required: true,
        create: function(input) {
            return {
                value: input,
                text: input
            };
        }
    });

    if($('#amounts').length) {
        amountVis();
        $('#id_status input').on('change', amountVis);
    }

    $('fieldset.collapsible').on('click', 'legend', function(e) {
        e.preventDefault();
        $(this).parent().toggleClass('collapsed');
    });

    $('#id_project').selectize();
    $('#id_collaborators').selectize({
      multiple: true,
    });

    // FOIA field on event form page
    $('#id_foia').selectize();
});
