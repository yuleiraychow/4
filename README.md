import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-please')

DATABASE = 'events.db'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ── 数据库 ──────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            category     TEXT NOT NULL,
            date         TEXT NOT NULL,
            time         TEXT NOT NULL,
            location     TEXT NOT NULL,
            lat          REAL,
            lng          REAL,
            description  TEXT NOT NULL,
            max_attendees INTEGER NOT NULL DEFAULT 20,
            img          TEXT,
            host_id      INTEGER NOT NULL,
            created_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (host_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS attendees (
            event_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            joined_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (event_id, user_id),
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id)  REFERENCES users(id)
        );
    ''')
    db.commit()

    # 插入示例数据（仅首次）
    if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        pw = generate_password_hash('demo1234')
        db.execute("INSERT INTO users (name, password) VALUES ('示例用户', ?)", (pw,))
        uid = db.execute("SELECT id FROM users WHERE name='示例用户'").fetchone()['id']
        db.execute('''INSERT INTO events
            (title,category,date,time,location,lat,lng,description,max_attendees,host_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            ('周末徒步 · 香山','户外','2026-06-21','08:00',
             '北京香山公园南门',40.0,116.18,
             '轻松友好的晨间徒步，约3小时，适合各年龄段。',20,uid))
        db.execute('''INSERT INTO events
            (title,category,date,time,location,lat,lng,description,max_attendees,host_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            ('AI 产品设计分享会','科技','2026-06-25','19:00',
             '上海·漕河泾 WeWork',31.15,121.38,
             '三位设计师分享AI时代实战经验，开放Q&A环节。',50,uid))
        db.commit()


# ── 工具函数 ─────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def current_user():
    if 'user_id' in session:
        return get_db().execute(
            'SELECT * FROM users WHERE id=?', (session['user_id'],)
        ).fetchone()
    return None


def event_detail(event_id):
    db = get_db()
    ev = db.execute('''
        SELECT e.*, u.name AS host_name
        FROM events e JOIN users u ON e.host_id = u.id
        WHERE e.id = ?
    ''', (event_id,)).fetchone()
    if not ev:
        return None, []
    attendees = db.execute('''
        SELECT u.name FROM attendees a JOIN users u ON a.user_id = u.id
        WHERE a.event_id = ?
    ''', (event_id,)).fetchall()
    return ev, attendees


# ── 路由 ─────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    cat = request.args.get('cat', '全部')
    q   = request.args.get('q', '').strip()

    query = '''
        SELECT e.*, u.name AS host_name,
               (SELECT COUNT(*) FROM attendees a WHERE a.event_id = e.id) AS joined_count
        FROM events e JOIN users u ON e.host_id = u.id
        WHERE 1=1
    '''
    params = []
    if cat != '全部':
        query += ' AND e.category = ?'
        params.append(cat)
    if q:
        query += ' AND (e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?)'
        params += [f'%{q}%', f'%{q}%', f'%{q}%']
    query += ' ORDER BY e.date ASC, e.time ASC'

    events = db.execute(query, params).fetchall()

    user_joined = set()
    if 'user_id' in session:
        rows = db.execute(
            'SELECT event_id FROM attendees WHERE user_id=?', (session['user_id'],)
        ).fetchall()
        user_joined = {r['event_id'] for r in rows}

    categories = ['全部','户外','科技','文化','运动','美食','公益','其他']
    return render_template('index.html',
        events=events, categories=categories,
        current_cat=cat, search=q,
        user=current_user(), user_joined=user_joined)


@app.route('/event/<int:event_id>')
def event(event_id):
    ev, attendees = event_detail(event_id)
    if not ev:
        flash('活动不存在', 'danger')
        return redirect(url_for('index'))
    user = current_user()
    joined = user and any(a['name'] == user['name'] for a in attendees)
    return render_template('event.html', ev=ev, attendees=attendees,
                           user=user, joined=joined)


@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        category = request.form.get('category', '其他')
        date     = request.form.get('date', '')
        time     = request.form.get('time', '')
        location = request.form.get('location', '').strip()
        lat      = request.form.get('lat') or None
        lng      = request.form.get('lng') or None
        desc     = request.form.get('description', '').strip()
        max_att  = int(request.form.get('max_attendees', 20))

        if not all([title, date, time, location, desc]):
            flash('请填写所有必填项', 'danger')
            return redirect(url_for('create'))

        img_path = None
        file = request.files.get('img')
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f'{uuid.uuid4().hex}.{ext}')
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            img_path = filename

        db = get_db()
        db.execute('''
            INSERT INTO events
            (title,category,date,time,location,lat,lng,description,max_attendees,img,host_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (title, category, date, time, location,
              float(lat) if lat else None,
              float(lng) if lng else None,
              desc, max_att, img_path, session['user_id']))
        db.commit()
        flash('活动发布成功！', 'success')
        return redirect(url_for('index'))

    categories = ['户外','科技','文化','运动','美食','公益','其他']
    return render_template('create.html', categories=categories, user=current_user())


@app.route('/event/<int:event_id>/join', methods=['POST'])
@login_required
def join(event_id):
    db = get_db()
    ev = db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
    if not ev:
        return jsonify(ok=False, msg='活动不存在')
    count = db.execute(
        'SELECT COUNT(*) FROM attendees WHERE event_id=?', (event_id,)
    ).fetchone()[0]
    if count >= ev['max_attendees']:
        return jsonify(ok=False, msg='名额已满')
    try:
        db.execute('INSERT INTO attendees (event_id, user_id) VALUES (?,?)',
                   (event_id, session['user_id']))
        db.commit()
        return jsonify(ok=True, msg='报名成功')
    except sqlite3.IntegrityError:
        return jsonify(ok=False, msg='你已报名')


@app.route('/event/<int:event_id>/cancel', methods=['POST'])
@login_required
def cancel(event_id):
    db = get_db()
    db.execute('DELETE FROM attendees WHERE event_id=? AND user_id=?',
               (event_id, session['user_id']))
    db.commit()
    return jsonify(ok=True, msg='已取消报名')


@app.route('/event/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    db = get_db()
    ev = db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
    if not ev or ev['host_id'] != session['user_id']:
        flash('无权删除', 'danger')
        return redirect(url_for('index'))
    if ev['img']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], ev['img']))
        except FileNotFoundError:
            pass
    db.execute('DELETE FROM events WHERE id=?', (event_id,))
    db.commit()
    flash('活动已删除', 'info')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        pw   = request.form.get('password', '')
        if not name or len(pw) < 4:
            flash('昵称不能为空，密码至少4位', 'danger')
            return redirect(url_for('register'))
        db = get_db()
        if db.execute('SELECT id FROM users WHERE name=?', (name,)).fetchone():
            flash('该昵称已被使用', 'danger')
            return redirect(url_for('register'))
        db.execute('INSERT INTO users (name, password) VALUES (?,?)',
                   (name, generate_password_hash(pw)))
        db.commit()
        user = db.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        flash(f'欢迎，{name}！', 'success')
        return redirect(url_for('index'))
    return render_template('auth.html', mode='register', user=None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        pw   = request.form.get('password', '')
        db   = get_db()
        user = db.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
        if not user or not check_password_hash(user['password'], pw):
            flash('昵称或密码错误', 'danger')
            return redirect(url_for('login'))
        session['user_id']   = user['id']
        session['user_name'] = user['name']
        flash(f'欢迎回来，{name}！', 'success')
        return redirect(url_for('index'))
    return render_template('auth.html', mode='login', user=None)


@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
