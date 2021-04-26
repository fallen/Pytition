import csv
from datetime import timedelta
import os
import urllib.parse
import random
from time import time

from django.shortcuts import render, redirect
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _
from django.contrib import messages
from django.contrib.messages import get_messages
from django.utils.html import format_html
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.views.generic.edit import CreateView

from formtools.wizard.views import SessionWizardView

from .models import Petition, Signature, Organization, PytitionUser, PetitionTemplate, Permission
from .models import SlugModel
from .forms import SignatureForm, ContentFormPetition, EmailForm, NewsletterForm, SocialNetworkForm, ContentFormTemplate
from .forms import StyleForm, PetitionCreationStep1, PetitionCreationStep2, PetitionCreationStep3, UpdateInfoForm
from .forms import DeleteAccountForm, OrgCreationForm
from .helpers import get_client_ip, get_session_user, petition_from_id
from .helpers import check_petition_is_accessible
from .helpers import send_confirmation_email, subscribe_to_newsletter, send_welcome_mail
from .helpers import get_update_form, petition_detail_meta
from .helpers import sanitize_html


#------------------------------------ Views -----------------------------------

# Path : /
# Depending on the settings.INDEX_PAGE, show a list of petitions or
# redirect to an user/org profile page
def index(request):
    if not hasattr(settings, 'INDEX_PAGE'):
        raise Http404(_("You must set an INDEX_PAGE config in your settings"))
    if settings.INDEX_PAGE == 'USER_PROFILE':
        try:
            user_name = settings.INDEX_PAGE_USER
        except:
            raise Http404(_("You must set an INDEX_PAGE_USER config in your settings"))
    elif settings.INDEX_PAGE == 'ORGA_PROFILE':
        try:
            org_name = settings.INDEX_PAGE_ORGA
        except:
            raise Http404(_("You must set an INDEX_PAGE_ORGA config in your settings"))

    if settings.INDEX_PAGE == 'ORGA_PROFILE':
        org = Organization.objects.get(name=org_name)
        return redirect("org_profile", org.slugname)
    elif settings.INDEX_PAGE == 'USER_PROFILE':
        return redirect("user_profile", user_name)
    elif settings.INDEX_PAGE == 'LOGIN_REGISTER':
        if request.user.is_authenticated:
            return redirect("user_dashboard")
        else:
            return redirect("login")
    else:
        authenticated = request.user.is_authenticated
        if authenticated:
            user = get_session_user(request)
        else:
            user = request.user
        sort = request.GET.get('sort', 'desc')
        creation_date = '-creation_date' if sort == 'desc' else 'creation_date'
        all_petitions = Petition.objects.filter(published=True).order_by(creation_date)
        paginator = Paginator(all_petitions, settings.PAGINATOR_COUNT)
        page = request.GET.get('page')
        petitions = paginator.get_page(page)

        return render(request, 'petition/index.html',
                {
                    'user': user,
                    'petitions': petitions,
                    'sort': sort
                }
        )


# <int:petition_id>/show_sympa_subscribe_bloc
# Show sympa subscribe bloc to mass subscribe people to newsletter
@login_required
def show_sympa_subscribe_bloc(request, petition_id):
    try:
        pytitionuser = get_session_user(request)
    except:
        pytitionuser = None

    if not pytitionuser:
        return redirect('index')

    petition = petition_from_id(petition_id)

    if petition.owner_type == "org" and not petition.org.is_allowed_to(pytitionuser, "can_view_signatures"):
        return redirect("index")
    elif petition.owner_type == "user" and petition.owner != pytitionuser:
        return redirect("index")

    text_bloc = ""
    signatures = petition.signature_set.filter(subscribed_to_mailinglist=True)
    if not signatures:
        return HttpResponse(_("No newsletter subscription yet!"))

    for signature in signatures:
        text_bloc = text_bloc + "{email} {firstname} {lastname}<br/>\n".format(email=signature.email,
                                                                               firstname=signature.first_name,
                                                                               lastname=signature.last_name)

    return HttpResponse(sanitize_html(text_bloc))


# /search?q=QUERY
# Show results of a search query
def search(request):
    q = request.GET.get('q', '')
    if q != "":
        petitions = Petition.objects.filter(Q(title__icontains=q) | Q(text__icontains=q)).filter(published=True)[:15]
        orgs = Organization.objects.filter(name__icontains=q)
    else:
        petitions = Petition.objects.filter(published=True).order_by('-id')
        paginator = Paginator(petitions, settings.PAGINATOR_COUNT)
        page = request.GET.get('page')
        petitions = paginator.get_page(page)
        orgs = []
    return render(
        request, 'petition/search.html',
        {
            'petitions': petitions,
            'orgs': orgs,
            'q': q
        }
    )

def hide_sign_form_if_user_just_signed(request, ctx):
    storage = get_messages(request)
    for message in storage:
        if message.level == messages.SUCCESS:
            just_confirmed = request.session.get('just_confirmed', False)
            if just_confirmed:
                ctx.update({'signature_is_confirmed': True})
                request.session['just_confirmed'] = False
            else:
                ctx.update({'petition_is_signed': True})

# /<int:petition_id>/
# Show information on a petition
def detail(request, petition_id):
    petition = petition_from_id(petition_id)
    check_petition_is_accessible(request, petition)
    try:
        pytitionuser = get_session_user(request)
    except:
        pytitionuser = None

    sign_form = SignatureForm(petition=petition)
    ctx = {"user": pytitionuser, 'petition': petition, 'form': sign_form,
           'meta': petition_detail_meta(request, petition_id)}

    # If we've just signed successfully the petition, do not show the sign form
    hide_sign_form_if_user_just_signed(request, ctx)

    if "application/json" in request.META.get('HTTP_ACCEPT', []):
        response = JsonResponse(petition.to_json)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        return response
    else:
        return render(request, 'petition/petition_detail.html', ctx)


# /<int:petition_id>/confirm/<confirmation_hash>
# Confirm signature to a petition
def confirm(request, petition_id, confirmation_hash):
    petition = petition_from_id(petition_id)
    check_petition_is_accessible(request, petition)
    try:
        successmsg = petition.confirm_signature(confirmation_hash)
        if successmsg is None:
            messages.error(request, _("Error: This confirmation code is invalid. Maybe you\'ve already confirmed?"))
        else:
            messages.success(request, successmsg)
            request.session['just_confirmed'] = True
    except ValidationError as e:
        messages.error(request, _(e.message))
    except Signature.DoesNotExist:
        messages.error(request, _("Error: This confirmation code is invalid."))
    return redirect(petition.url)


# <int:petition_id>/get_csv_signature
# <int:petition_id>/get_csv_confirmed_signature
# returns the CSV files of the list of signatures
@login_required
def get_csv_signature(request, petition_id, only_confirmed):
    user = get_session_user(request)
    try:
        petition = Petition.objects.get(pk=petition_id)
    except Petition.DoesNotExist:
        return JsonResponse({}, status=404)

    if petition.owner_type == "org" and not petition.org.is_allowed_to(user, "can_view_signatures"):
            return JsonResponse({}, status=403)
    elif petition.owner_type == "user" and petition.owner != user:
            return JsonResponse({}, status=403)

    filename = '{}.csv'.format(petition)
    signatures = Signature.objects.filter(petition = petition)
    if only_confirmed:
        signatures = signatures.filter(confirmed = True)
    else:
        signatures = signatures.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment;filename={}'.format(filename).replace('\r\n', '').replace(' ', '%20')
    writer = csv.writer(response)
    attrs = ['first_name', 'last_name', 'phone', 'email', 'subscribed_to_mailinglist', 'confirmed']
    writer.writerow(attrs)
    for signature in signatures:
        values = [getattr(signature, field) for field in attrs]
        writer.writerow(values)
    return response


