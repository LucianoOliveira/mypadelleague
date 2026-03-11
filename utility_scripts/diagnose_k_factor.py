"""
Check K factor discrepancy between old (league) and new (event) systems
for the shared 278 games.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from main import app
from website.models import Game, League, Event, Users
from website import db

with app.app_context():
    uid = 3  # Luciano

    shared_games = (
        db.session.query(Game)
        .join(League, Game.gm_idLeague == League.lg_id)
        .join(Event, Game.gm_idEvent == Event.ev_id)
        .filter(
            League.lg_eloK > 0,
            Event.ev_club_id == 1,
            Event.ev_exclude_from_elo != True,
            Game.gm_result_A != None,
            (Game.gm_idPlayer_A1 == uid) |
            (Game.gm_idPlayer_A2 == uid) |
            (Game.gm_idPlayer_B1 == uid) |
            (Game.gm_idPlayer_B2 == uid),
        )
        .order_by(Game.gm_date.asc(), Game.gm_timeStart.asc())
        .all()
    )

    print(f"Shared games: {len(shared_games)}")
    k_mismatches = []
    for g in shared_games:
        league = db.session.get(League, g.gm_idLeague)
        event = db.session.get(Event, g.gm_idEvent)
        k_old = league.lg_eloK
        k_new = event.ev_max_players * 2.5
        if k_old != k_new:
            k_mismatches.append((g.gm_id, g.gm_date, league.lg_name, k_old, event.ev_title, event.ev_max_players, k_new))

    print(f"Games where K differs between old and new system: {len(k_mismatches)}")
    if k_mismatches:
        # Group by K pair
        from collections import Counter
        pairs = Counter((m[3], m[6]) for m in k_mismatches)
        print("\nK mismatch pairs (old_K -> new_K): count")
        for (ko, kn), count in sorted(pairs.items()):
            print(f"  K={ko} -> K={kn}: {count} games")
        print("\nSample mismatches:")
        for m in k_mismatches[:8]:
            print(f"  gm_id={m[0]} date={m[1]} league='{m[2]}' K_old={m[3]} | event='{m[4]}' max_p={m[5]} K_new={m[6]}")
