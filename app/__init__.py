from flask import Flask, url_for, redirect,  \
render_template, request, abort, session, flash

import csv, codecs, os, datetime, json,sys, importlib, time

# from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user
from flask_migrate import Migrate

from flask_security import Security, SQLAlchemyUserDatastore
from flask_security.utils import encrypt_password
from werkzeug.utils import secure_filename


from instance import config
from functools import wraps

from flask_sslify import SSLify
from app import decorators, appconfig
from app.db_init import init_db, db, db_session, engine
from app.db_interactions import *



## IMAPLogin depende de la base de datos, por eso se importa despues de crearla
from app import IMAPLogin
login_manager = LoginManager()

def create_app(config_name):
    """ Main method of the server """

    # Creation of the app
    app = Flask(__name__, instance_relative_config=True)
    # Forced encription for deploying SSL connection
    # sslify = SSLify(app, subdomains=True)

    # Chargin config
    app.config.from_pyfile('config.py')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.getcwd()+'/app/milestones/files'

    from app import models

    # Initialisation method
    def init_system():
        with app.app_context():
            # Checking if table role exists, if not, return
            if not engine.dialect.has_table(engine, 'privilege'):
              return
            else:
                # Adding different core privileges
                user_privilege = models.Privilege(name='user')
                professor_privilege = models.Privilege(name='professor')
                admin_privilege = models.Privilege(name='admin')

                if (models.Privilege.query.filter_by(name='user').first()==None):
                    db_session.add(user_privilege)
                if (models.Privilege.query.filter_by(name='professor').first()==None):
                    db_session.add(professor_privilege)
                if (models.Privilege.query.filter_by(name='admin').first()==None):
                    db_session.add(admin_privilege)

            if not engine.dialect.has_table(engine, 'role'):
              return
            else:
                # Adding roles for functions in subjects
                user_role = models.Role(name='student')
                professor_role = models.Role(name='professor')
                admin_role = models.Role(name='admin')

                if (models.Role.query.filter_by(name='student').first()==None):
                    db_session.add(user_role)
                if (models.Role.query.filter_by(name='professor').first()==None):
                    db_session.add(professor_role)
                if (models.Role.query.filter_by(name='admin').first()==None):
                    db_session.add(admin_role)

                # Adding first user admin
                # IMPORTANT: delete after transferring admin privilege for security reasons


                try:
                    privilege_admin=get_privilege_by_name(db_session, 'admin')
                    if (get_privileges_users(db_session, privilege_admin.id)==None):
                        create_user(db_session, engine, 'admin', 'admin', 'admin')
                except:
                    create_user(db_session, engine, 'admin', 'admin', 'admin')


    # Initialisation of the app and the system
    init_system()
    db.init_app(app)

    #Close session after each request
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    # Routes

