"""
Diagnostic: compare old league-based ELO vs new event-based ELO for the same user.
Find which games are in one dataset but not the other.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from main import app
from website.models import Game, League, Event, Users, ELOranking
from website import db

TARGET_NAME = 'Luciano'  # partial name match

with app.app_context():
    # Find the user
    user = Users.query.filter(Users.us_name.ilike(f'%{TARGET_NAME}%')).first()
    if not user:
        print("User not found")
        exit()
    uid = user.us_id
    print(f"User: {user.us_name} (id={uid})")

    # Old stored ELO ranking
    old = ELOranking.query.filter_by(pl_id=uid).first()
    if old:
        print(f"\nOld stored ELO: {old.pl_rankingNow:.2f}  W:{old.pl_wins} L:{old.pl_losses} G:{old.pl_totalGames}")

    # Games counted by old system: gm_idLeague IN leagues with eloK > 0
    old_games = (
        db.session.query(Game)
        .join(League, Game.gm_idLeague == League.lg_id)
        .filter(
            League.lg_eloK > 0,
            Game.gm_result_A != None,
            Game.gm_result_B != None,
            (Game.gm_idPlayer_A1 == uid) |
            (Game.gm_idPlayer_A2 == uid) |
            (Game.gm_idPlayer_B1 == uid) |
            (Game.gm_idPlayer_B2 == uid),
        )
        .order_by(Game.gm_date.asc(), Game.gm_timeStart.asc())
        .all()
    )
    print(f"\nOld system (league) games for user: {len(old_games)}")

    # Games counted by new system: gm_idEvent -> ev_club_id = 1 (XT Padel), not excluded
    new_games = (
        db.session.query(Game)
        .join(Event, Game.gm_idEvent == Event.ev_id)
        .filter(
            Event.ev_club_id == 1,
            Event.ev_exclude_from_elo != True,
            Game.gm_result_A != None,
            Game.gm_result_B != None,
            (Game.gm_idPlayer_A1 == uid) |
            (Game.gm_idPlayer_A2 == uid) |
            (Game.gm_idPlayer_B1 == uid) |
            (Game.gm_idPlayer_B2 == uid),
        )
        .order_by(Game.gm_date.asc(), Game.gm_timeStart.asc())
        .all()
    )
    print(f"New system (event) games for user: {len(new_games)}")

    old_ids = {g.gm_id for g in old_games}
    new_ids = {g.gm_id for g in new_games}

    only_old = old_ids - new_ids
    only_new = new_ids - old_ids
    both = old_ids & new_ids

    print(f"\nIn both: {len(both)}")
    print(f"Only in OLD (league): {len(only_old)}")
    print(f"Only in NEW (event):  {len(only_new)}")

    if only_old:
        print("\nGames only in OLD system:")
        for gid in sorted(only_old):
            g = db.session.get(Game, gid)
            league = db.session.get(League, g.gm_idLeague)
            print(f"  gm_id={gid} date={g.gm_date} league='{league.lg_name}' eloK={league.lg_eloK} event={g.gm_idEvent}")

    if only_new:
        print("\nGames only in NEW system:")
        for gid in sorted(only_new):
            g = db.session.get(Game, gid)
            ev = db.session.get(Event, g.gm_idEvent) if g.gm_idEvent else None
            league = db.session.get(League, g.gm_idLeague)
            ev_title = ev.ev_title if ev else None
            print(f"  gm_id={gid} date={g.gm_date} event='{ev_title}' league='{league.lg_name}' eloK={league.lg_eloK}")
