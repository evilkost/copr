# coding: utf-8
import json

from logging import getLogger

from requests import request, ConnectionError

from ..util import UnicodeMixin

log = getLogger(__name__)


class RequestError(Exception, UnicodeMixin):
    def __init__(self, msg, url, request_kwargs=None, response=None):
        self.msg = msg
        self.url = url
        self.request_kwargs = request_kwargs or dict()
        if "auth" in self.request_kwargs:
            self.request_kwargs["auth"] = "<hidden>"
        self.response = response

    @property
    def response_json(self):
        if self.response is None:
            raise ValueError("No response")
        try:
            result = json.loads(self.response.text)
        except (ValueError, AttributeError):
            raise ValueError("Malformed response, couldn't get json content")

        return result

    def __unicode__(self):
        res = "Error occurred while accessing {}: {}\n".format(
            self.url, self.msg)
        if self.response is not None:
            res += "code {}: {}\n".format(self.response.status_code, self.response_json["message"])
        return res


class NetworkError(RequestError):
    def __init__(self, url, request_kwargs, requests_error):
        self.requests_error = requests_error
        super(NetworkError, self).__init__(
            u"Connection error", url, request_kwargs)

    def __unicode__(self):
        res = super(NetworkError, self).__unicode__()
        res += u"Original error: {}\n".format(self.requests_error)


class AuthError(RequestError):
    def __init__(self, url, request_kwargs, response):
        super(AuthError, self).__init__("Authorization failed",
                                        url, request_kwargs, response)


class ResponseWrapper(object):

    def __init__(self, response):
        """
        :raises ValueError: when fails to deserialize json content
        """
        self.response = response
        if response.status_code != 204 and response.content:
            self.json = json.loads(response.content)
        else:
            self.json = None

    @property
    def status_code(self):
        return self.response.status_code

    @property
    def headers(self):
        return self.response.headers


class NetClient(object):
    """
    Abstraction around python-requests

    :param unicode login: login for BasicAuth
    :param unicode password: password for BasicAuth
    """

    def __init__(self, login=None, password=None):
        self.login = login
        self.token = password

    def request(self, url, method=None, query_params=None, data=None, do_auth=False):

        if method is None:
            method = "get"
        elif method.lower() not in ["get", "post", "delete", "put"]:
            raise RequestError("Method {} not allowed".format(method), url)

        kwargs = {}
        if do_auth:
            if self.login is None or self.token is None:
                raise RequestError("Credentionals for BasicAuth "
                                   "not set, request aborted",
                                   url, kwargs)
            kwargs["auth"] = (self.login, self.token)
        if query_params:
            kwargs["params"] = query_params
        if data:
            kwargs["data"] = data

        try:
            response = request(
                method=method.upper(),
                url=url,
                **kwargs
            )
            log.debug("raw response: {0}".format(response.text))
        except ConnectionError as e:
            raise NetworkError(url, kwargs, e)

        if response.status_code == 403:
            raise AuthError(url, kwargs, response)

        if response.status_code > 399:
            raise RequestError("", url, kwargs, response)

        try:
            return ResponseWrapper(response)
        except ValueError:
            raise RequestError("Failed to parse server response", url, kwargs, response)