# resend/<int:signature_id>
# resend the signature confirmation email
@login_required
def go_send_confirmation_email(request, signature_id):
    app_label = Signature._meta.app_label
    signature = Signature.objects.filter(pk=signature_id).get()
    send_confirmation_email(request, signature)
    return redirect('admin:{}_signature_change'.format(app_label), signature_id)


# <int:petition_id>/sign
# Sign a petition
def create_signature(request, petition_id):
    petition = petition_from_id(petition_id)
    check_petition_is_accessible(request, petition)

    if request.method == "POST":
        form = SignatureForm(petition=petition, data=request.POST)
        if not form.is_valid():
            return render(request, 'petition/petition_detail.html', {'petition': petition, 'form': form, 'meta': petition_detail_meta(request, petition_id)})

        ipaddr = make_password(
                get_client_ip(request),
                salt=petition.salt.encode('utf-8'))
        since = now() - timedelta(seconds=settings.SIGNATURE_THROTTLE_TIMING)
        signatures = Signature.objects.filter(
            petition=petition,
            ipaddress=ipaddr,
            date__gt=since)
        if signatures.count() > settings.SIGNATURE_THROTTLE:
            messages.error(request, _("Too many signatures from your IP address, please try again later."))
            return render(request, 'petition/petition_detail.html', {'petition': petition, 'form': form, 'meta': petition_detail_meta(request, petition_id)})
        else:
            signature = form.save()
            signature.ipaddress = ipaddr
            signature.save()
            send_confirmation_email(request, signature)
            messages.success(request,
                format_html(_("Thank you for signing this petition, an email has just been sent to you at your address \'{}\'" \
                " in order to confirm your signature.<br>" \
                "You will need to click on the confirmation link in the email.<br>" \
                "If you cannot find the email in your Inbox, please have a look in your Spam box.")\
                , signature.email))

        if petition.has_newsletter and signature.subscribed_to_mailinglist:
            subscribe_to_newsletter(petition, signature.email)

    return redirect(petition.url)


# /org/<slug:orgslugname>/dashboard
# Show the dashboard of an organization
@login_required
def org_dashboard(request, orgslugname):
    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        messages.error(request, _("This organization does not exist: '{}'".format(orgslugname)))
        return redirect("user_dashboard")

    pytitionuser = get_session_user(request)

    if pytitionuser not in org.members.all():
        messages.error(request, _("You are not part of this organization: '{}'".format(org.name)))
        return redirect("user_dashboard")


    try:
        permissions = Permission.objects.get(organization=org, user=pytitionuser)
    except Permission.DoesNotExist:
        messages.error(request,
            _("Internal error, cannot find your permissions attached to this organization (\'{orgname}\')"
              .format(orgname=org.name)))
        return redirect("user_dashboard")

    can_create_petition = org.is_allowed_to(pytitionuser, "can_create_petitions")
    petitions = org.petition_set.all()
    other_orgs = pytitionuser.organization_set.filter(~Q(name=org.name)).all()
    return render(request, 'petition/org_dashboard.html',
            {'org': org, 'user': pytitionuser, "other_orgs": other_orgs,
            'petitions': petitions, 'user_permissions': permissions,
             'can_create_petition': can_create_petition})


# /user/dashboard
# Dashboard of the logged in user
@login_required
def user_dashboard(request):
    user = get_session_user(request)
    petitions = user.petition_set.all()

    return render(
        request,
        'petition/user_dashboard.html',
        {'user': user, 'petitions': petitions, 'can_create_petition': True}
    )


# /user/<user_name>
# Show the user profile
def user_profile(request, user_name):
    try:
        user = PytitionUser.objects.get(user__username=user_name)
    except PytitionUser.DoesNotExist:
        raise Http404(_("not found"))
    sort = request.GET.get('sort', 'desc')
    creation_date = '-creation_date' if sort == 'desc' else 'creation_date'
    petitions = user.petition_set.filter(published=True).order_by(creation_date)
    paginator = Paginator(petitions, settings.PAGINATOR_COUNT)
    page = request.GET.get('page')
    petitions = paginator.get_page(page)

    return render(
        request,
        'petition/user_profile.html',
        {'user': user, 'petitions': petitions, 'sort': sort }
    )


# /org/<slug:orgslugname>/leave_org
# User is leaving the organisation
@login_required
def leave_org(request, orgslugname):
    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("not found"))

    pytitionuser = get_session_user(request)

    if pytitionuser not in org.members.all():
        raise Http404(_("not found"))
    with transaction.atomic():
        if org.is_last_admin(pytitionuser):
            messages.error(request, _('Impossible to leave this organisation, you are the last administrator'))
            return redirect(reverse('account_settings') + '#a_org_form')
        elif org.members.count() == 1:
                messages.error(request, _('Impossible to leave this organisation, you are the last member'))
                return redirect(reverse('account_settings') + '#a_org_form')
        else:
            org.members.remove(pytitionuser)
    return redirect('account_settings')


# /org/<slug:orgslugname>
# Show the profile of an organization
def org_profile(request, orgslugname):
    try:
        user = get_session_user(request)
    except:
        user = None
    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("not found"))

    sort = request.GET.get('sort', 'desc')
    creation_date = '-creation_date' if sort == 'desc' else 'creation_date'
    petitions = org.petition_set.filter(published=True).order_by(creation_date)
    paginator = Paginator(petitions, settings.PAGINATOR_COUNT)
    page = request.GET.get('page')
    petitions = paginator.get_page(page)

    ctx = {'org': org,
           'petitions': petitions,
           'sort': sort}

    # if a user is logged-in, put it in the context, it will feed the navbar dropdown
    if user is not None:
        ctx['user'] = user

    return render(request, "petition/org_profile.html", ctx)


# /get_user_list
# get the list of users
@login_required
def get_user_list(request):
    q = request.GET.get('q', '')
    if q != "":
        users = PytitionUser.objects.filter(Q(user__username__contains=q) | Q(user__first_name__icontains=q) |
                                            Q(user__last_name__icontains=q)).all()
    else:
        users =  []

    userdict = {
        "values": [user.user.username for user in users],
    }
    return JsonResponse(userdict)


# PATH : org/<slug:orgslugname>/add_user
# Add an user to an organization
@login_required
def org_add_user(request, orgslugname):
    adduser = request.GET.get('user', '')

    try:
        adduser = PytitionUser.objects.get(user__username=adduser)
    except PytitionUser.DoesNotExist:
        message = _("This user does not exist (anylonger?)")
        return JsonResponse({"message": message}, status=404)

    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        message = _("This organization does not exist (anylonger?)")
        return JsonResponse({"message": message}, status=404)

    pytitionuser = get_session_user(request)

    if org not in pytitionuser.organization_set.all():
        message = _("You are not part of this organization.")
        return JsonResponse({"message": message}, status=403)

    if org in adduser.organization_set.all():
        message = _("User is already member of {orgname} organization".format(orgname=org.name))
        return JsonResponse({"message": message}, status=500)

    if not org.is_allowed_to(pytitionuser, "can_add_members"):
        message = _("You are not allowed to invite new members into this organization.")
        return JsonResponse({"message": message}, status=403)

    try:
        adduser.invitations.add(org)
        adduser.save()
    except:
        message = _("An error occured")
        return JsonResponse({"message": message}, status=500)

    message = _("You invited {username} to join {orgname}".format(username=adduser.name, orgname=org.name))
    return JsonResponse({"message": message})


# /org/<slug:orgslugname>/invite_accept
# Accept an invitation to an organisation
# Called from /user/dashboard
@login_required
def invite_accept(request, orgslugname):
    if orgslugname == "":
        return HttpResponse(status=500)

    pytitionuser = get_session_user(request)
    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("not found"))

    if org in pytitionuser.invitations.all():
        try:
            with transaction.atomic():
                pytitionuser.invitations.remove(org)
                org.members.add(pytitionuser)
        except:
            return HttpResponse(status=500)
    else:
        raise Http404(_("not found"))
    return redirect('user_dashboard')


