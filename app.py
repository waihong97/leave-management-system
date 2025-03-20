from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')

# Get the absolute path to the instance folder
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')

# Ensure the instance folder exists with proper permissions
try:
    os.makedirs(instance_path, mode=0o777, exist_ok=True)
except OSError as e:
    print(f"Error creating instance directory: {e}")

# Configure database with absolute path
db_path = os.path.join(instance_path, 'leave_management.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI', f'sqlite:///{db_path}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    leave_requests = db.relationship('LeaveRequest', backref='user', lazy=True)
    wfh_requests = db.relationship('WFHRequest', backref='user', lazy=True)
    leave_balance = db.relationship('LeaveBalance', backref='user', lazy=True)

class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    leave_type = db.Column(db.String(20), nullable=False)  # annual, sick, maternity, paternity, etc.

class WFHRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LeaveBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    leave_type = db.Column(db.String(20), nullable=False)
    balance = db.Column(db.Float, nullable=False)  # in days
    year = db.Column(db.Integer, nullable=False)

class LeaveRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    leave_type = db.Column(db.String(20), unique=True, nullable=False)
    max_days = db.Column(db.Float, nullable=False)
    min_days_notice = db.Column(db.Integer, nullable=False)  # minimum days notice required
    max_consecutive_days = db.Column(db.Integer, nullable=False)
    requires_approval = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        leave_requests = LeaveRequest.query.all()
        wfh_requests = WFHRequest.query.all()
    else:
        leave_requests = LeaveRequest.query.filter_by(user_id=current_user.id).all()
        wfh_requests = WFHRequest.query.filter_by(user_id=current_user.id).all()
    
    # Get leave balance for current year
    current_year = datetime.now().year
    leave_balance = LeaveBalance.query.filter_by(
        user_id=current_user.id,
        year=current_year
    ).all()
    
    return render_template('dashboard.html', 
                         leave_requests=leave_requests,
                         wfh_requests=wfh_requests,
                         leave_balance=leave_balance)

@app.route('/apply_leave', methods=['GET', 'POST'])
@login_required
def apply_leave():
    if request.method == 'POST':
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        reason = request.form.get('reason')
        leave_type = request.form.get('leave_type')
        
        # Check leave balance
        leave_balance = LeaveBalance.query.filter_by(
            user_id=current_user.id,
            leave_type=leave_type,
            year=start_date.year
        ).first()
        
        if not leave_balance or leave_balance.balance <= 0:
            flash('Insufficient leave balance')
            return redirect(url_for('apply_leave'))
        
        # Check leave rules
        leave_rule = LeaveRule.query.filter_by(leave_type=leave_type).first()
        if leave_rule:
            days_notice = (start_date - datetime.now().date()).days
            if days_notice < leave_rule.min_days_notice:
                flash(f'Please apply at least {leave_rule.min_days_notice} days in advance')
                return redirect(url_for('apply_leave'))
            
            consecutive_days = (end_date - start_date).days + 1
            if consecutive_days > leave_rule.max_consecutive_days:
                flash(f'Maximum consecutive days allowed is {leave_rule.max_consecutive_days}')
                return redirect(url_for('apply_leave'))
        
        leave_request = LeaveRequest(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            leave_type=leave_type
        )
        db.session.add(leave_request)
        db.session.commit()
        flash('Leave request submitted successfully')
        return redirect(url_for('dashboard'))
    
    # Get leave types for the form
    leave_rules = LeaveRule.query.all()
    return render_template('apply_leave.html', leave_rules=leave_rules)

@app.route('/apply_wfh', methods=['GET', 'POST'])
@login_required
def apply_wfh():
    if request.method == 'POST':
        date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        reason = request.form.get('reason')
        
        # Check if WFH request already exists for the date
        existing_request = WFHRequest.query.filter_by(
            user_id=current_user.id,
            date=date
        ).first()
        
        if existing_request:
            flash('You have already submitted a WFH request for this date')
            return redirect(url_for('apply_wfh'))
        
        wfh_request = WFHRequest(
            user_id=current_user.id,
            date=date,
            reason=reason
        )
        db.session.add(wfh_request)
        db.session.commit()
        flash('WFH request submitted successfully')
        return redirect(url_for('dashboard'))
    
    return render_template('apply_wfh.html')

@app.route('/approve_leave/<int:request_id>', methods=['POST'])
@login_required
def approve_leave(request_id):
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    leave_request = LeaveRequest.query.get_or_404(request_id)
    action = request.form.get('action')
    
    if action == 'approve':
        leave_request.status = 'approved'
        # Update leave balance
        leave_balance = LeaveBalance.query.filter_by(
            user_id=leave_request.user_id,
            leave_type=leave_request.leave_type,
            year=leave_request.start_date.year
        ).first()
        
        if leave_balance:
            days = (leave_request.end_date - leave_request.start_date).days + 1
            leave_balance.balance -= days
            db.session.commit()
            flash('Leave request approved')
    elif action == 'reject':
        leave_request.status = 'rejected'
        db.session.commit()
        flash('Leave request rejected')
    
    return redirect(url_for('dashboard'))

@app.route('/approve_wfh/<int:request_id>', methods=['POST'])
@login_required
def approve_wfh(request_id):
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    wfh_request = WFHRequest.query.get_or_404(request_id)
    action = request.form.get('action')
    
    if action == 'approve':
        wfh_request.status = 'approved'
        db.session.commit()
        flash('WFH request approved')
    elif action == 'reject':
        wfh_request.status = 'rejected'
        db.session.commit()
        flash('WFH request rejected')
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/calendar')
@login_required
def calendar():
    # Get all approved leave requests
    leave_events = LeaveRequest.query.filter_by(status='approved').all()
    # Get all approved WFH requests
    wfh_events = WFHRequest.query.filter_by(status='approved').all()
    
    # Format events for FullCalendar
    events = []
    
    # Add leave events
    for leave in leave_events:
        user = User.query.get(leave.user_id)
        current_date = leave.start_date
        while current_date <= leave.end_date:
            events.append({
                'title': f"{user.username} - {leave.leave_type.upper()}",
                'start': current_date.isoformat(),
                'end': (current_date + timedelta(days=1)).isoformat(),
                'backgroundColor': '#4CAF50' if leave.leave_type == 'annual' else '#FF9800' if leave.leave_type == 'sick' else '#9C27B0' if leave.leave_type == 'maternity' else '#2196F3',
                'borderColor': '#388E3C' if leave.leave_type == 'annual' else '#F57C00' if leave.leave_type == 'sick' else '#7B1FA2' if leave.leave_type == 'maternity' else '#1976D2'
            })
            current_date += timedelta(days=1)
    
    # Add WFH events
    for wfh in wfh_events:
        user = User.query.get(wfh.user_id)
        events.append({
            'title': f"{user.username} - WFH",
            'start': wfh.date.isoformat(),
            'end': (wfh.date + timedelta(days=1)).isoformat(),
            'backgroundColor': '#607D8B',
            'borderColor': '#455A64'
        })
    
    return render_template('calendar.html', events=events)

def init_db():
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            
            # Create admin user if it doesn't exist
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                print('Admin user created successfully')
            else:
                # Update admin password if user exists
                admin.password_hash = generate_password_hash('admin123')
                db.session.commit()
                print('Admin user password updated')
            
            # Create default leave rules if they don't exist
            default_rules = [
                LeaveRule(
                    leave_type='annual',
                    max_days=14,
                    min_days_notice=7,
                    max_consecutive_days=14,
                    requires_approval=True,
                    description='Annual leave for rest and recreation'
                ),
                LeaveRule(
                    leave_type='sick',
                    max_days=30,
                    min_days_notice=1,
                    max_consecutive_days=30,
                    requires_approval=True,
                    description='Sick leave for medical reasons'
                ),
                LeaveRule(
                    leave_type='maternity',
                    max_days=90,
                    min_days_notice=30,
                    max_consecutive_days=90,
                    requires_approval=True,
                    description='Maternity leave for expecting mothers'
                ),
                LeaveRule(
                    leave_type='paternity',
                    max_days=7,
                    min_days_notice=7,
                    max_consecutive_days=7,
                    requires_approval=True,
                    description='Paternity leave for new fathers'
                )
            ]
            
            for rule in default_rules:
                if not LeaveRule.query.filter_by(leave_type=rule.leave_type).first():
                    db.session.add(rule)
            
            db.session.commit()
            print('Default leave rules created successfully')
            
            # Set proper permissions on the database file
            if os.path.exists(db_path):
                os.chmod(db_path, 0o666)
                print(f'Database permissions set successfully: {db_path}')
            
        except Exception as e:
            print(f'Error initializing database: {e}')
            raise

# Initialize database and create admin user
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True) 