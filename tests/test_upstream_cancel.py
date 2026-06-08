import unittest
from unittest import mock

import claude_any


class FakeResponse:
    def __init__(self, items):
        self.items = list(items)
        self.closed = False

    def readline(self):
        if not self.items:
            return b""
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self):
        self.closed = True


class FakeHandler:
    headers = {}
    connection = None

    def __init__(self, wfile):
        self.wfile = wfile

    def send_response(self, _status):
        pass

    def send_header(self, _name, _value):
        pass

    def end_headers(self):
        pass


class BrokenWrite:
    def write(self, _data):
        raise BrokenPipeError("client closed")

    def flush(self):
        pass


class UpstreamCancelTests(unittest.TestCase):
    def test_stream_iterator_raises_when_client_disconnects_during_timeout(self):
        resp = FakeResponse([TimeoutError("timed out")])
        handler = FakeHandler(wfile=object())

        with mock.patch.object(claude_any, "router_client_connection_closed", side_effect=[False, True]):
            with self.assertRaises(claude_any.UpstreamClientDisconnected):
                list(claude_any.iter_upstream_lines_until_client_disconnect(handler, resp, 30.0))

    def test_ollama_stream_closes_upstream_on_downstream_write_failure(self):
        resp = FakeResponse(
            [
                b'{"message":{"content":"hello"},"done":false}\n',
                b'{"message":{"content":""},"done":true}\n',
            ]
        )
        handler = FakeHandler(wfile=BrokenWrite())

        claude_any._ollama_stream_to_anthropic_sse(handler, resp, "gemma4:12b", idle_timeout=30.0)

        self.assertTrue(resp.closed)


if __name__ == "__main__":
    unittest.main()
