"""
Team-Based Database Seeder — Creates 8 specific users across 3 teams.
Includes Energy, EHS, and Resident teams as per requirements.
"""
from database.db import SessionLocal, engine
from database.models import Base, User, Role, Team
from core.security import hash_password

# Create all tables if they don't exist yet
Base.metadata.create_all(bind=engine)

def seed():
    db = SessionLocal()
    pwd = hash_password("password123")

    users_to_seed = [
        # --- Energy Management Team ---
        {"email": "energy_mgr@city.com",     "name": "Energy Manager",   "role": Role.MANAGER,    "team": Team.ENERGY},
        {"email": "energy_tech@city.com",    "name": "Energy Technician", "role": Role.SERVICER,   "team": Team.ENERGY},
        {"email": "energy_analyst@city.com", "name": "Energy Analyst",    "role": Role.ANALYST,    "team": Team.ENERGY},

        # --- EHS Team ---
        {"email": "ehs_mgr@city.com",        "name": "EHS Manager",      "role": Role.MANAGER,    "team": Team.EHS},
        {"email": "ehs_tech@city.com",       "name": "EHS Technician",    "role": Role.SERVICER,   "team": Team.EHS},
        {"email": "ehs_analyst@city.com",    "name": "EHS Analyst",       "role": Role.ANALYST,    "team": Team.EHS},

        # --- Residents ---
        {"email": "resident@city.com",       "name": "General Resident", "role": Role.RESIDENT,   "team": Team.RESIDENTS},
        {"email": "smart_resident@city.com", "name": "Smart Space User", "role": Role.SMART_USER, "team": Team.RESIDENTS},
    ]

    for u_data in users_to_seed:
        existing = db.query(User).filter(User.email == u_data["email"]).first()
        if not existing:
            user = User(
                email=u_data["email"],
                full_name=u_data["name"],
                password_hash=pwd,
                role=u_data["role"],
                team=u_data["team"]
            )
            db.add(user)
            print(f"Created [{u_data['team'].value}] {u_data['role'].value}: {u_data['email']}")
        else:
            # Update team/role if already exists
            existing.role = u_data["role"]
            existing.team = u_data["team"]
            existing.full_name = u_data["name"]
            print(f"Updated {u_data['email']}")

    db.commit()
    db.close()
    print("\n✅ Team-based seeding complete.")

if __name__ == "__main__":
    seed()
