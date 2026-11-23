import os
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, g
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
        """)
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
</style>
<header><b>🌱 Volunteer Hub</b><nav>
<a href="/">Басты бет</a><a href="/organizations">Ұйымдар</a><a href="/events">Іс-шаралар</a>
<a href="/animals">Жануарларға көмек</a><a href="/help">Көмек сұрау</a>
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
    <a class="btn" href="/events">Іс-шараларды көру</a></section>
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
        db().execute("INSERT INTO events(title,description,place,event_date,capacity,created_by) VALUES(?,?,?,?,?,?)",
          (request.form["title"],request.form.get("description",""),request.form.get("place",""),
           request.form.get("event_date",""),max(1,int(request.form.get("capacity",30))),session["uid"]))
        db().commit(); return redirect(url_for("events"))
    rows=db().execute("""SELECT e.*, (SELECT COUNT(*) FROM event_members m WHERE m.event_id=e.id) joined
                         FROM events e ORDER BY e.event_date""").fetchall()
    return page("Іс-шаралар", """<h1>Волонтерлік іс-шаралар</h1>
    {% if user %}<form method="post"><h2>Жаңа іс-шара қосу</h2>Атауы<input name="title" required>
    Сипаттамасы<textarea name="description"></textarea>Өтетін орны<input name="place">
    Күні<input type="date" name="event_date">Қатысушы шегі<input type="number" name="capacity" value="30" min="1">
    <button>Жариялау</button></form>{% endif %}
    {% for e in rows %}<div class="card"><h2>{{e.title}}</h2><p>{{e.description}}</p>
    <p>📍 {{e.place}} · 📅 {{e.event_date}} · 👥 {{e.joined}}/{{e.capacity}}</p>
    {% if user and e.joined < e.capacity %}<a class="btn" href="/join/{{e.id}}">Қатысу</a>{% elif e.joined >= e.capacity %}<b>Орын жоқ</b>{% endif %}</div>
    {% else %}<div class="card">Іс-шара әзірге жоқ.</div>{% endfor %}""", rows=rows)

@app.route("/join/<int:event_id>")
@login_required
def join(event_id):
    e=db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if e:
        count=db().execute("SELECT COUNT(*) FROM event_members WHERE event_id=?", (event_id,)).fetchone()[0]
        if count < e["capacity"]:
            try:
                db().execute("INSERT INTO event_members(event_id,user_id) VALUES(?,?)",(event_id,session["uid"]))
                db().commit(); flash("Іс-шараға тіркелдіңіз.")
            except sqlite3.IntegrityError: flash("Сіз бұл іс-шараға тіркелгенсіз.")
        else: flash("Қатысушы саны толды.")
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
    return page("Профиль", """<div class="card"><h1>{{u.name}}</h1><p>{{u.email}} · {{u.phone}}</p>
    <h2>{{total}} волонтерлік сағат</h2><p>{{joined}} іс-шараға тіркелгенсіз.</p></div>
    <form method="post"><h2>Волонтерлік сағат қосу</h2>Сағат саны<input type="number" name="amount" min="0.5" step="0.5" required>
    Атқарылған жұмыс<input name="note"><button>Сақтау</button></form>""", u=u,total=total,joined=joined)

@app.route("/admin", methods=["GET","POST"])
@admin_required
def admin():
    if request.method=="POST":
        db().execute("""INSERT INTO organizations(name,category,description,address,contact,members)
        VALUES(?,?,?,?,?,?)""",(request.form["name"],request.form["category"],request.form.get("description",""),
        request.form.get("address",""),request.form.get("contact",""),int(request.form.get("members",0))))
        db().commit(); flash("Ұйым қосылды.")
    orgs=db().execute("SELECT * FROM organizations ORDER BY id DESC").fetchall()
    return page("Әкімші", """<h1>Әкімші панелі</h1><form method="post"><h2>Ұйым/волонтерлік топ қосу</h2>
    Атауы<input name="name" required>Бағыты<select name="category"><option>Қоғамдық волонтерлік</option>
    <option>Жануарларды қорғау</option><option>Экологиялық</option><option>Медициналық</option>
    <option>Әлеуметтік көмек</option><option>Жастар ұйымы</option><option>Басқа</option></select>
    Сипаттамасы<textarea name="description"></textarea>Мекенжайы<input name="address">
    Байланыс<input name="contact">Мүшелер саны<input type="number" name="members" min="0" value="0">
    <button>Ұйымды сақтау</button></form><h2>Қосылған ұйымдар</h2>
    {% for x in orgs %}<div class="card">{{x.name}} — {{x.category}} — {{x.members}} мүше</div>{% else %}<p>Әзірге ұйым жоқ.</p>{% endfor %}""", orgs=orgs)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
