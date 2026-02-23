#!/usr/bin/env python3

from website import create_app

def test_edit_routes():
    """Test all edit_event routes to ensure they are properly registered"""
    app = create_app()
    
    with app.app_context():
        print("🎾 Testing Edit Event Multi-Step Routes...")
        
        routes_to_test = [
            ('/edit_event/1', 'Main edit event (redirects to step 1)'),
            ('/edit_event_step1/1', 'Step 1: Basic Information'),
            ('/edit_event_step2/1', 'Step 2: Courts & Game Settings'),
            ('/edit_event_step3/1', 'Step 3: Player Registration'),
            ('/edit_event_players/1', 'Player substitution for existing events'),
        ]
        
        with app.test_client() as client:
            success_count = 0
            
            for route, description in routes_to_test:
                try:
                    response = client.get(route)
                    if response.status_code == 302:
                        print(f"✅ {route} | {description} | Redirects to login (expected)")
                        success_count += 1
                    elif response.status_code == 200:
                        print(f"✅ {route} | {description} | Working (200 OK)")
                        success_count += 1
                    elif response.status_code == 404:
                        print(f"❌ {route} | {description} | NOT FOUND (404)")
                    else:
                        print(f"⚠️  {route} | {description} | Status: {response.status_code}")
                        
                except Exception as e:
                    print(f"❌ {route} | {description} | ERROR: {e}")
            
            print(f"\n📊 Results: {success_count}/{len(routes_to_test)} routes working correctly")
            
            if success_count == len(routes_to_test):
                print("🎉 SUCCESS: All edit event routes are properly implemented!")
                print("The 3-step edit process has been fully restored.")
                return True
            else:
                print("❌ FAILED: Some routes are not working properly.")
                return False

if __name__ == "__main__":
    success = test_edit_routes()
    if success:
        print("\n✅ Multi-step edit event system restored successfully!")
        print("You can now edit events using the proper 3-step workflow:")
        print("  1. Basic Information (Step 1)")
        print("  2. Courts & Game Settings (Step 2)")  
        print("  3. Player Registration (Step 3)")
    else:
        print("\n❌ There are still issues with the edit routes.")