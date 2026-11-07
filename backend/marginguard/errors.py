class DomainError(Exception):
    """Stable, client-safe product error. Never include credentials or raw provider bodies."""

    def __init__(self, code: str, message: str, status: int = 400, **details):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details
