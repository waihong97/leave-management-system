from app import app, db, User, LeaveBalance
from werkzeug.security import generate_password_hash
from datetime import datetime

def add_users():
    with app.app_context():
        # Create users
        users = [
            {
                'username': 'admin',
                'password': 'admin123',
                'is_admin': True
            },
            {
                'username': 'john_doe',
                'password': 'password123',
                'is_admin': False
            },
            {
                'username': 'jane_smith',
                'password': 'password123',
                'is_admin': False
            },
            {
                'username': 'mike_wilson',
                'password': 'password123',
                'is_admin': False
            }
        ]

        # Add users to database
        for user_data in users:
            user = User.query.filter_by(username=user_data['username']).first()
            if not user:
                user = User(
                    username=user_data['username'],
                    password_hash=generate_password_hash(user_data['password']),
                    is_admin=user_data['is_admin']
                )
                db.session.add(user)
                print(f"Added user: {user_data['username']}")

        # Set leave balances for non-admin users
        current_year = datetime.now().year
        leave_types = ['annual', 'sick', 'maternity', 'paternity']
        
        for user in User.query.filter_by(is_admin=False).all():
            for leave_type in leave_types:
                balance = LeaveBalance.query.filter_by(
                    user_id=user.id,
                    leave_type=leave_type,
                    year=current_year
                ).first()
                
                if not balance:
                    # Set default balances
                    max_days = {
                        'annual': 14,
                        'sick': 30,
                        'maternity': 90,
                        'paternity': 7
                    }
                    
                    balance = LeaveBalance(
                        user_id=user.id,
                        leave_type=leave_type,
                        balance=max_days[leave_type],
                        year=current_year
                    )
                    db.session.add(balance)
                    print(f"Added leave balance for {user.username}: {leave_type} - {max_days[leave_type]} days")

        db.session.commit()
        print("Database updated successfully!")

if __name__ == '__main__':
    add_users() 