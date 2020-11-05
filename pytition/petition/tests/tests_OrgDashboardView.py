from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from petition.models import Organization, Petition, PytitionUser
from .utils import add_default_data


class OrgDashboardViewTest(TestCase):
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

    def test_orgNotExist(self):
        """
        This method to github.

        Args:
            self: (todo): write your description
        """
        org_name = "org that does not exist"
        orgslugname = slugify(org_name)
        self.login("julia")
        response = self.client.get(reverse("org_dashboard", args=[orgslugname]), follow=True)
        self.assertRedirects(response, reverse("user_dashboard"))
        self.assertTemplateUsed(response, "petition/user_dashboard.html")

    def test_NotAMember(self):
        """
        Test if user is logged in.

        Args:
            self: (todo): write your description
        """
        org_name = "Attac"
        orgslugname = slugify(org_name)
        self.login("julia")
        response = self.client.get(reverse("org_dashboard", args=[orgslugname]), follow=True)
        self.assertRedirects(response, reverse("user_dashboard"))
        self.assertTemplateUsed(response, "petition/user_dashboard.html")

    def test_NotLoggedIn(self):
        """
        This is the user

        Args:
            self: (todo): write your description
        """
        self.logout()
        org_name = "RAP"
        orgslugname = slugify(org_name)
        response = self.client.get(reverse("org_dashboard", args=[orgslugname]), follow=True)
        self.assertRedirects(response, reverse("login")+"?next="+reverse("org_dashboard", args=[orgslugname]))
        self.assertTemplateUsed(response, "registration/login.html")
        self.assertTemplateUsed(response, "layouts/base.html")

    def test_OrgOK1(self):
        """
        This is the organization that is_Org.

        Args:
            self: (todo): write your description
        """
        org_name = "Attac"
        orgslugname = slugify(org_name)
        john = self.login("john")
        org = Organization.objects.get(name=org_name)
        response = self.client.get(reverse("org_dashboard", args=[orgslugname]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/org_dashboard.html")
        petitions = response.context['petitions'].all()
        self.assertEqual(len(petitions), 4)
        self.assertEqual(response.context['user'], john)

    def test_OrgOK2(self):
        """
        Test if the organization is enabled.

        Args:
            self: (todo): write your description
        """
        org_name = "RAP"
        orgslugname = slugify(org_name)
        julia = self.login("julia")
        response = self.client.get(reverse("org_dashboard", args=[orgslugname]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/org_dashboard.html")
        petitions = response.context['petitions'].all()
        self.assertEqual(len(petitions), 0)
        self.assertEqual(response.context['user'], julia)

    def test_OrgOK3(self):
        """
        Respond to github organization is enabled.

        Args:
            self: (todo): write your description
        """
        org_name = "Les Amis de la Terre"
        orgslugname = slugify(org_name)
        max = self.login("max")
        response = self.client.get(reverse("org_dashboard", args=[orgslugname]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "petition/org_dashboard.html")
        petitions = response.context['petitions'].all()
        self.assertEqual(len(petitions), 1)
        self.assertEqual(response.context['user'], max)
