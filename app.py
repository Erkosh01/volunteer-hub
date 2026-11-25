
import os
import io
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, g, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DB = os.environ.get("DATABASE_PATH", "volunteer_hub.db")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()

def init_db():
    with sqlite3.connect(DB) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
          phone TEXT DEFAULT '', city TEXT DEFAULT 'Қызылорда',
          is_admin INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS organizations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          category TEXT NOT NULL, description TEXT DEFAULT '',
          address TEXT DEFAULT '', contact TEXT DEFAULT '',
          members INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
          description TEXT DEFAULT '', place TEXT DEFAULT '',
          event_date TEXT DEFAULT '', capacity INTEGER DEFAULT 30,
          created_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS event_members(
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER,
          user_id INTEGER, UNIQUE(event_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS animal_posts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, animal TEXT NOT NULL,
          kind TEXT NOT NULL, description TEXT DEFAULT '',
          location TEXT DEFAULT '', contact TEXT NOT NULL,
          author_id INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS help_requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
          description TEXT DEFAULT '', contact TEXT NOT NULL,
          author_id INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS hours(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
          amount REAL NOT NULL, note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS certificates(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cert_no TEXT UNIQUE NOT NULL,
          event_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          issued_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(event_id, user_id)
        );
        """)
        # Қолданыстағы деректерді сақтай отырып, жаңа бағандарды қосу
        event_columns = [r[1] for r in con.execute("PRAGMA table_info(events)").fetchall()]
        if "hours_value" not in event_columns:
            con.execute("ALTER TABLE events ADD COLUMN hours_value REAL DEFAULT 2")
        member_columns = [r[1] for r in con.execute("PRAGMA table_info(event_members)").fetchall()]
        if "attended" not in member_columns:
            con.execute("ALTER TABLE event_members ADD COLUMN attended INTEGER DEFAULT 0")
        if "hours_awarded" not in member_columns:
            con.execute("ALTER TABLE event_members ADD COLUMN hours_awarded INTEGER DEFAULT 0")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@volunteer.kz")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
        exists = con.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone()
        if not exists:
            con.execute("INSERT INTO users(name,email,password,is_admin) VALUES(?,?,?,1)",
                        ("Әкімші", admin_email, generate_password_hash(admin_pass)))

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("uid"):
            flash("Алдымен жүйеге кіріңіз.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = db().execute("SELECT * FROM users WHERE id=?", (session.get("uid"),)).fetchone()
        if not user or not user["is_admin"]:
            flash("Бұл бөлім тек әкімшіге арналған.")
            return redirect(url_for("home"))
        return fn(*args, **kwargs)
    return wrapped

BASE = """
<!doctype html><html lang="kk"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} | Volunteer Hub</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#182235;font:16px Arial}
header{background:#102a43;color:white;padding:17px 5%;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
header a{color:white;text-decoration:none;margin:5px}.wrap{max-width:1050px;margin:25px auto;padding:0 15px}
.hero,.card,form{background:white;border-radius:16px;padding:20px;margin:14px 0;box-shadow:0 5px 20px #102a4310}
.hero{background:linear-gradient(120deg,#123b5d,#167d78);color:white;padding:30px}
h1,h2{margin-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
input,textarea,select{width:100%;padding:12px;margin:7px 0 14px;border:1px solid #ccd5df;border-radius:9px;font:inherit}
button,.btn{display:inline-block;background:#087f75;color:white;border:0;border-radius:9px;padding:11px 16px;text-decoration:none;cursor:pointer}
small,.muted{color:#66758a}.hero .muted{color:#e2f3f2}.danger{color:#b42318}
.flash{background:#fff1cf;padding:12px;border-radius:9px;margin:10px 0}
footer{text-align:center;color:#718096;padding:25px}
.progress{height:12px;background:#e8edf3;border-radius:20px;overflow:hidden;margin:10px 0}
.progress span{display:block;height:100%;background:linear-gradient(90deg,#087f75,#22b8a7)}
.tag{display:inline-block;padding:5px 9px;border-radius:20px;background:#e5f5f2;color:#087f75;font-size:13px}
.chartbox{background:white;border-radius:16px;padding:18px;margin:14px 0;min-height:280px}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-bottom:1px solid #e8edf3}

</style>
<header><b>🌱 Volunteer Hub</b><nav>
<a href="/">Басты бет</a><a href="/organizations">Ұйымдар</a><a href="/events">Іс-шаралар</a>
<a href="/animals">Жануарларға көмек</a><a href="/help">Көмек сұрау</a><a href="/stats">Статистика</a>
{% if user %}<a href="/profile">Профиль</a><a href="/logout">Шығу</a>{% else %}<a href="/login">Кіру</a><a href="/register">Тіркелу</a>{% endif %}
{% if user and user.is_admin %}<a href="/admin">Әкімші</a>{% endif %}
</nav></header><main class="wrap">
{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}
{{ content|safe }}</main><footer>Volunteer Hub · Қызылорда волонтерлер порталы</footer></html>
"""

def page(title, body, **kwargs):
    user = db().execute("SELECT * FROM users WHERE id=?", (session.get("uid"),)).fetchone() if session.get("uid") else None
    inner = render_template_string(body, user=user, **kwargs)
    return render_template_string(BASE, title=title, content=inner, user=user)

@app.route("/")
def home():
    con=db()
    stats={
      "users":con.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
      "orgs":con.execute("SELECT COUNT(*) FROM organizations").fetchone()[0],
      "events":con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
      "animals":con.execute("SELECT COUNT(*) FROM animal_posts").fetchone()[0]}
    return page("Басты бет", """
    <section class="hero"><h1>Жақсылық жасауды бірге бастайық!</h1>
    <p class="muted">Қызылордадағы волонтерлерді, ұйымдарды және пайдалы бастамаларды біріктіретін платформа.</p>
    <a class="btn" href="/events">Іс-шараларды көру</a> <a class="btn" href="/stats">Статистиканы көру</a></section>
    <div class="grid">{% for k,v in stats.items() %}<div class="card"><h2>{{v}}</h2><span class="muted">{{ {'users':'Ерікті','orgs':'Ұйым','events':'Іс-шара','animals':'Жануарларға көмек жазбасы'}[k] }}</span></div>{% endfor %}</div>
    <div class="grid"><div class="card"><h2>🤝 Волонтерлік</h2><p>Қоғамдық шараларға қатысып, тәжірибе жинаңыз.</p></div>
    <div class="card"><h2>🐾 Жануарларды қорғау</h2><p>Жануарларға көмек, асырап алу және жоғалған жануар туралы хабарландыру.</p></div>
    <div class="card"><h2>📣 Көмек сұрау</h2><p>Қажетті көмек туралы хабарлама жариялаңыз.</p></div></div>
    """, stats=stats)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower()
        password=request.form["password"]
        try:
            db().execute("INSERT INTO users(name,email,password,phone) VALUES(?,?,?,?)",
                         (name,email,generate_password_hash(password),request.form.get("phone","")))
            db().commit(); flash("Тіркелу сәтті аяқталды. Енді жүйеге кіріңіз.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Бұл email бұрын тіркелген.")
    return page("Тіркелу", """<form method="post"><h2>Тіркелу</h2>
    Аты-жөні<input name="name" required> Email<input type="email" name="email" required>
    Телефон<input name="phone"> Құпиясөз<input type="password" name="password" minlength="6" required>
    <button>Тіркелу</button></form>""")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=db().execute("SELECT * FROM users WHERE email=?", (request.form["email"].lower(),)).fetchone()
        if u and check_password_hash(u["password"],request.form["password"]):
            session["uid"]=u["id"]; return redirect(url_for("home"))
        flash("Email немесе құпиясөз қате.")
    return page("Кіру", """<form method="post"><h2>Жүйеге кіру</h2>
    Email<input type="email" name="email" required> Құпиясөз<input type="password" name="password" required>
    <button>Кіру</button></form>""")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.route("/organizations")
def organizations():
    rows=db().execute("SELECT * FROM organizations ORDER BY name").fetchall()
    return page("Ұйымдар", """<h1>Волонтерлік ұйымдар мен топтар</h1><p class="muted">Мүшелер саны әкімші енгізген дерек бойынша көрсетіледі.</p>
    {% for x in rows %}<div class="card"><h2>{{x.name}}</h2><b>{{x.category}}</b><p>{{x.description}}</p>
    <p>📍 {{x.address}} · 👥 {{x.members}} мүше</p><p>Байланыс: {{x.contact}}</p></div>{% else %}<div class="card">Әзірге ұйымдар қосылмаған.</div>{% endfor %}""", rows=rows)

@app.route("/events", methods=["GET","POST"])
def events():
    if request.method=="POST":
        if not session.get("uid"): return redirect(url_for("login"))
        db().execute("INSERT INTO events(title,description,place,event_date,capacity,created_by,hours_value) VALUES(?,?,?,?,?,?,?)",
          (request.form["title"],request.form.get("description",""),request.form.get("place",""),
           request.form.get("event_date",""),max(1,int(request.form.get("capacity",30))),session["uid"],
           max(0.5, float(request.form.get("hours_value",2)))))
        db().commit(); return redirect(url_for("events"))
    rows=db().execute("""SELECT e.*, (SELECT COUNT(*) FROM event_members m WHERE m.event_id=e.id) joined
                         FROM events e ORDER BY e.event_date""").fetchall()
    return page("Іс-шаралар", """<h1>Волонтерлік іс-шаралар</h1>
    {% if user %}<form method="post"><h2>Жаңа іс-шара қосу</h2>Атауы<input name="title" required>
    Сипаттамасы<textarea name="description"></textarea>Өтетін орны<input name="place">
    Күні<input type="date" name="event_date">Қатысушы шегі<input type="number" name="capacity" value="30" min="1">
    Волонтерлік сағат<input type="number" name="hours_value" value="2" min="0.5" step="0.5">
    <button>Жариялау</button></form>{% endif %}
    {% for e in rows %}<div class="card"><h2>{{e.title}}</h2><p>{{e.description}}</p>
    <p>📍 {{e.place}} · 📅 {{e.event_date}} · 👥 {{e.joined}}/{{e.capacity}} · ⏱ {{e.hours_value or 2}} сағат</p>
    <div class="progress"><span style="width:{{ (e.joined * 100 / e.capacity) if e.capacity else 0 }}%"></span></div>
    {% if user and e.joined < e.capacity %}<form method="post" action="/join/{{e.id}}" style="box-shadow:none;padding:0;margin:8px 0"><button>Қатысу</button></form>{% elif e.joined >= e.capacity %}<b class="danger">Орын жоқ — тіркелу жабық</b>{% endif %}
    {% if user and user.is_admin %}<a class="btn" href="/admin/event/{{e.id}}">Қатысушыларды басқару</a>{% endif %}</div>
    {% else %}<div class="card">Іс-шара әзірге жоқ.</div>{% endfor %}""", rows=rows)

@app.route("/join/<int:event_id>", methods=["POST"])
@login_required
def join(event_id):
    con = db()
    try:
        # Бір мезетте бірнеше адам тіркелсе де орын санын асырмау
        con.execute("BEGIN IMMEDIATE")
        e = con.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not e:
            con.rollback()
            flash("Іс-шара табылмады.")
        else:
            already = con.execute(
                "SELECT id FROM event_members WHERE event_id=? AND user_id=?",
                (event_id, session["uid"])
            ).fetchone()
            count = con.execute(
                "SELECT COUNT(*) FROM event_members WHERE event_id=?", (event_id,)
            ).fetchone()[0]
            if already:
                con.rollback()
                flash("Сіз бұл іс-шараға тіркелгенсіз.")
            elif count >= e["capacity"]:
                con.rollback()
                flash("Қатысушы саны толды. Тіркелу жабық.")
            else:
                con.execute("INSERT INTO event_members(event_id,user_id) VALUES(?,?)",
                            (event_id, session["uid"]))
                con.commit()
                flash("Іс-шараға сәтті тіркелдіңіз.")
    except sqlite3.Error:
        con.rollback()
        flash("Тіркелу кезінде қате шықты. Қайталап көріңіз.")
    return redirect(url_for("events"))

@app.route("/animals", methods=["GET","POST"])
def animals():
    if request.method=="POST":
        if not session.get("uid"): return redirect(url_for("login"))
        db().execute("INSERT INTO animal_posts(animal,kind,description,location,contact,author_id) VALUES(?,?,?,?,?,?)",
          (request.form["animal"],request.form["kind"],request.form.get("description",""),
           request.form.get("location",""),request.form["contact"],session["uid"]))
        db().commit(); return redirect(url_for("animals"))
    rows=db().execute("SELECT * FROM animal_posts ORDER BY id DESC").fetchall()
    return page("Жануарларға көмек", """<h1>🐾 Жануарларды қорғау бөлімі</h1>
    {% if user %}<form method="post"><h2>Хабарландыру жариялау</h2>Жануар түрі<input name="animal" placeholder="Ит, мысық..." required>
    Хабарландыру түрі<select name="kind"><option>Көмек қажет</option><option>Асырап алу</option><option>Жоғалған жануар</option><option>Табылған жануар</option><option>Еріктілер іздейміз</option></select>
    Сипаттамасы<textarea name="description"></textarea>Орналасқан жері<input name="location">
    Байланыс телефоны<input name="contact" required><button>Жариялау</button></form>{% endif %}
    {% for x in rows %}<div class="card"><h2>{{x.animal}} · {{x.kind}}</h2><p>{{x.description}}</p><p>📍 {{x.location}} · ☎ {{x.contact}}</p></div>
    {% else %}<div class="card">Хабарландыру жоқ.</div>{% endfor %}""", rows=rows)

@app.route("/help", methods=["GET","POST"])
def help_board():
    if request.method=="POST":
        if not session.get("uid"): return redirect(url_for("login"))
        db().execute("INSERT INTO help_requests(title,description,contact,author_id) VALUES(?,?,?,?)",
          (request.form["title"],request.form.get("description",""),request.form["contact"],session["uid"]))
        db().commit(); return redirect(url_for("help_board"))
    rows=db().execute("SELECT * FROM help_requests ORDER BY id DESC").fetchall()
    return page("Көмек сұрау", """<h1>Көмек сұрау тақтасы</h1>
    {% if user %}<form method="post">Тақырып<input name="title" required>Толық ақпарат<textarea name="description"></textarea>
    Байланыс<input name="contact" required><button>Жариялау</button></form>{% endif %}
    {% for x in rows %}<div class="card"><h2>{{x.title}}</h2><p>{{x.description}}</p><p>Байланыс: {{x.contact}}</p></div>{% else %}<div class="card">Сұраныс жоқ.</div>{% endfor %}""", rows=rows)

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    if request.method=="POST":
        db().execute("INSERT INTO hours(user_id,amount,note) VALUES(?,?,?)",
                     (session["uid"],float(request.form["amount"]),request.form.get("note","")))
        db().commit()
    u=db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
    total=db().execute("SELECT COALESCE(SUM(amount),0) FROM hours WHERE user_id=?", (session["uid"],)).fetchone()[0]
    joined=db().execute("SELECT COUNT(*) FROM event_members WHERE user_id=?", (session["uid"],)).fetchone()[0]
    certs=db().execute("""SELECT c.cert_no,c.id,e.title,c.issued_at FROM certificates c
                          JOIN events e ON e.id=c.event_id WHERE c.user_id=? ORDER BY c.id DESC""",
                       (session["uid"],)).fetchall()
    return page("Профиль", """<div class="card"><h1>{{u.name}}</h1><p>{{u.email}} · {{u.phone}}</p>
    <h2>{{total}} волонтерлік сағат</h2><p>{{joined}} іс-шараға тіркелгенсіз.</p></div>
    <div class="card"><h2>🏅 Менің сертификаттарым</h2>
    {% for c in certs %}<p><b>{{c.title}}</b> · {{c.cert_no}} · <a href="/certificate/{{c.id}}/pdf">PDF жүктеу</a></p>
    {% else %}<p class="muted">Әзірге сертификат жоқ. Іс-шараға қатысуыңызды әкімші растағаннан кейін пайда болады.</p>{% endfor %}</div>
    <form method="post"><h2>Волонтерлік сағат қосу</h2>Сағат саны<input type="number" name="amount" min="0.5" step="0.5" required>
    Атқарылған жұмыс<input name="note"><button>Сақтау</button></form>""", u=u,total=total,joined=joined,certs=certs)

@app.route("/admin", methods=["GET","POST"])
@admin_required
def admin():
    if request.method=="POST":
        db().execute("""INSERT INTO organizations(name,category,description,address,contact,members)
        VALUES(?,?,?,?,?,?)""",(request.form["name"],request.form["category"],request.form.get("description",""),
        request.form.get("address",""),request.form.get("contact",""),int(request.form.get("members",0))))
        db().commit(); flash("Ұйым қосылды.")
    orgs=db().execute("SELECT * FROM organizations ORDER BY id DESC").fetchall()
    events_admin=db().execute("""SELECT e.*,(SELECT COUNT(*) FROM event_members m WHERE m.event_id=e.id) joined
                                 FROM events e ORDER BY e.event_date DESC""").fetchall()
    return page("Әкімші", """<h1>Әкімші панелі</h1><form method="post"><h2>Ұйым/волонтерлік топ қосу</h2>
    Атауы<input name="name" required>Бағыты<select name="category"><option>Қоғамдық волонтерлік</option>
    <option>Жануарларды қорғау</option><option>Экологиялық</option><option>Медициналық</option>
    <option>Әлеуметтік көмек</option><option>Жастар ұйымы</option><option>Басқа</option></select>
    Сипаттамасы<textarea name="description"></textarea>Мекенжайы<input name="address">
    Байланыс<input name="contact">Мүшелер саны<input type="number" name="members" min="0" value="0">
    <button>Ұйымды сақтау</button></form><h2>Қосылған ұйымдар</h2>
    {% for x in orgs %}<div class="card">{{x.name}} — {{x.category}} — {{x.members}} мүше</div>{% else %}<p>Әзірге ұйым жоқ.</p>{% endfor %}
    <h2>Іс-шаралар және қатысуды растау</h2>
    {% for e in events_admin %}<div class="card"><b>{{e.title}}</b><p>{{e.joined}}/{{e.capacity}} орын · {{e.event_date}}</p>
    <a class="btn" href="/admin/event/{{e.id}}">Қатысушыларды басқару</a></div>{% else %}<p>Іс-шара жоқ.</p>{% endfor %}
    <p><a href="/stats">Графикалық статистика →</a></p>""", orgs=orgs,events_admin=events_admin)


@app.route("/admin/event/<int:event_id>", methods=["GET"])
@admin_required
def admin_event(event_id):
    event = db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        abort(404)
    people = db().execute("""SELECT m.id AS member_id,m.attended,m.hours_awarded,
                            u.id AS user_id,u.name,u.email
                            FROM event_members m JOIN users u ON u.id=m.user_id
                            WHERE m.event_id=? ORDER BY u.name""", (event_id,)).fetchall()
    return page("Қатысушылар", """
    <div class="card"><h1>{{event.title}}</h1><p>{{event.event_date}} · {{event.place}}</p>
    <p>Қатысушылар: {{people|length}} / {{event.capacity}}</p>
    {% for p in people %}<div class="card">
      <b>{{p.name}}</b><p>{{p.email}}</p>
      {% if p.attended %}<span class="tag">Қатысуы расталды</span>
        <a href="/certificate/{{p.user_id}}/{{event.id}}/pdf">Сертификатты жүктеу</a>
      {% else %}<span class="tag">Расталмаған</span>
        <form method="post" action="/admin/attendance/{{event.id}}/{{p.user_id}}" style="box-shadow:none;padding:0">
          <button>Қатысқанын растау және сертификат беру</button>
        </form>
      {% endif %}
    </div>{% else %}<p>Әзірге тіркелген адам жоқ.</p>{% endfor %}
    <a href="/admin">Әкімші панеліне қайту</a></div>
    """, event=event, people=people)


@app.route("/admin/attendance/<int:event_id>/<int:user_id>", methods=["POST"])
@admin_required
def approve_attendance(event_id, user_id):
    con = db()
    member = con.execute("""SELECT m.*,e.title,e.hours_value FROM event_members m
                            JOIN events e ON e.id=m.event_id
                            WHERE m.event_id=? AND m.user_id=?""",
                         (event_id, user_id)).fetchone()
    if not member:
        flash("Қатысушы табылмады.")
        return redirect(url_for("admin_event", event_id=event_id))
    if not member["attended"]:
        con.execute("UPDATE event_members SET attended=1,hours_awarded=1 WHERE event_id=? AND user_id=?",
                    (event_id, user_id))
        con.execute("INSERT INTO hours(user_id,amount,note) VALUES(?,?,?)",
                    (user_id, float(member["hours_value"] or 2), "Расталған іс-шара: " + member["title"]))
        cur = con.execute("INSERT INTO certificates(cert_no,event_id,user_id) VALUES(?,?,?)",
                          ("TEMP-" + datetime.now().strftime("%Y%m%d%H%M%S%f"), event_id, user_id))
        cert_id = cur.lastrowid
        cert_no = "VH-" + str(cert_id).zfill(6)
        con.execute("UPDATE certificates SET cert_no=? WHERE id=?", (cert_no, cert_id))
        con.commit()
        flash("Қатысу расталды. Сертификат дайын.")
    else:
        flash("Бұл қатысушының қатысуы бұрын расталған.")
    return redirect(url_for("admin_event", event_id=event_id))


@app.route("/certificate/<int:cert_id>/pdf")
@login_required
def certificate_pdf_by_id(cert_id):
    cert = db().execute("""SELECT c.*,u.name,e.title,e.event_date,e.hours_value
                           FROM certificates c JOIN users u ON u.id=c.user_id
                           JOIN events e ON e.id=c.event_id WHERE c.id=?""",
                        (cert_id,)).fetchone()
    if not cert:
        abort(404)
    current = db().execute("SELECT is_admin FROM users WHERE id=?", (session["uid"],)).fetchone()
    if cert["user_id"] != session["uid"] and not (current and current["is_admin"]):
        abort(403)
    return make_certificate_pdf(cert)


@app.route("/certificate/<int:user_id>/<int:event_id>/pdf")
@login_required
def certificate_pdf_by_event(user_id, event_id):
    current = db().execute("SELECT is_admin FROM users WHERE id=?", (session["uid"],)).fetchone()
    if not current or not current["is_admin"]:
        abort(403)
    cert = db().execute("""SELECT c.*,u.name,e.title,e.event_date,e.hours_value
                           FROM certificates c JOIN users u ON u.id=c.user_id
                           JOIN events e ON e.id=c.event_id
                           WHERE c.user_id=? AND c.event_id=?""", (user_id,event_id)).fetchone()
    if not cert:
        abort(404)
    return make_certificate_pdf(cert)


def make_certificate_pdf(cert):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import qrcode
    except ImportError:
        flash("PDF жасауға қажетті кітапханалар орнатылмаған. requirements.txt файлын жаңартыңыз.")
        return redirect(url_for("profile"))

    output = io.BytesIO()
    width, height = landscape(A4)
    pdf = canvas.Canvas(output, pagesize=(width, height))
    # Қазақ әріптерін дұрыс көрсету үшін DejaVuSans.ttf қарпі болса тіркеледі.
    font_name = "Helvetica"
    font_candidates = [
        os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("VolunteerUnicode", font_path))
                font_name = "VolunteerUnicode"
                break
            except Exception:
                pass

    # Жақтауы және безендірілуі
    pdf.setLineWidth(3)
    pdf.setStrokeColorRGB(0.05, 0.40, 0.38)
    pdf.rect(25, 25, width-50, height-50)
    pdf.setLineWidth(1)
    pdf.setStrokeColorRGB(0.65, 0.78, 0.76)
    pdf.rect(34, 34, width-68, height-68)
    pdf.setFillColorRGB(0.06, 0.25, 0.36)
    pdf.setFont(font_name, 29)
    pdf.drawCentredString(width/2, height-105, "СЕРТИФИКАТ")
    pdf.setFillColorRGB(0.05, 0.48, 0.43)
    pdf.setFont(font_name, 13)
    pdf.drawCentredString(width/2, height-135, "БЕЛСЕНДІ ҚАТЫСҚАНЫ ҮШІН")
    pdf.setFillColorRGB(0.12, 0.16, 0.22)
    pdf.setFont(font_name, 15)
    pdf.drawCentredString(width/2, height-190, "Осы сертификат беріледі:")
    pdf.setFont(font_name, 25)
    pdf.drawCentredString(width/2, height-230, cert["name"])
    pdf.setFont(font_name, 14)
    pdf.drawCentredString(width/2, height-270, "«" + cert["title"] + "» іс-шарасына қатысқаны үшін")
    pdf.drawCentredString(width/2, height-298, "Волонтерлік сағат: " + str(cert["hours_value"] or 2))
    pdf.drawCentredString(width/2, height-326, "Өткізілген күні: " + (cert["event_date"] or "Күні көрсетілмеген"))
    pdf.setFont(font_name, 11)
    pdf.drawString(65, 70, "Сертификат № " + cert["cert_no"])
    pdf.drawString(65, 52, "Volunteer Hub · Қызылорда")
    pdf.drawRightString(width-65, 70, "Ұйымдастырушы: __________________")
    # QR код сертификатты тексеру бетіне апарады
    verify_url = url_for("verify_certificate", cert_no=cert["cert_no"], _external=True)
    qr_img = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    from reportlab.lib.utils import ImageReader
    pdf.drawImage(ImageReader(qr_buffer), width-145, 48, width=75, height=75, preserveAspectRatio=True)
    pdf.showPage()
    pdf.save()
    output.seek(0)
    return send_file(output, mimetype="application/pdf", as_attachment=True,
                     download_name=cert["cert_no"] + ".pdf")


@app.route("/verify/<cert_no>")
def verify_certificate(cert_no):
    cert = db().execute("""SELECT c.cert_no,c.issued_at,u.name,e.title,e.event_date,e.hours_value
                           FROM certificates c JOIN users u ON u.id=c.user_id
                           JOIN events e ON e.id=c.event_id WHERE c.cert_no=?""",
                        (cert_no,)).fetchone()
    if not cert:
        return page("Сертификат", "<div class='card'><h1>Сертификат табылмады</h1><p>Нөмір қате немесе сертификат жарамсыз.</p></div>"), 404
    return page("Сертификатты тексеру", """
    <div class="card"><span class="tag">Сертификат расталды</span><h1>№ {{c.cert_no}}</h1>
    <h2>{{c.name}}</h2><p>Іс-шара: {{c.title}}</p><p>Күні: {{c.event_date}}</p>
    <p>Волонтерлік сағат: {{c.hours_value or 2}}</p><p class="muted">Берілген күні: {{c.issued_at}}</p></div>
    """, c=cert)


@app.route("/stats")
def stats():
    con = db()
    total_users = con.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0]
    total_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_orgs = con.execute("SELECT COUNT(*) FROM organizations").fetchone()[0]
    total_hours = con.execute("SELECT COALESCE(SUM(amount),0) FROM hours").fetchone()[0]
    event_labels = [r["label"] or "Күні белгісіз" for r in con.execute(
        "SELECT event_date AS label FROM events ORDER BY event_date").fetchall()]
    event_values = [r["count"] for r in con.execute(
        "SELECT COUNT(m.id) AS count FROM events e LEFT JOIN event_members m ON m.event_id=e.id GROUP BY e.id ORDER BY e.event_date").fetchall()]
    org_rows = con.execute("SELECT category,COUNT(*) AS amount FROM organizations GROUP BY category").fetchall()
    org_labels = [r["category"] for r in org_rows]
    org_values = [r["amount"] for r in org_rows]
    return page("Графикалық статистика", """
    <h1>📊 Volunteer Hub статистикасы</h1>
    <div class="grid">
      <div class="card"><h2>{{users}}</h2><span class="muted">Тіркелген волонтер</span></div>
      <div class="card"><h2>{{events}}</h2><span class="muted">Іс-шара</span></div>
      <div class="card"><h2>{{orgs}}</h2><span class="muted">Ұйым</span></div>
      <div class="card"><h2>{{hours}}</h2><span class="muted">Волонтерлік сағат</span></div>
    </div>
    <div class="chartbox"><h2>Іс-шаралардағы тіркелушілер</h2><canvas id="eventChart"></canvas></div>
    <div class="chartbox"><h2>Ұйымдар бағыттары</h2><canvas id="orgChart"></canvas></div>
    <p class="muted">Көрсеткіштер сайттың деректер қорынан автоматты түрде алынады.</p>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
    const eventLabels = {{ event_labels|tojson }};
    const eventValues = {{ event_values|tojson }};
    const orgLabels = {{ org_labels|tojson }};
    const orgValues = {{ org_values|tojson }};
    new Chart(document.getElementById('eventChart'), {
      type:'bar', data:{labels:eventLabels,datasets:[{label:'Тіркелушілер',data:eventValues}]},
      options:{responsive:true,plugins:{legend:{display:true}}}
    });
    new Chart(document.getElementById('orgChart'), {
      type:'doughnut', data:{labels:orgLabels,datasets:[{label:'Ұйымдар',data:orgValues}]},
      options:{responsive:true}
    });
    </script>
    """, users=total_users,events=total_events,orgs=total_orgs,hours=round(total_hours,1),
    event_labels=event_labels,event_values=event_values,org_labels=org_labels,org_values=org_values)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
