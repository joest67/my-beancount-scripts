#!/bin/env python


class BaseBizException(BaseException):
    def __init__(self, msg):
        super(BaseBizException, self).__init__(msg)


class NotSuitableImporterException(BaseBizException):

    def __init__(self, msg):
        super(NotSuitableImporterException, self).__init__(msg)
