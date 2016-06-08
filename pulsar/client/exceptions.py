"""
Pulsar client exceptions
"""


class PulsarClientTransportError(Exception):
    TIMEOUT = 'timeout'
    CONNECTION_REFUSED = 'connection_refused'
    UNKNOWN = 'unknown'

    messages = {
        TIMEOUT: 'Connection timed out',
        CONNECTION_REFUSED: 'Connection refused',
        UNKNOWN: 'Unknown transport error'
    }

    INVALID_CODE_MESSAGE = 'Unknown transport error code: %s'

    def __init__(self, code=None, message=None,
                 transport_code=None, transport_message=None):
        self.code = code or PulsarClientTransportError.UNKNOWN
        self.message = message or PulsarClientTransportError.messages.get(
            self.code,
            PulsarClientTransportError.INVALID_CODE_MESSAGE % code
        )
        self.transport_code = transport_code
        self.transport_message = transport_message
        if transport_code or transport_message:
            self.message += " ("
            if transport_code:
                self.message += "transport code: %s" % transport_code
                if transport_message:
                    self.message += ", "
            if transport_message:
                self.message += "transport message: %s" % transport_message
            self.message += ")"

    def __str__(self):
        return self.message
