import os
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database', 'buildtrack.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bbc526b52e2940db5dabd52ba4092d56577b350e6eb42dc7'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Database tables (created automatically the first time the app runs)
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    skill TEXT,
    daily_wage REAL DEFAULT 0,
    availability TEXT DEFAULT 'Available'
);
CREATE TABLE IF NOT EXISTS labour (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contractor_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    skill TEXT,
    phone TEXT,
    address TEXT,
    daily_wage REAL DEFAULT 0,
    availability TEXT DEFAULT 'Available'
);
CREATE TABLE IF NOT EXISTS work_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    skill_needed TEXT,
    location TEXT,
    budget REAL DEFAULT 0,
    deadline TEXT,
    status TEXT DEFAULT 'Open',
    created_on TEXT
);
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    contractor_id INTEGER NOT NULL,
    workers_count INTEGER DEFAULT 1,
    message TEXT,
    created_on TEXT
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT,
    budget REAL DEFAULT 0,
    spent REAL DEFAULT 0,
    progress INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Planning',
    deadline TEXT
);
CREATE TABLE IF NOT EXISTS workers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    skill TEXT,
    daily_wage REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    in_stock INTEGER DEFAULT 0,
    reorder_point INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    title TEXT NOT NULL,
    amount REAL DEFAULT 0,
    expense_date TEXT
);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    filename TEXT NOT NULL,
    caption TEXT,
    uploaded_on TEXT
);
"""


def get_db():
    """Open one database connection per request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def current_user():
    """Return the logged-in user's row, or None if nobody is logged in."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def login_required(role=None):
    """Only let logged-in users in. If role is given, only that role is allowed."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                flash('Please log in first.')
                return redirect(url_for('login'))
            if role and user['role'] != role:
                flash('That page is not for your account type.')
                return redirect(url_for('dashboard'))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_current_user():
    # Makes current_user available in every template (used by the navbar)
    return {'current_user': current_user()}


# ---------- Sign up, log in, log out ----------

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        role = request.form.get('role')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if role not in ('worker', 'client', 'contractor') or not name or not email:
            flash('Please fill in all required fields.')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.')
        elif password != confirm:
            flash('Passwords do not match.')
        else:
            db = get_db()
            if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
                flash('This email is already registered. Please log in.')
            else:
                cursor = db.execute(
                    'INSERT INTO users (role, name, email, password_hash, phone) VALUES (?, ?, ?, ?, ?)',
                    (role, name, email, generate_password_hash(password), phone),
                )
                db.commit()
                session.clear()
                session['user_id'] = cursor.lastrowid
                flash('Account created successfully.')
                return redirect(url_for('dashboard'))
    return render_template('auth.html', mode='signup')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = get_db().execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            flash('Welcome back!')
            return redirect(url_for('dashboard'))
        flash('Wrong email or password.')
    return render_template('auth.html', mode='login')


@app.route('/logout')
def logout():
    session.clear()
    flash('You are logged out.')
    return redirect(url_for('landing'))


# ---------- Role-based dashboards ----------

@app.route('/dashboard')
@login_required()
def dashboard():
    # Send each user to their own dashboard
    role = current_user()['role']
    if role == 'worker':
        return redirect(url_for('worker_dashboard'))
    if role == 'contractor':
        return redirect(url_for('contractor_dashboard'))
    return redirect(url_for('client_dashboard'))


# Worker

@app.route('/worker/dashboard', methods=['GET', 'POST'])
@login_required('worker')
def worker_dashboard():
    db = get_db()
    user = current_user()

    if request.method == 'POST':
        db.execute(
            'UPDATE users SET skill = ?, phone = ?, address = ?, daily_wage = ?, availability = ? WHERE id = ?',
            (
                request.form.get('skill', '').strip(),
                request.form.get('phone', '').strip(),
                request.form.get('address', '').strip(),
                float(request.form.get('daily_wage') or 0),
                request.form.get('availability', 'Available'),
                user['id'],
            ),
        )
        db.commit()
        flash('Profile saved.')
        return redirect(url_for('worker_dashboard'))

    requests_list = db.execute(
        """SELECT wr.*, u.name AS client_name, u.phone AS client_phone
           FROM work_requests wr
           JOIN users u ON u.id = wr.client_id
           WHERE wr.status = 'Open'
           ORDER BY wr.id DESC"""
    ).fetchall()
    return render_template('worker_dashboard.html', user=user, requests=requests_list)


