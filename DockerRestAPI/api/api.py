"""
Brevet times REST service (Project 6).

Exposes the brevets that the calculator (the "brevets" service) saved
in MongoDB:

    /listAll        open and close times
    /listOpenOnly   open times only
    /listCloseOnly  close times only

Each one also answers at /<name>/json and /<name>/csv. JSON is the
default. Add ?top=k to get only the k earliest times, in ascending
order.
"""

import csv
import io
import os

import arrow
from flask import Flask, Response, request
from flask_restful import Api, Resource, abort
from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

app = Flask(__name__)
api = Api(app)

# In docker-compose the database service is called "db".
# MongoClient connects lazily, so a database that is down shows up as
# an error on the first query, which each request handles.
MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))
client = MongoClient(MONGO_HOST, MONGO_PORT, serverSelectionTimeoutMS=3000)
brevets = client.brevetsdb.brevets   # Written by the brevets service

DATE_FORMAT = "MM/DD/YYYY"
TIME_FORMAT = "HH:mm"
DATETIME_FORMAT = DATE_FORMAT + " " + TIME_FORMAT
KM_TO_MILES = 0.621371


###
# Reading and shaping the data
###

def _number(x):
    """60.0 -> 60, 60.5 -> 60.5, so whole distances print without '.0'."""
    return int(x) if float(x).is_integer() else x


def _load_brevets():
    """Every saved brevet, oldest submission first, controls in km order.

    Each control keeps its open and close times as arrow objects (under
    '_open' and '_close') so they can be sorted as times, not strings.
    """
    result = []
    for doc in brevets.find().sort("submitted_at", ASCENDING):
        start = arrow.get(doc["start"])
        controls = []
        for c in sorted(doc.get("controls", []), key=lambda c: c["km"]):
            controls.append({
                "km": _number(c["km"]),
                "mi": round(c["km"] * KM_TO_MILES),
                "location": c.get("location") or None,
                "_open": arrow.get(c["open"]),
                "_close": arrow.get(c["close"]),
            })
        result.append({
            "distance": doc["brevet_dist_km"],
            "begin_date": start.format(DATE_FORMAT),
            "begin_time": start.format(TIME_FORMAT),
            "controls": controls,
        })
    return result


def _top_k(all_brevets, k, sort_field):
    """Keep only the k controls with the earliest sort_field time.

    Controls stay grouped under their brevet. Brevets come out in the
    order of their earliest kept time, and brevets left with no
    controls are dropped.
    """
    pairs = [(b, c) for b in all_brevets for c in b["controls"]]
    pairs.sort(key=lambda bc: bc[1][sort_field])   # stable: ties keep km order
    groups = {}   # id(brevet) -> trimmed copy; dicts keep insertion order
    for b, c in pairs[:k]:
        if id(b) not in groups:
            groups[id(b)] = dict(b, controls=[])
        groups[id(b)]["controls"].append(c)
    return list(groups.values())


def _present(all_brevets, fields):
    """Replace the internal arrow times with formatted strings,
    keeping only the requested fields ('open' and/or 'close')."""
    out = []
    for b in all_brevets:
        controls = []
        for c in b["controls"]:
            shown = {"km": c["km"], "mi": c["mi"], "location": c["location"]}
            for f in fields:
                shown[f] = c["_" + f].format(DATETIME_FORMAT)
            controls.append(shown)
        out.append(dict(b, controls=controls))
    return out


def _to_csv(all_brevets, fields):
    """One row per control, with the brevet's columns repeated
    (the layout of data-samples/sample-data-pivoted.csv)."""
    header = (["brevets/distance", "brevets/begin_date", "brevets/begin_time"]
              + ["brevets/controls/0/" + f
                 for f in ["km", "mi", "location"] + fields])
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for b in all_brevets:
        for c in b["controls"]:
            writer.writerow([b["distance"], b["begin_date"], b["begin_time"],
                             c["km"], c["mi"], c["location"] or ""]
                            + [c[f] for f in fields])
    return buf.getvalue()


def _parse_top():
    """The ?top=k value as a positive int, None if absent; 400 if invalid."""
    raw = request.args.get("top")
    if raw is None:
        return None
    try:
        k = int(raw)
    except ValueError:
        k = 0
    if k < 1:
        abort(400, error="top must be a whole number of 1 or more")
    return k


###
# Resources
###

class BrevetList(Resource):
    """Base class: subclasses set FIELDS, the times they expose."""
    FIELDS = []

    def get(self, fmt="json"):
        if fmt not in ("json", "csv"):
            abort(404, error="Unknown format '{}'. Use json or csv.".format(fmt))
        k = _parse_top()
        try:
            data = _load_brevets()
        except PyMongoError as e:
            app.logger.error("Database error: {}".format(e))
            abort(503, error="Could not reach the database. Try again in a moment.")
        if k is not None:
            # listAll sorts by open time; the others by the time they show.
            data = _top_k(data, k, "_" + self.FIELDS[0])
        data = _present(data, self.FIELDS)
        if fmt == "csv":
            return Response(_to_csv(data, self.FIELDS), mimetype="text/csv")
        return {"brevets": data}


class ListAll(BrevetList):
    FIELDS = ["open", "close"]


class ListOpenOnly(BrevetList):
    FIELDS = ["open"]


class ListCloseOnly(BrevetList):
    FIELDS = ["close"]


class Index(Resource):
    def get(self):
        return {"endpoints": [
            "/listAll", "/listOpenOnly", "/listCloseOnly",
            "/<endpoint>/json", "/<endpoint>/csv", "?top=k",
        ]}


api.add_resource(Index, "/")
api.add_resource(ListAll, "/listAll", "/listAll/<string:fmt>")
api.add_resource(ListOpenOnly, "/listOpenOnly", "/listOpenOnly/<string:fmt>")
api.add_resource(ListCloseOnly, "/listCloseOnly", "/listCloseOnly/<string:fmt>")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
