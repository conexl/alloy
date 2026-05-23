"""Custom exceptions for report service."""


class RFQNotFoundException(Exception):
    """RFQ not found error."""

    pass


class NoQuotesException(Exception):
    """No quotes for RFQ error."""

    pass
