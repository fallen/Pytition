from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from petition.models import Organization, Petition, PytitionUser, Permission
from .utils import add_default_data

import os

class EditPetitionViewTest(TestCase):
    """Test index view"""
    @classmethod
    def setUpTestData(cls):
        """
        Sets the default data set.

        Args:
            cls: (todo): write your description
        """
        add_default_data()

    def login(self, name):
        """
        Authenticate with the server.

        Args:
            self: (todo): write your description
            name: (str): write your description
        """
        self.client.login(username=name, password=name)
        self.pu = PytitionUser.objects.get(user__username=name)
        return self.pu

    def logout(self):
        """
        Logout of the client.

        Args:
            self: (todo): write your description
        """
        self.client.logout()

    def tearDown(self):
        """
        Tear down the next callable.

        Args:
            self: (todo): write your description
        """
        # Clean up run after every test method.
        pass

    def test_edit_404(self):
        """ Non-existent petition id : should return 404 """
        self.login("julia")
        response = self.client.get(reverse("edit_petition", args=[1000]))
        self.assertEqual(response.status_code, 404)

    def test_edit_200(self):
        """ edit your own petition while being logged-in """
        self.login('julia')
        petition = self.pu.petition_set.first()
        response = self.client.get(reverse("edit_petition", args=[petition.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['petition'], petition)
        self.assertTemplateUsed(response, "petition/edit_petition.html")

    def test_edit_loggedout(self):
        """ edit your own petition while being logged out """
        self.login('julia')
        petition = self.pu.petition_set.first()
        self.logout()
        response = self.client.get(reverse("edit_petition", args=[petition.id]), follow=True)
        self.assertRedirects(response, reverse("login")+"?next="+reverse("edit_petition", args=[petition.id]))

    def test_edit_notYourOwnPetition(self):
        """ editing somebody else's petition """
        self.login('julia')
        max = PytitionUser.objects.get(user__username="max")
        petition = max.petition_set.first()
        response = self.client.get(reverse("edit_petition", args=[petition.id]), follow=True)
        self.assertRedirects(response, reverse("user_dashboard"))
        self.assertTemplateUsed(response, "petition/user_dashboard.html")

    def test_edit_notInOrg(self):
        """ editing a petition owned by an Organization the logged-in user is *NOT* part of """
        self.login('sarah')
        attac = Organization.objects.get(name='Les Amis de la Terre')
        petition = attac.petition_set.first()
        response = self.client.get(reverse("edit_petition", args=[petition.id]), follow=True)
        self.assertRedirects(response, reverse("user_dashboard"))
        self.assertTemplateUsed(response, "petition/user_dashboard.html")

    def test_edit_InOrgButNoEditPermission(self):
        """
        editing a petition owned by an Organization the logged-in user is part of
        but without the can_modify_petitions permission
        """
        max = self.login('max')
        at = Organization.objects.get(name='Les Amis de la Terre')
        perm = Permission.objects.get(organization=at, user=max)
        perm.can_modify_petitions = False
        perm.save()
        petition = at.petition_set.first()
        response = self.client.get(reverse("edit_petition", args=[petition.id]), follow=True)
        self.assertRedirects(response, reverse("user_dashboard"))

    def test_edit_InOrgWithEditPerm(self):
        """
        editing a petition owned by an Organization the logged-in user is part of
        *AND* with the can_modify_petitions permission
        """
        self.login('julia')
        at = Organization.objects.get(name='Les Amis de la Terre')
        petition = at.petition_set.first()
        response = self.client.get(reverse("edit_petition", args=[petition.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['petition'], petition)
        self.assertTemplateUsed(response, "petition/edit_petition.html")

    def test_edit_post_content_form(self):
        """
        Update the post form.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        content_form_data = {
            'content_form_submitted': 'yes',
            'title': 'toto',
            'text': 'tata',
            'side_text': 'titi',
            'footer_text': 'tutu',
            'footer_links': 'tyty',
            'sign_form_footer': 'lorem',
            'target': 4242,
            'paper_signatures': 0
        }
        # For an org petition
        p = Petition.objects.create(title="My Petition", org=org)
        response = self.client.post(reverse("edit_petition", args=[p.id]), content_form_data)
        self.assertEqual(response.status_code, 200)
        p.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['content_form'].is_valid(), True)
        self.assertEquals(response.context['content_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], True)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        self.assertEquals(p.get_signature_number(), 0)

        # For a user petition
        p2 = Petition.objects.create(title="My Petition 2", user=julia)
        response = self.client.post(reverse("edit_petition", args=[p2.id]), content_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        p2.refresh_from_db()
        for key, value in content_form_data.items():
            if key == "content_form_submitted":
                continue
            self.assertEquals(getattr(p2, key), value)
            self.assertEquals(getattr(p, key), value)
        self.assertEquals(response.context['content_form'].is_valid(), True)
        self.assertEquals(response.context['content_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], True)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        self.assertEquals(p2.get_signature_number(), 0)

        for key, value in content_form_data.items():
            if key == "content_form_submitted":
                continue
            self.assertEquals(getattr(p, key), value)
            self.assertEquals(getattr(p2, key), value)

    def test_edit_post_content_form_papersigntest(self):
        """
        Update the organization form.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        content_form_data = {
            'content_form_submitted': 'yes',
            'title': 'toto',
            'text': 'tata',
            'side_text': 'titi',
            'footer_text': 'tutu',
            'footer_links': 'tyty',
            'sign_form_footer': 'lorem',
            'target': 4242,
            'paper_signatures': 42
        }
        # For an org petition
        p = Petition.objects.create(title="My Petition", org=org)
        response = self.client.post(reverse("edit_petition", args=[p.id]), content_form_data)
        self.assertEqual(response.status_code, 200)
        p.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['content_form'].is_valid(), True)
        self.assertEquals(response.context['content_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], True)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        self.assertEquals(p.get_signature_number(), 0) # paper_signatures_enabled is False

        # For a user petition
        p2 = Petition.objects.create(title="My Petition 2", user=julia)
        response = self.client.post(reverse("edit_petition", args=[p2.id]), content_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        p2.refresh_from_db()
        for key, value in content_form_data.items():
            if key == "content_form_submitted":
                continue
            self.assertEquals(getattr(p2, key), value)
            self.assertEquals(getattr(p, key), value)
        self.assertEquals(response.context['content_form'].is_valid(), True)
        self.assertEquals(response.context['content_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], True)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        self.assertEquals(p2.get_signature_number(), 0) # paper_signatures_enabled is False

        for key, value in content_form_data.items():
            if key == "content_form_submitted":
                continue
            self.assertEquals(getattr(p, key), value)
            self.assertEquals(getattr(p2, key), value)

    def test_edit_petition_POST_email_form(self):
        """
        Edit a new organization email.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        email_form_data = {
            'email_form_submitted': 'yes',
            'confirmation_email_reply': 'toto@tata.com',
        }
        # For an org template
        p = Petition.objects.create(title="My petition", org=org)
        response = self.client.post(reverse("edit_petition", args=[p.id]), email_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['email_form'].is_valid(), True)
        self.assertEquals(response.context['email_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], True)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        p.refresh_from_db()

        # For an user template
        p2 = Petition.objects.create(title="My petition 2", user=julia)
        response = self.client.post(reverse("edit_petition", args=[p2.id]), email_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['email_form'].is_valid(), True)
        self.assertEquals(response.context['email_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], True)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        p2.refresh_from_db()

        for key, value in email_form_data.items():
            if key == "email_form_submitted":
                continue
            self.assertEquals(getattr(p2, key), value)
            self.assertEquals(getattr(p, key), value)

    def test_edit_petition_POST_social_network_form(self):
        """
        Test if organization

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        thispath = os.path.join(os.path.dirname(__file__))
        logo = os.path.join(thispath, '..', '..', '..', 'logo.png')
        fp = open(logo, "rb")
        social_network_form_data = {
            'social_network_form_submitted': 'yes',
            'twitter_description': 'This is my twitter desc!',
            'org_twitter_handle': '@Rap_Asso',
            'twitter_image': fp
        }

        # For an org template
        p = Petition.objects.create(title="My petition", org=org)
        social_network_form_data.update({'twitter_image': fp})
        response = self.client.post(reverse("edit_petition", args=[p.id]),
                                    social_network_form_data)
        fp.close()
        self.assertEqual(response.status_code, 200)
        p.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['social_network_form'].is_valid(), True)
        self.assertEquals(response.context['social_network_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], True)
        self.assertEquals(response.context['newsletter_form_submitted'], False)

        fp = open(logo, "rb")
        social_network_form_data.update({'twitter_image': fp})
        # For an user template
        p2 = Petition.objects.create(title="My petition 2", user=julia)
        response2 = self.client.post(reverse("edit_petition", args=[p2.id]), social_network_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        p2.refresh_from_db()

        for key, value in social_network_form_data.items():
            if key == "social_network_form_submitted":
                continue
            if key == "twitter_image":
                self.assertTrue(p.twitter_image.startswith(settings.MEDIA_URL))
                self.assertTrue(p2.twitter_image.startswith(settings.MEDIA_URL))
                petition_path = settings.MEDIA_ROOT + '/' + p.twitter_image[len(settings.MEDIA_URL):]
                petition2_path = settings.MEDIA_ROOT + '/' + p2.twitter_image[len(settings.MEDIA_URL):]
                with open(petition_path, "rb") as img:
                    with open(petition2_path, "rb") as img2:
                        with open(logo, "rb") as logofp:
                            logocontent = logofp.read()
                            self.assertEquals(img.read(), logocontent)
                            self.assertEquals(img2.read(), logocontent)
                continue
            self.assertEquals(getattr(p2, key), value)
            self.assertEquals(getattr(p, key), value)
        self.assertEquals(response2.context['social_network_form'].is_valid(), True)
        self.assertEquals(response2.context['social_network_form'].is_bound, True)
        self.assertEquals(response2.context['content_form_submitted'], False)
        self.assertEquals(response2.context['email_form_submitted'], False)
        self.assertEquals(response2.context['social_network_form_submitted'], True)
        self.assertEquals(response2.context['newsletter_form_submitted'], False)

    def test_edit_template_POST_newsletter_form(self):
        """
        Edit template for edit template.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        newsletter_form_data = {
            'newsletter_form_submitted': 'yes',
            'has_newsletter': 'on',
            'newsletter_subscribe_http_data': 'blah',
            'newsletter_subscribe_http_mailfield': 'blih',
            'newsletter_subscribe_http_mailfield': 'bluh',
            'newsletter_subscribe_mail_subject': 'bloh',
            'newsletter_subscribe_mail_from': 'toto@titi.com',
            'newsletter_subscribe_mail_to': 'titi@toto.com',
            'newsletter_subscribe_method': 'POST',
            'newsletter_subscribe_mail_smtp_host': 'localhost',
            'newsletter_subscribe_mail_smtp_port': 1234,
            'newsletter_subscribe_mail_smtp_user': 'root',
            'newsletter_subscribe_mail_smtp_password': 'rootpassword',
            'newsletter_subscribe_mail_smtp_tls': 'on',
            'newsletter_subscribe_mail_smtp_starttls': '',
        }
        # For an org template
        p = Petition.objects.create(title="My petition", org=org)
        response = self.client.post(reverse("edit_petition", args=[p.id]), newsletter_form_data)
        self.assertEqual(response.status_code, 200)
        p.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['newsletter_form'].is_valid(), True)
        self.assertEquals(response.context['newsletter_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], True)

        # For an user template
        p2 = Petition.objects.create(title="My petition 2", user=julia)
        response2 = self.client.post(reverse("edit_petition", args=[p2.id]), newsletter_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        p2.refresh_from_db()

        newsletter_form_data['has_newsletter'] = True
        newsletter_form_data['newsletter_subscribe_mail_smtp_tls'] = True
        newsletter_form_data['newsletter_subscribe_mail_smtp_starttls'] = False
        for key, value in newsletter_form_data.items():
            if key == "newsletter_form_submitted":
                continue
            self.assertEquals(getattr(p2, key), value)
            self.assertEquals(getattr(p, key), value)
        self.assertEquals(response2.context['newsletter_form'].is_valid(), True)
        self.assertEquals(response2.context['newsletter_form'].is_bound, True)
        self.assertEquals(response2.context['content_form_submitted'], False)
        self.assertEquals(response2.context['email_form_submitted'], False)
        self.assertEquals(response2.context['social_network_form_submitted'], False)
        self.assertEquals(response2.context['newsletter_form_submitted'], True)

    def test_edit_template_POST_style_form(self):
        """
        Test for edit template.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        style_form_data = {
            'style_form_submitted': 'yes',
            'bgcolor': '33ccff',
            'linear_gradient_direction': 'to right',
            'gradient_from': '0000ff',
            'gradient_to': 'ff0000',
        }
        # For an org template
        p = Petition.objects.create(title="My petition", org=org)
        response = self.client.post(reverse("edit_petition", args=[p.id]), style_form_data)
        self.assertEqual(response.status_code, 200)
        p.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        self.assertEquals(response.context['style_form'].is_valid(), True)
        self.assertEquals(response.context['style_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        self.assertEquals(response.context['style_form_submitted'], True)

        # For an user template
        p2 = Petition.objects.create(title="My petition 2", user=julia)
        response2 = self.client.post(reverse("edit_petition", args=[p2.id]), style_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_petition.html")
        p2.refresh_from_db()

        style_form_data['bgcolor'] = '#' + style_form_data['bgcolor']
        style_form_data['gradient_from'] = '#' + style_form_data['gradient_from']
        style_form_data['gradient_to'] = '#' + style_form_data['gradient_to']
        for key, value in style_form_data.items():
            if key == "style_form_submitted":
                continue
            self.assertEquals(getattr(p2, key), value)
            self.assertEquals(getattr(p, key), value)
        self.assertEquals(response.context['style_form'].is_valid(), True)
        self.assertEquals(response.context['style_form'].is_bound, True)
        self.assertEquals(response2.context['content_form_submitted'], False)
        self.assertEquals(response2.context['email_form_submitted'], False)
        self.assertEquals(response2.context['social_network_form_submitted'], False)
        self.assertEquals(response2.context['newsletter_form_submitted'], False)
        self.assertEquals(response.context['style_form_submitted'], True)
