"""
Nose tests for the REST service.

The MongoDB collection is swapped for mongomock, an in-memory fake,
and filled with documents shaped like the ones the calculator saves.
"""
import mongomock
from pymongo.errors import ServerSelectionTimeoutError

import api


# Two brevets, saved in this order. The second starts earlier, so its
# times sort ahead of the first brevet's when ?top is used.
DOCS = [
    {"brevet_dist_km": 200, "start": "2021-12-01T18:06:00+00:00",
     "submitted_at": "2026-11-01T10:00:00+00:00",
     "controls": [
         {"km": 100.0, "miles": 62.1, "location": "",
          "open": "2021-12-01T21:02:00+00:00", "close": "2021-12-02T00:46:00+00:00"},
         {"km": 0.0, "miles": 0.0, "location": "begin",
          "open": "2021-12-01T18:06:00+00:00", "close": "2021-12-01T19:06:00+00:00"},
         {"km": 200.0, "miles": 124.3, "location": "last checkpoint",
          "open": "2021-12-01T23:59:00+00:00", "close": "2021-12-02T07:36:00+00:00"},
     ]},
    {"brevet_dist_km": 1000, "start": "2021-11-30T00:00:00+00:00",
     "submitted_at": "2026-11-02T10:00:00+00:00",
     "controls": [
         {"km": 0.0, "miles": 0.0, "location": "begin",
          "open": "2021-11-30T00:00:00+00:00", "close": "2021-11-30T01:00:00+00:00"},
         {"km": 1000.0, "miles": 621.4, "location": "finish line",
          "open": "2021-11-30T09:05:00+00:00", "close": "2021-12-03T03:00:00+00:00"},
     ]},
]


def _client(docs=DOCS):
    api.brevets = mongomock.MongoClient().brevetsdb.brevets
    for d in docs:
        api.brevets.insert_one(dict(d))
    api.app.config["TESTING"] = True
    return api.app.test_client()


def _times(body, field):
    return [c[field] for b in body["brevets"] for c in b["controls"]]


# ---------- Basic APIs (JSON by default) ----------

def test_list_all_default_is_json():
    resp = _client().get("/listAll")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    body = resp.get_json()
    first = body["brevets"][0]
    assert first["distance"] == 200
    assert first["begin_date"] == "12/01/2021"
    assert first["begin_time"] == "18:06"
    # Controls come out in km order, formatted like the sample data.
    assert first["controls"][0] == {
        "km": 0, "mi": 0, "location": "begin",
        "open": "12/01/2021 18:06", "close": "12/01/2021 19:06"}
    assert first["controls"][1]["location"] is None   # blank -> null
    assert first["controls"][1]["mi"] == 62
    assert [b["distance"] for b in body["brevets"]] == [200, 1000]


def test_open_only_and_close_only():
    client = _client()
    for path, keep, drop in [("/listOpenOnly", "open", "close"),
                             ("/listCloseOnly", "close", "open")]:
        body = client.get(path).get_json()
        controls = [c for b in body["brevets"] for c in b["controls"]]
        assert len(controls) == 5, path
        assert all(keep in c and drop not in c for c in controls), path


def test_json_path_matches_default():
    client = _client()
    for name in ["listAll", "listOpenOnly", "listCloseOnly"]:
        assert (client.get("/" + name + "/json").get_json()
                == client.get("/" + name).get_json()), name


def test_empty_database():
    client = _client(docs=[])
    assert client.get("/listAll").get_json() == {"brevets": []}
    assert client.get("/listAll/csv").data.decode().count("\n") == 1  # header only


# ---------- CSV ----------

def test_list_all_csv():
    resp = _client().get("/listAll/csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    lines = resp.data.decode().splitlines()
    assert lines[0] == ("brevets/distance,brevets/begin_date,brevets/begin_time,"
                        "brevets/controls/0/km,brevets/controls/0/mi,"
                        "brevets/controls/0/location,brevets/controls/0/open,"
                        "brevets/controls/0/close")
    assert lines[1] == "200,12/01/2021,18:06,0,0,begin,12/01/2021 18:06,12/01/2021 19:06"
    assert lines[2] == "200,12/01/2021,18:06,100,62,,12/01/2021 21:02,12/02/2021 00:46"
    assert len(lines) == 6


def test_open_and_close_only_csv():
    client = _client()
    open_lines = client.get("/listOpenOnly/csv").data.decode().splitlines()
    assert open_lines[0].endswith("location,brevets/controls/0/open")
    assert open_lines[1] == "200,12/01/2021,18:06,0,0,begin,12/01/2021 18:06"
    close_lines = client.get("/listCloseOnly/csv").data.decode().splitlines()
    assert close_lines[0].endswith("location,brevets/controls/0/close")
    assert close_lines[1] == "200,12/01/2021,18:06,0,0,begin,12/01/2021 19:06"


def test_unknown_format_is_404():
    assert _client().get("/listAll/xml").status_code == 404


# ---------- ?top=k ----------

def test_top_open_json_is_earliest_k_ascending():
    body = _client().get("/listOpenOnly/json?top=3").get_json()
    # The 1000 km brevet starts a day earlier, so its two times come first.
    assert _times(body, "open") == ["11/30/2021 00:00", "11/30/2021 09:05",
                                    "12/01/2021 18:06"]
    assert [b["distance"] for b in body["brevets"]] == [1000, 200]


def test_top_close_csv():
    lines = _client().get("/listCloseOnly/csv?top=4").data.decode().splitlines()
    assert [l.rsplit(",", 1)[1] for l in lines[1:]] == [
        "11/30/2021 01:00", "12/01/2021 19:06", "12/02/2021 00:46",
        "12/02/2021 07:36"]


def test_top_larger_than_data_returns_everything():
    body = _client().get("/listAll?top=50").get_json()
    assert len(_times(body, "open")) == 5


def test_bad_top_is_400():
    client = _client()
    for bad in ["0", "-2", "abc", "2.5", ""]:
        resp = client.get("/listOpenOnly?top=" + bad)
        assert resp.status_code == 400, bad
        assert "top" in resp.get_json()["error"], bad


# ---------- Database down ----------

def test_database_down_is_503():
    client = _client()

    class DownCollection:
        def find(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("down")

    api.brevets = DownCollection()
    resp = client.get("/listAll")
    assert resp.status_code == 503
    assert "database" in resp.get_json()["error"]
