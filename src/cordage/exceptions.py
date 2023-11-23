class CordageError(Exception):
    pass


class MissingValueError(CordageError):
    pass


class WrongTypeError(CordageError):
    pass


class UnexpectedDataError(CordageError):
    pass
