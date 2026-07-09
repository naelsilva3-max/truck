import re

from django.contrib.auth.forms import AuthenticationForm

from accounts.models import UserProfile


class CPFOrUsernameAuthenticationForm(AuthenticationForm):
    """Login form that authenticates by CPF by default.

    A hidden `login_mode` field (rendered by the template) tells this form
    whether the `username` input should be interpreted as a CPF (default) or
    as a literal username — the login page lets the user switch to username
    mode after a failed CPF attempt.
    """

    def clean(self):
        mode = self.data.get('login_mode', 'cpf')
        login_input = self.cleaned_data.get('username')

        if login_input and mode != 'username':
            digits = re.sub(r'\D', '', login_input)
            profile = UserProfile.objects.select_related('user').filter(cpf=digits).first()
            if profile:
                self.cleaned_data['username'] = profile.user.username

        return super().clean()
