import io, os, secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from db import get_db, init_app
from logic import BusinessError, validate_event, can_register, certificate_allowed

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    init_app(app)

    @app.before_request
    def csrf_guard():
        if request.method == "POST":
            token = session.get("_csrf")
            submitted = request.form.get("_csrf")
            if not token or not submitted or not secrets.compare_digest(token, submitted):
                abort(400, "Қауіпсіздік токені жарамсыз. Бетті жаңартыңыз.")

    @app.context_processor
    def inject_globals():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["_csrf"], "current_user": session.get("user")}

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user"):
                flash("Алдымен жүйеге кіріңіз.", "warning")
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return wrapper

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user") or session["user"]["role"] != "admin":
                abort(403)
            return fn(*args, **kwargs)
        return wrapper

    @app.get("/")
    def index():
        db = get_db()
        events = db.execute("""SELECT e.*,
            (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registered
            FROM events e WHERE e.status != 'cancelled' ORDER BY e.event_date""").fetchall()
        return render_template("index.html", events=events)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name","").strip()
            email = request.form.get("email","").strip().lower()
            password = request.form.get("password","")
            if not name or len(name) > 80 or "@" not in email or len(password) < 8:
                flash("Аты-жөнін, дұрыс email және кемінде 8 таңбалы құпиясөз енгізіңіз.", "danger")
            else:
                try:
                    get_db().execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                        (name,email,generate_password_hash(password)))
                    get_db().commit()
                    flash("Тіркелу сәтті аяқталды. Жүйеге кіріңіз.", "success")
                    return redirect(url_for("login"))
                except Exception:
                    get_db().rollback()
                    flash("Бұл email бұрын тіркелген болуы мүмкін.", "danger")
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email","").strip().lower()
            user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], request.form.get("password","")):
                session.clear()
                session["user"] = {"id": user["id"], "name": user["name"], "role": user["role"]}
                session["_csrf"] = secrets.token_urlsafe(32)
                return redirect(url_for("index"))
            flash("Email немесе құпиясөз қате.", "danger")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.get("/events/<int:event_id>")
    def event_detail(event_id):
        db = get_db()
        event = db.execute("""SELECT e.*,(SELECT COUNT(*) FROM registrations r
            WHERE r.event_id=e.id) registered FROM events e WHERE e.id=?""",(event_id,)).fetchone()
        if not event: abort(404)
        joined = False
        if session.get("user"):
            joined = db.execute("SELECT 1 FROM registrations WHERE user_id=? AND event_id=?",
                (session["user"]["id"],event_id)).fetchone() is not None
        return render_template("event.html", event=event, joined=joined)

    @app.post("/events/<int:event_id>/join")
    @login_required
    def join_event(event_id):
        db=get_db()
        db.execute("BEGIN IMMEDIATE")
        event=db.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone()
        if not event:
            db.rollback(); abort(404)
        count=db.execute("SELECT COUNT(*) FROM registrations WHERE event_id=?",(event_id,)).fetchone()[0]
        if event["status"] != "open" or not can_register(event["capacity"],count):
            db.rollback(); flash("Орын жоқ немесе тіркелу жабық.","warning")
        else:
            try:
                db.execute("INSERT INTO registrations(user_id,event_id) VALUES(?,?)",
                    (session["user"]["id"],event_id))
                db.commit(); flash("Іс-шараға сәтті тіркелдіңіз!","success")
            except Exception:
                db.rollback(); flash("Сіз бұл іс-шараға бұрын тіркелгенсіз.","warning")
        return redirect(url_for("event_detail",event_id=event_id))

    @app.get("/my")
    @login_required
    def my_events():
        rows=get_db().execute("""SELECT e.*,r.attended,r.id registration_id
            FROM registrations r JOIN events e ON e.id=r.event_id
            WHERE r.user_id=? ORDER BY e.event_date""",(session["user"]["id"],)).fetchall()
        return render_template("my.html", rows=rows)

    @app.get("/admin")
    @admin_required
    def admin():
        db=get_db()
        events=db.execute("""SELECT e.*,(SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) registered
            FROM events e ORDER BY e.event_date""").fetchall()
        stats=db.execute("""SELECT COUNT(*) users,
            (SELECT COUNT(*) FROM events) events,
            (SELECT COUNT(*) FROM registrations) registrations FROM users""").fetchone()
        # Matplotlib chart is generated locally from aggregate DB values.
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            labels=["Пайдаланушылар","Іс-шаралар","Тіркелулер"]
            values=[stats["users"],stats["events"],stats["registrations"]]
            fig,ax=plt.subplots(figsize=(6,3.2)); ax.bar(labels,values)
            ax.set_title("Портал статистикасы"); ax.set_ylabel("Саны")
            fig.tight_layout()
            os.makedirs(app.static_folder,exist_ok=True)
            fig.savefig(os.path.join(app.static_folder,"stats.png"),dpi=120)
            plt.close(fig)
        except Exception:
            pass
        return render_template("admin.html",events=events,stats=stats)

    @app.route("/admin/events/new", methods=["GET","POST"])
    @admin_required
    def new_event():
        if request.method=="POST":
            try:
                data=validate_event(request.form.get("title"),request.form.get("description"),
                    request.form.get("capacity"),request.form.get("event_date"))
                get_db().execute("""INSERT INTO events(title,description,capacity,event_date,location,created_by)
                    VALUES(?,?,?,?,?,?)""",(data["title"],data["description"],data["capacity"],
                    data["event_date"],request.form.get("location","").strip(),session["user"]["id"]))
                get_db().commit(); flash("Іс-шара қосылды.","success"); return redirect(url_for("admin"))
            except BusinessError as exc: flash(str(exc),"danger")
        return render_template("new_event.html")

    @app.post("/admin/events/<int:event_id>/complete")
    @admin_required
    def complete_event(event_id):
        db=get_db()
        db.execute("UPDATE events SET status='completed' WHERE id=?",(event_id,))
        db.commit()
        flash("Іс-шара аяқталды. Енді қатысқан еріктілер сертификат ала алады.","success")
        return redirect(url_for("admin"))

    @app.post("/admin/registrations/<int:registration_id>/attendance")
    @admin_required
    def attendance(registration_id):
        db=get_db()
        db.execute("UPDATE registrations SET attended=1 WHERE id=?",(registration_id,))
        db.commit()
        flash("Қатысу белгіленді.","success")
        return redirect(url_for("admin"))

    @app.get("/certificate/<int:event_id>")
    @login_required
    def certificate(event_id):
        row=get_db().execute("""SELECT u.name,e.title,e.event_date,e.status,r.attended
            FROM registrations r JOIN users u ON u.id=r.user_id JOIN events e ON e.id=r.event_id
            WHERE r.user_id=? AND r.event_id=?""",(session["user"]["id"],event_id)).fetchone()
        if not row: abort(404)
        if not certificate_allowed(row["status"],row["attended"]):
            flash("Сертификат іс-шара аяқталып, қатысу расталғаннан кейін беріледі.","warning")
            return redirect(url_for("my_events"))
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase import pdfmetrics
        from reportlab.lib import colors
        buffer=io.BytesIO()
        pdf=canvas.Canvas(buffer,pagesize=landscape(A4))
        w,h=landscape(A4)
        pdf.setStrokeColor(colors.HexColor("#1d6b59")); pdf.setLineWidth(4); pdf.rect(25,25,w-50,h-50)
        # Helvetica is used for portability; Latin transliteration keeps PDF text reliable.
        pdf.setFont("Helvetica-Bold",28); pdf.drawCentredString(w/2,h-145,"CERTIFICATE")
        pdf.setFont("Helvetica",16); pdf.drawCentredString(w/2,h-195,"This certificate is awarded to")
        pdf.setFont("Helvetica-Bold",24); pdf.drawCentredString(w/2,h-245,row["name"])
        pdf.setFont("Helvetica",14); pdf.drawCentredString(w/2,h-290,"for participating in the volunteer event:")
        pdf.setFont("Helvetica-Bold",18); pdf.drawCentredString(w/2,h-325,row["title"][:70])
        pdf.setFont("Helvetica",12); pdf.drawCentredString(w/2,90,f"Event date: {row['event_date']}  |  Volunteer Hub")
        pdf.save(); buffer.seek(0)
        return send_file(buffer,mimetype="application/pdf",as_attachment=True,
            download_name=f"certificate_{event_id}.pdf")

    @app.errorhandler(403)
    def forbidden(_): return render_template("error.html",code=403,message="Бұл бөлімге рұқсатыңыз жоқ."),403
    @app.errorhandler(404)
    def not_found(_): return render_template("error.html",code=404,message="Бет немесе жазба табылмады."),404
    @app.errorhandler(400)
    def bad_request(_): return render_template("error.html",code=400,message="Сұраныс жарамсыз. Бетті жаңартып көріңіз."),400
    return app

app=create_app()
if __name__=="__main__":
    app.run(debug=True)
