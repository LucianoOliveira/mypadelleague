import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from main import app
from website.tools import func_calculate_ELO_by_club
from website.models import Club, Event, Game
from website import db

with app.app_context():
    clubs = (
        db.session.query(Club)
        .join(Event, Event.ev_club_id == Club.cl_id)
        .join(Game, Game.gm_idEvent == Event.ev_id)
        .filter(Game.gm_result_A != None, Game.gm_idPlayer_A1 != None)
        .distinct().all()
    )
    for club in clubs:
        rankings = func_calculate_ELO_by_club(club.cl_id)
        print(f"--- {club.cl_name} ---")
        for r in rankings[:5]:
            name = r['player'].us_name
            elo = round(r['rankingNow'], 1)
            print(f"  {name:<30} {elo:>8}  W:{r['wins']} L:{r['losses']} G:{r['totalGames']}")
        print()