# /org/<slug:orgslugname>/invite_dismiss
# Dismiss the invitation to an organisation
@login_required
def invite_dismiss(request, orgslugname):
    if orgslugname == "":
        return JsonResponse({}, status=500)

    pytitionuser = get_session_user(request)

    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("not found"))

    if org in pytitionuser.invitations.all():
        try:
            pytitionuser.invitations.remove(org)
        except:
            return JsonResponse({}, status=500)
    else:
        raise Http404(_("not found"))

    return redirect('user_dashboard')


# /org/<slug:orgslugname>/new_template
# /user/new_template
# Create a new template
@login_required
def new_template(request, orgslugname=None):
    pytitionuser = get_session_user(request)
    ctx = {'user': pytitionuser}

    if orgslugname:
        redirection = "org_new_template"
        try:
            org = Organization.objects.get(slugname=orgslugname)
            ctx['org'] = org
        except Organization.DoesNotExist:
            raise Http404(_("Organization does not exist"))

        if org not in pytitionuser.organization_set.all():
            return HttpResponseForbidden(_("You are not allowed to view this organization dashboard"))

        try:
            permissions = Permission.objects.get(organization=org, user=pytitionuser)
            ctx['user_permissions'] = permissions
        except Permission.DoesNotExist:
            return HttpResponse(
                _("Internal error, cannot find your permissions attached to this organization (\'{orgname}\')"
                  .format(orgname=org.name)), status=500)

        if not permissions.can_create_templates:
            return HttpResponseForbidden(_("You don't have the permission to create a Template in this organization"))

        ctx['base_template'] = 'petition/org_base.html'
    else:
        redirection = "user_new_template"
        ctx['base_template'] = 'petition/user_base.html'

    if request.method == "POST":
        template_name = request.POST.get('template_name', '')
        if template_name != '':
            if orgslugname:
                template = PetitionTemplate(name=template_name, org=org)
            else:
                template = PetitionTemplate(name=template_name, user=pytitionuser)
            template.save()
            return redirect("edit_template", template.id)
        else:
            messages.error(request, _("You need to provide a template name."))
            return redirect(redirection)
    else:
        return render(request, "petition/new_template.html", ctx)


# /templates/<int:template_id>/edit
# Edit a petition template
@login_required
def edit_template(request, template_id):
    id = template_id
    if id == '':
        return HttpResponseForbidden(_("You need to provide the template id to modify"))

    try:
        template = PetitionTemplate.objects.get(pk=id)
    except PetitionTemplate.DoesNotExist:
        raise Http404(_("This template does not exist"))

    pytitionuser = get_session_user(request)
    context = {'user': pytitionuser}

    if template.owner_type == "org":
        owner = template.org
    else:
        owner = template.user

    if template.owner_type == "org":
        try:
            permissions = Permission.objects.get(organization=owner, user=pytitionuser)
        except:
            return HttpResponse(
                _("Internal error, cannot find your permissions attached to this organization (\'{orgname}\')"
                  .format(orgname=owner.name)), status=500)
        context['user_permissions'] = permissions
        if owner not in pytitionuser.organization_set.all() or not permissions.can_modify_templates:
            return HttpResponseForbidden(_("You are not allowed to edit this organization's templates"))
        context['org'] = owner
        base_template = "petition/org_base.html"
    else:
        if owner != pytitionuser:
            return HttpResponseForbidden(_("You are not allowed to edit this user's templates"))
        base_template = "petition/user_base.html"

    submitted_ctx = {
        'content_form_submitted': False,
        'email_form_submitted': False,
        'social_network_form_submitted': False,
        'newsletter_form_submitted': False,
        'style_form_submitted': False,
    }

    if request.method == "POST":
        if 'content_form_submitted' in request.POST:
            content_form = ContentFormTemplate(request.POST)
            submitted_ctx['content_form_submitted'] = True
            if content_form.is_valid():
                template.name = content_form.cleaned_data['name']
                template.text = content_form.cleaned_data['text']
                template.side_text = content_form.cleaned_data['side_text']
                template.footer_text = content_form.cleaned_data['footer_text']
                template.footer_links = content_form.cleaned_data['footer_links']
                template.sign_form_footer = content_form.cleaned_data['sign_form_footer']
                template.save()
        else:
            content_form = ContentFormTemplate({f: getattr(template, f) for f in ContentFormTemplate.base_fields})


        if 'email_form_submitted' in request.POST:
            email_form = EmailForm(request.POST)
            submitted_ctx['email_form_submitted'] = True
            if email_form.is_valid():
                template.confirmation_email_reply = email_form.cleaned_data['confirmation_email_reply']
                template.save()
        else:
            email_form = EmailForm({f: getattr(template, f) for f in EmailForm.base_fields})

        if 'social_network_form_submitted' in request.POST:
            social_network_form = SocialNetworkForm(request.POST, request.FILES)
            submitted_ctx['social_network_form_submitted'] = True
            if social_network_form.is_valid():
                storage = FileSystemStorage()
                file = social_network_form.cleaned_data['twitter_image']
                if file:
                    path = os.path.join(storage.location, pytitionuser.username, file.name)
                    name = storage._save(path, file)
                    newrelpath = os.path.relpath(name, storage.location)
                    template.twitter_image = urllib.parse.urljoin(settings.MEDIA_URL, newrelpath)
                if social_network_form.cleaned_data['remove_twitter_image']:
                    template.twitter_image = ""
                template.twitter_description = social_network_form.cleaned_data['twitter_description']
                template.org_twitter_handle = social_network_form.cleaned_data['org_twitter_handle']
                template.save()
        else:
            remove_fields = ["twitter_image", "remove_twitter_image"]
            fields = dict((k, v) for k,v in SocialNetworkForm.base_fields.items() if k not in remove_fields)
            social_network_form = SocialNetworkForm({f: getattr(template, f) for f in fields})

        if 'newsletter_form_submitted' in request.POST:
            newsletter_form = NewsletterForm(request.POST)
            submitted_ctx['newsletter_form_submitted'] = True
            if newsletter_form.is_valid():
                template.has_newsletter = newsletter_form.cleaned_data['has_newsletter']
                template.newsletter_text = newsletter_form.cleaned_data['newsletter_text']
                template.newsletter_subscribe_http_data = newsletter_form.cleaned_data['newsletter_subscribe_http_data']
                template.newsletter_subscribe_http_mailfield = newsletter_form.cleaned_data['newsletter_subscribe_http_mailfield']
                template.newsletter_subscribe_http_url = newsletter_form.cleaned_data['newsletter_subscribe_http_url']
                template.newsletter_subscribe_mail_subject = newsletter_form.cleaned_data['newsletter_subscribe_mail_subject']
                template.newsletter_subscribe_mail_from = newsletter_form.cleaned_data['newsletter_subscribe_mail_from']
                template.newsletter_subscribe_mail_to = newsletter_form.cleaned_data['newsletter_subscribe_mail_to']
                template.newsletter_subscribe_method = newsletter_form.cleaned_data['newsletter_subscribe_method']
                template.newsletter_subscribe_mail_smtp_host = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_host']
                template.newsletter_subscribe_mail_smtp_port = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_port']
                template.newsletter_subscribe_mail_smtp_user = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_user']
                template.newsletter_subscribe_mail_smtp_password = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_password']
                template.newsletter_subscribe_mail_smtp_tls = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_tls']
                template.newsletter_subscribe_mail_smtp_starttls = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_starttls']
                template.save()
        else:
            newsletter_form = NewsletterForm({f: getattr(template, f) for f in NewsletterForm.base_fields})

        if 'style_form_submitted' in request.POST:
            submitted_ctx['style_form_submitted'] = True
            style_form = StyleForm(request.POST)
            if style_form.is_valid():
                template.bgcolor = style_form.cleaned_data['bgcolor']
                template.linear_gradient_direction = style_form.cleaned_data['linear_gradient_direction']
                template.gradient_from = style_form.cleaned_data['gradient_from']
                template.gradient_to = style_form.cleaned_data['gradient_to']
                template.save()
        else:
            style_form = StyleForm({f: getattr(template, f) for f in StyleForm.base_fields})
    else:
        remove_fields = ["twitter_image", "remove_twitter_image"]
        fields = dict((k, v) for k, v in SocialNetworkForm.base_fields.items() if k not in remove_fields)
        social_network_form = SocialNetworkForm({f: getattr(template, f) for f in fields})
        content_form = ContentFormTemplate({f: getattr(template, f) for f in ContentFormTemplate.base_fields})
        email_form = EmailForm({f: getattr(template, f) for f in EmailForm.base_fields})
        newsletter_form = NewsletterForm({f: getattr(template, f) for f in NewsletterForm.base_fields})
        style_form = StyleForm({f: getattr(template, f) for f in StyleForm.base_fields})

    ctx = {'content_form': content_form,
           'email_form': email_form,
           'social_network_form': social_network_form,
           'newsletter_form': newsletter_form,
           'style_form': style_form,
           'petition': template}


    context['base_template'] = base_template
    context.update(ctx)
    context.update(submitted_ctx)
    return render(request, "petition/edit_template.html", context)


