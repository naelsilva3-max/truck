from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Token generator for email verification links.

    Includes the profile's email_verified flag in the hash so a token
    becomes invalid once the email has already been confirmed.
    """

    def _make_hash_value(self, user, timestamp):
        profile = getattr(user, 'profile', None)
        verified = profile.email_verified if profile else False
        return f'{user.pk}{user.email}{verified}{timestamp}'


email_verification_token = EmailVerificationTokenGenerator()
