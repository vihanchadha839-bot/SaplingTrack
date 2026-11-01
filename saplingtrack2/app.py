import os
import secrets
from datetime import date, timedelta

from flask import Flask, redirect, render_template, request, url_for
from supabase import create_client

app = Flask(__name__)

# Connect to the Supabase database using keys stored as environment variables
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

MAX_NOTES_LENGTH = 200
REMINDER_DAYS = 730  # reminders stop two years after planting

# One place for status colours and icons, so the list and the map always match
COLOURS = {
    "damaged": "#c0392b",
    "overdue": "#d68910",
    "healthy": "#1e8449",
    "established": "#2471a3",
    "dead": "#566573",
}
ICONS = {
    "damaged": "✖",
    "overdue": "◷",
    "healthy": "✔",
    "established": "❦",
    "dead": "†",
}

# Damaged first because it can still be saved, dead last because it can't
PRIORITY = {"damaged": 0, "overdue": 1, "healthy": 2, "established": 3, "dead": 4}


# ---------- Reading from the database ----------

def get_volunteers():
    """Load every registered volunteer so the dropdown and lookup check use the same list."""
    return db.table("volunteers").select("id, name, phone, token").order("name").execute().data


def get_species():
    """Load every species name from the species table."""
    rows = db.table("species").select("name").order("name").execute().data
    return [row["name"] for row in rows]


def get_intervals():
    """Watering interval in days for each species."""
    rows = db.table("species").select("name, watering_interval_days").execute().data
    return {row["name"]: row["watering_interval_days"] for row in rows}


def get_drives():
    return db.table("drives").select("*").order("date", desc=True).execute().data


def get_saplings(drive_id):
    return (db.table("saplings")
              .select("*, volunteers(name)")
              .eq("drive_id", drive_id)
              .execute().data)


def get_volunteer_saplings(volunteer_id):
    return (db.table("saplings")
              .select("*")
              .eq("carer_id", volunteer_id)
              .order("sapling_number")
              .execute().data)


def next_sapling_number():
    """One running number across every drive, so no two tree tags ever match."""
    rows = (db.table("saplings").select("sapling_number")
              .order("sapling_number", desc=True).limit(1).execute().data)
    return rows[0]["sapling_number"] + 1 if rows else 1


# ---------- Status and reminders ----------

def get_status(sapling, interval_days, today):
    if sapling["status"] in ("damaged", "dead"):
        return sapling["status"]
    planted = date.fromisoformat(sapling["planted_on"])
    if (today - planted).days > REMINDER_DAYS:
        return "established"
    last = sapling["last_watered"] or sapling["planted_on"]
    due = date.fromisoformat(last) + timedelta(days=interval_days)
    if today > due:
        return "overdue"
    return "healthy"


def add_status(saplings, intervals):
    """Work out the status and next watering date for every sapling."""
    today = date.today()
    for s in saplings:
        interval = intervals.get(s["species"], 7)
        s["status"] = get_status(s, interval, today)
        last = date.fromisoformat(s["last_watered"] or s["planted_on"])
        s["next_due"] = last + timedelta(days=interval)
        s["days_overdue"] = (today - s["next_due"]).days
        s["colour"] = COLOURS[s["status"]]
        s["icon"] = ICONS[s["status"]]
    return saplings


# ---------- Validation ----------

