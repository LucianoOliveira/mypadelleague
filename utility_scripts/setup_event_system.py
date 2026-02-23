#!/usr/bin/env python3
"""
Script to create event system tables manually
"""
from website import create_app, db
from website.models import EventType, MexicanConfig

def create_event_tables():
    app = create_app()
    with app.app_context():
        # Create all tables defined in models
        db.create_all()
        print("Created all database tables")
        
        # Check if EventType table has data
        event_types_count = EventType.query.count()
        print(f"EventType table has {event_types_count} records")
        
        if event_types_count == 0:
            # Insert initial event types
            event_types = [
                EventType(et_name='Mexican Tournament', et_description='Traditional Mexican format tournament with multiple rounds', et_is_active=True, et_order=1),
                EventType(et_name='Single Elimination', et_description='Knockout tournament format', et_is_active=True, et_order=2),
                EventType(et_name='Round Robin', et_description='Everyone plays everyone format', et_is_active=True, et_order=3),
                EventType(et_name='Swiss System', et_description='Swiss system pairing tournament', et_is_active=True, et_order=4),
                EventType(et_name='Friendly Match', et_description='Casual friendly games', et_is_active=True, et_order=5)
            ]
            
            for event_type in event_types:
                db.session.add(event_type)
            
            print("Added initial event types")
        
        # Check if MexicanConfig table has data
        mexican_configs_count = MexicanConfig.query.count()
        print(f"MexicanConfig table has {mexican_configs_count} records")
        
        if mexican_configs_count == 0:
            # Insert initial Mexican configurations
            mexican_configs = [
                MexicanConfig(mc_name='Standard Mexican (3 rounds)', mc_rounds=3, mc_players_per_game=4, mc_games_per_round=1, mc_is_active=True),
                MexicanConfig(mc_name='Extended Mexican (4 rounds)', mc_rounds=4, mc_players_per_game=4, mc_games_per_round=1, mc_is_active=True),
                MexicanConfig(mc_name='Long Mexican (5 rounds)', mc_rounds=5, mc_players_per_game=4, mc_games_per_round=1, mc_is_active=True),
                MexicanConfig(mc_name='Quick Mexican (2 rounds)', mc_rounds=2, mc_players_per_game=4, mc_games_per_round=1, mc_is_active=True)
            ]
            
            for config in mexican_configs:
                db.session.add(config)
                
            print("Added initial Mexican configurations")
        
        db.session.commit()
        print("Event system setup completed successfully!")

if __name__ == '__main__':
    create_event_tables()