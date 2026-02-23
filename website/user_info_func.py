from flask_login import login_required, current_user
from flask import render_template, Blueprint
from website import db
from website.models import League, Club, Users

def ext_home():
    # Temporarily redirect to events page instead of showing leagues
    from flask import redirect, url_for
    return redirect(url_for('views.events'))

def ext_userInfo(p_user_id):
    pass_user = Users.query.get_or_404(p_user_id)
    return render_template("user_info.html", user=current_user, p_user=pass_user)