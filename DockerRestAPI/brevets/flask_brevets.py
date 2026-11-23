"""
Replacement for RUSA ACP brevet time calculator
(see https://rusa.org/octime_acp.html)

Project 5 adds a MongoDB database: the Submit button saves the
controls on the page, and the Display button shows what was saved.
"""

import flask
from flask import request
import arrow  # Replacement for datetime, based on moment.js
import acp_times  # Brevet time calculations
import config

import logging
import math
import os

from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError

###
# Globals
###
app = flask.Flask(__name__)
CONFIG = config.configuration()
app.secret_key = CONFIG.SECRET_KEY

# In docker-compose the database service is called "db".
# MongoClient connects lazily, so this does not fail if Mongo is down;
# errors show up on the first query and are handled in each route.
MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))
client = MongoClient(MONGO_HOST, MONGO_PORT, serverSelectionTimeoutMS=3000)
db = client.brevetsdb
brevets = db.brevets   # One document per submitted brevet

###
# Pages
###


@app.route("/")
@app.route("/index")
def index():
    app.logger.debug("Main page entry")
    return flask.render_template('calc.html')


@app.route("/display")
def display():
    """Show every submitted brevet, newest first."""
    try:
        saved = list(brevets.find().sort("submitted_at", DESCENDING))
    except PyMongoError as e:
        app.logger.error("Database error on display: {}".format(e))
        return flask.render_template(
            'display.html', brevets=[],
            error="Could not reach the database. Try again in a moment."), 503
    return flask.render_template('display.html', brevets=saved, error=None)


@app.errorhandler(404)
def page_not_found(error):
    app.logger.debug("Page not found")
    flask.session['linkback'] = flask.url_for("index")
    return flask.render_template('404.html'), 404


###############
#
# AJAX request handlers
#   These return JSON, rather than rendering pages.
#
###############
@app.route("/_calc_times")
def _calc_times():
    """
    Calculates open/close times for one control.
    Expects URL arguments: km, brevet_dist_km, begin_date (YYYY-MM-DD),
    begin_time (HH:mm). Returns JSON with ISO 8601 formatted open and close times,
    or an error message with status 400 if the input is invalid.
    """
    km = request.args.get('km', type=float)
    brevet_dist_km = request.args.get('brevet_dist_km', 200, type=int)
    begin_date = request.args.get('begin_date', '', type=str)
    begin_time = request.args.get('begin_time', '', type=str)
    app.logger.debug("km={} brevet={} start={} {}".format(
        km, brevet_dist_km, begin_date, begin_time))

    if km is None or math.isnan(km):
        return flask.jsonify(error="Enter a number for the control distance"), 400

    try:
        start = arrow.get(begin_date + "T" + begin_time).isoformat()
    except ValueError:
        return flask.jsonify(error="Enter a valid start date and time"), 400

    try:
        open_time = acp_times.open_time(km, brevet_dist_km, start)
        close_time = acp_times.close_time(km, brevet_dist_km, start)
    except ValueError as e:
        return flask.jsonify(error=str(e)), 400

    result = {"open": open_time, "close": close_time}
    return flask.jsonify(result=result)


def _error(message, status=400):
    return flask.jsonify(error=message), status


@app.route("/_submit_times", methods=["POST"])
def _submit_times():
    """
    Saves one brevet and its controls in the database.

    Expects a JSON body:
      {"brevet_dist_km": 200, "begin_date": "2017-01-01",
       "begin_time": "00:00",
       "controls": [{"km": 60, "location": "Somewhere"}, ...]}

    Open and close times are recalculated here rather than trusted from
    the browser, so what is stored is always correct for the stored
    distances. Returns {"result": {"id": ..., "count": n}} on success,
    or {"error": message} with status 400 (bad input) or 503 (database
    unavailable).
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request must be JSON")

    try:
        brevet_dist_km = int(data.get("brevet_dist_km"))
    except (TypeError, ValueError):
        return _error("Brevet distance must be 200, 300, 400, 600, or 1000 km")
    if brevet_dist_km not in acp_times.FINISH_CLOSE_HOURS:
        return _error("Brevet distance must be 200, 300, 400, 600, or 1000 km")

    try:
        start = arrow.get("{}T{}".format(data.get("begin_date", ""),
                                          data.get("begin_time", "")))
    except (ValueError, TypeError, arrow.parser.ParserError):
        return _error("Enter a valid start date and time")

    controls = data.get("controls")
    if not isinstance(controls, list) or len(controls) == 0:
        return _error("There are no controls to submit. "
                      "Enter at least one control distance first.")

    saved_controls = []
    seen_km = set()
    for i, control in enumerate(controls, start=1):
        if not isinstance(control, dict):
            return _error("Control {} is not valid".format(i))
        try:
            km = float(control.get("km"))
        except (TypeError, ValueError):
            return _error("Control {}: enter a number for the distance".format(i))
        if math.isnan(km) or math.isinf(km):
            return _error("Control {}: enter a number for the distance".format(i))
        if km in seen_km:
            return _error("Control {}: {:g} km is listed twice".format(i, km))
        seen_km.add(km)

        try:
            open_time = acp_times.open_time(km, brevet_dist_km, start.isoformat())
            close_time = acp_times.close_time(km, brevet_dist_km, start.isoformat())
        except ValueError as e:
            return _error("Control {} ({:g} km): {}".format(i, km, e))

        location = str(control.get("location") or "").strip()[:100]
        saved_controls.append({
            "km": km,
            "miles": round(km * 0.621371, 1),
            "location": location,
            "open": open_time,
            "close": close_time,
        })

    # Store controls in route order, whatever order the rows were filled in.
    saved_controls.sort(key=lambda c: c["km"])

    doc = {
        "brevet_dist_km": brevet_dist_km,
        "start": start.isoformat(),
        "controls": saved_controls,
        "submitted_at": arrow.utcnow().isoformat(),
    }
    try:
        inserted = brevets.insert_one(doc)
    except PyMongoError as e:
        app.logger.error("Database error on submit: {}".format(e))
        return _error("Could not save to the database. Try again in a moment.", 503)

    return flask.jsonify(result={"id": str(inserted.inserted_id),
                                 "count": len(saved_controls)})


#############

app.debug = CONFIG.DEBUG
if app.debug:
    app.logger.setLevel(logging.DEBUG)

if __name__ == "__main__":
    print("Opening for global access on port {}".format(CONFIG.PORT))
    app.run(port=CONFIG.PORT, host="0.0.0.0")