def validate_sapling(form, valid_carers, valid_species):
    """
    Check every field before anything is saved.
    Returns a dictionary of errors (empty if the form is valid)
    and a dictionary of cleaned data ready to insert.
    """
    errors = {}

    carer_id = form.get("carer", "").strip()
    species = form.get("species", "").strip()
    lat_raw = form.get("latitude", "").strip()
    lng_raw = form.get("longitude", "").strip()
    notes = form.get("notes", "").strip()

    # Presence check and lookup check on the carer
    if not carer_id:
        errors["carer"] = "Pick a volunteer to look after this sapling"
    elif carer_id not in valid_carers:
        errors["carer"] = "That volunteer isn't registered. Add them first"

    # Presence check and lookup check on the species
    if not species:
        errors["species"] = "Pick a species"
    elif species not in valid_species:
        errors["species"] = "That species isn't in the list"

    # Presence check, type check and range check on the GPS coordinates
    lat = lng = None
    if not lat_raw or not lng_raw:
        errors["gps"] = "Location not found yet. Wait a few seconds and try again"
    else:
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
        except ValueError:
            errors["gps"] = "Location came through wrong. Refresh and try again"
        else:
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                errors["gps"] = "Location is out of range. Refresh and try again"

    # Length check on notes
    if len(notes) > MAX_NOTES_LENGTH:
        errors["notes"] = f"Keep notes under {MAX_NOTES_LENGTH} characters"

    clean = {
        "carer_id": carer_id,
        "species": species,
        "latitude": lat,
        "longitude": lng,
        "notes": notes,
        "status": "healthy",
    }
    return errors, clean


# ---------- Organiser pages ----------

@app.route("/dashboard")
def dashboard():
    drives = get_drives()
    if not drives:
        return render_template("dashboard.html", drives=[], drive=None)

    drive_id = request.args.get("drive", str(drives[0]["id"]))
    drive = next((d for d in drives if str(d["id"]) == drive_id), drives[0])

    all_saplings = add_status(get_saplings(drive["id"]), get_intervals())

    # Survival rate: saplings still alive out of everything planted
    alive = [s for s in all_saplings if s["status"] != "dead"]
    survival = round(len(alive) / len(all_saplings) * 100) if all_saplings else 0

    counts = {k: len([s for s in all_saplings if s["status"] == k]) for k in PRIORITY}

    # Most urgent first, then filter if a button was pressed
    saplings = list(all_saplings)
    saplings.sort(key=lambda s: (PRIORITY[s["status"]], s["sapling_number"]))
    show = request.args.get("show", "all")
    if show != "all":
        saplings = [s for s in saplings if s["status"] == show]

    return render_template(
        "dashboard.html",
        drives=drives, drive=drive, saplings=saplings, all_saplings=all_saplings,
        survival=survival, alive=len(alive), total=len(all_saplings),
        counts=counts, show=show, colours=COLOURS,
    )


