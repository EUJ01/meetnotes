"""meetnotes: meeting recording -> transcript -> grouped to-do update file -> Telegram / Drive."""

__version__ = "0.1.0"


class Fail(Exception):
    """A step failed in a way the user can fix. code 1 = a step failed, 2 = usage or config error."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code
