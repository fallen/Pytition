from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from petition.models import Organization, Petition, PytitionUser, SlugModel, Signature, Permission


class PetitionTest(TestCase):
    def setUp(self):
        """
        Creates a new organization for this user.

        Args:
            self: (todo): write your description
        """
        User = get_user_model()
        u = User.objects.create_user('julia', password='julia')
        org = Organization.objects.create(name="RAP")

    def test_createUserPetition(self):
        """
        Creates a new user.

        Args:
            self: (todo): write your description
        """
        self.assertEqual(Petition.objects.count(), 0)
        pu = PytitionUser.objects.get(user__username='julia')
        Petition.objects.create(title="Petition", user=pu)
        self.assertEqual(Petition.objects.count(), 1)

    def test_createOrgPetition(self):
        """
        Create a new icalculate a new organization.

        Args:
            self: (todo): write your description
        """
        self.assertEqual(Petition.objects.count(), 0)
        org = Organization.objects.first()
        Petition.objects.create(title="Petition", org=org)
        self.assertEqual(Petition.objects.count(), 1)

    def test_createPetitionRefused(self):
        """
        Creates a new user for the given user.

        Args:
            self: (todo): write your description
        """
        org = Organization.objects.first()
        pu = PytitionUser.objects.get(user__username='julia')
        self.assertEqual(Petition.objects.count(), 0)
        self.assertRaises(Exception, Petition.objects.create, title="Petition")
        self.assertEqual(Petition.objects.count(), 0)
        self.assertRaises(Exception, Petition.objects.create, title="Petition", user=pu, org=org)
        self.assertEqual(Petition.objects.count(), 0)

    def test_owner_type(self):
        """
        Create a new owner of owner.

        Args:
            self: (todo): write your description
        """
        org = Organization.objects.first()
        pu = PytitionUser.objects.get(user__username='julia')
        p1 = Petition.objects.create(title="Petition", org=org)
        self.assertEqual('org', p1.owner_type)
        p2 = Petition.objects.create(title="Petition", user=pu)
        self.assertEqual('user', p2.owner_type)

    def test_Petition_url(self):
        """
        Test if the user has a dict with the database.

        Args:
            self: (todo): write your description
        """
        # If there is no slug, returns detail
        pu = PytitionUser.objects.get(user__username='julia')
        p = Petition.objects.create(title="Petition", user=pu)
        self.assertEqual(p.url, reverse('slug_show_petition', args=[pu.username, 'petition']))
        # This should never happen but testing just in case
        s = SlugModel.objects.first()
        s.delete()
        self.assertEqual(p.url, reverse('detail', args=[p.id]))
        # Create a slug
        #p.add_slug('foobar')

    def test_PetitionDelete(self):
        """
        Deletes a user from the database.

        Args:
            self: (todo): write your description
        """
        # Deleting a petition should delete related slugs and signatures
        pu = PytitionUser.objects.get(user__username='julia')
        p = Petition.objects.create(title="Petition", user=pu)
        self.assertEqual(Petition.objects.count(), 1)
        self.assertEqual(SlugModel.objects.count(), 1)
        p.delete()
        self.assertEqual(PytitionUser.objects.count(), 1)
        self.assertEqual(Petition.objects.count(), 0)
        self.assertEqual(SlugModel.objects.count(), 0)

    def testPetitionPublish(self):
        """
        Test if a user has already been published.

        Args:
            self: (todo): write your description
        """
        pu = PytitionUser.objects.get(user__username='julia')
        p = Petition.objects.create(title="Petition", user=pu)
        self.assertEqual(p.published, False)
        p.publish()
        self.assertEqual(p.published, True)
        p.unpublish()
        self.assertEqual(p.published, False)

    def test_autocreation_salt(self):
        """
        Test if the autocreation is enabled.

        Args:
            self: (todo): write your description
        """
        pu = PytitionUser.objects.get(user__username='julia')
        p = Petition.objects.create(title="Petition", user=pu)
        self.assertIsNotNone(p.salt)

    def test_is_allowed_edit(self):
        """
        Checks if a user is allowed to edit an issue.

        Args:
            self: (todo): write your description
        """
        # if the petition belong to the user, yes
        pu = PytitionUser.objects.get(user__username='julia')
        p = Petition.objects.create(title="Petition", user=pu)
        self.assertEqual(p.is_allowed_to_edit(pu), True)
        # else no
        User = get_user_model()
        u = User.objects.create_user('john', password='john')
        john = PytitionUser.objects.get(user__username='john')
        self.assertEqual(p.is_allowed_to_edit(john), False)
        # Now with org petitions
        rap = Organization.objects.get(name="RAP")
        p2 = Petition.objects.create(title="Petition2", org=rap)
        self.assertEqual(p2.is_allowed_to_edit(john), False)
        # If the user has no rights
        rap.members.add(john)
        self.assertEqual(p2.is_allowed_to_edit(john), True)
        perm = Permission.objects.get(organization=rap, user=john)
        perm.can_modify_petitions = False
        perm.save()
        self.assertEqual(p2.is_allowed_to_edit(john), False)

    def test_paper_signatures(self):
        """
        Create a new signatures.

        Args:
            self: (todo): write your description
        """
        pu = PytitionUser.objects.get(user__username='julia')
        p = Petition.objects.create(title="Petition", user=pu)
        p.paper_signatures_enabled = True
        p.paper_signatures = 42
        p.save()
        self.assertEqual(p.get_signature_number(), 42)
        p.paper_signatures_enabled = False
        p.save()
        self.assertEqual(p.get_signature_number(), 0)
        s = Signature.objects.create(first_name="User", last_name="User", email="user@example.org", petition=p)
        self.assertEqual(p.get_signature_number(), 1)
        p.paper_signatures_enabled = True
        p.save()
        self.assertEqual(p.get_signature_number(), 43)