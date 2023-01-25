#  Copyright (c) 2023 Fuka Narita.
#  This source code is licensed under the MIT license found in the
#  LICENSE file in the root directory of this source tree.

#  Copyright (c) 2020 Kurohashi-Chu-Murawaki lab, Kyoto University.
#  Licensed under the MIT license.
#  https://opensource.org/licenses/mit-license.php

from datetime import date, datetime
import dateutil.parser
from flask import Flask, jsonify, render_template, request, send_from_directory, session
from flask_session import Session
from jinja2.exceptions import TemplateNotFound
import jinja2
import json
import os
from pathlib import Path
import pytz
import sys
import threading
import time
import traceback
import uuid
import base64
import hashlib


tz = pytz.timezone('Asia/Tokyo')

evt_type = {
    'action',
    'command',
    'msg'
}

COND = [""]
SALT = 'タスクの1番'.encode('utf-8')

def flatten(l):
    return [item for sublist in l for item in sublist]

def get_session_id(user_id):
    index_of_underscore = user_id.find('_')
    if index_of_underscore == -1:
        return user_id
    return user_id[:index_of_underscore]

def events_for_user(evt, user_id):
    event_for_user = {
        'from': 'self' if evt['from'] == user_id else 'other',
        'timestamp': evt['timestamp'],
        'type': evt['type']
    }
    if 'body' in evt:
        event_for_user['body'] = evt['body']
    return event_for_user

def utc_to_local(utc_timestamp):
    return datetime.fromisoformat(f"{utc_timestamp}+00:00").astimezone(tz).isoformat() if utc_timestamp else ""

def convert_chatroom_to_dict(chatroom):
    return {
        "id": chatroom.id,
        "experimentId": chatroom.experiment_id,
        "users": chatroom.users,
        "leaved_users": chatroom.leaved_users,
        "created": chatroom.created,
        "modified": chatroom.modified,
        "initiator": chatroom.initiator,
        "closed": chatroom.closed,
        "events": len(chatroom.events),
        "poll_requests": chatroom.poll_requests
    }


class BaseUser(object):

    def __init__(self, id_, attribs=dict()):
        self.id = id_
        self.attribs = attribs

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.id == other.id

    def has_matching_attribs(self, other):
        # This should be overridden by the superclass.
        # True should be returned when the other user has matching attributes with the self user
        # so that they can be matched together for a chat.  Otherwise, False is returned.
        # In this default implementation, any user is considered ok to chat with.
        return True


class BaseChatroom(object):

    def __init__(self, id_=None, experiment_id=None, initiator=None, attribs=dict()):
        self.id = id_
        self.created = datetime.utcnow().isoformat()
        self.modified = self.created
        self.events = []
        self.users = []
        self.leaved_users = {}
        self.experiment_id = experiment_id
        self.initiator = initiator
        self.closed = False
        self.poll_requests = {}
        if initiator is not None:
            self.add_user(initiator)
        self.attribs = attribs

        # 追記
        self.news = None
        self.tweets = None

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.id == other.id

    def add_event(self, event):
        timestamp = datetime.utcnow()
        self.events.append(event)
        self.modified = timestamp.isoformat()
        # print(f"add_event modified={self.modified}")
        if 'from' in event:
            self.poll_requests[event['from']].append(self.modified)

    def add_user(self, user):
        timestamp = datetime.utcnow()
        self.modified = timestamp.isoformat()
        self.users.append(user)
        if len(self.users) == 2:
            self.closed = True
        self.poll_requests[user] = [self.modified]

    def remove_user(self, user):
        if user in self.users:
            if len(self.leaved_users) == 0:
                str_user = f"U{self.users.index(user) + 1}"
            else:
                str_user = 'U2' if 'U1' in self.leaved_users else 'U1'
            self.leaved_users[str_user] = {
                'user_id': user,
                'last_poll': self.poll_requests[user][-1],
                'poll_num': len(self.poll_requests[user])
            }

            self.users.remove(user)
            self.modified = datetime.utcnow().isoformat()
            if user in self.poll_requests:
                del self.poll_requests[user]

    def has_changed(self, timestamp):
        return self.modified > timestamp

    def has_polled(self, user, timestamp):
        self.poll_requests[user].append(timestamp)