# Contractor

@app.route('/contractor/dashboard')
@login_required('contractor')
def contractor_dashboard():
    db = get_db()
    user = current_user()
    labour = db.execute(
        'SELECT * FROM labour WHERE contractor_id = ? ORDER BY id DESC', (user['id'],)
    ).fetchall()
    open_requests = db.execute(
        """SELECT wr.*, u.name AS client_name
           FROM work_requests wr
           JOIN users u ON u.id = wr.client_id
           WHERE wr.status = 'Open'
           ORDER BY wr.id DESC"""
    ).fetchall()
    my_offers = db.execute(
        """SELECT o.*, wr.title AS request_title
           FROM offers o
           JOIN work_requests wr ON wr.id = o.request_id
           WHERE o.contractor_id = ?
           ORDER BY o.id DESC""",
        (user['id'],),
    ).fetchall()
    return render_template(
        'contractor_dashboard.html',
        user=user,
        labour=labour,
        requests=open_requests,
        my_offers=my_offers,
    )


@app.route('/contractor/profile', methods=['POST'])
@login_required('contractor')
def update_contractor_profile():
    db = get_db()
    user = current_user()
    db.execute(
        'UPDATE users SET skill = ?, phone = ?, address = ? WHERE id = ?',
        (
            request.form.get('skill', '').strip(),
            request.form.get('phone', '').strip(),
            request.form.get('address', '').strip(),
            user['id'],
        ),
    )
    db.commit()
    flash('Contractor profile saved.')
    return redirect(url_for('contractor_dashboard'))


