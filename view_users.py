from app import app, db, User, LeaveBalance
from datetime import datetime

def view_users():
    with app.app_context():
        print("\n=== Users and Leave Balances ===\n")
        
        # Get all users
        users = User.query.all()
        current_year = datetime.now().year
        
        for user in users:
            print(f"Username: {user.username}")
            print(f"Admin: {'Yes' if user.is_admin else 'No'}")
            
            if not user.is_admin:
                print("\nLeave Balances:")
                balances = LeaveBalance.query.filter_by(
                    user_id=user.id,
                    year=current_year
                ).all()
                
                for balance in balances:
                    print(f"- {balance.leave_type.title()}: {balance.balance} days")
            
            print("\n" + "="*50 + "\n")

if __name__ == '__main__':
    view_users() 