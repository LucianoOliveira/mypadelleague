"""
setup_nicknames.py
------------------
One-time script to:
1. Find all users whose us_name contains text in double quotes (e.g. António "Shiri" Couto).
2. Extract the nickname (text between the first pair of double quotes).
3. Store the nickname in tb_player_nickname for club "XT Padel" (club ID looked up by name).
4. Strip the quoted portion (and clean up extra spaces) from us_name.

Run from the project root:
    python utility_scripts/setup_nicknames.py
"""
import sys
import os
import re

# Allow running from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from website import db
from website.models import Users, Club, PlayerClubNickname


def run():
    with app.app_context():
        # Find the XT Padel club
        club = Club.query.filter(Club.cl_name.ilike('%XT Padel%')).first()
        if not club:
            print("ERROR: Club 'XT Padel' not found. Check the club name in the database.")
            return

        print(f"Found club: {club.cl_name} (ID {club.cl_id})")

        # Find all users with a nickname in their name
        users = Users.query.all()
        nickname_pattern = re.compile(r'"([^"]+)"')

        saved = 0
        cleaned = 0
        skipped = 0

        for user in users:
            match = nickname_pattern.search(user.us_name)
            if not match:
                continue

            nickname = match.group(1).strip()
            original_name = user.us_name

            # Save / update the nickname for this club
            existing = PlayerClubNickname.query.filter_by(
                pcn_user_id=user.us_id,
                pcn_club_id=club.cl_id
            ).first()

            if existing:
                if existing.pcn_nickname != nickname:
                    existing.pcn_nickname = nickname
                    print(f"  UPDATED nickname for '{original_name}' → '{nickname}'")
                    saved += 1
                else:
                    print(f"  SKIPPED (already exists): '{original_name}' → '{nickname}'")
                    skipped += 1
            else:
                db.session.add(PlayerClubNickname(
                    pcn_user_id=user.us_id,
                    pcn_club_id=club.cl_id,
                    pcn_nickname=nickname
                ))
                print(f"  SAVED: '{original_name}' → nickname='{nickname}'")
                saved += 1

            # Clean up us_name: remove the "Nickname" part and tidy spaces
            clean_name = nickname_pattern.sub('', user.us_name)
            clean_name = re.sub(r'\s{2,}', ' ', clean_name).strip()
            if clean_name != user.us_name:
                print(f"  CLEANED name: '{user.us_name}' → '{clean_name}'")
                user.us_name = clean_name
                cleaned += 1

        db.session.commit()
        print(f"\nDone. Nicknames saved/updated: {saved}, skipped: {skipped}, names cleaned: {cleaned}")


if __name__ == '__main__':
    run()
