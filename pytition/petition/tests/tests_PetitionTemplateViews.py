from django.test import TestCase
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model

from petition.models import Organization, Petition, PytitionUser, PetitionTemplate
from petition.models import Permission
from .utils import add_default_data

import os

class PetitionViewTest(TestCase):
    """Test index view"""
    @classmethod
    def setUpTestData(cls):
        """
        Sets the default data set.

        Args:
            cls: (todo): write your description
        """
        add_default_data()

    def tearDown(self):
        """
        Tear down the next callable.

        Args:
            self: (todo): write your description
        """
        # Clean up run after every test method.
        pass

    def login(self, name, password=None):
        """
        Login with the given credentials.

        Args:
            self: (todo): write your description
            name: (str): write your description
            password: (str): write your description
        """
        self.client.login(username=name, password=password if password else name)
        self.pu = PytitionUser.objects.get(user__username=name)
        return self.pu

    def logout(self):
        """
        Logout of the client.

        Args:
            self: (todo): write your description
        """
        self.client.logout()

    def test_org_new_template_get(self):
        """
        Get a new organization.

        Args:
            self: (todo): write your description
        """
        # GET request just shows the page
        # Not logged
        org = Organization.objects.get(name='RAP')
        response = self.client.get(reverse("org_new_template", args=[org.slugname]))
        self.assertEqual(response.status_code, 302)
        # Logged
        self.login('julia')
        response = self.client.get(reverse("org_new_template", args=[org.slugname]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/new_template.html")

    def test_org_new_template_post(self):
        """
        Creates a new organization.

        Args:
            self: (todo): write your description
        """
        self.login('julia')
        org = Organization.objects.get(name='RAP')
        self.assertEqual(org.petitiontemplate_set.count(), 0)
        data = {'template_name': 'This is a default template'}
        response = self.client.post(reverse("org_new_template", args=[org.slugname]), data)
        self.assertEqual(org.petitiontemplate_set.count(), 1)
        self.assertEqual(response.status_code, 302)
        pt = org.petitiontemplate_set.first()
        self.assertRedirects(response, reverse("edit_template", args=[pt.id]))

    def test_user_new_template_post(self):
        """
        Create a new login.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        data = {'template_name': 'This is a default template'}
        response = self.client.post(reverse("user_new_template"), data)
        self.assertEqual(julia.petitiontemplate_set.count(), 1)
        self.assertEqual(response.status_code, 302)
        pt = julia.petitiontemplate_set.first()
        self.assertRedirects(response, reverse("edit_template", args=[pt.id]))

    def test_user_new_template_get(self):
        """
        Test for new login template.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        response = self.client.get(reverse("user_new_template"))
        self.assertEqual(julia.petitiontemplate_set.count(), 0)
        self.assertEqual(response.status_code, 200)

    def test_edit_template(self):
        """
        Test if the login template.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        # For an org template
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.get(reverse("edit_template", args=[pt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")
        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template", user=julia)
        response = self.client.get(reverse("edit_template", args=[pt2.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")

    def test_template_fav_toggle(self):
        """
        This method is_template in the database.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        # For an org template
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.get(reverse("template_fav_toggle", args=[pt.id]))
        self.assertEqual(response.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.default_template, pt)
        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template", user=julia)
        response = self.client.get(reverse("template_fav_toggle", args=[pt2.id]))
        self.assertEqual(response.status_code, 200)
        julia.refresh_from_db()
        self.assertEqual(julia.default_template, pt2)

    def test_template_fav_toggletwice(self):
        """
        Create a github login

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        # For an org template
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.get(reverse("template_fav_toggle", args=[pt.id]))
        self.assertEqual(response.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.default_template, pt)
        response = self.client.get(reverse("template_fav_toggle", args=[pt.id]))
        self.assertEqual(response.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.default_template, None)
        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template", user=julia)
        response = self.client.get(reverse("template_fav_toggle", args=[pt2.id]))
        self.assertEqual(response.status_code, 200)
        julia.refresh_from_db()
        self.assertEqual(julia.default_template, pt2)
        response = self.client.get(reverse("template_fav_toggle", args=[pt2.id]))
        self.assertEqual(response.status_code, 200)
        julia.refresh_from_db()
        self.assertEqual(julia.default_template, None)

    def test_org_template_delete(self):
        """
        Deletes the organization.

        Args:
            self: (todo): write your description
        """
        max = self.login('max')
        org = Organization.objects.get(name='Les Amis de la Terre')
        # For an org template
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        self.assertEqual(PetitionTemplate.objects.count(), 1)
        response = self.client.get(reverse("template_delete", args=[pt.id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PetitionTemplate.objects.count(), 1)
        # Ah yes, Max does not have access rights for that
        p = Permission.objects.get(organization=org, user=max)
        p.can_delete_templates = True
        p.save()
        response = self.client.get(reverse("template_delete", args=[pt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PetitionTemplate.objects.count(), 0)
        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template", user=max)
        self.assertEqual(PetitionTemplate.objects.count(), 1)
        response = self.client.get(reverse("template_delete", args=[pt2.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PetitionTemplate.objects.count(), 0)

    def test_edit_template_POST_content_form(self):
        """
        Handle post template.

        Args:
            self: (todo): write your description
        """
        julia = self.login('julia')
        org = Organization.objects.get(name='RAP')
        content_form_data = {
            'content_form_submitted': 1,
            'name': 'toto',
            'text': 'tata',
            'side_text': 'titi',
            'footer_text': 'tutu',
            'footer_links': 'tyty',
            'sign_form_footer': 'lorem',

        }
        # For an org template
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.post(reverse("edit_template", args=[pt.id]), content_form_data)
        self.assertEqual(response.status_code, 200)
        pt.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_template.html")
        self.assertEquals(response.context['content_form'].is_valid(), True)
        self.assertEquals(response.context['content_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], True)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)

        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template", user=julia)
        response = self.client.post(reverse("edit_template", args=[pt2.id]), content_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")
        pt2.refresh_from_db()
        for key, value in content_form_data.items():
            if key == "content_form_submitted":
                continue
            self.assertEquals(getattr(pt2, key), value)
            self.assertEquals(getattr(pt, key), value)
        self.assertEquals(response.context['content_form'].is_valid(), True)
        self.assertEquals(response.context['content_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], True)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)

    def test_edit_template_POST_email_form(self):
        """
        View for new email.

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
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.post(reverse("edit_template", args=[pt.id]), email_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")
        self.assertEquals(response.context['email_form'].is_valid(), True)
        self.assertEquals(response.context['email_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], True)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        pt.refresh_from_db()

        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template", user=julia)
        response = self.client.post(reverse("edit_template", args=[pt2.id]), email_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")
        self.assertEquals(response.context['email_form'].is_valid(), True)
        self.assertEquals(response.context['email_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], True)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], False)
        pt2.refresh_from_db()

        for key, value in email_form_data.items():
            if key == "email_form_submitted":
                continue
            self.assertEquals(getattr(pt2, key), value)
            self.assertEquals(getattr(pt, key), value)

    def test_edit_template_POST_social_network_form(self):
        """
        Formats the network template.

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
            'twitter_image': fp,
            'org_twitter_handle': '@Rap_Asso',
        }
        # For an org template
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.post(reverse("edit_template", args=[pt.id]), social_network_form_data)
        fp.close()
        self.assertEqual(response.status_code, 200)
        pt.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_template.html")
        self.assertEquals(response.context['social_network_form'].is_valid(), True)
        self.assertEquals(response.context['social_network_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], True)
        self.assertEquals(response.context['newsletter_form_submitted'], False)

        fp = open(logo, "rb")
        social_network_form_data.update({'twitter_image': fp})

        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template 2", user=julia)
        response2 = self.client.post(reverse("edit_template", args=[pt2.id]), social_network_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")
        pt2.refresh_from_db()

        for key, value in social_network_form_data.items():
            if key == "social_network_form_submitted":
                continue
            if key == "twitter_image":
                self.assertTrue(pt.twitter_image.startswith(settings.MEDIA_URL))
                self.assertTrue(pt2.twitter_image.startswith(settings.MEDIA_URL))
                petition_path = settings.MEDIA_ROOT + '/' + pt.twitter_image[len(settings.MEDIA_URL):]
                petition2_path = settings.MEDIA_ROOT + '/' + pt2.twitter_image[len(settings.MEDIA_URL):]
                with open(petition_path, "rb") as img:
                    with open(petition2_path, "rb") as img2:
                        with open(logo, "rb") as logofp:
                            logocontent = logofp.read()
                            self.assertEquals(img.read(), logocontent)
                            self.assertEquals(img2.read(), logocontent)
                continue
            self.assertEquals(getattr(pt2, key), value)
            self.assertEquals(getattr(pt, key), value)
        self.assertEquals(response2.context['social_network_form'].is_valid(), True)
        self.assertEquals(response2.context['social_network_form'].is_bound, True)
        self.assertEquals(response2.context['content_form_submitted'], False)
        self.assertEquals(response2.context['email_form_submitted'], False)
        self.assertEquals(response2.context['social_network_form_submitted'], True)
        self.assertEquals(response2.context['newsletter_form_submitted'], False)

    def test_edit_template_POST_newsletter_form(self):
        """
        Edit templates template.

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
        pt = PetitionTemplate.objects.create(name="Default template", org=org)
        response = self.client.post(reverse("edit_template", args=[pt.id]), newsletter_form_data)
        self.assertEqual(response.status_code, 200)
        pt.refresh_from_db()
        self.assertTemplateUsed(response, "petition/edit_template.html")
        self.assertEquals(response.context['newsletter_form'].is_valid(), True)
        self.assertEquals(response.context['newsletter_form'].is_bound, True)
        self.assertEquals(response.context['content_form_submitted'], False)
        self.assertEquals(response.context['email_form_submitted'], False)
        self.assertEquals(response.context['social_network_form_submitted'], False)
        self.assertEquals(response.context['newsletter_form_submitted'], True)

        # For an user template
        pt2 = PetitionTemplate.objects.create(name="Default template 2", user=julia)
        response2 = self.client.post(reverse("edit_template", args=[pt2.id]), newsletter_form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/edit_template.html")
        pt2.refresh_from_db()

        newsletter_form_data['has_newsletter'] = True
        newsletter_form_data['newsletter_subscribe_mail_smtp_tls'] = True
        newsletter_form_data['newsletter_subscribe_mail_smtp_starttls'] = False
        for key, value in newsletter_form_data.items():
            if key == "newsletter_form_submitted":
                continue
            self.assertEquals(getattr(pt2, key), value)
            self.assertEquals(getattr(pt, key), value)
        self.assertEquals(response2.context['newsletter_form'].is_valid(), True)
        self.assertEquals(response2.context['newsletter_form'].is_bound, True)
        self.assertEquals(response2.context['content_form_submitted'], False)
        self.assertEquals(response2.context['email_form_submitted'], False)
        self.assertEquals(response2.context['social_network_form_submitted'], False)
        self.assertEquals(response2.context['newsletter_form_submitted'], True)
