import requests

from fleece.httperror import HTTPError

TOKEN_URL_FMT = "https://identity.api.rackspacecloud.com/v2.0/tokens/{token}"  # nosec


def authenticate():
    def wrap(fxn):
        """Return a decorated callable."""

        def wrapped(*args, **kwargs):
            """Validate token and return auth context."""
            if not kwargs.get("token"):
                raise HTTPError(status=401)
            userinfo = validate(kwargs["token"])
            if "userinfo" in kwargs:
                kwargs["userinfo"] = userinfo
            return fxn(*args, **kwargs)

        return wrapped

    return wrap


def validate(token):
    """Validate token and return auth context."""
    token_url = TOKEN_URL_FMT.format(token=token)
    headers = {
        "x-auth-token": token,
        "accept": "application/json",
    }
    resp = requests.get(token_url, headers=headers)

    if not resp.status_code == 200:
        raise HTTPError(status=401)
    return resp.json()
