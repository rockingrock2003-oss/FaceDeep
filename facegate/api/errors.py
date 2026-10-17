"""Rekognition error types, serialised the way the AWS SDKs expect.

AWS JSON 1.1 errors carry the type in ``__type`` (and the
``x-amzn-ErrorType`` header). botocore turns that into
``ClientError.response["Error"]["Code"]`` and the SDKs raise the matching
modelled exception, e.g. ``client.exceptions.ResourceNotFoundException`` -
so the attendance app's existing error handling keeps working.
"""

from __future__ import annotations


class RekognitionError(Exception):
    status = 400
    code = "InternalServerError"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _make(name: str, status: int = 400) -> type[RekognitionError]:
    return type(name, (RekognitionError,), {"code": name, "status": status})


AccessDeniedException = _make("AccessDeniedException")
ImageTooLargeException = _make("ImageTooLargeException")
InternalServerError = _make("InternalServerError", 500)
InvalidImageFormatException = _make("InvalidImageFormatException")
InvalidParameterException = _make("InvalidParameterException")
InvalidPaginationTokenException = _make("InvalidPaginationTokenException")
InvalidS3ObjectException = _make("InvalidS3ObjectException")
ProvisionedThroughputExceededException = _make("ProvisionedThroughputExceededException")
ResourceAlreadyExistsException = _make("ResourceAlreadyExistsException")
ResourceNotFoundException = _make("ResourceNotFoundException")
ServiceQuotaExceededException = _make("ServiceQuotaExceededException")
SessionNotFoundException = _make("SessionNotFoundException")
ThrottlingException = _make("ThrottlingException")
ValidationException = _make("ValidationException")
ConflictException = _make("ConflictException")
UnknownOperationException = _make("UnknownOperationException")

NO_FACES_MESSAGE = "There are no faces in the image. Should be at least 1."