class ChatroomCleaner(threading.Thread):

    def __init__(self, server, logger, check_interval=30):
        threading.Thread.__init__(self)
        self.server = server
        self.logger = logger
        self.check_interval = check_interval

    def run(self):
        while True:
            try:
                time.sleep(self.check_interval)
                self.server.clean_inactive_users()
            except:
                (typ, val, tb) = sys.exc_info()
                error_msg = "An exception occurred in the ChatroomCleaner:\n"
                for line in traceback.format_exception(typ, val, tb):
                    error_msg += line + "\n"
                self.logger.debug(error_msg)


class BaseApi:

    def __init__(self, cfg, logger, user_class=BaseUser, chatroom_class=BaseChatroom):
        self.cfg = cfg
        self.logger = logger
        self.user_class = user_class
        self.chatroom_class = chatroom_class

        self.mutex = threading.Lock()

        self.users = {}

        # Dictionaries organized by chatroom ids.
        self.chatrooms = {}
        self.chatroom_locks = {}
        self.released_chatrooms = {}

        self.chatroom_cleaner = ChatroomCleaner(self, self.logger,
                                                check_interval=self.cfg['chatroom_cleaning_interval'])
        self.chatroom_cleaner.start()

    def version(self):
        return "1.0"

    def get_chatrooms(self):
        return {
            "chatrooms": list(self.chatrooms.values()),
            "released_chatrooms": list(self.released_chatrooms.values())
        }

    def join(self, user_id, attribs=dict()):
        self.logger.debug(f"join user={user_id} attribs={attribs}")
        self.mutex.acquire()

        try:
            user = self.user_class(user_id, attribs)
            self.users[user_id] = user

            if 'prevent_multiple_tabs' in self.cfg and self.cfg['prevent_multiple_tabs'] == 'True':
                all_users = flatten([chatroom.users for chatroom in self.chatrooms.values()])
                all_sessions = set([get_session_id(user_id) for user_id in all_users])
                if get_session_id(user_id) in all_sessions:
                    return f"Error: MultipleTabAccessForbidden for user: {user_id}."

            # Try to find an available partner.
            # If none is found, assign the user to a new chatroom.
            available_chatrooms = [self.chatrooms[id_] for id_ in self.chatrooms if
                                    len(self.chatrooms[id_].users) == 1 and
                                    not self.chatrooms[id_].closed and
                                    user_id not in self.chatrooms[id_].users and
                                    user.has_matching_attribs(self.chatrooms[id_].users[0])]

            system_or_user = request.form['systemOrUser']
            in_chatroom = False
            if system_or_user == "system":
                if len(available_chatrooms) > 0:
                    for chatroom in sorted(available_chatrooms, key=lambda x: x.created, reverse=False):
                        if not chatroom.initiator:
                            if chatroom.id in self.chatroom_locks:
                                self.chatroom_locks[chatroom.id].acquire()
                                try:
                                    chatroom.initiator = user_id
                                    chatroom.add_user(user_id)
                                    self.logger.info(f"{user_id} joined as system")
                                    in_chatroom = True
                                finally:
                                    self.chatroom_locks[chatroom.id].release()
                        if in_chatroom:
                            break
                if not in_chatroom:
                    experiment_id = self.cfg['experiment_id']
                    chatroom = self.chatroom_class(id_=str(uuid.uuid4()), experiment_id=experiment_id,
                                                   initiator=user_id)
                    self.chatrooms[chatroom.id] = chatroom
                    self.chatroom_locks[chatroom.id] = threading.Lock()

            else:
                if len(available_chatrooms) > 0:
                    for chatroom in sorted(available_chatrooms, key=lambda x: x.created, reverse=False):
                        if chatroom.initiator:
                            if chatroom.id in self.chatroom_locks:
                                self.chatroom_locks[chatroom.id].acquire()
                                try:
                                    chatroom.add_user(user_id)
                                    in_chatroom = True
                                finally:
                                    self.chatroom_locks[chatroom.id].release()
                        if in_chatroom:
                            break

                if not in_chatroom:
                    experiment_id = self.cfg['experiment_id']
                    chatroom = self.chatroom_class(id_=str(uuid.uuid4()), experiment_id=experiment_id)
                    chatroom.add_user(user_id)
                    self.chatrooms[chatroom.id] = chatroom
                    self.chatroom_locks[chatroom.id] = threading.Lock()

            self.logger.debug(f"User {user_id} is assigned to chatroom {chatroom.id}.")

            data = self._get_chatroom_data(chatroom.id)
            return data
        except:
            self.logger.info('data is None!')
            return None
        finally:
            self.mutex.release()

    def set_news(self, chatroom_id, news, tweets):
        self.chatrooms[chatroom_id].news = news
        self.chatrooms[chatroom_id].tweets = tweets

    def get_chatroom(self, chatroom_id, user_id, client_timestamp):
        self.logger.debug(f"get_chatroom chatroom={chatroom_id} user={user_id} client_timestamp={client_timestamp}")
        request_time = datetime.utcnow()

        while True:
            if chatroom_id in self.chatroom_locks:
                chatroom_lock = self.chatroom_locks[chatroom_id]

                chatroom_lock.acquire()
                try:
                    if chatroom_id not in self.chatrooms:
                        self.logger.debug("chatroom_id not in self.chatroom")
                        return None
                    chatroom = self.chatrooms[chatroom_id]
                    if user_id not in chatroom.users:
                        self.logger.debug("user_id not in chatroom.users")
                        return None
                    chatroom.has_polled(user_id, request_time.isoformat())
                    chatroom_has_changed = not client_timestamp or chatroom.has_changed(client_timestamp)
                    self.logger.debug(f"user {user_id} checks if the chatroom has changed={chatroom_has_changed} "
                                      f"modified={chatroom.modified} vs client_timestamp={client_timestamp}")
                    if chatroom_has_changed:
                        data = self._get_chatroom_data(chatroom_id)
                        self.logger.debug("chatroom_has_changed")
                        return data

                finally:
                    chatroom_lock.release()

            # Make sure that the function terminates after a certain delay.
            # Otherwise, the poll requests will accumulate and make the web server crash.
            waiting_period = (datetime.utcnow() - request_time).total_seconds()
            if waiting_period >= (self.cfg['poll_interval']):
                self.logger.debug(f"Waiting period has expired: {waiting_period}")
                return "expired"

            time.sleep(1.0)

    def post_message(self, user_id, chatroom_id, message, used_tweet):
        self.logger.debug(f"post_message user_id={user_id} chatroom_id={chatroom_id} message={message}")
        if chatroom_id not in self.chatroom_locks:
            return

        chatroom_lock = self.chatroom_locks[chatroom_id]
        chatroom_lock.acquire()
        try:
            if chatroom_id not in self.chatrooms:
                return
            chatroom = self.chatrooms[chatroom_id]
            if user_id not in chatroom.users:
                return
            evt = {
                'type': 'msg',
                'from': user_id,
                'body': message,
                'timestamp': datetime.utcnow().isoformat(),
                'used_tweet': used_tweet
            }
            chatroom.add_event(evt)

            data = self._get_chatroom_data(chatroom_id)
            return data
        finally:
            chatroom_lock.release()

    def leave_chatroom(self, user_id, chatroom_id, news, cond):
        self.logger.debug(f"leave_chatroom user_id={user_id} chatroom_id={chatroom_id}")
        self.mutex.acquire()
        try:
            data = self._leave_chatroom(user_id, chatroom_id, news, cond)
            return data
        finally:
            self.mutex.release()

    def clean_inactive_users(self):
        self.logger.debug("clean_inactive_users")
        start = time.time()
        self.mutex.acquire()
        try:
            inactive_users = []
            now = datetime.utcnow()
            for chatroom_id in self.chatrooms:
                if chatroom_id in self.chatroom_locks:
                    chatroom_lock = self.chatroom_locks[chatroom_id]
                    chatroom_lock.acquire()
                    try:
                        chatroom = self.chatrooms[chatroom_id]
                        for user_id in chatroom.users:
                            if user_id in chatroom.poll_requests.keys():
                                last_poll = datetime.fromisoformat(chatroom.poll_requests[user_id][-1])
                                self.logger.debug(f"now={now} type={type(now)} last_poll={last_poll} type={type(last_poll)}")
                                delta = now - last_poll

                                # Fix to prevent this normalization issue that occurs when the now and last_poll values are very close to each other:
                                # https://stackoverflow.com/questions/28677673/why-does-datetime-datetime-now-datetime-datetime-now-equal-to-datetime-tim
                                delta_in_secs = delta.seconds if delta.days >= 0 else 0

                                self.logger.debug(
                                    f"Check user {user_id}... Last poll: {last_poll.isoformat()} Now: {now.isoformat()}"
                                    " Delta(s): {delta_in_secs}"
                                )
                                # To play safe, I use a larger value than poll_interval
                                if delta_in_secs > self.cfg['poll_interval'] * 3:
                                    self.logger.debug(f"{user_id} has been inactive for too long. Let's kick him out of room {chatroom_id}")
                                    inactive_users.append((user_id, chatroom_id))
                    finally:
                        chatroom_lock.release()
            for inactive_user in inactive_users:
                user_id, chatroom_id = inactive_user
                self._leave_chatroom(user_id, chatroom_id, "in_active_user", "in_active_user")
        finally:
            self.mutex.release()
            self.logger.debug(f"clean_inactive_users performed in {time.time() - start}")

    def _get_chatroom_data(self, chatroom_id):
        chatroom = self.chatrooms[chatroom_id]

        data = {
            'chatroom': chatroom,
            'msg_count_low': self.cfg['msg_count_low'],
            'msg_count_high': self.cfg['msg_count_high'],
            'poll_interval': self.cfg['poll_interval'],
            'delay_for_partner': self.cfg['delay_for_partner']
        }
        return data

    def _leave_chatroom(self, user_id, chatroom_id, news, cond):  # ここにcond_idを入れよう 2人で対話するのにuser_idなぜ一つ？
        if chatroom_id not in self.chatrooms:
            return
        chatroom = self.chatrooms[chatroom_id]
        if user_id not in chatroom.users:
            return

        chatroom.remove_user(user_id)
        if len(chatroom.users) == 0:
            self._archive_dialog(chatroom_id, news, cond)
            self.released_chatrooms[chatroom_id] = self.chatrooms[chatroom_id]
            self.chatrooms.pop(chatroom_id)
            self.chatroom_locks.pop(chatroom_id)
            return

        data = self._get_chatroom_data(chatroom_id)
        return data

    def _archive_dialog(self, chatroom_id, news, cond):
        self.logger.debug(f"Archiving dialog from chatroom {chatroom_id}...")

        creation_date = dateutil.parser.parse(self.chatrooms[chatroom_id].created)

        tz = pytz.timezone('Asia/Tokyo')

        dialog_dir = f"{self.cfg['archives']}/{creation_date.year}/{creation_date.month:02}/{creation_date.day:02}"
        Path(dialog_dir).mkdir(parents=True, exist_ok=True)
        dialog_filename = f"{chatroom_id}.txt"
        with open(f"{dialog_dir}/{dialog_filename}", mode="w") as output_file:
            if self.chatrooms[chatroom_id].experiment_id:
                output_file.write(f"Experiment: {self.chatrooms[chatroom_id].experiment_id}\n")
                news = self.chatrooms[chatroom_id].news
                tweets = self.chatrooms[chatroom_id].tweets
                output_file.write(f"news: {news}\ncond = {cond}\ntweets =\n")
                for i, tweet in enumerate(tweets):
                    output_file.write(f"{i:02} {tweet}\n")
            for i, evt in enumerate(self.chatrooms[chatroom_id].events):
                str_from = f"U{1 if evt['from'] == self.chatrooms[chatroom_id].initiator else 2}"
                timestamp = datetime.fromisoformat(f"{evt['timestamp']}+00:00").astimezone(tz).isoformat()
                output_file.write(f"{i:02} {timestamp}|{str_from} [{evt['used_tweet']}] :\t {evt['body']}\n")
        self.logger.debug(f"Dialog has been archived in {dialog_dir}/{dialog_filename}")