# View Routes ______________________________________________________________________________________________
    @app.route('/')
    def root_directory():
        return render_template('index.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':

            #  IMAP Login attempt
            response=IMAPLogin.IMAPLogin(db_session, engine, request.form['email'], request.form['password'])

            # Charging the username (first part of the email) in the session
            session["email"]=request.form['email']

            # If failed attempt, error
            if (response==False):
                flash('Invalid credentials', 'danger')
                return redirect('/login')

            else:
                # Changing param of logged_in in session
                session['logged_in'] = True

                return redirect('/home')


        return render_template('login.html')

    @app.route('/logout', methods=['GET', 'POST'])
    def logout():
        # Clearing everything charged in session (id, username, logged_in, etc)
        session.clear()
        return render_template('index.html')

    @app.route('/home')
    @decorators.login_required
    def home():
        privilege=get_user_privileges(db_session, session["email"])
        session["privilege"]=privilege.name
        # Obtaining current year for showing the active subjects
        # An academic year is being considered (from 1/sep until 31/aug)
        now = datetime.datetime.now()
        if  now.month<9:
            current_year=now.year-1
        else:
            current_year=now.year

        # Querying database for taking the subjects that each user has access
        subjects = []
        user_id=get_user_id(db_session,session["email"])
        subjects_id=get_subjects_from_user(db_session, user_id)

        for id in subjects_id:
            subjects.extend(get_subject_by_year(db_session, id, current_year))

        user=(session["email"].split('@'))[0]

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])


        return render_template('home.html', \
        user=user, privilege=session["privilege"], subjects= subjects, degrees=appconfig.degrees,\
        sidebar_content=sidebar_content)

    @app.route('/allSubjects')
    @decorators.login_required
    def allSubjects():
        # Querying database for taking the subjects that each user has access
        subjects = []
        # If user is admin, render all subjects
        privilege= get_user_privileges(db_session, session["email"])

        if privilege.name == 'admin':
            subjects.extend(get_all_subjects(db_session))
            return render_template('allSubjects.html', privilege=session["privilege"],\
            user=(session["email"].split('@'))[0], subjects= subjects)

        user_id= get_user_id(db_session, session["email"])
        subjects_id= get_subjects_from_user(db_session, user_id)

        for id in subjects_id:
            subjects.append(get_subject(db_session, id))

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])

        return render_template('allSubjects.html', privilege=session["privilege"], \
        user=(session["email"].split('@'))[0], subjects= subjects, sidebar_content=sidebar_content)

    @app.route('/subject/<id>', methods=['GET', 'POST'])
    @decorators.login_required
    def subject(id):
        subject=get_subject(db_session, id)
        if (subject == None):
            flash('Error! Subject does not exists', 'danger')
            return redirect('/home')

        user=(session["email"].split('@'))[0]
        practices=get_practices(db_session, id)
        privilege=get_user_privileges(db_session, session["email"])

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])


        if privilege.name== 'admin':
            role='admin'
            session["role"]=role

            return render_template('subject.html',privilege=session["privilege"], \
            user=user, role=role, subject= subject,practices=practices,degrees=appconfig.degrees, sidebar_content=sidebar_content )

        role=get_role_subject(db_session, session["email"], id)
        session["role"]=role
        session["subject_id"]=id

        sessions_in_subject=get_sessions_from_subject(db_session,id)



        return render_template('subject.html',user=user, privilege=session["privilege"], \
        role=role, subject= subject, practices=practices, degrees=appconfig.degrees,\
        sessions_in_subject=sessions_in_subject, sidebar_content=sidebar_content)

    @app.route('/manageSubject/<id>', methods=['GET', 'POST'])
    @decorators.login_required
    def manageSubject(id):
        if not (session["privilege"]=="admin"):
            role=get_role_subject(db_session, session["email"] , id)
            if not (role=="admin" or role=="professor"):
                flash('Error! You cannot do that!', 'danger')
                return redirect('/home')

        subject= get_subject(db_session, id)

        if (subject == None):
            flash('Error! Subject does not exists', 'danger')
            return redirect('/home')

        user=(session["email"].split('@'))[0]
        users = get_users_in_subject(db_session,id)

        users_in_subject=[]

        for i in range(len(users)):
            user_in=get_user_by_id(db_session,users[i][0])
            role=get_role(db_session,users[i][1])

            group=get_group_from_user_in_subject(db_session, users[i][0], id)

            if (group != None):
                grouping=get_grouping(db_session, group.grouping_id)
            else:
                grouping=None

            row = [user_in,role, grouping, group]
            users_in_subject.append(row)

        roles_db=get_roles(db_session)
        groupings=get_groupings_in_subject(db_session,id)
        groupings_json=json.dumps(groupings)
        groups=get_groups_in_subject(db_session,id)
        groups_json=json.dumps(groups)

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])

        if session["privilege"]== 'admin':
            role='admin'

            return render_template('manageSubject.html', privilege=session["privilege"], user=user,\
             role=role, subject= subject, users_in_subject=users_in_subject, roles_db=roles_db, \
             groupings_json=groupings_json, groups_json=groups_json, groupings=groupings, groups=groups,\
             sidebar_content=sidebar_content)

        role=get_role_subject(db_session, session["email"], id)

        return render_template('manageSubject.html',user=user, privilege=session["privilege"],\
        role=role, subject= subject, users_in_subject=users_in_subject, roles_db=roles_db, \
        groupings_json=groupings_json, groups_json=groups_json, groupings=groupings, groups=groups,\
        sidebar_content=sidebar_content)

    @app.route('/manageSession/<id>', methods=['GET', 'POST'])
    @decorators.login_required
    def manageSession(id):

        if not (session["role"] or session["role"]=="professor"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        session_a= get_session(db_session, id)

        if (session_a== None):
            flash('Error! Session does not exists', 'danger')
            return redirect('/home')

        user=(session["email"].split('@'))[0]
        users=get_users_in_session(db_session, id)

        users_in_session=[]

        for i in range(len(users)):
            user_in=get_user_by_id(db_session,users[i][0])

            group=get_group(db_session, users[i][1])

            if (group != None):
                grouping=get_grouping(db_session, group.grouping_id)
            else:
                grouping=None

            points=get_points_session(db_session, id, users[i][0])[0]

            row = [user_in, grouping, group,points]
            users_in_session.append(row)

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])


        return render_template('manageSession.html',user=user, privilege=session["privilege"],\
        session_a= session_a, role=session["role"],users_in_session=users_in_session, sidebar_content=sidebar_content)

    @app.route('/practice/<id>', methods=['GET', 'POST'])
    @decorators.login_required
    def practice(id):
        practice=get_practice(db_session, id)

        if (practice == None):
            flash('Error! Practice does not exists', 'danger')
            return redirect('/home')

        user=(session["email"].split('@'))[0]

        milestones=get_practice_milestones(db_session, id)

        sessions=get_sessions_from_practice(db_session, id)

        groupings=get_groupings_in_subject(db_session, practice.subject_id)

        ## Get list of milestones modes implemented in milestones folder
        modes=os.listdir(os.getcwd()+'/app/milestones')
        modes_in=[]
        for mode in modes:
            if mode == 'files' or mode=='__pycache__':
                continue
            index=mode.find('.')
            modes_in.append(mode[:(index-len(mode))])

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])

        return render_template('practice.html',user=user, privilege=session["privilege"], \
        practice=practice, role=session["role"],milestones=milestones, modes=modes_in,\
        groupings=groupings, sessions=sessions, sidebar_content=sidebar_content)

    @app.route('/session/<id>', methods=['GET', 'POST'])
    @decorators.login_required
    def session_a(id):
        session_a=get_session(db_session, id)
        user=(session["email"].split('@'))[0]
        role=get_role_session(db_session, session["email"], id)
        session["role"]=role
        session["session_id"]=id

        if (session_a== None):
            flash('Error! Practice does not exists', 'danger')
            return redirect('/home')

        groups_points=get_groups_points_session(db_session, id)

        data_table=[]
        for element in groups_points:
            group=get_group(db_session,element[0])
            grouping=get_grouping(db_session, group.grouping_id)
            row=[grouping.name, group.name,element[1]]
            data_table.append(row)

        datetimes=get_session_datetimes(db_session, id)

        start_datetime=time.mktime(datetimes[0].timetuple())
        if (datetimes[1]!=None):
            end_datetime=time.mktime(datetimes[1].timetuple())
        else:
            end_datetime=None

        timestamp=time.time()

        milestones=get_practice_milestones(db_session, session_a.practice_id)
        user_id=get_user(db_session, session["email"]).id

        active_milestones=[]
        for milestone in milestones:
            dependencies=get_milestone_dependencies(db_session,milestone.id)
            dependant=False
            if (dependencies!=[]):
                for element in dependencies:
                    if (get_log(db_session, element.dependency_id, user_id)!=[]):
                        dependant=False
                    else:
                        dependant=True
                        break

            active_milestones.append([milestone,dependant])

        sidebar_content=get_user_subject_session(db_session, user_id)

        return render_template('session.html',user=user, privilege=session["privilege"], \
        session_a=session_a, role=session["role"], data_table=data_table, start_datetime=start_datetime,\
        end_datetime=end_datetime, timestamp=timestamp, milestones=active_milestones, sidebar_content=sidebar_content)

    @app.route('/milestone/<id>', methods=['GET', 'POST'])
    @decorators.login_required
    def milestone(id):
        user=get_user(db_session,session['email'])
        milestone=get_milestone(db_session, id)
        session["milestone_id"]=id

        try:
            module_imported=importlib.import_module("app.milestones."+milestone.mode)
            data=module_imported.load(milestone)

        except Exception as e:
            print(e)
            flash('Error! Error in milestone module', 'danger')
            return redirect('/home')

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])


        return render_template('/milestoneViews/' +milestone.mode+'.html',user=user.username, \
        privilege=session["privilege"], sidebar_content=sidebar_content,data=data)

    @app.route('/verifyMilestone/', methods=['GET', 'POST'])
    @decorators.login_required
    def milestoneVerify():

        milestone_id=session["milestone_id"]
        user_id=get_user_id(db_session,session["email"])

        if not "session_id" in session:
            session_s=get_session_from_milestone(db_session, milestone_id, user_id)
        else:
            session_id=session["session_id"]
            session_s=get_session(db_session, session_id)


        user_session=get_user_session(db_session, session_s.id, user_id)
        milestone=get_milestone(db_session, milestone_id)



        try:
            module_imported=importlib.import_module("app.milestones."+milestone.mode)
            answer=module_imported.verify(request.args.to_dict(flat=False), milestone)

        except Exception as e:
            print(e)
            flash('Error! Error in milestone module', 'danger')
            return redirect('/home')


        datetime_now=datetime.datetime.now()

        # Do not receive new answers if milestone is closed
        if (session_s.end_datetime):
            end_timestamp=time.mktime(session_s.end_datetime.timetuple())
            if (session_s.end_datetime<datetime_now):
                flash('Error! Milestone closed', 'danger')
                return redirect('/milestone/'+milestone_id)


        for element in answer:
            if (element=="answer" and answer.get("answer", False)==True):
                points=answer.get("points",0)*(milestone.weight/100)

                # If time_trial==True calculate the score with time
                datetime_sql=datetime_now.strftime("%Y-%m-%d %H:%M:%S")
                timestamp =time.mktime(datetime_now.timetuple())
                start_timestamp=time.mktime(session_s.start_datetime.timetuple())

                practice=get_practice(db_session, session_s.practice_id)
                if (practice.time_trial==True):
                    if (end_timestamp):
                        time_points=appconfig.max_time_points-\
                        ((appconfig.max_time_points/(end_timestamp-start_timestamp))*(timestamp-start_timestamp))
                    else:
                        time_points=appconfig.max_time_points-\
                        appconfig.points_lost_per_second*(timestamp-start_timestamp)
                        if (time_points<0):
                            time_points=0
                else:
                    time_points=0

                # Calculate bonus for accomplishing in 1st, 2nd or 3rd place
                position=get_log_count(db_session, milestone_id, session_s.id)[0]

                if (position==0):
                    bonus=appconfig.bonus_position.get("1", 0)
                elif(position==1):
                    bonus=appconfig.bonus_position.get("2", 0)
                elif(position==2):
                    bonus=appconfig.bonus_position.get("3", 0)
                else:
                    bonus=0

                if (get_log(db_session, milestone_id, user_id)!=[]):
                    max_points=get_log_maxpoints(db_session, milestone_id, user_id)
                    new_points=points+bonus+time_points

                    add_milestone_log(db_session, milestone_id,user_id,new_points, datetime_sql)

                    if (max_points[0]<new_points):

                        updated_points=user_session.points-max_points+new_points

                        users_group=get_users_group(db_session, session_s.id, user_session.group_id)
                        for user in users_group:
                            update_user_session_points(db_session,user.session_id,user.user_id,updated_points)
                else:

                    new_points=points+bonus+time_points
                    add_milestone_log(db_session, milestone_id,user_id,new_points, datetime_sql)

                    updated_points=user_session.points+new_points

                    users_group=get_users_group(db_session, session_s.id, user_session.group_id)
                    for user in users_group:
                        update_user_session_points(db_session,user.session_id,user.user_id,updated_points)

                flash('Milestone completed', 'success')
                return redirect('/milestone/'+milestone_id)

            else:
                continue
        else:
            flash('Error! Milestone not correct', 'danger')
            return redirect('/milestone/'+milestone_id)

    @app.route('/users')
    @decorators.login_required
    @decorators.privileges_required('admin')
    def users():
        user=(session["email"].split('@'))[0]
        users = get_users_privileges(db_session)
        privileges=get_privileges(db_session)

        users_in_system=[]

        for i in range(len(users)):
            row = [get_user_by_id(db_session, users[i][0]), get_privilege(db_session,users[i][1])]
            users_in_system.append(row)

        user_id=get_user_id(db_session,session["email"])
        sidebar_content=get_user_subject_session(db_session, user_id[0])

        return render_template('users.html', user=user, users=users_in_system, \
        privilege=session["privilege"], privileges=privileges, sidebar_content=sidebar_content)

