"""
Custom exceptions for the biometric module.
"""


class BiometricDeviceNotFoundError(Exception):
    """
    Raised when the ZKTeco ZK9500 biometric device cannot be found or
    accessed.  This covers both the case where the device is physically
    absent and the case where the pyzkfp library is not installed.
    """

    def __init__(self, message: str = "Biometric device not found or not accessible."):
        super().__init__(message)


class BiometricNotConnectedError(Exception):
    """
    Raised when an operation that requires an active device connection is
    attempted while the service is in a disconnected state.
    """

    def __init__(
        self, message: str = "No biometric device is currently connected."
    ):
        super().__init__(message)