# /templates/<int:template_id>/delete
# Delete a template
@login_required
def template_delete(request, template_id):
    pytitionuser = get_session_user(request)
    if template_id == '':
        return JsonResponse({}, status=500)

    try:
        template = PetitionTemplate.objects.get(pk=template_id)
    except:
        return JsonResponse({}, status=404)

    if template.owner_type == "org":
        if not pytitionuser in template.org.members.all():
            return JsonResponse({}, status=403)  # User not in organization
        try:
            permissions = Permission.objects.get(
                    organization=template.org,
                    user=pytitionuser)
        except Permission.DoesNotExist:
            return JsonResponse({}, status=500)  # No permission? fatal error!
        if not permissions.can_delete_templates:
            return JsonResponse({}, status=403)  # User does not have the permission!
    else:
        if pytitionuser != template.user:
            return JsonResponse({}, status=403)  # User cannot delete a template if it's not his
    template.delete()
    return JsonResponse({})


# /templates/<int:template_id>/fav
# Set a template as favourite
@login_required
def template_fav_toggle(request, template_id):
    pytitionuser = get_session_user(request)
    if template_id == '':
        return JsonResponse({}, status=500)

    try:
        template = PetitionTemplate.objects.get(pk=template_id)
    except PetitionTemplate.DoesNotExist:
        return JsonResponse({}, status=404)

    if template.owner_type == "org":
        owner = template.org
    else:
        owner = template.user

    if template.owner_type == "org":
        if owner not in pytitionuser.organization_set.all():
            return JsonResponse({}, status=403)  # Forbidden
    else:
        if owner != pytitionuser:
            return JsonResponse({'msg': _("You are not allowed to change this user's default template")}, status=403)

    if owner.default_template == template:
        owner.default_template = None
    else:
        owner.default_template = template
    owner.save()

    return JsonResponse({})


# /org/<slug:orgslugname>/delete_member
# Remove a member from an organization
@login_required
def org_delete_member(request, orgslugname):
    member_name = request.GET.get('member', '')
    try:
        member = PytitionUser.objects.get(user__username=member_name)
    except PytitionUser.DoesNotExist:
        raise Http404(_("User does not exist"))

    pytitionuser = get_session_user(request)

    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("Organization does not exist"))

    if pytitionuser not in org.members.all():
        return JsonResponse({}, status=403)  # Forbidden

    try:
        permissions = Permission.objects.get(user=pytitionuser, organization=org)
    except Permission.DoesNoeExist:
        return JsonResponse({}, status=500)

    if permissions.can_remove_members or pytitionuser == member:
        if org in member.organization_set.all():
            if org.is_last_admin(member):
                return JsonResponse({}, status=403)  # Forbidden
            member.organization_set.remove(org)
        else:
            return JsonResponse({}, status=404)
    else:
        return JsonResponse({}, status=403)  # Forbidden

    return JsonResponse({}, status=200)


# PATH : org/<slug:orgslugname>/edit_user_permissions/<slug:user_name>
# Show a webpage to edit permissions
@login_required
def org_edit_user_perms(request, orgslugname, user_name):
    """Shows the page which lists the user permissions."""
    pytitionuser = get_session_user(request)

    try:
        member = PytitionUser.objects.get(user__username=user_name)
    except PytitionUser.DoesNotExist:
        messages.error(request, _("User '{name}' does not exist".format(name=user_name)))
        return redirect("org_dashboard", orgslugname)

    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("Organization '{name}' does not exist".format(name=orgslugname)))

    if org not in member.organization_set.all():
        messages.error(request, _("The user '{username}' is not member of this organization ({orgname}).".
                                  format(username=user_name, orgname=org.name)))
        return redirect("org_dashboard", org.slugname)

    try:
        permissions = Permission.objects.get(organization=org, user=member)
    except Permission.DoesNotExist:
        messages.error(request,
                       _("Internal error, this member does not have permissions attached to this organization."))
        return redirect("org_dashboard", org.slugname)

    try:
        user_permissions = Permission.objects.get(organization=org, user=pytitionuser)
    except:
        return HttpResponse(
            _("Internal error, cannot find your permissions attached to this organization (\'{orgname}\')"
              .format(orgname=org.name)), status=500)

    return render(request, "petition/org_edit_user_perms.html",
            {'org': org, 'member': member, 'user': pytitionuser,
            'permissions': permissions,
            'user_permissions': user_permissions})

# PATH /org/<slug:orgslugname>/set_user_permissions/<slug:user_name>
# Set a permission for an user
@login_required
def org_set_user_perms(request, orgslugname, user_name):
    """Actually do the modification of user permissions.
    Data come from "org_edit_user_perms" view's form.
    """
    pytitionuser = get_session_user(request)

    try:
        member = PytitionUser.objects.get(user__username=user_name)
    except PytitionUser.DoesNotExist:
        messages.error(request, _("User does not exist"))
        return redirect("org_dashboard", orgslugname)

    try:
        org = Organization.objects.get(slugname=orgslugname)
    except Organization.DoesNotExist:
        raise Http404(_("Organization does not exist"))

    if org not in member.organization_set.all():
        messages.error(request, _("This user is not part of organization \'{orgname}\'".format(orgname=org.name)))
        return redirect("org_dashboard", org.slugname)

    try:
        permissions = Permission.objects.get(user=member, organization=org)
    except Permission.DoesNotExist:
        messages.error(request, _("Fatal error, this user does not have permissions attached for this organization"))
        return redirect("org_dashboard", org.slugname)

    try:
        userperms = Permission.objects.get(user=pytitionuser, organization=org)
    except:
        messages.error(request, _("Fatal error, you don't have permissions attached to you for this organization"))
        return redirect("org_dashboard", org.slugname)

    if pytitionuser not in org.members.all():
        messages.error(request, _("You are not part of this organization"))
        return redirect("user_dashboard")

    if not userperms.can_modify_permissions:
        messages.error(request, _("You are not allowed to modify this organization members' permissions"))
        return redirect("org_edit_user_perms", orgslugname, user_name)

    if request.method == "POST":
        error = False
        post = request.POST
        permissions.can_remove_members = post.get('can_remove_members', '') == 'on'
        permissions.can_add_members = post.get('can_add_members', '') == 'on'
        permissions.can_create_petitions = post.get('can_create_petitions', '') == 'on'
        permissions.can_modify_petitions = post.get('can_modify_petitions', '') == 'on'
        permissions.can_delete_petitions = post.get('can_delete_petitions', '') == 'on'
        permissions.can_create_templates = post.get('can_create_templates', '') == 'on'
        permissions.can_modify_templates = post.get('can_modify_templates', '') == 'on'
        permissions.can_delete_templates = post.get('can_delete_templates', '') == 'on'
        permissions.can_view_signatures = post.get('can_view_signatures', '') == 'on'
        permissions.can_modify_signatures = post.get('can_modify_signatures', '') == 'on'
        permissions.can_delete_signatures = post.get('can_delete_signatures', '') == 'on'
        can_modify_perms = post.get('can_modify_permissions', '') == 'on'
        with transaction.atomic():
            # if user is dropping his own permissions
            if not can_modify_perms and permissions.can_modify_permissions and pytitionuser == member:
                # get list of people with can_modify_permissions permission on this org
                owners = org.owners
                if owners.count() > 1:
                    permissions.can_modify_permissions = can_modify_perms
                else:
                    if org.members.count() > 1:
                        error = True
                        messages.error(request, _("You cannot remove your ability to change permissions on this "
                                                  "Organization because you are the only one left who can do this. "
                                                  "Give the permission to someone else before removing yours."))
                    else:
                        error = True
                        messages.error(request, _("You cannot remove your ability to change permissions on this "
                                                  "Organization because you are the only member left."))
        if not error:
            permissions.can_modify_permissions = can_modify_perms
            messages.success(request, _("Permissions successfully changed!"))
        permissions.save()

    return redirect("org_edit_user_perms", orgslugname, user_name)


