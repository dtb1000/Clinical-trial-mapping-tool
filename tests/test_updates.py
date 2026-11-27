from sdtm_helper import updates


class Resp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class Http:
    def __init__(self, resp):
        self.resp = resp

    def get(self, *a, **k):
        return self.resp


def test_reminds_when_newer():
    msg = updates.check_for_update("0.1.0", Http(Resp(200, {"tag_name": "v0.2.0", "html_url": "u"})))
    assert "v0.2.0" in msg


def test_quiet_when_current_or_offline():
    assert updates.check_for_update("0.2.0", Http(Resp(200, {"tag_name": "v0.2.0"}))) is None
    assert updates.check_for_update("0.1.0", Http(Resp(404, {}))) is None