class BaseApp(Flask):

    def __init__(self, import_name, api):
        Flask.__init__(self, import_name)

        my_loader = jinja2.ChoiceLoader([
            self.jinja_loader,
            jinja2.FileSystemLoader(os.path.join(sys.prefix, 'templates')),
        ])
        self.jinja_loader = my_loader

        self.api = api
        self.cfg = api.cfg
        self.logger = api.logger

        self.SESSION_TYPE = 'filesystem'
        self.SESSION_COOKIE_NAME = 'CGISESSID'
        self.SESSION_FILE_DIR = self.cfg['sessions']
        self.SESSION_COOKIE_PATH = self.cfg['cookiePath']
        self.SESSION_COOKIE_SECURE = True

        self.config.from_object(self)

        self.cond_id = 0

        self.news = "initial_value"
        self.cond = "initial_cond"
        self.tweet_lst = "initial_tweet_lst"
        self.crowd_sourcing_url = self.cfg['crowd_sourcing_url']
        self.urls_path = self.cfg["urls_path"]
        Session(self)

        self.system_hash_set = set()
        for i in range(self.cfg["number_of_dialog"]):
            self.system_hash_set.add(self.hashing_urlsafe(str(i + self.cfg["experiment_id"] * 2)))

        self.user_hash_set = set()
        for i in range(self.cfg["number_of_dialog"]):
            self.user_hash_set.add(self.hashing_urlsafe(str(i + self.cfg["experiment_id"] * 3 + 1)))

        with open(self.urls_path, 'w') as wf:
            for system_hash in self.system_hash_set:
                wf.write(f"{self.crowd_sourcing_url}system_index_{system_hash}\n")
                self.logger.info(f"{self.crowd_sourcing_url}system_index_{system_hash}\n")

            for user_hash in self.user_hash_set:
                wf.write(f"{self.crowd_sourcing_url}user_index_{user_hash}\n")
                self.logger.info(f"{self.crowd_sourcing_url}user_index_{user_hash}\n")

        @self.route(f"/{self.cfg['web_context']}/static/<path:path>")
        def get_static(path):
            return self.get_static(path)

        @self.route(f"/{self.cfg['web_context']}/default_static/<path:path>")
        def get_default_static(path):
            return self.get_default_static(path)

        @self.route(f"/{self.cfg['web_context']}/version")
        def version():
            return self.version()

        @self.route(f"/{self.cfg['web_context']}/index")
        def index():
            return self.index()

        @self.route(f"/{self.cfg['web_context']}/system_index_<uid>")
        def system_index(uid):
            return self.system_index(uid)

        @self.route(f"/{self.cfg['web_context']}/user_index_<uid>")
        def user_index(uid):
            return self.user_index(uid)

        @self.route(f"/{self.cfg['web_context']}/admin")
        def admin():
            return self.admin()

        @self.route(f"/{self.cfg['web_context']}/join", methods=['POST'])
        def join():
            return self.join(session, request)

        @self.route(f"/{self.cfg['web_context']}/chatroom")
        def get_chatroom():
            return self.get_chatroom(session, request)

        @self.route(f"/{self.cfg['web_context']}/post", methods=['POST'])
        def post_message():
            return self.post_message(session, request)

        @self.route(f"/{self.cfg['web_context']}/leave")
        def leave_chatroom():
            return self.leave_chatroom(session, request)

    def get_static(self, path):
        return send_from_directory('static', path)

    def get_default_static(self, path):
        abs_base_path = os.path.join(sys.prefix, 'static')
        # Useful to test the framework as is.
        if not os.path.isdir(abs_base_path):
            abs_base_path = Path(sys.prefix).parent / 'static'
        return send_from_directory(abs_base_path, path)

    def hashing_urlsafe(self, s: str) -> str:
        h = hashlib.sha256()
        # SALT = 'タスクの1番'.encode('utf-8')
        h.update(SALT)
        h.update(s.encode('utf-8'))
        return ('0' * 32 + base64.urlsafe_b64encode(h.digest()).rstrip(b'=').decode('ascii'))[-32:]

    def version(self):
        version = self.api.version()
        try:
            return render_template(template_name_or_list='version.html', version=version)
        except TemplateNotFound:
            return render_template(template_name_or_list='default_version.html', version=version)

    def system_index(self, uid):
        if uid not in self.system_hash_set:
            return render_template(
                template_name_or_list='errorInvalidAccess.html',
                news=self.news
            )
        try:
            with open(self.cfg["news_json"]) as rf:
                line = json.load(rf)
                if "news_num" in self.cfg and self.cfg["news_num"] >= 0:
                    news_num = self.cfg["news_num"]
                else:
                    self.cond_id += 1
                    news_num = self.cond_id % len(line)

                self.news = (line[news_num]["title"], line[news_num]["url"])
                self.tweet_lst = line[news_num]["tweets"]
                for text, tid in self.tweet_lst:
                    text.replace("&gt;", ">").replace("&lt;", "<")
            cond_num = self.cfg["cond_num"]
            self.cond = COND[cond_num]

            return render_template(
                template_name_or_list='system_index.html',
                news_num=news_num,
                news=self.news,
                cond=self.cond,
                tweet_lst=self.tweet_lst,
                msg_count_low=self.cfg["msg_count_low"],
                msg_count_high=self.cfg["msg_count_high"],
            )
        except TemplateNotFound:
            return render_template(template_name_or_list='default_index.html')

    def user_index(self, uid):
        if uid not in self.user_hash_set:
            return render_template(
                template_name_or_list='errorInvalidAccess.html'
            )
        try:
            return render_template(template_name_or_list='user_index.html')
        except TemplateNotFound:
            return render_template(template_name_or_list='default_index.html')

    def admin(self):
        data = self.api.get_chatrooms()
        chatrooms = [convert_chatroom_to_dict(chatroom) for chatroom in data['chatrooms']]
        released_chatrooms = [convert_chatroom_to_dict(released_chatrooms)
                                for released_chatrooms in data['released_chatrooms']]
        try:
            return render_template(
                template_name_or_list='admin.html',
                chatrooms=chatrooms,
                released_chatrooms=released_chatrooms,
                experiment_id=self.cfg['experiment_id'],
                utc_to_local=utc_to_local)
        except TemplateNotFound:
            return render_template(
                template_name_or_list='default_admin.html',
                chatrooms=chatrooms,
                released_chatrooms=released_chatrooms,
                experiment_id=self.cfg['experiment_id'],
                utc_to_local=utc_to_local)

    def join(self, session, request):
        if 'clientTabId' not in request.form:
            return '', 400

        client_tab_id = request.form['clientTabId']
        system_or_user = request.form['systemOrUser']
        news_num = int(request.form['newsNum'])
        with open(self.cfg["news_json"]) as rf:
            line = json.load(rf)
            news = (line[news_num]["title"], line[news_num]["url"])
            tweet_lst = line[news_num]["tweets"]
            for text, tid in tweet_lst:
                text.replace("&gt;", ">").replace("&lt;", "<")
        user_id = f'{session.sid}_{client_tab_id}'
        data = self.api.join(user_id)

        if isinstance(data, str) and data.startswith("Error: MultipleTabAccessForbidden"):
            return self.error_forbidden_access_multiple_tabs()

        if system_or_user == "system":
            self.api.set_news(data['chatroom'].id, news, tweet_lst)
            self.logger.info(f"{data['chatroom'].id}に{news}を保存しました")

        try:
            return render_template(
                template_name_or_list='chatroom.html',
                client_tab_id=client_tab_id,
                msg_count_low=data['msg_count_low'],
                msg_count_high=data['msg_count_high'],
                poll_interval=data['poll_interval'],
                delay_for_partner=0 if data['chatroom'].closed else data['delay_for_partner'],
                experiment_id=data['chatroom'].experiment_id,
                chatroom_id=data['chatroom'].id,
                is_first_user=(data['chatroom'].initiator == user_id),
                server_url='',
                news=news,
                tweet_lst=tweet_lst,
                cond=self.cond,
            )
        except TemplateNotFound:
            return render_template(
                template_name_or_list='default_chatroom.html',
                client_tab_id=client_tab_id,
                msg_count_low=data['msg_count_low'],
                msg_count_high=data['msg_count_high'],
                poll_interval=data['poll_interval'],
                delay_for_partner=0 if data['chatroom'].closed else data['delay_for_partner'],
                experiment_id=data['chatroom'].experiment_id,
                chatroom_id=data['chatroom'].id,
                is_first_user=(data['chatroom'].initiator == user_id)
            )

    def get_chatroom(self, session, request):
        params = request.args.to_dict()
        if 'clientTabId' not in params or 'id' not in params or 'timestamp' not in params:
            return '', 400
        client_tab_id = params.get('clientTabId')
        chatroom_id = params.get('id')
        client_timestamp = params.get('timestamp')
        user_id = f'{session.sid}_{client_tab_id}'
        data = self.api.get_chatroom(chatroom_id, user_id, client_timestamp if client_timestamp != '' else None)
        response = "{}"
        if data is not None:
            if data == "expired":
                response = '{"msg": "poll expired"}'
            else:
                response = self._get_chatroom_response(user_id, data)
        return jsonify(response)

    def post_message(self, session, request):
        if 'clientTabId' not in request.form or 'chatroom' not in request.form or 'message' not in request.form:
            return '', 400
        client_tab_id = request.form['clientTabId']
        chatroom_id = request.form['chatroom']
        message = request.form['message']
        used_tweet = request.form['tweets']
        user_id = f'{session.sid}_{client_tab_id}'
        data = self.api.post_message(user_id, chatroom_id, message, used_tweet)
        response = "{}"
        if data is not None:
            response = self._get_chatroom_response(user_id, data)
        return jsonify(response)

    def leave_chatroom(self, session, request):
        params = request.args.to_dict()
        if 'clientTabId' not in params or 'chatroom' not in params:
            return '', 400
        client_tab_id = params.get('clientTabId')
        chatroom_id = params.get('chatroom')

        user_id = f'{session.sid}_{client_tab_id}'
        data = self.api.leave_chatroom(user_id, chatroom_id, self.news, self.cond)
        response = "{}"
        if data is not None:
            response = self._get_chatroom_response(user_id, data)
        return jsonify(response)

    def error_forbidden_access_multiple_tabs(self):
        try:
            return render_template(
                template_name_or_list='errorForbiddenAccess.html'
            )
        except TemplateNotFound:
            return render_template(
                template_name_or_list='default_errorForbiddenAccess.html'
            )

    def _get_chatroom_response(self, user_id, data):
        formatted_events = [events_for_user(evt, user_id) for evt in data['chatroom'].events]
        try:
            # assert data['chatroom'] is not None
            response = render_template(
                template_name_or_list='chatroom.json',
                chatroom_id=data['chatroom'].id,
                experiment_id=data['chatroom'].experiment_id,
                users=json.dumps(data['chatroom'].users),
                created=data['chatroom'].created,
                modified=data['chatroom'].modified,
                initiator="self" if data['chatroom'].initiator == user_id else "other",
                closed="true" if data['chatroom'].closed else "false",
                events=json.dumps(formatted_events, ensure_ascii=False),
                msg_count_low=data['msg_count_low'],
                msg_count_high=data['msg_count_high'],
                poll_interval=data['poll_interval'],
                delay_for_partner=data['delay_for_partner']
            )
        except TemplateNotFound:
            response = render_template(
                template_name_or_list='default_chatroom.json',
                chatroom_id=data['chatroom'].id,
                experiment_id=data['chatroom'].experiment_id,
                users=json.dumps(data['chatroom'].users),
                created=data['chatroom'].created,
                modified=data['chatroom'].modified,
                initiator="self" if data['chatroom'].initiator == user_id else "other",
                closed="true" if data['chatroom'].closed else "false",
                events=json.dumps(formatted_events, ensure_ascii=False),
                msg_count_low=data['msg_count_low'],
                msg_count_high=data['msg_count_high'],
                poll_interval=data['poll_interval'],
                delay_for_partner=data['delay_for_partner']
            )
        return response