# DB Interaction Routes _____________________________________________________________________________________________________________
    @app.route('/createUser', methods=['GET', 'POST'])
    @decorators.login_required
    @decorators.privileges_required('admin')
    def createUser():
        email=request.form["email"]
        privilege=request.form["privilege"]

        if (get_user(db_session, email)!=None):
            flash('Error: User already exists', 'danger')
            return redirect('/users')

        name=email.split('@')[0]
        create_user(db_session,engine,name,email,privilege)

        flash ("Success! User " + email +" added",'success')
        return redirect('/users')

    @app.route('/createSubject', methods=['GET', 'POST'])
    @decorators.login_required
    # @decorators.privileges_required('admin', 'professor')
    def createSubject():
        acronym=request.form["acronym"]
        name=request.form["name"]
        degree=request.form["degree"]
        year= request.form["year"]
        description=request.form["description"]

        if (acronym=="" or name=="" or degree=="" or year==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/home')

        subject= create_subject(db_session, acronym, name, degree, year, description)

        add_user_to_subject(db_session, engine, session["email"], subject.id, "admin")

        return redirect('/home')

    @app.route('/createPractice', methods=['GET', 'POST'])
    @decorators.login_required
    def createPractice():
        name=request.form["name"]
        milestones=request.form["milestones"]
        time_trial=request.form["time_trial"]
        subject_id=request.form["subject_id"]
        description=request.form["description"]

        if (name=="" or milestones=="" or time_trial==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/subject/'+subject_id)

        time_trial_bool=str(time_trial).lower() in ('true')

        create_practice(db_session,name,milestones,time_trial_bool,subject_id, description)

        return redirect('/subject/'+subject_id)

    @app.route('/createSession', methods=['GET', 'POST'])
    @decorators.login_required
    def createSession():
        name=request.form["name"]
        start_date=request.form["start_date"]
        end_date=request.form["end_date"]
        practice_id=request.form["practice_id"]
        grouping_session=request.form["grouping_session"]
        initial_points=request.form["points"]
        description=request.form["description"]

        if (name=="" or start_date=="" or practice_id==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/practice/'+practice_id)

        start_year=(start_date.split(" ")[0]).split("/")[2]
        start_month=(start_date.split(" ")[0]).split("/")[1]
        start_day=(start_date.split(" ")[0]).split("/")[0]
        start_hour=(start_date.split(" ")[1]).split(":")[0]
        start_minute=(start_date.split(" ")[1]).split(":")[1]

        sql_start_date=(start_year+"-"+start_month+"-"+start_day+" "+start_hour+":"+start_minute+":00")

        if (end_date!=""):
            end_year=(end_date.split(" ")[0]).split("/")[2]
            end_month=(end_date.split(" ")[0]).split("/")[1]
            end_day=(end_date.split(" ")[0]).split("/")[0]
            end_hour=(end_date.split(" ")[1]).split(":")[0]
            end_minute=(end_date.split(" ")[1]).split(":")[1]

            sql_end_date=(end_year+"-"+end_month+"-"+end_day+" "+end_hour+":"+end_minute+":00")

        else:
            sql_end_date=None

        create_session(db_session,name,sql_start_date,sql_end_date, initial_points, practice_id, description)
        session=get_session_from_param(db_session, name,sql_start_date,sql_end_date, practice_id, description)

        users=get_users_in_grouping(db_session, grouping_session)

        for user in users:
            add_user_session(db_session, session.id,user[1],user[0],initial_points)

        return redirect('/practice/'+practice_id)

    @app.route('/createMilestone', methods=['GET', 'POST'])
    @decorators.login_required
    def createMilestone():
        name=request.form["name"]
        mode=request.form["mode"]
        weight=request.form["weight"]
        practice_id=request.form["practice_id"]
        description=request.form["description"]

        practice=get_practice(db_session, practice_id)
        milestone_dependencies=[]


        milestones=get_practice_milestones(db_session,practice_id)

        if (len(milestones)>=practice.milestones):
            flash("Error! Practice has " + str(practice.milestones) +" milestone(s) and they already exist.", 'danger')
            return redirect('/practice/'+practice_id)

        if (name=="" or mode==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/practice/'+practice_id)

        for milestone in milestones:
            if (("dependsMilestone"+str(milestone.id)) in request.form):
                milestone_dependencies.append(request.form["dependsMilestone"+str(milestone.id)])

        create_milestone(db_session, name, mode, weight, practice_id, description)
        milestone_id= get_milestone_id(db_session, name, mode, practice_id)

        for dependency in milestone_dependencies:
            add_milestone_dependency(db_session, milestone_id[0], dependency)

        return redirect('/practice/'+practice_id)

    @app.route('/deleteMilestone', methods=['GET', 'POST'])
    @decorators.login_required
    def deleteMilestone():

        practice_id=request.form["practice_id"]
        milestone_id=request.form["milestone_id"]

        delete_milestone(db_session, milestone_id)

        flash ("Success! Milestone removed",'success')

        return redirect('/practice/'+practice_id)

    @app.route('/uploadUsers', methods=['POST'])
    @decorators.login_required
    def uploadUsers():
        subject_id = request.form['subject_id']
        if request.files['file']:
            flask_file = request.files['file']
            data = []
            stream = codecs.iterdecode(flask_file.stream, 'utf-8')
            read_file=list(csv.reader(stream, dialect=csv.excel))
            read_file_lower=[]

            for x in read_file[0]:
                read_file_lower.append(x.lower())

            if 'email' in read_file_lower:
                email_index=read_file_lower.index('email')

            if 'grouping' in read_file_lower:
                grouping_name_index=read_file_lower.index('grouping')

            if 'group' in read_file_lower:
                group_name_index=read_file_lower.index('group')

            for row in read_file:
                if row:
                    if (row[email_index].lower()=="email" or row[grouping_name_index].lower() == 'grouping' \
                    or row[group_name_index].lower() == 'group' or row[grouping_name_index]==None or row[group_name_index] ==None):
                        continue

                    exists_grouping=get_grouping_by_name_and_subject(db_session, str(row[grouping_name_index]), subject_id)
                    if (exists_grouping==None and row[grouping_name_index]!=""):
                        add_grouping_subject_session(db_session, row[grouping_name_index], subject_id)

                    exists_group=get_group_by_name_and_subject(db_session, str(row[group_name_index]), subject_id)
                    if (exists_group==None and row[group_name_index] !="" ):
                        grouping=get_grouping_by_name_and_subject(db_session, str(row[grouping_name_index]) , subject_id)
                        add_group_subject_session(db_session, row[group_name_index], grouping[0])

                    if (row[email_index]):
                        if (row[group_name_index]):
                            data.append([row[email_index], row[group_name_index]])
                        else:
                            data.append([row[email_index]])

            for line in data:
                if (line[0].lower()=='email'):
                    continue
                if (len(line)==2):
                    if (line[1].lower()== 'group'):
                        continue

                name = (line[0].split('@'))[0]
                user_id = get_user_id(db_session, line[0])

                # If the user isn't in the DB, we add it
                if (user_id == None ):
                    create_user(db_session, engine, name, line[0], "user")

                # Taking id again in case the user didn't exist
                user_id = get_user_id(db_session, line[0])

                #If the user is already added, continue
                if (check_user_in_subject(db_session,subject_id,user_id)==True):
                    flash ("Warning! User "+ line[0] + " was already added",'warning')
                    continue

                add_user_to_subject(db_session, engine, line[0], subject_id, request.form["role"])

                if (len(line)==2 and line[1]!=""):
                    group=get_group_by_name_and_subject(db_session, line[1], subject_id)
                    add_user_group_subject(engine, group[0], user_id)

            return redirect('/manageSubject/'+ subject_id)
        else:
            flash ("Error! It is not a valid input", 'danger')
            return redirect('/manageSubject/'+ subject_id)

    @app.route('/uploadUser', methods=['POST'])
    @decorators.login_required
    def uploadUser():
        # Getting subject_id from form
        subject_id = request.form['subject_id']
        group = request.form['addGroup']

        # Checking if we have email in form
        if request.form['email']:
            # Taking email, name and id
            email=request.form['email']
            name = (email.split('@'))[0]
            user_id = get_user_id(db_session, email)

            # If the user isn't in the DB, we add it
            if (user_id == None):
                create_user(db_session, engine, name, email, "user")

            # Taking id again in case the user didn't exist
            user_id = get_user_id(db_session, email)

            #If the user is already added, return
            if (check_user_in_subject(db_session,subject_id,user_id)==True):
                flash ("Warning! User was already added",'warning')
                return redirect('/manageSubject/'+ subject_id)

            add_user_to_subject(db_session, engine, email, subject_id,  request.form["role"])

            if (group!="0"):
                add_user_group_subject(engine, group, user_id)

            # Redirecting to same page with a success message
            flash ("Success! User " + email +" added to subject",'success')
            return redirect('/manageSubject/'+ subject_id)
        else:
            # If there is not email, flash error
            flash ("Error! Empty input",'danger')
            return redirect('/manageSubject/'+ subject_id)

    @app.route('/uploadUserSession', methods=['POST'])
    @decorators.login_required
    def uploadUserSession():
        # Getting subject_id from form
        session_id = request.form['session_id']
        # Checking if we have email in form
        if request.form['email']:
            # Taking email, name and id
            email=request.form['email']
            user_id = get_user_id(db_session, email)

            # If the user isn't in the DB, return error
            if (user_id == None):
                flash ("Error! User not found",'danger')
                return redirect('/manageSession/'+ session_id)

            if (get_user_session(db_session, session_id, user_id)!=None):
                flash ("Error! User already added",'danger')
                return redirect('/manageSession/'+ session_id)

            session_a=get_session(db_session,session_id)
            group=get_group_session(db_session,user_id,session_a.practice_id)

            if (group==None):
                flash ("Error! User does not belong to any group",'danger')
                return redirect('/manageSession/'+ session_id)

            add_user_session(db_session, session_id,user_id,group.group_id,0)

            # Redirecting to same page with a success message
            flash ("Success! User " + email +" added to session",'success')
            return redirect('/manageSession/'+ session_id)
        else:
            # If there is not email, flash error
            flash ("Error! Empty input",'danger')
            return redirect('/manageSession/'+ session_id)

    @app.route('/updateSubject', methods=['GET', 'POST'])
    @decorators.login_required
    # @decorators.privileges_required('admin', 'professor')
    def updateSubject():
        id=request.form["id"]
        acronym=request.form["acronym"]
        name=request.form["name"]
        degree=request.form["degree"]
        year= request.form["year"]
        description=request.form["description"]

        if (acronym=="" or name=="" or degree=="" or year==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/subject/'+ id)

        update_subject(db_session,id, acronym, name, degree, year, description)

        return redirect('/subject/'+id)

    @app.route('/updateUserGroup', methods=['GET', 'POST'])
    @decorators.login_required
    # @decorators.privileges_required('admin', 'professor')
    def updateuserGroup():
        email=request.form["email"]
        subject_id=request.form["subject_id"]
        group_id=request.form["selectGroups"]
        user_id=get_user_id(db_session, email)

        if (group_id==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/manageSubject/'+ subject_id)

        groups_user=get_group_id_user(db_session,user_id[0])

        if (group_id == "0" and groups_user==[]):
            return redirect('/manageSubject/'+ subject_id)

        elif (group_id == "0" and groups_user!=[]):
            for group_user in groups_user:
                group=get_group(db_session,group_user[0])
                grouping= get_grouping(db_session, group.grouping_id)

                if (str(grouping.subject_id)==subject_id):
                    delete_user_group_subject(db_session,user_id[0], group[0])

            return redirect('/manageSubject/'+ subject_id)


        groups_user=get_group_id_user(db_session,user_id[0])
        if (groups_user==[]):
            add_user_group_subject(engine, group_id, user_id)
        else:
            changed=False
            for group_user in groups_user:
                group=get_group(db_session,group_user[0])
                grouping= get_grouping(db_session, group.grouping_id)

                if (str(grouping.subject_id)==subject_id):
                    changed=True
                    update_user_group(db_session,group[0], group_id, user_id[0])

            if (changed==False):
                add_user_group_subject(engine, group_id, user_id)


        return redirect('/manageSubject/'+subject_id)

    @app.route('/createGrouping', methods=['POST'])
    @decorators.login_required
    def createGrouping():
        name=request.form["name"]
        subject_id = request.form['subject_id']

        if (name==""):
            flash ("Error! Empty input",'danger')
            return redirect('/manageSubject/'+ subject_id)

        add_grouping_subject_session(db_session, name, subject_id)

        flash ("Success! Grouping " + name +" added to subject",'success')
        return redirect('/manageSubject/'+ subject_id)

    @app.route('/createGroup', methods=['POST'])
    @decorators.login_required
    def createGroup():
        name=request.form["name"]
        grouping_id = request.form['grouping_id']
        subject_id=request.form['subject_id']

        if (name==""):
            flash ("Error! Empty input",'danger')
            return redirect('/manageSubject/'+ subject_id)

        add_group_subject_session(db_session, name, grouping_id)

        flash ("Success! Group " + name +" added to subject",'success')
        return redirect('/manageSubject/'+ subject_id)


    @app.route('/updatePractice', methods=['GET', 'POST'])
    @decorators.login_required
    def updatePractice():
        id=request.form["practice_id"]
        name=request.form["name"]
        milestones=request.form["milestones"]
        time_trial=request.form["time_trial"]
        description=request.form["description"]
        subject_id=request.form["subject_id"]

        if (name=="" or milestones=="" or time_trial==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/practice/'+id)

        time_trial_bool=str(time_trial).lower() in ('true')

        update_practice(db_session,id,name,milestones,time_trial_bool,subject_id, description)

        return redirect('/practice/'+id)


    @app.route('/updateSession', methods=['GET', 'POST'])
    @decorators.login_required
    def updateSession():
        id=request.form["session_id"]
        name=request.form["name"]
        start_date=request.form["start_date"]
        end_date=request.form["end_date"]
        practice_id=request.form["practice_id"]
        initial_points=request.form["points"]
        description=request.form["description"]

        if (name=="" or start_date=="" or practice_id==""):
            flash('Error! Incompleted fields', 'danger')
            return redirect('/practice/'+practice_id)

        start_year=(start_date.split(" ")[0]).split("/")[2]
        start_month=(start_date.split(" ")[0]).split("/")[1]
        start_day=(start_date.split(" ")[0]).split("/")[0]
        start_hour=(start_date.split(" ")[1]).split(":")[0]
        start_minute=(start_date.split(" ")[1]).split(":")[1]

        sql_start_date=(start_year+"-"+start_month+"-"+start_day+" "+start_hour+":"+start_minute+":00")

        if (end_date!=""):
            end_year=(end_date.split(" ")[0]).split("/")[2]
            end_month=(end_date.split(" ")[0]).split("/")[1]
            end_day=(end_date.split(" ")[0]).split("/")[0]
            end_hour=(end_date.split(" ")[1]).split(":")[0]
            end_minute=(end_date.split(" ")[1]).split(":")[1]

            sql_end_date=(end_year+"-"+end_month+"-"+end_day+" "+end_hour+":"+end_minute+":00")

        else:
            sql_end_date=None

        old_points=get_session_initial_points(db_session,id)
        difference_points=int(old_points[0])- int(initial_points)

        update_session(db_session,id, name, sql_start_date, sql_end_date,initial_points, practice_id, description)

        users=get_users_in_session(db_session, id)

        for user in users:
            current_points= get_points_session(db_session,id, user[0])[0] - difference_points
            update_user_session_points(db_session,id, user[0], current_points)

        return redirect('/session/'+id)


    @app.route('/changePrivilege', methods=['GET', 'POST'])
    @decorators.login_required
    @decorators.privileges_required('admin')
    def changePrivilege():
        privilege=request.form['privilege']
        email=request.form['email']

        update_privilege(db_session, email, privilege)

        flash ("Success! You changed the privilege of " + email + " to " + privilege ,'success')
        return redirect('/users')

    @app.route('/changeRole', methods=['GET', 'POST'])
    @decorators.login_required
    def changeRole():
        role=request.form['role']
        email=request.form['email']
        subject_id=request.form['subject_id']

        update_role(db_session, email, role, subject_id)

        flash ("Success! You changed the role of " + email + " to " + role ,'success')

        return redirect('/manageSubject/'+ subject_id)

    @app.route('/changePoints', methods=['GET', 'POST'])
    @decorators.login_required
    def changePoints():
        points=request.form['points']
        email=request.form['email']
        session_id=request.form['session_id']

        user_id=get_user_id(db_session, email)

        update_user_session_points(db_session, session_id, user_id, points)

        flash ("Success! You changed the points of " + email + " to " + points ,'success')

        return redirect('/manageSession/'+ session_id)

    @app.route('/deleteUserSubject',  methods=['GET', 'POST'])
    @decorators.login_required
    def deleteUserSubject():

        if not (session["role"]=="admin" or session["role"]=="professor"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        user_id=request.form['user_id']
        subject_id=request.form['subject_id']

        delete_user_in_subject(db_session, user_id, subject_id)

        flash ("Success! User deleted from subject",'success')
        return redirect('/manageSubject/'+ subject_id)

    @app.route('/deleteUserSession',  methods=['GET', 'POST'])
    @decorators.login_required
    def deleteUserSession():
        user_id=request.form['user_id']
        session_id=request.form['session_id']

        if not (session["role"]=="admin" or session["role"]=="professor"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/session/'+session_id)

        delete_user_in_session(db_session, session_id, user_id)

        flash ("Success! User deleted from subject",'success')
        return redirect('/manageSession/'+ session_id)

    @app.route('/deleteSubject/<id>', methods=['GET','POST'])
    @decorators.login_required
    def deleteSubject(id):
        role=get_role_subject(db_session, session["email"] , id)
        if not (role=="admin"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')
        subject=get_subject(db_session, id)
        name=subject.name
        year=subject.year
        delete_subject(db_session, id)

        flash ("Success! Subject "+ name + " ("+ str(year)+" - "+str(year+1)+") deleted",'success')
        return redirect('/home')


    @app.route('/deleteUser', methods=['GET', 'POST'])
    @decorators.login_required
    @decorators.privileges_required('admin')
    def deleteUser():
        user_id=request.form['user_id']


        if not (session["privilege"]=="admin"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        delete_user(db_session,user_id)

        flash ("Success! User deleted from system",'success')
        return redirect('/users')


    @app.route('/deletePractice/<id>', methods=['GET','POST'])
    @decorators.login_required
    def deletePractice(id):
        subject_id= get_subject_id_practice(db_session, id)
        role=get_role_subject(db_session, session["email"] , subject_id)

        if not (role=="admin"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        delete_practice(db_session, id)

        return redirect('/subject/'+session["subject_id"])

    @app.route('/deleteSession/<id>', methods=['GET','POST'])
    @decorators.login_required
    def deleteSession(id):

        subject_id= get_subject_id_session(db_session, id)
        role=get_role_subject(db_session, session["email"] , subject_id)


        if not (role=="admin" or role=="professor"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        practice_id=(get_session(db_session, id)).practice_id

        delete_session(db_session, id)

        return redirect('/practice/'+ str(practice_id))

    @app.route('/deleteGroup',  methods=['GET', 'POST'])
    @decorators.login_required
    def deleteGroup():

        if not (session["role"]=="admin" or session["role"]=="professor"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        group_id=request.form['group_id']
        subject_id=request.form['subject_id']

        delete_group_subject(db_session,group_id)

        flash ("Success! Group deleted from subject",'success')
        return redirect('/manageSubject/'+ subject_id)

    @app.route('/deleteGrouping',  methods=['GET', 'POST'])
    @decorators.login_required
    def deleteGrouping():

        if not (session["role"]=="admin" or session["role"]=="professor"):
            flash('Error! You cannot do that!', 'danger')
            return redirect('/home')

        grouping_id=request.form['grouping_id']
        subject_id=request.form['subject_id']

        delete_grouping_subject(db_session,grouping_id)

        flash ("Success! Grouping deleted from subject",'success')
        return redirect('/manageSubject/'+ subject_id)

    @app.route("/getTopPoints")
    @decorators.login_required
    def getTopPoints():
        if (request.args.get("session_id")):
            session_id=request.args.get("session_id")
            top=get_top_points(db_session, session_id)

            top_groups=[]

            for i in range(len(top)):
                group_in=get_group(db_session,top[i][0])
                grouping_in=get_grouping(db_session, group_in.grouping_id)

                row = [group_in.group_id, group_in.name, grouping_in.name ,top[i][1]]

                top_groups.append(row)

            json_string = json.dumps(top_groups)

        if (request.args.get("subject_id")):
            subject_id=request.args.get("subject_id")

            top=get_top_points_subject(db_session, subject_id)


            top_groups=[]

            for i in range(len(top)):
                user_in=get_user_by_id(db_session, top[i][0])

                row = [user_in.id, user_in.email ,int(top[i][1])]


                top_groups.append(row)

            json_string = json.dumps(top_groups)


        if (request.args.get("practice_id")):
            practice_id=request.args.get("practice_id")

            top=get_top_points_practice(db_session, practice_id)


            top_groups=[]

            for i in range(len(top)):
                user_in=get_user_by_id(db_session, top[i][0])

                row = [user_in.id, user_in.email ,int(top[i][1])]

                top_groups.append(row)

            json_string = json.dumps(top_groups)

        return json_string

    @app.route('/uploadFile', methods=['GET', 'POST'])
    def upload_file():
        if request.method == 'POST':
            practice_id=request.form["practice_id"]
            milestone_id=request.form["milestone_id"]
            mode=get_milestone_mode(db_session, milestone_id)

            # check if the post request has the file part
            if 'file' not in request.files:
                flash('No file part','danger')
                return redirect('/practice/'+ practice_id)
            file = request.files['file']
            # if user does not select file, browser also
            # submit an empty part without filename
            if file.filename == '' or practice_id== '' or milestone_id=='':
                flash('Not valid input arguments given','danger')
                return redirect('/practice/'+ practice_id)

            if file:
                extension=file.filename.rsplit('.', 1)[1].lower()

                name=mode[0]+'_'+milestone_id+'.'+extension

                filename=secure_filename(name)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                flash ("Success! File uploaded",'success')

        return redirect('/practice/'+ practice_id)

# End of routes ______________________________________________________________________________


    migrate = Migrate(app,db)

    return app
