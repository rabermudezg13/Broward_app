import os, re, sqlite3, secrets, hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from functools import wraps
from pathlib import Path
from flask import Flask, request, jsonify, g, send_from_directory
from flask_limiter import Limiter

app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 16384
DB = os.environ.get('DATABASE_PATH', '/data/broward.db')
ADMIN = 'cculturausallc@gmail.com'
ROLES = ('staff', 'management', 'admin')
VISIT_REASONS = ('Badge Pickup', 'Fingerprinting', 'Talent Advisor Question', 'Speak with My Onboarder', 'Incident Question', 'Other')
limiter = Limiter(key_func=lambda: request.remote_addr, app=app, default_limits=['120 per minute'], storage_uri='memory://')

def now(): return datetime.now(timezone.utc).isoformat()
def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close(_):
    if 'db' in g: g.db.close()

def initialize():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        db().executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expires TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY, first_name TEXT NOT NULL,last_name TEXT NOT NULL,email TEXT NOT NULL,phone TEXT NOT NULL,zip_code TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'waiting',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,handled_by INTEGER REFERENCES users(id));
        CREATE INDEX IF NOT EXISTS visits_arrival ON visits(created_at,id);
        ''')
        columns={row['name'] for row in db().execute('PRAGMA table_info(visits)')}
        if 'visit_reason' not in columns:
            db().execute("ALTER TABLE visits ADD COLUMN visit_reason TEXT NOT NULL DEFAULT ''")
        password = os.environ.get('ADMIN_INITIAL_PASSWORD')
        if password and not db().execute('SELECT id FROM users WHERE email=?',(ADMIN,)).fetchone():
            from werkzeug.security import generate_password_hash
            db().execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',('Administrator',ADMIN,generate_password_hash(password),'admin'))
        db().commit()

@app.after_request
def headers(r):
    origin = request.headers.get('Origin','')
    allowed = os.environ.get('FRONTEND_ORIGIN','http://localhost:5173').split(',')
    if origin in allowed:
        r.headers['Access-Control-Allow-Origin']=origin
        r.headers['Vary']='Origin'
        r.headers['Access-Control-Allow-Headers']='Content-Type, Authorization'
        r.headers['Access-Control-Allow-Methods']='GET, POST, PATCH, DELETE, OPTIONS'
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['Referrer-Policy']='no-referrer'
    r.headers['Cache-Control']='no-store' if request.path.startswith('/api') else 'no-cache'
    return r

@app.errorhandler(429)
def limited(_): return jsonify(error='Too many attempts. Please wait a minute and try again.'),429
@app.errorhandler(413)
def large(_): return jsonify(error='Request too large.'),413

def auth(admin=False):
    def decorate(f):
        @wraps(f)
        def wrapped(*a,**kw):
            if request.method=='OPTIONS': return '',204
            token=request.headers.get('Authorization','').removeprefix('Bearer ')
            g.user=db().execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()
            if not g.user: return jsonify(error='Please sign in again.'),401
            if admin and g.user['role']!='admin': return jsonify(error='Administrator access required.'),403
            return f(*a,**kw)
        return wrapped
    return decorate

def public_user(u): return {k:u[k] for k in ('id','name','email','role','active')}
def data(): return request.get_json(silent=True) or {}
def text(d,k): return str(d.get(k,'')).strip()
def email_valid(v): return len(v)<=254 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v)

@app.get('/health')
def health():
    db().execute('SELECT 1')
    return jsonify(status='ok')
@app.get('/')
def index(): return send_from_directory(app.static_folder,'index.html')

@app.route('/api/visits',methods=['POST','OPTIONS'])
@limiter.limit('10 per minute')
def checkin():
    if request.method=='OPTIONS': return '',204
    d=data(); fields={k:text(d,k) for k in ('first_name','last_name','email','phone','zip_code')}
    if any(not 1<=len(fields[k])<=80 for k in ('first_name','last_name')) or not email_valid(fields['email']) or not re.fullmatch(r'\d{5}',fields['zip_code']) or not 10<=len(re.sub(r'\D','',fields['phone']))<=15:
        return jsonify(error='Enter your name, valid email, phone number and five-digit ZIP code.'),400
    if len(fields['phone'])>30: return jsonify(error='Phone number is too long.'),400
    reason=text(d,'visit_reason')
    if reason not in VISIT_REASONS: return jsonify(error='Please select a reason for your visit.'),400
    fields['email']=fields['email'].lower()
    stamp=now()
    day=datetime.now(ZoneInfo('America/New_York')).replace(hour=0,minute=0,second=0,microsecond=0)
    start=day.astimezone(timezone.utc).isoformat();end=(day+timedelta(days=1)).astimezone(timezone.utc).isoformat()
    db().execute('BEGIN IMMEDIATE')
    duplicate=db().execute('SELECT id FROM visits WHERE lower(email)=? AND created_at>=? AND created_at<? LIMIT 1',(fields['email'],start,end)).fetchone()
    if duplicate:
        db().rollback()
        return jsonify(error='You have already checked in today. Please take a seat or speak with our front desk team.'),409
    db().execute('INSERT INTO visits(first_name,last_name,email,phone,zip_code,created_at,updated_at,visit_reason) VALUES(?,?,?,?,?,?,?,?)',(*fields.values(),stamp,stamp,reason));db().commit()
    return jsonify(message='You are checked in. Our team will be with you shortly.'),201

@app.route('/api/login',methods=['POST','OPTIONS'])
@limiter.limit('5 per minute')
def login():
    if request.method=='OPTIONS': return '',204
    from werkzeug.security import check_password_hash
    d=data();u=db().execute('SELECT * FROM users WHERE email=? AND active=1',(text(d,'email').lower(),)).fetchone()
    if not u or not check_password_hash(u['password'],text(d,'password')): return jsonify(error='Email or password is incorrect.'),401
    token=secrets.token_urlsafe(48)
    db().execute('DELETE FROM sessions WHERE expires<?',(now(),))
    db().execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()));db().commit()
    return jsonify(token=token,user=public_user(u))

@app.route('/api/logout',methods=['POST','OPTIONS'])
@auth()
def logout():
    token=request.headers.get('Authorization','').removeprefix('Bearer ')
    db().execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),));db().commit();return jsonify(ok=True)
@app.route('/api/me',methods=['GET','OPTIONS'])
@auth()
def me(): return jsonify(public_user(g.user))
@app.route('/api/visits',methods=['GET'])
@auth()
def visits():
    historical=request.args.get('history')=='1'
    today=datetime.now(ZoneInfo('America/New_York')).date()
    monday=today-timedelta(days=today.weekday())
    try:
        if historical:
            query=request.args.get('q','').strip()[:80]
            week=request.args.get('week','')
            start=datetime.strptime(week,'%Y-%m-%d').date() if week else None
            if start: start=start-timedelta(days=start.weekday())
            if not start and not query: return jsonify(error='Choose a week or enter a name.'),400
        else:
            query='';start=monday
        page=max(1,int(request.args.get('page','1')))
    except ValueError: return jsonify(error='Invalid date or page.'),400
    conditions=[];params=[]
    if start:
        begin=datetime.combine(start,datetime.min.time(),tzinfo=ZoneInfo('America/New_York'))
        end=begin+timedelta(days=5)
        conditions+=['v.created_at>=?','v.created_at<?']
        params+=[begin.astimezone(timezone.utc).isoformat(),end.astimezone(timezone.utc).isoformat()]
    if query:
        conditions.append("instr(lower(v.first_name || ' ' || v.last_name), lower(?))>0")
        params.append(query)
    where=' AND '.join(conditions) or '1=1'
    total=db().execute('SELECT count(*) FROM visits v WHERE '+where,params).fetchone()[0]
    counts={r['status']:r['n'] for r in db().execute('SELECT status,count(*) n FROM visits v WHERE '+where+' GROUP BY status',params)}
    unique=db().execute('SELECT count(DISTINCT lower(email)) FROM visits v WHERE '+where,params).fetchone()[0]
    rows=db().execute('SELECT v.*,u.name as staff_name FROM visits v LEFT JOIN users u ON v.handled_by=u.id WHERE '+where+' ORDER BY v.created_at ASC,v.id ASC LIMIT 50 OFFSET ?',[*params,(page-1)*50]).fetchall()
    return jsonify(items=[dict(r) for r in rows],total=total,page=page,pages=max(1,(total+49)//50),counts=counts,unique_visitors=unique,week_start=start.isoformat() if start else None)

@app.route('/api/visits/<int:visit_id>',methods=['PATCH','OPTIONS'])
@auth()
def update_visit(visit_id):
    status=data().get('status')
    if status not in ('waiting','in_progress','completed'): return jsonify(error='Invalid status.'),400
    db().execute('BEGIN IMMEDIATE')
    visit=db().execute('SELECT * FROM visits WHERE id=?',(visit_id,)).fetchone()
    if not visit:
        db().rollback();return jsonify(error='Visit not found.'),404
    privileged=g.user['role'] in ('admin','management')
    if visit['handled_by'] and visit['handled_by']!=g.user['id'] and not privileged:
        db().rollback();return jsonify(error='This visit is assigned to another team member.'),409
    if status=='waiting' and not privileged:
        db().rollback();return jsonify(error='Only Admin or Management can reopen a visit.'),403
    db().execute('UPDATE visits SET status=?,updated_at=?,handled_by=COALESCE(handled_by,?) WHERE id=?',(status,now(),g.user['id'],visit_id));db().commit()
    return jsonify(ok=True)
@app.route('/api/visits/<int:visit_id>',methods=['DELETE'])
@auth()
def delete_visit(visit_id):
    if g.user['role'] not in ('admin','management'): return jsonify(error='Admin or Management access required.'),403
    cursor=db().execute('DELETE FROM visits WHERE id=?',(visit_id,));db().commit()
    if not cursor.rowcount: return jsonify(error='Visit not found.'),404
    return jsonify(ok=True)

@app.route('/api/users',methods=['GET','POST','OPTIONS'])
@auth(admin=True)
def users():
    if request.method=='GET': return jsonify([public_user(u) for u in db().execute('SELECT * FROM users ORDER BY name')])
    from werkzeug.security import generate_password_hash
    d=data();name=text(d,'name');email=text(d,'email').lower();password=text(d,'password')
    if not 1<=len(name)<=80 or not email_valid(email) or not 1<=len(password)<=128: return jsonify(error='Enter a name, valid email, and password of 1–128 characters.'),400
    role=d.get('role','staff')
    if role not in ROLES: return jsonify(error='Choose Staff, Management or Admin.'),400
    try: db().execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',(name,email,generate_password_hash(password),role));db().commit()
    except sqlite3.IntegrityError: return jsonify(error='This email already has an account.'),409
    return jsonify(ok=True),201
@app.route('/api/users/<int:user_id>',methods=['PATCH','OPTIONS'])
@auth(admin=True)
def update_user(user_id):
    target=db().execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
    if not target: return jsonify(error='User not found.'),404
    d=data()
    if not d or any(k not in ('active','role') for k in d): return jsonify(error='Provide active or role.'),400
    if 'active' in d and type(d['active']) is not bool: return jsonify(error='Active must be true or false.'),400
    if 'role' in d and d['role'] not in ROLES: return jsonify(error='Choose Staff, Management or Admin.'),400
    role=d.get('role',target['role']);active=int(d.get('active',bool(target['active'])))
    if user_id==g.user['id'] and (role!='admin' or not active): return jsonify(error='You cannot remove your own administrator access.'),400
    if target['email']==ADMIN and (role!='admin' or not active): return jsonify(error='The primary administrator must remain active with the Admin role.'),400
    db().execute('UPDATE users SET active=?,role=? WHERE id=?',(active,role,user_id))
    db().execute('DELETE FROM sessions WHERE user_id=?',(user_id,));db().commit();return jsonify(ok=True)
@app.route('/api/password',methods=['POST','OPTIONS'])
@auth()
def password():
    from werkzeug.security import check_password_hash,generate_password_hash
    d=data();new=text(d,'new_password')
    if not check_password_hash(g.user['password'],text(d,'current_password')) or not 1<=len(new)<=128: return jsonify(error='Check your current password. New password must have 1–128 characters.'),400
    db().execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(new),g.user['id']));db().execute('DELETE FROM sessions WHERE user_id=?',(g.user['id'],));db().commit();return jsonify(ok=True)

initialize()
