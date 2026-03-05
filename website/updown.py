"""
Up-Down (Sobe e Desce) event format – next-round pairing logic.

Court numbering convention (0-indexed):
  index 0  = Court 1 = top / best court
  index N-1 = Court N = bottom / worst court

After a completed round:
  winners[i] = winning pair on court i
  losers[i]  = losing pair on court i

Next-round court assignments:
  Court 0       : winners[0]  + winners[1]
  Court k (mid) : losers[k-1] + winners[k+1]    (1 <= k <= N-2)
  Court N-1     : losers[N-2] + losers[N-1]

Within every new court the two arriving pairs are split and re-mixed:
  sorted pair_a → [a_best, a_worst]   (by current classification)
  sorted pair_b → [b_best, b_worst]
  Team A : a_best  + b_worst
  Team B : a_worst + b_best

Tiebreaker inside a pair: points → games_diff → player name (alphabetical).
"""

from datetime import datetime, timedelta


def create_updown_next_round_games(event_id, classifications, round_number):
    """
    Build and persist Game objects for the next Up-Down round.

    Parameters:
        event_id        – ID of the Event
        classifications – list of EventClassification objects (already up-to-date)
        round_number    – the new round index (informational only)

    Returns:
        Number of games created (int).

    Raises:
        Exception on validation errors (caught by the caller in views.py).
    """
    from . import db
    from .models import Event, EventCourts, Game, GameDay

    event = Event.query.get_or_404(event_id)

    # Courts ordered by insertion sequence: index 0 = top, index N-1 = bottom
    event_courts = (
        EventCourts.query
        .filter_by(evc_event_id=event_id)
        .order_by(EventCourts.evc_id)
        .all()
    )
    num_courts = len(event_courts)

    if num_courts not in (2, 3, 4):
        raise Exception(
            f"Up-Down format requires 2, 3, or 4 courts. This event has {num_courts}."
        )

    # ── Classification lookup ────────────────────────────────────────────────
    classif_by_player = {c.ec_player_id: c for c in classifications}

    def rank_key(player_id):
        """Lower rank = better player. Tiebreak: name alphabetical = worse rank."""
        c = classif_by_player.get(player_id)
        if not c:
            return (0, 0, "")
        return (-c.ec_points, -c.ec_games_diff, c.player.us_name.lower())

    # ── Find the most recently played round ──────────────────────────────────
    all_completed = (
        Game.query
        .filter(
            Game.gm_idEvent == event_id,
            Game.gm_result_A.isnot(None),
            Game.gm_result_B.isnot(None),
        )
        .all()
    )
    if not all_completed:
        raise Exception("No completed games found – cannot generate next Up-Down round.")

    latest_time = max(g.gm_timeStart for g in all_completed)
    last_round_games = [g for g in all_completed if g.gm_timeStart == latest_time]

    # ── Map each last-round game to its court index ──────────────────────────
    court_id_to_index = {ec.evc_court_id: i for i, ec in enumerate(event_courts)}
    court_to_game = {}
    for game in last_round_games:
        idx = court_id_to_index.get(game.gm_court)
        if idx is not None:
            court_to_game[idx] = game

    # ── Determine winners and losers per court ───────────────────────────────
    def winner_loser(game):
        """Return (winner_player_ids, loser_player_ids)."""
        team_a = [game.gm_idPlayer_A1, game.gm_idPlayer_A2]
        team_b = [game.gm_idPlayer_B1, game.gm_idPlayer_B2]
        if game.gm_result_A > game.gm_result_B:
            return team_a, team_b
        return team_b, team_a

    winners = {}  # court_index -> [p1, p2]
    losers  = {}  # court_index -> [p1, p2]
    for i in range(num_courts):
        g = court_to_game.get(i)
        if g:
            winners[i], losers[i] = winner_loser(g)

    # ── Build court slots for next round ─────────────────────────────────────
    # court_slots[i] = (pair_a, pair_b) where each pair is a list of 2 player IDs
    court_slots = []
    for i in range(num_courts):
        if i == 0:
            # Top court: winners from court 0 and court 1
            pair_a = winners.get(0, [])
            pair_b = winners.get(1, [])
        elif i == num_courts - 1:
            # Bottom court: losers from second-to-last and last court
            pair_a = losers.get(num_courts - 2, [])
            pair_b = losers.get(num_courts - 1, [])
        else:
            # Middle courts: losers from court above + winners from court below
            pair_a = losers.get(i - 1, [])
            pair_b = winners.get(i + 1, [])
        court_slots.append((pair_a, pair_b))

    # ── Compute new game start/end times ─────────────────────────────────────
    base_dt   = datetime.combine(event.ev_date, latest_time)
    new_start = (base_dt + timedelta(minutes=14)).time()
    new_end   = (base_dt + timedelta(minutes=27)).time()   # 14 + 13 min duration

    # ── Retrieve the GameDay attached to this event ───────────────────────────
    existing_game = Game.query.filter_by(gm_idEvent=event_id).first()
    if not existing_game:
        raise Exception("No existing games found for this event.")
    gameday = GameDay.query.get(existing_game.gm_idGameDay)
    if not gameday:
        raise Exception("GameDay not found for this event.")

    # ── Create games ──────────────────────────────────────────────────────────
    games_created = 0
    for court_idx, (pair_a, pair_b) in enumerate(court_slots):
        if len(pair_a) < 2 or len(pair_b) < 2:
            # Safety guard – should never happen in a valid event
            continue

        # Sort each pair: index 0 = better-ranked, index 1 = lower-ranked
        sorted_a = sorted(pair_a, key=rank_key)
        sorted_b = sorted(pair_b, key=rank_key)

        a_best,  a_worst = sorted_a[0], sorted_a[1]
        b_best,  b_worst = sorted_b[0], sorted_b[1]

        court = event_courts[court_idx]

        game = Game(
            gm_idLeague=gameday.gd_idLeague,
            gm_idGameDay=gameday.gd_id,
            gm_idEvent=event_id,
            gm_date=event.ev_date,
            gm_timeStart=new_start,
            gm_timeEnd=new_end,
            gm_court=court.evc_court_id,
            # Team A : best-of-A  +  worst-of-B
            gm_idPlayer_A1=a_best,
            gm_idPlayer_A2=b_worst,
            # Team B : worst-of-A +  best-of-B
            gm_idPlayer_B1=a_worst,
            gm_idPlayer_B2=b_best,
            gm_result_A=None,
            gm_result_B=None,
            gm_teamA='A',
            gm_teamB='B',
        )
        db.session.add(game)
        games_created += 1

    return games_created