@app.route('/contractor/labour/new', methods=['POST'])
@login_required('contractor')
def add_labour():
    db = get_db()
    user = current_user()
    db.execute(
        """INSERT INTO labour (contractor_id, name, skill, phone, address, daily_wage, availability)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user['id'],
            request.form.get('name', '').strip(),
            request.form.get('skill', '').strip(),
            request.form.get('phone', '').strip(),
            request.form.get('address', '').strip(),
            float(request.form.get('daily_wage') or 0),
            request.form.get('availability', 'Available'),
        ),
    )
    db.commit()
    flash('Labour added.')
    return redirect(url_for('contractor_dashboard'))


@app.route('/contractor/labour/<int:lid>/delete', methods=['POST'])
@login_required('contractor')
def delete_labour(lid):
    db = get_db()
    user = current_user()
    # A contractor can only delete their own labour
    db.execute('DELETE FROM labour WHERE id = ? AND contractor_id = ?', (lid, user['id']))
    db.commit()
    flash('Labour removed.')
    return redirect(url_for('contractor_dashboard'))


@app.route('/contractor/offers/new', methods=['POST'])
@login_required('contractor')
def new_offer():
    db = get_db()
    user = current_user()
    request_id = request.form.get('request_id')

    already_sent = db.execute(
        'SELECT id FROM offers WHERE request_id = ? AND contractor_id = ?', (request_id, user['id'])
    ).fetchone()
    if already_sent:
        flash('You have already sent an offer for this request.')
        return redirect(url_for('contractor_dashboard'))

    db.execute(
        """INSERT INTO offers (request_id, contractor_id, workers_count, message, created_on)
           VALUES (?, ?, ?, ?, ?)""",
        (
            request_id,
            user['id'],
            int(request.form.get('workers_count') or 1),
            request.form.get('message', '').strip(),
            date.today().isoformat(),
        ),
    )
    db.commit()
    flash('Offer sent to the client.')
    return redirect(url_for('contractor_dashboard'))


# Client

@app.route('/client/dashboard')
@login_required('client')
def client_dashboard():
    db = get_db()
    user = current_user()

    # Worker search (only runs when the search form was submitted)
    workers = None
    if 'skill' in request.args or 'area' in request.args:
        skill = request.args.get('skill', '').strip()
        area = request.args.get('area', '').strip()
        workers = db.execute(
            """SELECT * FROM users
               WHERE role = 'worker' AND availability = 'Available'
                 AND skill LIKE ? AND address LIKE ?
               ORDER BY name""",
            (f'%{skill}%', f'%{area}%'),
        ).fetchall()

    # Contractors with how many labour each one has
    contractors = db.execute(
        """SELECT u.*, (SELECT COUNT(*) FROM labour l WHERE l.contractor_id = u.id) AS labour_count
           FROM users u
           WHERE u.role = 'contractor'
           ORDER BY u.name"""
    ).fetchall()

    # This client's own requests
    my_requests = db.execute(
        'SELECT * FROM work_requests WHERE client_id = ? ORDER BY id DESC', (user['id'],)
    ).fetchall()

    # Offers that contractors sent to this client's requests
    offers = db.execute(
        """SELECT o.*, wr.title AS request_title, u.name AS contractor_name, u.phone AS contractor_phone
           FROM offers o
           JOIN work_requests wr ON wr.id = o.request_id
           JOIN users u ON u.id = o.contractor_id
           WHERE wr.client_id = ?
           ORDER BY o.id DESC""",
        (user['id'],),
    ).fetchall()

    return render_template(
        'client_dashboard.html',
        user=user,
        workers=workers,
        contractors=contractors,
        requests=my_requests,
        offers=offers,
    )


@app.route('/client/requests/new', methods=['POST'])
@login_required('client')
def new_request():
    db = get_db()
    user = current_user()
    db.execute(
        """INSERT INTO work_requests (client_id, title, skill_needed, location, budget, deadline, status, created_on)
           VALUES (?, ?, ?, ?, ?, ?, 'Open', ?)""",
        (
            user['id'],
            request.form.get('title', '').strip(),
            request.form.get('skill_needed', '').strip(),
            request.form.get('location', '').strip(),
            float(request.form.get('budget') or 0),
            request.form.get('deadline') or None,
            date.today().isoformat(),
        ),
    )
    db.commit()
    flash('Work request posted.')
    return redirect(url_for('client_dashboard'))


@app.route('/client/requests/<int:rid>/close', methods=['POST'])
@login_required('client')
def close_request(rid):
    db = get_db()
    user = current_user()
    # The client can only close their own requests
    db.execute("UPDATE work_requests SET status = 'Closed' WHERE id = ? AND client_id = ?", (rid, user['id']))
    db.commit()
    flash('Request closed.')
    return redirect(url_for('client_dashboard'))


# ---------- Original BuildTrack pages ----------

@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/overview')
def overview():
    db = get_db()
    projects = db.execute('SELECT * FROM projects ORDER BY id DESC').fetchall()
    totals = db.execute(
        'SELECT COALESCE(SUM(budget), 0) AS budget, COALESCE(SUM(spent), 0) AS spent FROM projects'
    ).fetchone()
    worker_count = db.execute('SELECT COUNT(*) FROM workers').fetchone()[0]
    overdue = db.execute(
        "SELECT COUNT(*) FROM projects WHERE deadline < ? AND status != 'Completed'",
        (date.today().isoformat(),)
    ).fetchone()[0]
    low_stock = db.execute('SELECT COUNT(*) FROM materials WHERE in_stock <= reorder_point').fetchone()[0]
    return render_template(
        'dashboard.html',
        projects=projects,
        totals=totals,
        worker_count=worker_count,
        overdue=overdue,
        low_stock=low_stock,
        chart_labels=[p['name'] for p in projects],
        chart_budget=[p['budget'] for p in projects],
        chart_spent=[p['spent'] for p in projects],
    )


@app.route('/projects', methods=['GET', 'POST'])
def projects():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            'INSERT INTO projects (name, location, budget, progress, status, deadline) VALUES (?, ?, ?, ?, ?, ?)',
            (
                request.form['name'],
                request.form.get('location'),
                float(request.form.get('budget') or 0),
                int(request.form.get('progress') or 0),
                request.form.get('status', 'Planning'),
                request.form.get('deadline') or None,
            ),
        )
        db.commit()
        flash('Project added successfully.')
        return redirect(url_for('projects'))
    rows = db.execute('SELECT * FROM projects ORDER BY id DESC').fetchall()
    return render_template('projects.html', projects=rows)


@app.route('/projects/<int:pid>/delete', methods=['POST'])
def delete_project(pid):
    db = get_db()
    db.execute('DELETE FROM projects WHERE id = ?', (pid,))
    db.commit()
    flash('Project deleted.')
    return redirect(url_for('projects'))


@app.route('/workers', methods=['GET', 'POST'])
def workers():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            '''INSERT INTO workers (name, skill, daily_wage, phone, email, address, availability)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                request.form['name'],
                request.form.get('skill'),
                float(request.form.get('daily_wage') or 0),
                request.form.get('phone'),
                request.form.get('email'),
                request.form.get('address'),
                request.form.get('availability', 'Available'),
            ),
        )
        db.commit()
        flash('Worker added successfully.')
        return redirect(url_for('workers'))
    rows = db.execute('SELECT * FROM workers ORDER BY id DESC').fetchall()
    return render_template('workers.html', workers=rows)


@app.route('/materials', methods=['GET', 'POST'])
def materials():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            'INSERT INTO materials (name, category, in_stock, reorder_point) VALUES (?, ?, ?, ?)',
            (
                request.form['name'],
                request.form.get('category'),
                int(request.form.get('in_stock') or 0),
                int(request.form.get('reorder_point') or 0),
            ),
        )
        db.commit()
        flash('Material added successfully.')
        return redirect(url_for('materials'))
    rows = db.execute('SELECT * FROM materials ORDER BY id DESC').fetchall()
    return render_template('materials.html', materials=rows)


@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    db = get_db()
    if request.method == 'POST':
        amount = float(request.form.get('amount') or 0)
        project_id = request.form.get('project_id') or None
        db.execute(
            'INSERT INTO expenses (project_id, title, amount, expense_date) VALUES (?, ?, ?, ?)',
            (project_id, request.form['title'], amount, request.form.get('expense_date') or date.today().isoformat()),
        )
        if project_id:
            db.execute('UPDATE projects SET spent = spent + ? WHERE id = ?', (amount, project_id))
        db.commit()
        flash('Expense recorded.')
        return redirect(url_for('expenses'))
    rows = db.execute(
        'SELECT e.*, p.name AS project_name FROM expenses e LEFT JOIN projects p ON p.id = e.project_id ORDER BY e.id DESC'
    ).fetchall()
    project_list = db.execute('SELECT id, name FROM projects').fetchall()
    return render_template('expenses.html', expenses=rows, projects=project_list)


@app.route('/photos', methods=['GET', 'POST'])
def photos():
    db = get_db()
    if request.method == 'POST':
        file = request.files.get('photo')
        if file and allowed_file(file.filename):
            stamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{stamp}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            db.execute(
                'INSERT INTO photos (project_id, filename, caption, uploaded_on) VALUES (?, ?, ?, ?)',
                (request.form.get('project_id') or None, filename, request.form.get('caption'), date.today().isoformat()),
            )
            db.commit()
            flash('Photo uploaded successfully.')
        else:
            flash('Please choose a png, jpg, jpeg or gif file.')
        return redirect(url_for('photos'))
    rows = db.execute('SELECT * FROM photos ORDER BY id DESC').fetchall()
    project_list = db.execute('SELECT id, name FROM projects').fetchall()
    return render_template('photos.html', photos=rows, projects=project_list)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # Add the worker columns to an older database (safe to run again)
    new_columns = {
        'phone': 'TEXT',
        'email': 'TEXT',
        'address': 'TEXT',
        'availability': "TEXT DEFAULT 'Available'",
    }
    for column, column_type in new_columns.items():
        try:
            conn.execute(f'ALTER TABLE workers ADD COLUMN {column} {column_type}')
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


init_db()

if __name__ == '__main__':
    app.run(debug=True)