@app.route("/drives", methods=["POST"])
def add_drive():
    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    if name:
        row = db.table("drives").insert({
            "name": name, "location": location, "date": date.today().isoformat()
        }).execute().data[0]
        return redirect(url_for("dashboard", drive=row["id"]))
    return redirect(url_for("dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    volunteers = get_volunteers()
    species_list = get_species()
    drives = get_drives()

    if request.method == "POST":
        valid_carers = {str(v["id"]) for v in volunteers}
        errors, clean = validate_sapling(request.form, valid_carers, species_list)

        drive_id = request.form.get("drive", "").strip()
        if drive_id not in {str(d["id"]) for d in drives}:
            errors["drive"] = "Pick which drive this sapling belongs to"

        if not errors:
            try:
                clean["drive_id"] = drive_id
                clean["sapling_number"] = next_sapling_number()
                clean["planted_on"] = date.today().isoformat()
                db.table("saplings").insert(clean).execute()
                return render_template("saved.html", number=clean["sapling_number"], drive_id=drive_id)
            except Exception:
                # The database layer rejected it, e.g. the NOT NULL rule on carer_id
                errors["form"] = "Not saved. Check every field and try again"

        # Send the form back with the errors and keep what the user already typed
        return render_template(
            "register.html", errors=errors, form=request.form,
            volunteers=volunteers, species=species_list, drives=drives,
        ), 400

    return render_template(
        "register.html", errors={}, form={"drive": request.args.get("drive", "")},
        volunteers=volunteers, species=species_list, drives=drives,
    )


@app.route("/sapling/<int:sapling_id>/status", methods=["POST"])
def set_status(sapling_id):
    """Organiser marks a sapling dead, or back to healthy after a damage report is fixed."""
    new_status = request.form.get("status")
    if new_status in ("healthy", "dead"):
        db.table("saplings").update({"status": new_status}).eq("id", sapling_id).execute()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/volunteers", methods=["GET", "POST"])
def volunteers_page():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        if not name:
            error = "Enter the volunteer's name"
        else:
            # Random code so links can't be guessed by changing a number
            db.table("volunteers").insert({
                "name": name, "phone": phone, "token": secrets.token_urlsafe(6)
            }).execute()
            return redirect(url_for("volunteers_page"))
    return render_template("volunteers.html", volunteers=get_volunteers(), error=error)


# ---------- Volunteer pages (no login, no organiser menu) ----------

def find_volunteer(token):
    found = db.table("volunteers").select("*").eq("token", token).execute().data
    return found[0] if found else None


@app.route("/v/<token>")
def volunteer_page(token):
    found = db.table("volunteers").select("*").eq("token", token).execute().data
    if not found:
        return render_template("not_found.html"), 404
    volunteer = found[0]
    saplings = add_status(get_volunteer_saplings(volunteer["id"]), get_intervals())
    saplings = [s for s in saplings if s["status"] != "dead"]

    # First time volunteers get the simplified view from B3
    sapling_ids = [s["id"] for s in saplings]
    has_logged = bool(sapling_ids) and bool(
        db.table("logs").select("id").in_("sapling_id", sapling_ids).limit(1).execute().data
    )
    return render_template("volunteer.html", volunteer=volunteer, saplings=saplings,
                           first_time=not has_logged, today=date.today())


@app.route("/v/<token>/s/<int:sapling_id>")
def volunteer_sapling(token, sapling_id):
    """Tap 2: choose Water done or Report damage."""
    volunteer = find_volunteer(token)
    if not volunteer:
        return render_template("not_found.html"), 404
    rows = db.table("saplings").select("*").eq("id", sapling_id).eq("carer_id", volunteer["id"]).execute().data
    if not rows:
        return render_template("not_found.html"), 404
    return render_template("action.html", volunteer=volunteer, sapling=rows[0])


@app.route("/v/<token>/s/<int:sapling_id>/<action>", methods=["GET", "POST"])
def volunteer_confirm(token, sapling_id, action):
    """Tap 3: confirm, then save the log."""
    volunteer = find_volunteer(token)
    if not volunteer or action not in ("water", "damage"):
        return render_template("not_found.html"), 404
    rows = db.table("saplings").select("*").eq("id", sapling_id).eq("carer_id", volunteer["id"]).execute().data
    if not rows:
        return render_template("not_found.html"), 404
    sapling = rows[0]

    if request.method == "POST":
        db.table("logs").insert({"sapling_id": sapling_id, "type": action}).execute()
        if action == "water":
            db.table("saplings").update({"last_watered": date.today().isoformat()}).eq("id", sapling_id).execute()
        else:
            db.table("saplings").update({"status": "damaged"}).eq("id", sapling_id).execute()
        return render_template("done.html", volunteer=volunteer, sapling=sapling, action=action)

    return render_template("confirm.html", volunteer=volunteer, sapling=sapling, action=action)


# ---------- Homepage ----------

@app.route("/")
def home():
    """Landing page with live totals across every drive."""
    saplings = add_status(db.table("saplings").select("*").execute().data, get_intervals())
    alive = [s for s in saplings if s["status"] != "dead"]
    stats = {
        "planted": len(saplings),
        "alive": len(alive),
        "survival": round(len(alive) / len(saplings) * 100) if saplings else 0,
        "volunteers": len(db.table("volunteers").select("id").execute().data),
        "waterings": len(db.table("logs").select("id").eq("type", "water").execute().data),
        "drives": len(get_drives()),
    }
    return render_template("home.html", stats=stats)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("not_found.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
