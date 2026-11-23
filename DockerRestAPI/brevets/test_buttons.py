"""
Nose tests for the Submit and Display buttons.

Submit posts to /_submit_times; Display opens /display.
The real MongoDB collection is swapped for mongomock, an in-memory
fake, so these tests run without a database server.
"""
import mongomock
from pymongo.errors import ServerSelectionTimeoutError

import flask_brevets

def _client():
    """A test client backed by a fresh, empty fake collection."""
    flask_brevets.brevets = mongomock.MongoClient().brevetsdb.brevets
    flask_brevets.app.config["TESTING"] = True
    return flask_brevets.app.test_client()

def _submit(client, controls, brevet=200, date="2017-01-01", time="00:00"):
    return client.post("/_submit_times", json={
        "brevet_dist_km": brevet,
        "begin_date": date,
        "begin_time": time,
        "controls": controls,
    })

# ---------- Submit button ----------

def test_submit_saves_controls_with_server_calculated_times():
    client = _client()
    resp = _submit(client, [{"km": "60", "location": "Coburg"},
                            {"km": "200", "location": "Finish"}])
    assert resp.status_code == 200
    assert resp.get_json()["result"]["count"] == 2

    saved = list(flask_brevets.brevets.find())
    assert len(saved) == 1
    doc = saved[0]
    assert doc["brevet_dist_km"] == 200
    assert [c["km"] for c in doc["controls"]] == [60, 200]
    assert doc["controls"][0]["location"] == "Coburg"
    assert doc["controls"][0]["open"] == "2017-01-01T01:46:00+00:00"
    assert doc["controls"][0]["close"] == "2017-01-01T04:00:00+00:00"
    assert doc["controls"][1]["close"] == "2017-01-01T13:30:00+00:00"

def test_submit_sorts_controls_by_distance():
    client = _client()
    _submit(client, [{"km": "150"}, {"km": "50"}, {"km": "100"}])
    doc = flask_brevets.brevets.find_one()
    assert [c["km"] for c in doc["controls"]] == [50, 100, 150]

def test_submit_with_no_controls_is_an_error():
    client = _client()
    resp = _submit(client, [])
    assert resp.status_code == 400
    assert "no controls" in resp.get_json()["error"]
    assert flask_brevets.brevets.count_documents({}) == 0

def test_submit_rejects_bad_rows_and_saves_nothing():
    bad_cases = [
        [{"km": "abc"}],                 # not a number
        [{"km": ""}],                    # blank
        [{"km": "-5"}],                  # negative
        [{"km": "300"}],                 # >20% past a 200 km brevet
        [{"km": "50"}, {"km": "50"}],    # duplicate distance
        [{"km": "50"}, {"km": "nan"}],   # one good row, one bad row
    ]
    for controls in bad_cases:
        client = _client()
        resp = _submit(client, controls)
        assert resp.status_code == 400, controls
        assert "error" in resp.get_json()
        assert flask_brevets.brevets.count_documents({}) == 0, controls

def test_submit_rejects_bad_brevet_or_start():
    client = _client()
    assert _submit(client, [{"km": "50"}], brevet=250).status_code == 400
    assert _submit(client, [{"km": "50"}], date="not-a-date").status_code == 400
    assert client.post("/_submit_times", data="hello").status_code == 400
    assert flask_brevets.brevets.count_documents({}) == 0

def test_submit_reports_database_down():
    client = _client()

    class DownCollection:
        def insert_one(self, doc):
            raise ServerSelectionTimeoutError("down")

    flask_brevets.brevets = DownCollection()
    resp = _submit(client, [{"km": "50"}])
    assert resp.status_code == 503
    assert "database" in resp.get_json()["error"]

# ---------- Display button ----------

def test_display_with_empty_database():
    client = _client()
    resp = client.get("/display")
    assert resp.status_code == 200
    assert b"Nothing has been saved yet" in resp.data

def test_display_shows_submitted_controls():
    client = _client()
    _submit(client, [{"km": "60", "location": "Coburg"}])
    _submit(client, [{"km": "350"}], brevet=400)
    resp = client.get("/display")
    page = resp.data.decode()
    assert resp.status_code == 200
    assert "200 km brevet" in page and "400 km brevet" in page
    assert "Coburg" in page
    assert "2017-01-01 01:46" in page   # open at 60 km
    assert "2017-01-01 04:00" in page   # close at 60 km
    assert "2017-01-01 10:34" in page   # open at 350 km
    # Newest submission is listed first.
    assert page.index("400 km brevet") < page.index("200 km brevet")

def test_display_reports_database_down():
    _client()

    class DownCollection:
        def find(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("down")

    flask_brevets.brevets = DownCollection()
    resp = flask_brevets.app.test_client().get("/display")
    assert resp.status_code == 503
    assert b"Could not reach the database" in resp.data
