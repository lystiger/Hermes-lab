class SprintRunnerError(Exception):
    """Fail-fast error with a stable machine-readable status code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message
