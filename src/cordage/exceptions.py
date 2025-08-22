class CordageError(Exception):
    pass


class MissingValueError(CordageError):
    pass

class UnexpectedDataError(CordageError):
    pass

class InvalidValueError(CordageError):
    pass
