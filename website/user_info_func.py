from flask_login import login_required, current_user
from flask import render_template, Blueprint
from website import db
from website.models import League, Club, Users

def ext_home():
    try:
        result_data = db.session.query(League, Club.cl_name)\
            .join(Club, League.lg_club_id == Club.cl_id)\
            .order_by(League.lg_startDate.desc())\
            .all()
    except Exception as e:
        print(f"Error: {e}")
    return render_template("index.html", user=current_user, result=result_data)

def ext_userInfo(p_user_id):
    pass_user = Users.query.get_or_404(p_user_id)
    return render_template("user_info.html", user=current_user, p_user=pass_user)