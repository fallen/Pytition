{% load i18n %}

$(function () {
  $('[data-toggle="tooltip"]').tooltip()
});

$(function () {
   $('[data-action="template-delete"]').on("click", function() {
    var template_delete_url = $(this).closest("[data-template-delete]").data("template-delete");
    $.ajax(template_delete_url).done(function() {
       if (window.location.href.endsWith('/edit')) {
           // If we were on this template edit page and the user clicks on delete
           // we cannot reload the edit page, we then reload the dashboard
           window.location = "{{ dashboard }}";
       } else
           window.location = window.location.href;
    });
   });
});

function do_toggle_template_picture(template) {
    if (template.prop("class").includes("text-warning"))
        template.removeClass("text-warning").addClass("text-dark");
    else
        template.removeClass("text-dark").addClass("text-warning");
}

$(function () {
    $('[data-fav-toggle="true"]').on("click", function () {
        var template_fav_url = $(this).closest("[data-template-fav]").data("template-fav");
        var template = $(this);
        $.ajax(template_fav_url).done(function() {
            var hash = document.location.hash;
            if (hash)
                do_toggle_template_picture(template);
            else
                window.location = window.location.href;
        });
    });
});

$(function () {
   $('[data-action="petition-delete"]').on("click", function() {
    var petition_delete_url = $(this).closest("[data-petition-delete]").data("petition-delete");
    $.ajax(petition_delete_url).done(function() {
           window.location = window.location.href;
    });
   });
});

$(function () {
   $('[data-action="publish"]').find('input:checkbox').on("change", function() {
    var box = $(this);
    var publish = box.prop('checked');
    box.prop('checked', !publish);
    var petition_publish_url = $(this).closest("[data-petition-publish]").data("petition-publish");
    var petition_unpublish_url = $(this).closest("[data-petition-unpublish]").data("petition-unpublish");
    var label = box.siblings('label');
    var custom_switch = box.closest('.custom-switch');
    box.prop('disabled', true);
    var loader_id = 'loader_to_remove_' + Math.round(Math.random() * 100);
    $(`<div id=${loader_id} class="spinner-border spinner-border-sm ml-1" \
        style="color: initial" role="status"><span class="sr-only">Loading...</span></div>`)
           .insertAfter(label);
    loader_id = '#' + loader_id;
    $.ajax(publish ? petition_publish_url : petition_unpublish_url
    ).done(function() {
        var published = box.prop('checked');
        label.text(published ? "{% trans "Not published" %}" : "{% trans "Published" %}");
        box.prop('disabled', false);
        box.prop('checked', !box.prop('checked'));
        $(loader_id).remove();
    }).fail(function () {
        setTimeout(function() {
            box.prop('disabled', false);
            $(loader_id).remove();
            var action = box.prop('checked') ? 'unpublish' : 'publish';
            if (!box.siblings("div.alert").length)
                $(`<div class="alert alert-danger" role="alert">Failed to ${action} the petition, try to refresh the page</div>`).insertAfter(label);
        }, 1000);
    });
   });
});
