class DuplicateScanError(Exception):
    """
    Raised when a scan for an employee arrives before their cooldown window
    (AttendanceService.SCAN_COOLDOWN) since their last IN/OUT registration
    has elapsed — guards against accidental double-taps at the reader.
    """

    def __init__(self, employee_name: str, retry_after_seconds: int) -> None:
        self.employee_name = employee_name
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"{employee_name}: aguarde {retry_after_seconds}s antes de bater ponto novamente."
        )
