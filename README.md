# Project 6: Brevet time calculator service

The ACP brevet calculator from Project 5 saves control times in MongoDB.
This project adds a REST service that exposes those saved times as JSON or
CSV, and a separate consumer website that uses the service.

**Author:** Nigel Epperson
**Email:** epperson@uoregon.edu

---

## Running it

You need Docker. From the `DockerRestAPI` directory:

```bash
docker compose up --build
```

This starts four containers:

| Service | URL on your machine | What it is |
|---|---|---|
| `brevets` | http://localhost:5001 | The Project 5 calculator. **Submit** saves to MongoDB, **Display** lists what is saved. |
| `api` | http://localhost:5002 | The REST service (Flask-RESTful). |
| `website` | http://localhost:5003 | The consumer program (PHP), in its own container. |
| `db` | (internal only) | MongoDB 7. Data is kept in the `mongo-data` volume. |

Host ports start at 5001 because macOS often reserves 5000 for AirPlay
Receiver. To stop and delete the saved data, run `docker compose down -v`.

To try it out, open the calculator, enter some controls, click **Submit**,
then use the API URLs below or the website.

---

## REST API

All three lists return JSON by default. Add `/json` or `/csv` to pick the
format.

| URL | Returns |
|---|---|
| `/listAll` | open and close times |
| `/listOpenOnly` | open times only |
| `/listCloseOnly` | close times only |
| `/listAll/csv`, `/listOpenOnly/csv`, `/listCloseOnly/csv` | the same, as CSV |
| `/listAll/json`, `/listOpenOnly/json`, `/listCloseOnly/json` | the same, as JSON |

Examples: http://localhost:5002/listAll, http://localhost:5002/listOpenOnly/csv?top=3

### `?top=k`

`?top=k` returns only the **k earliest times across all saved brevets, in
ascending order**. `listOpenOnly` sorts by open time, `listCloseOnly` by close
time, and `listAll` by open time. If k is larger than the number of controls,
everything is returned. Controls stay grouped under their brevet, and a brevet
with no remaining controls is left out.

`top` must be a whole number of 1 or more. Anything else returns status 400
with an error message.

### JSON format

This follows [data-samples/sample-data.json](data-samples/sample-data.json).
Without `top`, brevets are listed in the order they were submitted (oldest
first), and each brevet's controls are listed by distance.

```json
{
  "brevets": [
    {
      "distance": 200,
      "begin_date": "12/01/2021",
      "begin_time": "18:06",
      "controls": [
        {"km": 0, "mi": 0, "location": "begin",
         "open": "12/01/2021 18:06", "close": "12/01/2021 19:06"},
        {"km": 100, "mi": 62, "location": null,
         "open": "12/01/2021 21:02", "close": "12/02/2021 00:46"}
      ]
    }
  ]
}
```

- `mi` is rounded to a whole number, as in the sample.
- A control with no location name has `"location": null`.
- `listOpenOnly` leaves out `close`, and `listCloseOnly` leaves out `open`.

### CSV format

This follows [data-samples/sample-data-pivoted.csv](data-samples/sample-data-pivoted.csv):
one row per control, with the brevet's columns repeated on each row. With one
row per control, `?top=k` returns exactly k rows. `listOpenOnly` and
`listCloseOnly` leave out the `close` or `open` column.

```csv
brevets/distance,brevets/begin_date,brevets/begin_time,brevets/controls/0/km,brevets/controls/0/mi,brevets/controls/0/location,brevets/controls/0/open,brevets/controls/0/close
200,12/01/2021,18:06,0,0,begin,12/01/2021 18:06,12/01/2021 19:06
200,12/01/2021,18:06,100,62,,12/01/2021 21:02,12/02/2021 00:46
```

### Errors

| Status | When |
|---|---|
| 400 | `top` is not a whole number of 1 or more |
| 404 | an unknown format, such as `/listAll/xml`, or an unknown path |
| 503 | the database can't be reached |

Errors come back as JSON: `{"error": "..."}`.

---

## Consumer website

http://localhost:5003 has a form to choose the list, the format (JSON or
CSV), and an optional top k. The PHP page calls the API server side at
`http://api/...` (the Compose service name), then shows the result as a table
along with the raw response. If the API returns an error, the page shows the
error message.

---

## Running the tests

The tests use `mongomock`, so they don't need MongoDB or Docker running.

```bash
cd DockerRestAPI/api && nosetests -v       # REST service
cd DockerRestAPI/brevets && nosetests -v   # Project 5 calculator
```

Install each folder's `requirements.txt` first, for example in a virtualenv.

---

## Project layout

| Path | Purpose |
|---|---|
| `DockerRestAPI/docker-compose.yml` | Runs all four services together |
| `DockerRestAPI/brevets/` | Project 5 calculator (Flask, `acp_times.py`, templates, tests) |
| `DockerRestAPI/brevets/credentials.ini` | `author` and `repo` for grading |
| `DockerRestAPI/api/api.py` | The REST service |
| `DockerRestAPI/api/test_api.py` | Tests for every endpoint, format, `top`, and error |
| `DockerRestAPI/api/Dockerfile` | API container build (Python 3.13) |
| `DockerRestAPI/website/index.php` | Consumer program |
| `data-samples/` | The suggested JSON and CSV formats |

The calculator's own endpoints and time rules are unchanged from Project 5.
