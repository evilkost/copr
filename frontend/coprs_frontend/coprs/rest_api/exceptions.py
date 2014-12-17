# coding: utf-8
import six


class ApiError(Exception):
    def __init__(self, code, data, **kwargs):
        super(ApiError, self).__init__(**kwargs)

        self.code = code
        self.data = data

    def __str__(self):
        return str(self.data)

    if six.PY2:
        def __unicode__(self):
            return unicode(self.data)


class ObjectNotFoundError(ApiError):
    def __init__(self, data, **kwargs):
        super(ObjectNotFoundError, self).__init__(404, data, **kwargs)


class MalformedRequest(ApiError):
    def __init__(self, data=None, **kwargs):
        super(MalformedRequest, self).__init__(400, data, **kwargs)
