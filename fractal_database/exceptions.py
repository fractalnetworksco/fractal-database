class StaleObjectException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(
            "Object version was updated by another process. Reload object and try again."
        )