WizardTemplates = {"step1": "petition/new_petition_step1.html",
                    "step2": "petition/new_petition_step2.html",
                    "step3": "petition/new_petition_step3.html"}

WizardForms = [("step1", PetitionCreationStep1),
         ("step2", PetitionCreationStep2),
         ("step3", PetitionCreationStep3)]


# Class Based Controller
# PATH : subroutes of /wizard
@method_decorator(login_required, name='dispatch')
class PetitionCreationWizard(SessionWizardView):
    def dispatch(self, request, *args, **kwargs):
        if settings.DISABLE_USER_PETITION and "orgslugname" not in self.kwargs:
            messages.error(request, _("Users are not allowed to create their own petitions."))
            return redirect("user_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        return [WizardTemplates[self.steps.current]]

    def get_form_initial(self, step):
        if step == "step2":
            use_template = False
            org_petition = "orgslugname" in self.kwargs
            if org_petition:
                orgslugname = self.kwargs['orgslugname']
                org = Organization.objects.get(slugname=orgslugname)
            else:
                pytitionuser = get_session_user(self.request)

            # Use a specific template if its id is given
            if "template_id" in self.kwargs:
                template = PetitionTemplate.objects.get(pk=self.kwargs['template_id'])
                if org_petition:
                    if template in org.petitiontemplate_set.all():
                        return {'message': template.text}
                else:
                    if template in pytitionuser.petitiontemplate_set.all():
                        return {'message': template.text}

            # if no template id is given, check for default templates
            if org_petition:
                if org.default_template is not None:
                    template = org.default_template
                    use_template = True
            elif pytitionuser.default_template is not None:
                template = pytitionuser.default_template
                use_template = True

            if use_template:
                return {'message': template.text}

        return self.initial_dict.get(step, {})

    def get_form_kwargs(self, step=None):
        if step == "step1":
            org_petition = "orgslugname" in self.kwargs
            if org_petition:
                orgslugname = self.kwargs['orgslugname']
                kwargs = {"orgslugname": orgslugname}
            else:
                pytitionuser = get_session_user(self.request)
                kwargs = {"user_name": pytitionuser.user.username}
            return kwargs
        else:
            return {}

    def done(self, form_list, **kwargs):
        org_petition = "orgslugname" in self.kwargs
        title = self.get_cleaned_data_for_step("step1")["title"]
        message = self.get_cleaned_data_for_step("step2")["message"]
        publish = self.get_cleaned_data_for_step("step3")["publish"]
        pytitionuser = get_session_user(self.request)
        _redirect = self.request.POST.get('redirect', '')

        if org_petition:
            orgslugname = self.kwargs['orgslugname']
            try:
                org = Organization.objects.get(slugname=orgslugname)
            except Organization.DoesNotExist:
                messages.error(self.request, _("Cannot find this organization"))
                return redirect("user_dashboard")
                #raise Http404(_("Organization does not exist"))

            try:
                permissions = Permission.objects.get(organization=org, user=pytitionuser)
            except Permission.DoesNotExist:
                return redirect("org_dashboard", orgslugname)

            if pytitionuser in org.members.all() and permissions.can_create_petitions:
                #FIXME I think new here is better than create
                petition = Petition.objects.create(title=title, text=message, org=org)
                if "template_id" in self.kwargs:
                    template = PetitionTemplate.objects.get(pk=self.kwargs['template_id'])
                    if template in org.petitiontemplate_set.all():
                        petition.prepopulate_from_template(template)
                        petition.save()
                    else:
                        messages.error(self.request, _("This template does not belong to your organization"))
                        return redirect("org_dashboard", orgslugname)
                if publish:
                    petition.publish()
                if _redirect and _redirect == '1':
                    return redirect("edit_petition", petition.id)
                else:
                    return redirect("org_dashboard", orgslugname)
            else:
                messages.error(self.request, _("You don't have the permission to create a new petition in this Organization"))
                return redirect("org_dashboard", orgslugname)
        else:
            petition = Petition.objects.create(title=title, text=message, user=pytitionuser)
            if "template_id" in self.kwargs:
                template = PetitionTemplate.objects.get(pk=self.kwargs['template_id'])
                if template in pytitionuser.petitiontemplate_set.all():
                    petition.prepopulate_from_template(template)
                    petition.save()
                else:
                    messages.error(self.request, _("This template does not belong to you"))
                    return redirect("user_dashboard")
            if publish:
                petition.publish()
            if _redirect and _redirect == '1':
                return redirect("edit_petition", petition.id)
            else:
                return redirect("user_dashboard")

    def get_context_data(self, form, **kwargs):
        org_petition = "orgslugname" in self.kwargs
        context = super(PetitionCreationWizard, self).get_context_data(form=form, **kwargs)
        if org_petition:
            base_template = 'petition/org_base.html'
            try:
                org = Organization.objects.get(slugname=self.kwargs['orgslugname'])
            except Organization.DoesNotExist:
                raise Http404(_("Organization does not exist"))
        else:
            base_template = 'petition/user_base.html'

        pytitionuser = get_session_user(self.request)
        context.update({'user': pytitionuser,
                        'base_template': base_template})

        if org_petition:
            try:
                permissions = Permission.objects.get(organization=org, user=pytitionuser)
            except Permission.DoesNotExist:
                return HttpResponse(
                    _("Internal error, cannot find your permissions attached to this organization (\'{orgname}\')"
                      .format(orgname=org.name)), status=500)
            context.update({'org': org,
                            'user_permissions': permissions})
        else:
            petitions = pytitionuser.petition_set.all()
            context.update({'petitions': petitions})

        if self.steps.current == "step3":
            context.update(self.get_cleaned_data_for_step("step1"))
            context.update(self.get_cleaned_data_for_step("step2"))
        return context


# /<int:petition_id>/delete
# Delete a petition
@login_required
def petition_delete(request, petition_id):
    petition = petition_from_id(petition_id)
    pytitionuser = get_session_user(request)

    if petition.owner_type == "user":
        if petition.user == pytitionuser:
            petition.delete()
            return JsonResponse({})
        else:
            return JsonResponse({}, status=403)
    else:  # an organization owns the petition
        userperms = Permission.objects.get(organization=petition.org, user=pytitionuser)
        if userperms.can_delete_petitions:
            petition.delete()
            return JsonResponse({})
        else:
            return JsonResponse({}, status=403)


# /<int:petition_id>/publish
# Publish a petition
@login_required
def petition_publish(request, petition_id):
    pytitionuser = get_session_user(request)
    petition = petition_from_id(petition_id)

    if petition.owner_type == "user":
        if petition.user == pytitionuser:
            petition.publish()
            return JsonResponse({})
        else:
            # Petition owned by someone else
            return JsonResponse({}, status=403)
    else:
        # Check if the user has permission over this org
        try:
            userperms = Permission.objects.get(organization=petition.org, user=pytitionuser)
            if userperms.can_modify_petitions:
                petition.publish()
                return JsonResponse({})
            else:
                return JsonResponse({}, status=403)
        except Permission.DoesNotExist:
            return JsonResponse({}, status=403)


# /<int:petition_id>/unpublish
# Unpublish a petition
@login_required
def petition_unpublish(request, petition_id):
    pytitionuser = get_session_user(request)
    petition = petition_from_id(petition_id)

    if petition.owner_type == "user":
        if petition.user == pytitionuser:
            petition.unpublish()
            return JsonResponse({})
        else:
            return JsonResponse({}, status=403)
    else:
        # Check if the user has permission over this org
        try:
            userperms = Permission.objects.get(organization=petition.org, user=pytitionuser)
            if userperms.can_modify_petitions:
                petition.unpublish()
                return JsonResponse({})
            else:
                return JsonResponse({}, status=403)
        except Permission.DoesNotExist:
            return JsonResponse({}, status=403)


# /<int:petition_id>/edit
# Edit a petition
@login_required
def edit_petition(request, petition_id):
    petition = petition_from_id(petition_id)
    pytitionuser = get_session_user(request)

    if not petition.is_allowed_to_edit(pytitionuser):
        messages.error(request, _("You are not allowed to edit this petition"))
        return redirect("user_dashboard")

    submitted_ctx = {
        'content_form_submitted': False,
        'email_form_submitted': False,
        'social_network_form_submitted': False,
        'newsletter_form_submitted': False,
    }

    if request.method == "POST":
        if 'content_form_submitted' in request.POST:
            submitted_ctx['content_form_submitted'] = True
            content_form = ContentFormPetition(request.POST)
            if content_form.is_valid():
                petition.title = content_form.cleaned_data['title']
                petition.target = content_form.cleaned_data['target']
                petition.paper_signatures = content_form.cleaned_data['paper_signatures']
                petition.text = content_form.cleaned_data['text']
                petition.side_text = content_form.cleaned_data['side_text']
                petition.footer_text = content_form.cleaned_data['footer_text']
                petition.footer_links = content_form.cleaned_data['footer_links']
                petition.sign_form_footer = content_form.cleaned_data['sign_form_footer']
                petition.save()
        else:
            content_form = ContentFormPetition({f: getattr(petition, f) for f in ContentFormPetition.base_fields})

        if 'email_form_submitted' in request.POST:
            submitted_ctx['email_form_submitted'] = True
            email_form = EmailForm(request.POST)
            if email_form.is_valid():
                petition.confirmation_email_reply = email_form.cleaned_data['confirmation_email_reply']
                petition.save()
        else:
            email_form = EmailForm({f: getattr(petition, f) for f in EmailForm.base_fields})

        if 'social_network_form_submitted' in request.POST:
            submitted_ctx['social_network_form_submitted'] = True
            social_network_form = SocialNetworkForm(request.POST, request.FILES)
            if social_network_form.is_valid():
                storage = FileSystemStorage()
                file = social_network_form.cleaned_data['twitter_image']
                if file:
                    path = os.path.join(storage.location, pytitionuser.username, file.name)
                    name = storage._save(path, file)
                    newrelpath = os.path.relpath(name, storage.location)
                    petition.twitter_image = urllib.parse.urljoin(settings.MEDIA_URL, newrelpath)
                if social_network_form.cleaned_data['remove_twitter_image']:
                    petition.twitter_image = ""
                petition.twitter_description = social_network_form.cleaned_data['twitter_description']
                petition.org_twitter_handle = social_network_form.cleaned_data['org_twitter_handle']
                petition.save()
        else:
            data = {'twitter_description': petition.twitter_description,
                    'org_twitter_handle': petition.org_twitter_handle}
            social_network_form = SocialNetworkForm(data)


        if 'newsletter_form_submitted' in request.POST:
            submitted_ctx['newsletter_form_submitted'] = True
            newsletter_form = NewsletterForm(request.POST)
            if newsletter_form.is_valid():
                petition.has_newsletter = newsletter_form.cleaned_data['has_newsletter']
                petition.newsletter_text = newsletter_form.cleaned_data['newsletter_text']
                petition.newsletter_subscribe_http_data = newsletter_form.cleaned_data['newsletter_subscribe_http_data']
                petition.newsletter_subscribe_http_mailfield = newsletter_form.cleaned_data['newsletter_subscribe_http_mailfield']
                petition.newsletter_subscribe_http_url = newsletter_form.cleaned_data['newsletter_subscribe_http_url']
                petition.newsletter_subscribe_mail_subject = newsletter_form.cleaned_data['newsletter_subscribe_mail_subject']
                petition.newsletter_subscribe_mail_from = newsletter_form.cleaned_data['newsletter_subscribe_mail_from']
                petition.newsletter_subscribe_mail_to = newsletter_form.cleaned_data['newsletter_subscribe_mail_to']
                petition.newsletter_subscribe_method = newsletter_form.cleaned_data['newsletter_subscribe_method']
                petition.newsletter_subscribe_mail_smtp_host = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_host']
                petition.newsletter_subscribe_mail_smtp_port = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_port']
                petition.newsletter_subscribe_mail_smtp_user = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_user']
                petition.newsletter_subscribe_mail_smtp_password = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_password']
                petition.newsletter_subscribe_mail_smtp_tls = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_tls']
                petition.newsletter_subscribe_mail_smtp_starttls = newsletter_form.cleaned_data['newsletter_subscribe_mail_smtp_starttls']
                petition.save()
        else:
            newsletter_form = NewsletterForm({f: getattr(petition, f) for f in NewsletterForm.base_fields})

        if 'style_form_submitted' in request.POST:
            submitted_ctx['style_form_submitted'] = True
            style_form = StyleForm(request.POST)
            if style_form.is_valid():
                petition.bgcolor = style_form.cleaned_data['bgcolor']
                petition.linear_gradient_direction = style_form.cleaned_data['linear_gradient_direction']
                petition.gradient_from = style_form.cleaned_data['gradient_from']
                petition.gradient_to = style_form.cleaned_data['gradient_to']
                petition.save()
        else:
            style_form = StyleForm({f: getattr(petition, f) for f in StyleForm.base_fields})
    else:
        data = {'twitter_description': petition.twitter_description,
                'org_twitter_handle': petition.org_twitter_handle}
        social_network_form = SocialNetworkForm(data)
        content_form = ContentFormPetition({f: getattr(petition, f) for f in ContentFormPetition.base_fields})
        style_form = StyleForm({f: getattr(petition, f) for f in StyleForm.base_fields})
        email_form = EmailForm({f: getattr(petition, f) for f in EmailForm.base_fields})
        newsletter_form = NewsletterForm({f: getattr(petition, f) for f in NewsletterForm.base_fields})

    ctx = {'user': pytitionuser,
        'content_form': content_form,
        'style_form': style_form,
        'email_form': email_form,
        'social_network_form': social_network_form,
        'newsletter_form': newsletter_form,
        'petition': petition}
    url_prefix = request.scheme + "://" + request.get_host()

    if petition.owner_type == "org":
        permissions = Permission.objects.get(organization=petition.org, user=pytitionuser)
        example_url = url_prefix + reverse("slug_show_petition",
                            kwargs={'orgslugname': petition.org.slugname,
                            'petitionname': _("save-the-kittens-from-bad-wolf")})
        slug_prefix = (url_prefix + reverse("slug_show_petition",
                                            kwargs={'orgslugname': petition.org.slugname,
                                                    'petitionname': 'toto'})).rsplit('/', 1)[0]
        ctx.update({'org': petition.org,
                    'user_permissions': permissions,
                    'base_template': 'petition/org_base.html',
                    'example_url': example_url,
                    'slug_prefix': slug_prefix})
    else:
        example_url = url_prefix + reverse("slug_show_petition",
                            kwargs={'username': pytitionuser.user.username,
                                        'petitionname': _("save-the-kittens-from-bad-wolf")})
        slug_prefix = (url_prefix + reverse("slug_show_petition",
                                            kwargs={'username': pytitionuser.user.username,
                                                    'petitionname': 'toto'})).rsplit('/', 1)[0]
        ctx.update({'base_template': 'petition/user_base.html',
                    'example_url': example_url,
                    'slug_prefix': slug_prefix})
    ctx.update(submitted_ctx)

    return render(request, "petition/edit_petition.html", ctx)


# /<int:petition_id>/show_signatures
# Show the signatures of a petition
@login_required
def show_signatures(request, petition_id):
    petition = petition_from_id(petition_id)
    pytitionuser = get_session_user(request)
    ctx = {}

    if petition.owner_type == "user":
        base_template = 'petition/user_base.html'
        if petition.user != pytitionuser:
            messages.error(request, _("You are not allowed to view this petition's signatures."))
            return redirect("user_dashboard")
    else:
        org = petition.org
        base_template = 'petition/org_base.html'
        other_orgs = pytitionuser.organization_set.filter(~Q(name=org.name)).all()
        if pytitionuser not in org.members.all():
            messages.error(request, _("You are not member of the following organization: \'{}\'".format(org.name)))
            return redirect("user_dashboard")
        try:
            permissions = Permission.objects.get(organization=org, user=pytitionuser)
        except Permission.DoesNotExist:
            messages.error(request, _("Internal error, cannot find your permissions attached to this organization (\'{orgname}\')".format(orgname=org.name)))
            return redirect("user_dashboard")

        if not permissions.can_view_signatures:
            messages.error(request, _("You are not allowed to view signatures in this organization"))
            return redirect("org_dashboard", org.slugname)

        ctx.update({'org': org, 'other_orgs': other_orgs,
                    'user_permissions': permissions})

    if request.method == "POST":
        action = request.POST.get('action', '')
        selected_signature_ids = request.POST.getlist('signature_id', '')
        failed = False
        if selected_signature_ids and action:
            selected_signatures = Signature.objects.filter(pk__in=selected_signature_ids)
            if action == "delete":
                for s in selected_signatures:
                    pet = s.petition
                    if pet.org: # Petition is owned by an org, we check for rights
                        if pet.org.is_allowed_to(pytitionuser, 'can_delete_signatures'):
                            s.delete()
                        else:
                            failed = True
                    else: # Petition is owned by a user, we check it's the one asking for deletion
                        s.delete()
                if failed:
                    messages.error(request, _("You don't have permission to delete some or all of selected signatures"))
                else:
                    messages.success(request, _("You successfully deleted all selected signatures"))
            if action == "re-send":
                for s in selected_signatures:
                    try:
                        send_confirmation_email(request, s)
                    except:
                        failed = True
                if failed:
                    messages.error(request, _("An error happened while trying to re-send confirmation emails"))
                else:
                    messages.success(request, _("You successfully re-sent all selected confirmation emails"))
        if action == "re-send-all":
            selected_signatures = Signature.objects.filter(petition=petition)
            for s in selected_signatures:
                try:
                    send_confirmation_email(request, s)
                except:
                    failed = True
            if failed:
                messages.error(request, _("An error happened while trying to re-send confirmation emails"))
            else:
                messages.success(request, _("You successfully re-sent all confirmation emails"))
        return redirect("show_signatures", petition_id)

    signatures = petition.signature_set.all()

    ctx.update({'petition': petition, 'user': pytitionuser,
                'base_template': base_template,
                'signatures': signatures})

    return render(request, "petition/signature_data.html", ctx)


# /account_settings
# Show settings for the user accounts
@login_required
def account_settings(request):
    pytitionuser = get_session_user(request)
    submitted_ctx = {
        'update_info_form_submitted': False,
        'delete_account_form_submitted': False,
        'password_change_form_submitted': False
    }

    if request.method == "POST":
        if 'update_info_form_submitted' in request.POST:
            update_info_form = UpdateInfoForm(pytitionuser.user, request.POST)
            submitted_ctx['update_info_form_submitted'] = True
            if update_info_form.is_valid():
                update_info_form.save()
        else:
            update_info_form = get_update_form(pytitionuser.user)

        if 'delete_account_form_submitted' in request.POST:
            delete_account_form = DeleteAccountForm(request.POST)
            submitted_ctx['delete_account_form_submitted'] = True
            if delete_account_form.is_valid():
                pytitionuser.drop()
                return redirect("index")
        else:
            delete_account_form = DeleteAccountForm()

        if 'password_change_form_submitted' in request.POST:
            password_change_form = PasswordChangeForm(pytitionuser.user, request.POST)
            submitted_ctx['password_change_form_submitted'] = True
            if password_change_form.is_valid():
                password_change_form.save()
                messages.success(request, _("You successfully changed your password!"))
        else:
            password_change_form = PasswordChangeForm(pytitionuser.user)

    else:
        update_info_form = get_update_form(pytitionuser.user)
        delete_account_form = DeleteAccountForm()
        password_change_form = PasswordChangeForm(pytitionuser.user)

    orgs = pytitionuser.organization_set.all()
    # Checking if the user is allowed to leave the organisation
    for org in orgs:
        if org.members.count() < 2:
            org.leave = False
        else:
            # More than one user, we need to check owners
            owners = org.owners.all()
            if owners.count() == 1 and pytitionuser in owners:
                org.leave = False
            else:
                org.leave = True

    ctx = {'user': pytitionuser,
           'update_info_form': update_info_form,
           'delete_account_form': delete_account_form,
           'password_change_form': password_change_form,
           'base_template': 'petition/user_base.html',
           'orgs': orgs}
    ctx.update(submitted_ctx)

    return render(request, "petition/account_settings.html", ctx)


# GET/POST /org/create
# Create a new organization
@login_required
def org_create(request):
    if settings.RESTRICT_ORG_CREATION and not request.user.is_superuser:
        messages.error(request, _("Only super users can create an organization."))
        return redirect("user_dashboard")
    user = get_session_user(request)

    ctx = {'user': user}

    if request.method == "POST":
        form = OrgCreationForm(request.POST)
        if form.is_valid():
            org = form.save()
            org.members.add(user)
            perm = Permission.objects.get(organization=org)
            perm.set_all(True)
            messages.success(request, _("You successfully created organization '{}'".format(org.name)))
            return redirect('user_dashboard')
        else:
            ctx.update({'form': form})
            return render(request, "petition/org_create.html", ctx)

    form = OrgCreationForm()
    ctx.update({'form': form})
    return render(request, "petition/org_create.html", ctx)


# GET /org/<slug:orgslugname>/<slug:petitionname>
# Show a petition
def slug_show_petition(request, orgslugname=None, username=None, petitionname=None):
    try:
        pytitionuser = get_session_user(request)
    except:
        pytitionuser = None

    if orgslugname:
        try:
            org = Organization.objects.get(slugname=orgslugname)
            slug = SlugModel.objects.get(slug=petitionname, petition__org=org)
        except (Organization.DoesNotExist, SlugModel.DoesNotExist):
            raise Http404(_("Sorry, we are not able to find this petition"))
        petition = slug.petition
    else:
        try:
            user = PytitionUser.objects.get(user__username=username)
            slug = SlugModel.objects.get(slug=petitionname, petition__user=user)
        except PytitionUser.DoesNotExist:
            raise Http404(_("Sorry, we are not able to find this petition"))
        except SlugModel.DoesNotExist:
            raise Http404(_("Sorry, we are not able to find this petition"))
        petition = slug.petition

    initial = None if not pytitionuser else {
        'first_name': pytitionuser.user.first_name,
        'last_name': pytitionuser.user.last_name,
        'email': pytitionuser.user.email
    }

    sign_form = SignatureForm(petition=petition, initial=initial)

    ctx = {"user": pytitionuser, "petition": petition, "form": sign_form,
           'meta': petition_detail_meta(request, petition.id)}

    # If we've just signed successfully the petition, do not show the sign form
    hide_sign_form_if_user_just_signed(request, ctx)

    if "application/json" in request.META.get('HTTP_ACCEPT', []):
        response = JsonResponse(petition.to_json)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        return response
    else:
        return render(request, "petition/petition_detail.html", ctx)


# /<int:petition_id>/add_new_slug
# Add a new slug for a petition
@login_required
def add_new_slug(request, petition_id):
    pytitionuser = get_session_user(request)
    try:
        petition = petition_from_id(petition_id)
    except:
        messages.error(request, _("This petition does not exist (anymore?)."))
        return redirect("user_dashboard")

    if request.method == "POST":
        slugtexts = request.POST.getlist('slugtext', '')
        if slugtexts == '' or slugtexts == []:
            messages.error(request, _("You entered an empty slug text"))
        else:
            if petition.is_allowed_to_edit(pytitionuser):
                for slugtext in slugtexts:
                    try:
                        petition.add_slug(slugtext)
                        petition.save()
                        messages.success(request, _("Successful addition of the slug '{}'!".format(slugtext)))
                    except IntegrityError:
                        messages.error(request, _("The slug '{}' already exists!".format(slugtext)))
                    except ValidationError as v:
                        for message in v.messages:
                            messages.error(request, message)
            else:
                messages.error(request, _("You don't have the permission to modify petitions"))
        return redirect(reverse("edit_petition", args=[petition_id]) + "#tab_social_network_form")
    else:
        return redirect("user_dashboard")


# /<int:petition_id>/del_slug
# Remove a slug from a petition
@login_required
def del_slug(request, petition_id):
    pytitionuser = get_session_user(request)
    try:
        petition = petition_from_id(petition_id)
    except:
        messages.error(request, _("This petition does not exist (anymore?)."))
        return redirect("user_dashboard")
    if petition.is_allowed_to_edit(pytitionuser):
        slug_id = request.GET.get('slugid', None)
        if not slug_id:
            return redirect(reverse("edit_petition", args=[petition_id]) + "#tab_social_network_form")

        slug = SlugModel.objects.get(pk=slug_id)
        petition.del_slug(slug)
        petition.save()
        messages.success(request, _("Successful deletion of a slug"))
    else:
        messages.error(request, _("You don't have the permission to modify petitions"))
        if petition.owner_type == "org":
            return redirect("org_dashboard", petition.owner.slugname)
        else:
            return redirect("user_dashboard")
    return redirect(reverse("edit_petition", args=[petition_id]) + "#tab_social_network_form")


@login_required
def image_upload(request):
    pytitionuser = get_session_user(request)

    if request.method != "POST":
        return HttpResponseForbidden()

    file = request.FILES.get('file', '')
    if file == '':
        return HttpResponseForbidden()

    storage = FileSystemStorage()
    path = os.path.join(storage.location, pytitionuser.username, file.name)
    name = storage._save(path, file)
    newrelpath = os.path.relpath(name, storage.location)

    return JsonResponse({'location': storage.base_url + newrelpath})


# /transfer_petition/<int:petition_id>
# Transfer a petition to another org or user
@login_required
def transfer_petition(request, petition_id):
    pytitionuser = get_session_user(request)
    try:
        petition = petition_from_id(petition_id)
    except:
        messages.error(request, _("This petition does not exist."))
        return redirect("user_dashboard")

    ctx = {'user': pytitionuser,
           'petition': petition}

    if petition.owner_type == "org":
        org = petition.owner
        if not org.is_allowed_to(pytitionuser, "can_modify_permissions"):
            messages.error(request, _("You don't have the permission to transfer a petition from Organization '{}'"
                                      .format(petition.owner)))
            return redirect("org_dashboard", petition.owner)
    elif petition.owner_type == "user" and petition.user != pytitionuser:
        messages.error(request, _("You don't have the permission to transfer this petition"))
        return redirect("user_dashboard")

    if petition.owner_type == "org":
        ctx['base_template'] = 'petition/org_base.html'
        ctx['org'] = petition.owner
    else:
        ctx['base_template'] = 'petition/user_base.html'

    if request.method == "GET":
        return render(request, "petition/transfer_petition.html", ctx)

    if request.method == "POST":
        owner_type = request.POST.get('new_owner_type', '')
        new_owner_name = request.POST.get('new_owner_name', '')
        org = None
        user = None
        notFound = False
        if owner_type == '' or new_owner_name == '':
            messages.error(request, _("Incorrect request, something went wrong."))
            return redirect(request, "petition/transfer_petition.html", ctx)
        if owner_type == "org":
            try:
                org = Organization.objects.get(slugname=new_owner_name)
            except:
                notFound = True
        if owner_type == "user":
            if settings.DISABLE_USER_PETITION:
                messages.error(request, _("Users are not allowed to transfer petitions to organizations on this instance."))
                return redirect("user_dashboard")
            try:
                user = PytitionUser.objects.get(user__username=new_owner_name)
            except:
                notFound = True

        if notFound:
            messages.error(request, _("You tried to transfer a petition to a non-exiting account"))
            return redirect("transfer_petition", petition.id)

        try:
            petition.transfer_to(user, org)
            petition.unpublish() # To prevent sending an unwanted published petition to an organization.
            messages.success(request, _("Petition successfully transfered!"))
            return redirect("user_dashboard")
        except ValueError:
            messages.error(request, _("Something went wrong while transferring this petition."))
            return redirect("transfer_petition", petition.id)


@login_required
def search_users_and_orgs(request):
    query = request.GET.get('q', '')
    if query != "":
        users = PytitionUser.objects.filter(Q(user__username__contains=query) | Q(user__first_name__icontains=query) |
                                            Q(user__last_name__icontains=query)).all()
        orgs = Organization.objects.filter(name__icontains=query).all()
    else:
        users = []
        orgs = []

    result = {
        "orgs": [{'slugname': org.slugname,
                  'name': org.name} for org in orgs],
        "users": [{'username': user.user.username,
                   'firstname': user.user.first_name,
                   'lastname': user.user.last_name} for user in users]
    }
    return JsonResponse(result)


class PytitionUserCreateView(CreateView):

    def save_numbers(self, request):
        request.session['random_a'] = self.a
        request.session['random_b'] = self.b
        request.session['answer'] = self.answer

    def get_new_numbers(self):
        r = random.Random(time())
        self.a = r.choice(range(0, 100))
        self.b = r.choice(range(0, 100))
        self.answer = self.a + self.b
        self.form_class.base_fields['answer'].label = _("How much is {a} + {b}?").format(a=self.a, b=self.b)

    def __init__(self, *args, **kwargs):
        super(PytitionUserCreateView, self).__init__(*args, **kwargs)
        self.get_new_numbers()

    def get_context_data(self, **kwargs):
        self.save_numbers(self.request)
        return super(PytitionUserCreateView, self).get_context_data(**kwargs)

    def get_form_kwargs(self):
        kwargs = super(PytitionUserCreateView, self).get_form_kwargs()
        kwargs.update({
            'request': self.request
        })
        return kwargs

    def form_valid(self, form):
        form.send_success_email()
        return super().form_valid(form)
