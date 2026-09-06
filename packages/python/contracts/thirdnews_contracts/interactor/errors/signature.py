from .base import ContractError


class SignatureError(ContractError, ValueError):
    pass
