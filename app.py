import os
from datetime import datetime, date
from urllib.parse import quote_plus
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY','krin-group-portal-v4-secret')
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://','postgresql://',1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///kringroup_portal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default='Employee')
    department = db.Column(db.String(80), default='General')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    contract_number = db.Column(db.String(100))
    organization = db.Column(db.String(80), nullable=False, default='Army')
    client = db.Column(db.String(160))
    value = db.Column(db.Float, default=0)
    department = db.Column(db.String(80), default='Sales')
    manager = db.Column(db.String(120))
    priority = db.Column(db.String(30), default='Medium')
    status = db.Column(db.String(40), default='In Progress')
    progress = db.Column(db.Integer, default=0)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    uploaded_by = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    project = db.relationship('Project', backref='documents')

class Bulletin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def log_action(action):
    db.session.add(Activity(action=action, user_name=getattr(current_user, 'name', 'System')))
    db.session.commit()

def parse_date(value):
    if not value: return None
    try: return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError: return None

def admin_required():
    return current_user.is_authenticated and current_user.role == 'Admin'

@app.context_processor
def inject_data():
    return dict(today=date.today(), organizations=['Army','Navy','Air Force','Police','Government','Private Company','Other'], departments=['Sales','Engineering','Procurement','Finance','HR','Logistics','IT','Management'], statuses=['Not Started','In Progress','Waiting','Completed','Delayed'], priorities=['Low','Medium','High','Critical'])

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email','').lower().strip()).first()
        if user and user.check_password(request.form.get('password','')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Wrong email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    org = request.args.get('organization','')
    status = request.args.get('status','')
    priority = request.args.get('priority','')
    q = request.args.get('q','').strip()
    query = Project.query
    if org: query = query.filter_by(organization=org)
    if status: query = query.filter_by(status=status)
    if priority: query = query.filter_by(priority=priority)
    if q: query = query.filter((Project.name.ilike(f'%{q}%')) | (Project.contract_number.ilike(f'%{q}%')) | (Project.client.ilike(f'%{q}%')))
    projects = query.order_by(Project.updated_at.desc()).all()
    all_projects = Project.query.all()
    return render_template('dashboard.html', projects=projects[:8], all_projects=all_projects, filters={'organization':org,'status':status,'priority':priority,'q':q}, activities=Activity.query.order_by(Activity.created_at.desc()).limit(8).all(), bulletins=Bulletin.query.order_by(Bulletin.created_at.desc()).limit(4).all())

@app.route('/projects')
@login_required
def projects():
    return render_template('projects.html', projects=Project.query.order_by(Project.updated_at.desc()).all())

@app.route('/projects/new', methods=['GET','POST'])
@login_required
def project_new():
    if request.method == 'POST':
        p = Project(name=request.form['name'], contract_number=request.form.get('contract_number'), organization=request.form.get('organization'), client=request.form.get('client'), value=float(request.form.get('value') or 0), department=request.form.get('department'), manager=request.form.get('manager'), priority=request.form.get('priority'), status=request.form.get('status'), progress=max(0,min(100,int(request.form.get('progress') or 0))), start_date=parse_date(request.form.get('start_date')), end_date=parse_date(request.form.get('end_date')), description=request.form.get('description'))
        db.session.add(p); db.session.commit(); log_action(f'Created project: {p.name}')
        flash('Project added successfully.', 'success')
        return redirect(url_for('project_detail', project_id=p.id))
    return render_template('project_form.html', project=None)

@app.route('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    url = request.url_root.rstrip('/') + url_for('project_detail', project_id=project.id)
    qr_url = 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=' + quote_plus(url)
    return render_template('project_detail.html', project=project, qr_url=qr_url, public_url=url)

@app.route('/projects/<int:project_id>/edit', methods=['GET','POST'])
@login_required
def project_edit(project_id):
    p = Project.query.get_or_404(project_id)
    if request.method == 'POST':
        for field in ['name','contract_number','organization','client','department','manager','priority','status','description']:
            setattr(p, field, request.form.get(field))
        p.value = float(request.form.get('value') or 0)
        p.progress = max(0,min(100,int(request.form.get('progress') or 0)))
        p.start_date = parse_date(request.form.get('start_date'))
        p.end_date = parse_date(request.form.get('end_date'))
        db.session.commit(); log_action(f'Updated project: {p.name}')
        flash('Project updated successfully.', 'success')
        return redirect(url_for('project_detail', project_id=p.id))
    return render_template('project_form.html', project=p)

@app.route('/projects/<int:project_id>/delete', methods=['POST'])
@login_required
def project_delete(project_id):
    p = Project.query.get_or_404(project_id)
    name = p.name
    db.session.delete(p); db.session.commit(); log_action(f'Deleted project: {name}')
    return redirect(url_for('projects'))

@app.route('/projects/<int:project_id>/upload', methods=['POST'])
@login_required
def upload_document(project_id):
    project = Project.query.get_or_404(project_id)
    file = request.files.get('file')
    if file and file.filename:
        original = file.filename
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(original)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        db.session.add(Document(filename=filename, original_name=original, project=project, uploaded_by=current_user.name))
        db.session.commit(); log_action(f'Uploaded document to {project.name}: {original}')
    return redirect(url_for('project_detail', project_id=project_id))

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/employees')
@login_required
def employees():
    return render_template('employees.html', users=User.query.order_by(User.created_at.desc()).all())

@app.route('/employees/new', methods=['GET','POST'])
@login_required
def employee_new():
    if not admin_required():
        flash('Only admin can add employees.', 'danger'); return redirect(url_for('employees'))
    if request.method == 'POST':
        email = request.form.get('email','').lower().strip()
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
        else:
            u = User(name=request.form.get('name'), email=email, role=request.form.get('role'), department=request.form.get('department'))
            u.set_password(request.form.get('password') or 'password123')
            db.session.add(u); db.session.commit(); log_action(f'Added employee: {u.name}')
            return redirect(url_for('employees'))
    return render_template('employee_form.html', user=None)

@app.route('/employees/<int:user_id>/edit', methods=['GET','POST'])
@login_required
def employee_edit(user_id):
    if not admin_required():
        flash('Only admin can edit employees.', 'danger'); return redirect(url_for('employees'))
    u = User.query.get_or_404(user_id)
    if request.method == 'POST':
        u.name=request.form.get('name'); u.email=request.form.get('email').lower().strip(); u.role=request.form.get('role'); u.department=request.form.get('department')
        if request.form.get('password'): u.set_password(request.form.get('password'))
        db.session.commit(); log_action(f'Updated employee: {u.name}')
        return redirect(url_for('employees'))
    return render_template('employee_form.html', user=u)

@app.route('/employees/<int:user_id>/delete', methods=['POST'])
@login_required
def employee_delete(user_id):
    if not admin_required():
        return redirect(url_for('employees'))
    if user_id != current_user.id:
        u=User.query.get_or_404(user_id); db.session.delete(u); db.session.commit()
    return redirect(url_for('employees'))

@app.route('/bulletin', methods=['GET','POST'])
@login_required
def bulletin():
    if request.method == 'POST':
        b=Bulletin(title=request.form.get('title'), message=request.form.get('message'), created_by=current_user.name)
        db.session.add(b); db.session.commit(); log_action(f'Posted bulletin: {b.title}')
        return redirect(url_for('bulletin'))
    return render_template('bulletin.html', bulletins=Bulletin.query.order_by(Bulletin.created_at.desc()).all())

@app.route('/calendar')
@login_required
def calendar():
    items=Project.query.filter(Project.end_date.isnot(None)).order_by(Project.end_date.asc()).all()
    return render_template('calendar.html', projects=items)

@app.route('/documents')
@login_required
def documents():
    return render_template('documents.html', documents=Document.query.order_by(Document.created_at.desc()).all())

@app.route('/activity')
@login_required
def activity():
    return render_template('activity.html', activities=Activity.query.order_by(Activity.created_at.desc()).all())

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@kringroup.com').first():
        admin=User(name='Admin User', email='admin@kringroup.com', role='Admin', department='Management')
        admin.set_password('admin123')
        db.session.add(admin)
        demo=User(name='Project Staff', email='staff@kringroup.com', role='Employee', department='Engineering')
        demo.set_password('staff123')
        db.session.add(demo)
        if Project.query.count()==0:
            db.session.add_all([
                Project(name='KAT Drone Integration', contract_number='KRIN-ARMY-001', organization='Army', client='Army Aviation Unit', value=2500000, department='Engineering', manager='Admin User', priority='Critical', status='In Progress', progress=62, start_date=date(2026,7,1), end_date=date(2026,8,20), description='Main tactical drone integration project.'),
                Project(name='Naval ISR Proposal', contract_number='KRIN-NAVY-014', organization='Navy', client='Procurement Office', value=1800000, department='Sales', manager='Project Staff', priority='High', status='Waiting', progress=35, start_date=date(2026,7,5), end_date=date(2026,9,12), description='Proposal and stakeholder coordination.'),
                Project(name='Air Force Sensor Demo', contract_number='KRIN-AF-009', organization='Air Force', client='Technical Evaluation Team', value=900000, department='IT', manager='Admin User', priority='Medium', status='Not Started', progress=10, start_date=date(2026,7,10), end_date=date(2026,10,1), description='Dashboard demo and technical preparation.')
            ])
        db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
