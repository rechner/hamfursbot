#!/usr/bin/env python3

import os
import re
import time
import datetime
import math
import random
import requests
import json
import schedule
import telebot
from io import BytesIO
from telebot import apihelper, types
from pymongo import MongoClient
import threading
import logging
from metaphone import doublemetaphone
from PIL import Image, ImageDraw, ImageFont

import reversebeacon
import hamqth
import callsigns

API_TOKEN = os.environ["TELEGRAM_API_TOKEN"]
HAMFURS = os.environ["HAMFURS_CHAT_ID"]
APRS_FI_KEY = os.environ["HAMFURS_APRS_FI_KEY"]
HAMQTH_USER = os.environ["HAMFURS_HAMQTH_USER"]
HAMQTH_PASS = os.environ["HAMFURS_HAMQTH_PASS"]

ENABLE_REVERSEBEACON = False

logger = telebot.logger
hamfurs_log = logging.getLogger("HamfursBot")
formatter = logging.Formatter(
    "%(asctime)s (%(filename)s:%(lineno)d %(threadName)s) "
    '%(levelname)s - %(name)s: "%(message)s"'
)

# console_output_handler = logging.StreamHandler(sys.stderr)
# console_output_handler.setFormatter(formatter)
# logger.addHandler(console_output_handler)
# hamfurs_log.addHandler(console_output_handler)

logger.setLevel(logging.INFO)
hamfurs_log.setLevel(logging.INFO)

definition_regex = re.compile(r"(.*?):(.*?)([^\\]\#\w.*)?$")

# Pretty print a list
oxford_string = lambda data: ", ".join(data[:-2] + [" and ".join(data[-2:])])

NORWAY_CALL_PREFIXES = ["JW", "JX", "3Y"]
NORWAY_CALL_PREFIXES += ["L" + a for a in list(map(chr, range(ord("A"), ord("N") + 1)))]


class HamQTHStub(object):
    def __init__(self, *args, **kwargs):
        pass

    def callbook(self, *args, **kwargs):
        pass


# Override to handle processing spotter stream
class NotifyTelebot(telebot.TeleBot):
    def __init__(self, *args, **kwargs):
        self.db = kwargs["db"]
        del kwargs["db"]
        self.logger = logging.getLogger("Telebot")
        super().__init__(*args, **kwargs)

        self.oneminute_spots = {}
        self.muted = False
        if ENABLE_REVERSEBEACON:
            self.reload_callsigns()
            self.reversebeacon = reversebeacon.ReverseBeaconClient("KF3RRY")
            schedule.every(10).minutes.do(self.reload_callsigns)
            schedule.every(1).minutes.do(self.one_minute_cron)

    def mute_spots(self):
        self.muted = True
        self.logger.debug("Spotter notifications muted")
        if ENABLE_REVERSEBEACON:
            schedule.every(60).minutes.do(self.unmute_spots)

    def unmute_spots(self):
        self.muted = False
        self.logger.debug("Spotter notifications unmuted")
        if ENABLE_REVERSEBEACON:
            return schedule.CancelJob

    def reload_callsigns(self):
        logger.debug("Refreshing callsign watch list")
        rv = self.db.aliases.find({}, {"callsign": 1})
        self.callsigns = [row["callsign"] for row in rv]

    def one_minute_cron(self):
        logger.debug("Culling one minute spots")
        for key in list(self.oneminute_spots.keys()):
            if int(time.time()) - self.oneminute_spots[key]["time"] > 60:
                logger.debug("{0} stale, culling".format(key))
                del self.oneminute_spots[key]

    def polling(self, none_stop=False, interval=0, timeout=10):
        print("Call polling()")
        self.__non_threaded_polling(none_stop, interval, timeout)

    def __retrieve_updates(self, timeout=20):
        """
        Retrieves any updates from the Telegram API.
        Registered listeners and applicable message handlers will be
        notified when a new message arrives.
        :raises ApiException when a call has failed.
        """
        if self.skip_pending:
            logger.debug("Skipped {0} pending messages".format(self.__skip_updates()))
            self.skip_pending = False
        updates = self.get_updates(offset=(self.last_update_id + 1), timeout=timeout)
        self.process_new_updates(updates)

    def __non_threaded_polling(self, none_stop=False, interval=0, timeout=5):
        logger.info("Started polling.")
        self.__stop_polling = threading.Event()
        self.__stop_polling.clear()
        error_interval = 0.25

        while not self.__stop_polling.wait(interval):
            try:
                logger.debug("tick")
                self.process_rbn()
                self.__retrieve_updates(timeout)
                error_interval = 0.25
            except apihelper.ApiException as e:
                raise
                logger.error(e)
                if not none_stop:
                    self.__stop_polling.set()
                    if ENABLE_REVERSEBEACON:
                        self.reversebeacon.close()
                    logger.info("Exception occurred. Stopping.")
                else:
                    raise
                    logger.info(
                        "Waiting for {0} seconds until retry".format(error_interval)
                    )
                    time.sleep(error_interval)
                    error_interval *= 2
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt received.")
                self.__stop_polling.set()
                if ENABLE_REVERSEBEACON:
                    self.reversebeacon.close()
                break

        logger.info("Stopped polling.")

    def process_rbn(self):
        schedule.run_pending()
        if not ENABLE_REVERSEBEACON:
            return
        skimmer_line = "(via {skimmer}, {rate} {units} @ {snr} dB, {time})"
        chunk = self.reversebeacon.read_chunk()
        for line in chunk:
            # Do something with the info
            if line.callsign in self.callsigns:
                if self.muted:
                    logger.info(
                        "Heard {0}, but notifications are muted".format(line.callsign)
                    )
                    continue

                logger.info("Heard {0} - process notification".format(line.callsign))
                # Check if they were heard in the last minute:
                if line.callsign in self.oneminute_spots.keys():
                    # Increment the spot counter and update matching telegram message:
                    self.oneminute_spots[line.callsign]["count"] += 1
                    message = self.oneminute_spots[line.callsign]["message"]
                    text = message.text + "\n" + skimmer_line.format(**line)
                    message = bot.edit_message_text(
                        chat_id=HAMFURS, message_id=message.message_id, text=text
                    )
                    if message:
                        logger.warn(
                            "Tried to edit message for {0}, but last message was unchanged".format(
                                line.callsign
                            )
                        )
                    else:
                        self.oneminute_spots[line.callsign]["message"] = message
                else:
                    # Send message and add them to self.oneminute_spots
                    text = (
                        "Heard *{callsign}* calling {match} on {frequency} operating {mode}\n"
                        + skimmer_line
                    )
                    logger.info(text.format(**line))
                    message = self.send_message(
                        HAMFURS, text=text.format(**line), parse_mode="Markdown"
                    )
                    self.oneminute_spots[line.callsign] = {
                        "message": message,
                        "count": 1,
                        "time": int(time.time()),
                    }

            # logger.debug("Heard: {0}".format(line.callsign))


# bot = telebot.TeleBot(API_TOKEN)
mongo_client = MongoClient(host=os.environ["HAMFURS_MONGO_HOST"])
mongo_db = mongo_client.arrl
bot = NotifyTelebot(API_TOKEN, threaded=False, db=mongo_client.hamfurs)

try:
    hamqth_client = hamqth.HamQTH(HAMQTH_USER, HAMQTH_PASS)
    # hamqth_client = HamQTHStub()
except TimeoutError as e:
    # We didn't need you anyways
    logger.error(e)
    logger.error("Unable to use HamQTH (is it down?) - those lookup calls will fail")
    hamqth_client = HamQTHStub()
    pass

with open("res/flags.json") as f:
    flag_json = json.load(f)
FLAG_EMOJI = {row["name"]: row["emoji"] for row in flag_json}


def is_canadian(callsign):
    if callsign.upper()[:2] in ("VE", "VA", "VO", "VY", "CY"):
        return True
    return False


def is_norwegian(callsign):
    if callsign.upper()[:2] in NORWAY_CALL_PREFIXES:
        return True
    return False


def is_australian(callsign):
    if callsign.upper()[:2] in ("VK", "VI", "AX"):
        return True
    return False


def get_pinned_message(chat_id):
    chat = bot.get_chat(chat_id)
    return chat.pinned_message


def get_message_url(message):
    if message is None:
        return None
    if message.chat.username is not None:
        return "https://t.me/{0}/{1}".format(message.chat.username, message.message_id)
    return None


# @bot.message_handler(content_types=['join_chat_member',])


@bot.message_handler(commands=["register"])
def register_callsign(message):
    chat_id = message.chat.id

    def register_callsign_interactive(message):
        register_alias(message, message.text)

    if " " not in message.text:
        # interactive
        markup = types.ForceReply(selective=True)
        next_msg = bot.reply_to(
            message, "OK, please specify a callsign to alias", reply_markup=markup
        )
        bot.register_for_reply(next_msg, register_callsign_interactive)
        return

    callsign = message.text.split(" ")[1].upper()
    register_alias(message, callsign)


def register_alias(message, callsign):
    chat_id = message.chat.id
    db = mongo_client.hamfurs.aliases

    timestamp = int(time.time())
    username_lower = None
    if message.from_user.username is not None:
        username_lower = message.from_user.username.lower()
    callsign = callsign.upper()

    document = {
        "callsign": callsign,
        "user_id": message.from_user.id,
        "user_name": message.from_user.username,
        "user_name_lower": username_lower,
        "user_first": message.from_user.first_name,
        "user_last": message.from_user.last_name,
        "alias": None,
        "bio": None,
        "twitter": None,
        "updated": timestamp,
    }

    r = db.replace_one({"user_id": message.from_user.id}, document, upsert=True)
    if r.modified_count == 0:
        r = db.replace_one(
            {"user_name": message.from_user.username}, document, upsert=True
        )
    if r.modified_count:
        bot.send_message(
            chat_id=chat_id,
            text="Updated callsign alias for {0}".format(
                format_user(message.from_user)
            ),
        )
    else:
        bot.send_message(
            chat_id=chat_id,
            text="Created callsign alias for {0}".format(
                format_user(message.from_user)
            ),
        )


def format_user(from_user, use_handle=False):
    if use_handle:
        if from_user.username is not None:
            return "@{0}".format(from_user.username)
    if from_user.last_name is None:
        return from_user.first_name
    else:
        return "{0} {1}".format(from_user.first_name, from_user.last_name)


def escape_markdown(text):
    text = text.replace("_", "\_")
    text = text.replace("*", "\*")
    text = text.replace("[", "\[")
    text = text.replace("]", "\]")
    return text


def is_administrator(message):
    if message.from_user.username == "rechner":
        return True
    administrators = bot.get_chat_administrators(chat_id=message.chat.id)
    administrator_ids = [row.user.id for row in administrators]
    if message.from_user.id in administrator_ids:
        return True
    return False


# @bot.message_handler(commands=['nuke',])
def nuke_aliasdb(message):
    return
    hamfurs = mongo_client.hamfurs.aliases
    hamfurs.drop()
    print("Dropped all records")


@bot.message_handler(commands=["freebeer", "beer"])
def beer(message):
    bot.send_message(chat_id=message.chat.id, text="\U0001f37a\U0001f37b\U0001f37a")


@bot.message_handler(
    commands=[
        "arrl",
    ]
)
def dead_horse(message):
    bot.send_document(message.chat.id, "BQADAQADUgADlek7ChDvVWLw6qmQAg")


@bot.message_handler(
    commands=[
        "aarp",
    ]
)
def old_yote(message):
    bot.send_sticker(message.chat.id, "CAADAQADWxoAAq8ZYgfnwh72WkV5nwI")


@bot.message_handler(
    commands=[
        "rsgb",
    ]
)
def silly_walk(message):
    bot.send_document(message.chat.id, "BQADAQADZQEAAptvSAb_CoDNeA8cTAI")


@bot.message_handler(
    commands=[
        "dmr",
    ]
)
def old_fox_yells_at_dmr(message):
    bot.send_sticker(message.chat.id, "CAADAQAD7wEAAllaGgIYbpRM1Bw8TwI")


@bot.message_handler(
    commands=[
        "awoo",
    ]
)
def awoo(message):
    bot.send_sticker(message.chat.id, "CAADAQADdAEAAptvSAZR8ElrZgRavQI")


@bot.message_handler(
    commands=[
        "fcc",
    ]
)
def fcc(message):
    stickers = [
        "PHOTO",
        "CAADAQADpAEAAptvSAbS5rEK5IeP8AI",
        "CAADAQADagEAAptvSAbfs0d4MEyGbgI",
        "CAADAQADaAEAAptvSAbPHkuRdk8jSAI",
        "CAADAQADdAEAAptvSAZR8ElrZgRavQI",
    ]
    choice = random.choice(stickers)
    if choice == "PHOTO":
        bot.send_photo(
            message.chat.id, "AgADAQAD6K8xG5tvSAYabOrZ1Tw3J9WF5y8ABEuc83jwVjWY1DwAAgI"
        )
    else:
        bot.send_sticker(message.chat.id, choice)


@bot.message_handler(commands=["races", "ares", "skywarn"])
def races(message):
    bot.send_photo(
        message.chat.id, "AgADAQADqacxG-f_kUQcHb3a_EhrTpyg5y8ABPaeF5Kdq-w1LaEAAgI"
    )


@bot.message_handler(
    commands=[
        "whacker",
    ]
)
def whacker(message):
    photos = [
        "AgADAQADqqcxG6wquEUjkFZxfNqArQyR3i8ABD2z_UHyaFH_2DAAAgI",
        "AgADAQADrKcxG6wquEUzmB_8llK9LmON3i8ABDtSuhIsNmYz5zAAAgI",
        "AgADAQADracxG6wquEV2BJayJ0TY9n-c3i8ABPr_E7Ng-UJ47DEAAgI",
        "AgADAQADrqcxG6wquEUnBkzKVE-SehXS5y8ABMxBKSFyc3WlR0MBAAEC",
        "AgADAQADvKcxG4MygUS6ETOqtvL3uHSD3i8ABNSR8ViJFCb5AUgAAgI",
        "AgADAQADr6cxG6wquEVYe0_gM2__hqeA3i8ABEWnbvkhEkqx03gAAgI",
        "AgADAQADr6cxG6wquEVYe0_gM2__hqeA3i8ABEWnbvkhEkqx03gAAgI",
        "AgADAQADr6cxG6wquEVYe0_gM2__hqeA3i8ABEWnbvkhEkqx03gAAgI",
        "AgADAQADr6cxG6wquEVYe0_gM2__hqeA3i8ABEWnbvkhEkqx03gAAgI",
    ]
    bot.send_photo(message.chat.id, random.choice(photos))


@bot.message_handler(
    commands=[
        "whackerkitty",
    ]
)
def tane(message):
    photos = [
        "AgADAQADvqcxGy3eoUSlnk70w6-Gy_mT3i8ABAI-_zIdKdPYOcMAAgI",
        "AgADAQADr6cxG6wquEVYe0_gM2__hqeA3i8ABEWnbvkhEkqx03gAAgI",
    ]
    bot.send_photo(message.chat.id, random.choice(photos))


# @bot.message_handler(commands=['whereistane', 'whereintheworldistane', 'whereintheworldiscarmensandiego', 'lokitty'])
def locate_tane(message):
    ssid = 7
    tokens = message.text.split()
    if len(tokens) > 1 and tokens[1].isdigit():
        ssid = tokens[1]

    try:
        r = requests.get(
            "https://api.aprs.fi/api/get?name=XXXXX-{1}&what=loc&apikey={0}&format=json".format(
                APRS_FI_KEY, ssid
            )
        )
        if "found" not in r.json() or r.json()["found"] == 0:
            bot.send_message(message.chat.id, "Error while fetching APRS location")
            return
        location = r.json()["entries"][0]
        bot.send_location(
            message.chat.id, float(location["lat"]), float(location["lng"])
        )
    except:
        bot.send_message(message.chat.id, "Error while processing APRS location")


@bot.message_handler(
    commands=[
        "standards",
    ]
)
def standards(message):
    chat_id = message.chat.id

    # if chat_id == -1001016478157:
    #    return tane(message)
    # if chat_id > 0:
    #    # Give them the original
    #    bot.send_photo(message.chat.id, "AgADAQADvacxG7Kc6USJW2G9OVs4dp6f3i8ABLPRlggDdF94vt8BAAEC")
    #    return
    hamfurs = mongo_client.hamfurs.chat
    settings = hamfurs.find_one({"chat_id": chat_id})
    if settings is None:
        settings = {"chat_id": chat_id, "standards": 2}
        hamfurs.insert_one(settings)

    # How many standards are there now?
    standards = int(settings["standards"])
    std_buffer = BytesIO()  # Output image buffer

    im = Image.open("res/standards.png")
    draw = ImageDraw.Draw(im)

    font = ImageFont.truetype("res/xkcd-script.ttf", 20)
    draw.text((15, 150), str(standards).rjust(2), font=font)
    draw.text((158, 45), str(standards).rjust(2), font=font)
    draw.text((375, 148), str(standards + 1).rjust(2), font=font)

    im.save(std_buffer, "PNG")
    std_buffer.seek(0)

    bot.send_photo(chat_id=chat_id, photo=("standards.png", std_buffer))

    # standards++
    if standards > 99:
        standards = 1
    standards += 1
    hamfurs.update_one({"chat_id": chat_id}, {"$set": {"standards": standards}})


@bot.message_handler(func=lambda m: True, content_types=["new_chat_member"])
def greet_user(message, new_chat_member=None):
    # if message.chat.id == HAMFURS Or message.chat.id > 0:
    if True:
        new_member = new_chat_member or message.new_chat_member
        chat_id = message.chat.id
        if chat_id > 0:
            chat_id = HAMFURS
        hamfurs = mongo_client.hamfurs.chat
        settings = hamfurs.find_one({"chat_id": chat_id})
        if settings is None:
            return
        if not settings["greeter_enabled"]:
            return
        greeter_text = settings["greeter_text"]
        pinned_message = get_message_url(get_pinned_message(chat_id))
        users_text = escape_markdown(format_user(new_member, True))
        greeter_text_formatted = greeter_text.format(
            user=users_text, pinned_message=pinned_message
        )
        bot.send_message(
            message.chat.id,
            text=greeter_text_formatted,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


@bot.message_handler(func=lambda m: True, content_types=["new_chat_members"])
def greet_users(message, new_chat_members=None):
    if message.chat.id == HAMFURS or message.chat.id > 0:
        new_members = new_chat_members or message.new_chat_members
        chat_id = message.chat.id
        if chat_id > 0:
            chat_id = HAMFURS
        hamfurs = mongo_client.hamfurs.chat
        settings = hamfurs.find_one({"chat_id": chat_id})
        if settings is None:
            return
        if not settings["greeter_enabled"]:
            return
        greeter_text = settings["greeter_text"]
        users_text = oxford_string(
            [escape_markdown(format_user(user, True)) for user in new_members]
        )
        pinned_message = get_message_url(get_pinned_message(chat_id))
        greeter_text_formatted = greeter_text.format(
            user=users_text, pinned_message=pinned_message
        )
        bot.send_message(
            message.chat.id, text=greeter_text_formatted, parse_mode="Markdown"
        )


@bot.message_handler(
    commands=[
        "pinned_message",
    ]
)
def return_pinned_message(message):
    pinned_message = get_pinned_message(message.chat.id)
    if pinned_message is not None:
        bot.send_message(
            message.chat.id,
            text="Click to see the pinned message",
            reply_to_message_id=pinned_message.message_id,
        )
    else:
        bot.send_message(message.chat.id, text="No pinned message has been set")


def unparse_markdown(message):
    """
    Checks if a message has formatting entities, and returns a markdown-
    formatted version of the message text.
    """
    markdown_types = ("bold", "italic", "code", "pre")
    if not hasattr("entities", message) or message.entities is None:
        return None
    parsed = ""
    string = message.text
    for entity in message.entities:
        if entity.type == "bold":
            pass


@bot.message_handler(commands=["set_join_message"])
def set_join_message(message):
    if is_administrator(message):
        chat_id = message.chat.id
        hamfurs = mongo_client.hamfurs.chat
        settings = hamfurs.find_one({"chat_id": chat_id})
        standards = 2
        if settings is not None:
            standards = settings["standards"]

        greeter_text = message.text[18:]
        if message.chat.id > 0:
            # From PM - default to hamfurs chat
            chat_id = HAMFURS
        document = {
            "chat_id": chat_id,
            "greeter_text": greeter_text,
            "greeter_enabled": True,
            "standards": standards,
        }

        hamfurs.replace_one({"chat_id": chat_id}, document, upsert=True)
        bot.send_message(message.chat.id, "OK")


@bot.message_handler(commands=["test_join_message"])
def test_join_message(message):
    greet_user(message, new_chat_member=message.from_user)


@bot.message_handler(commands=["enable_join_message"])
def enable_join_message(message):
    chat_id = message.chat.id
    if message.chat.id > 0:
        chat_id = HAMFURS
    if is_administrator(message):
        hamfurs = mongo_client.hamfurs.chat
        # FIXME
        # rv = hamfurs.update({ 'chat_id' : chat_id }, { 'greeter_enabled' : True })
        # if rv.modified_count:
        #    bot.send_message(message.chat.id, "OK")
        # else:
        #    bot.send_message(message.chat.id, "Use /set_join_message to enable greeter functionality")


@bot.message_handler(commands=["disable_join_message"])
def disable_join_message(message):
    chat_id = message.chat.id
    if message.chat.id > 0:
        chat_id = HAMFURS
    # FIXME
    # if is_administrator(message):
    #    hamfurs = mongo_client.hamfurs.chat
    #    hamfurs.update({ 'chat_id' : chat_id }, { 'greeter_enabled' : False })
    #    bot.send_message(message.chat.id, "OK")


@bot.message_handler(func=lambda m: True, content_types=["document"])
def debug_document(message):
    print("Got document file ID: {0}".format(message.document.file_id))


@bot.message_handler(func=lambda m: True, content_types=["video"])
def debug_video(message):
    print("Got video file ID: {0}".format(message.video.file_id))


@bot.message_handler(func=lambda m: True, content_types=["photo"])
def debug_photo(message):
    print("Got photo file ID: {0}".format(message.photo[0].file_id))


@bot.message_handler(func=lambda m: True, content_types=["audio"])
def debug_audio(message):
    print("Got audio file ID: {0}".format(message.audio.file_id))


@bot.message_handler(func=lambda m: True, content_types=["voice"])
def debug_voice(message):
    print("Got voice file ID: {0}".format(message.voice.file_id))


@bot.message_handler(func=lambda m: True, content_types=["sticker"])
def debug_sticker(message):
    print(
        "{1} Got sticker file ID: {0}".format(
            message.sticker.file_id, message.message_id
        )
    )


@bot.edited_message_handler(
    commands=[
        "define",
    ]
)
@bot.message_handler(
    commands=[
        "define",
    ]
)
def lookup_definition(message):
    chat_id = message.chat.id

    def lookup_definition_interactive(message):
        process_definition(message, message.text)

    if " " not in message.text:
        markup = types.ForceReply(selective=True)
        try:
            next_msg = bot.reply_to(
                message, text="Please enter a term to lookup", reply_markup=markup
            )
            bot.register_for_reply(next_msg, lookup_definition_interactive)
        except Exception as e:
            logger.error(e)
        return

    term = " ".join(message.text.split(" ")[1:])
    process_definition(message, term)


def process_definition(message, term):
    term_db = mongo_client.hamfurs.definitions
    term = term.lower()

    definition = term_db.find_one({"index": term})
    if definition is None:
        # Search by any keyword value
        definition = term_db.find_one({"keywords": term})

    # Search by metaphone
    if definition is None:
        definition = term_db.find_one({"metaphone": doublemetaphone(term)})

    if definition is None:
        send_editable_message(
            message,
            "No definition for the given term found.\n(use /add\_definition to contribute one)",
        )
        return

    txt = "*{term}*: {definition}\n(Contributed by {contributor} _{last_edit}_)".format(
        **definition
    )
    send_editable_message(
        message, txt, parse_mode="Markdown", disable_web_page_preview=True
    )
    return


@bot.message_handler(
    commands=[
        "add_definition",
    ]
)
def add_definition(message):
    chat_id = message.chat.id

    def define_term_interactive(message):
        process_add_definition(message)

    entry = " ".join(message.text.split(" ")[1:])
    match = definition_regex.match(entry)

    if match is None:
        bot.send_message(
            chat_id,
            "Definition format is as follows:\n`Term: Definition #optional #keywords #here`\nUse \\n for a literal newline in definition field.",
            parse_mode="Markdown",
        )
        return

    term = match.group(1).strip()
    definition = match.group(2).strip()
    try:
        tags = match.group(3).strip()
    except:
        tags = ""

    definition = definition.replace("\\#", "#")
    definition = definition.replace("\\n", "\n")

    if term == "" or definition == "":
        bot.send_message(
            chat_id,
            "Incorrect format. Definition format is as follows:\n`Term: Definition #optional #keywords #here`",
            parse_mode="Markdown",
        )
        return

    keywords = [tag.strip().lower() for tag in tags.split("#") if tag != ""]
    if len(keywords) == 0:
        keywords = term.lower().split()

    doc = {
        "term": term,
        "index": term.lower(),
        "keywords": keywords,
        "definition": definition,
        "metaphone": doublemetaphone(term),
        "contributor": escape_markdown(format_user(message.from_user)),
        "last_edit": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    txt = "*{term}*: {definition}\n(Contributed by {contributor} _{last_edit}_)".format(
        **doc
    )
    print(txt)
    try:
        msg = bot.send_message(
            chat_id, txt, parse_mode="Markdown", disable_web_page_preview=True
        )
    except Exception as e:
        print(e)
        bot.send_message(
            chat_id,
            "Error in definition format (check your Markdown! These literals must be escaped: ][*_`)",
        )
        return

    term_db = mongo_client.hamfurs.definitions
    rv = term_db.replace_one({"index": term.lower()}, doc, upsert=True)

    bot.send_message(chat_id, "Added definition successfully")


@bot.edited_message_handler(func=lambda m: hasattr(m, "reply_to_message"))
def callbook_lookup_edited_interactive(message):
    # Test if message is from our bot and has a corresponding reply message to edit:
    bot_messages = mongo_client.hamfurs.bot_messages
    old_message = bot_messages.find_one(
        {"chat_id": message.chat.id, "user_message_id": message.message_id}
    )
    if old_message is not None:
        try:
            process_lookup(message, message.text)
        except Exception as e:
            hamfurs_log.error("Error while making telegram request: {0}".format(e))


@bot.edited_message_handler(commands=["callsign", "lookup"])
@bot.message_handler(commands=["callsign", "lookup"])
def callbook_lookup(message):
    chat_id = message.chat.id

    def callbook_lookup_interactive(message):
        process_lookup(message, message.text)

    if " " not in message.text:
        markup = types.ForceReply(selective=True)
        try:
            next_msg = bot.reply_to(
                message, text="Please specify a valid callsign", reply_markup=markup
            )
            bot.register_for_reply(next_msg, callbook_lookup_interactive)
        except Exception as e:
            logger.error(e)
        return

    callsign = message.text.strip()
    callsign = callsign.split(" ")[-1]
    process_lookup(message, callsign)


def process_lookup(message, callsign):
    chat_id = message.chat.id
    print("Lookup: {0}".format(callsign))

    # import pdb; pdb.set_trace()

    if callsign.lower() == "ka6bim":
        return

    try:
        bot.send_chat_action(chat_id, "typing")
    except telebot.apihelper.ApiException as e:
        hamfurs_log.error("Error while making telegram API request: {0}".format(e))
        hamfurs_log.error("Stopping lookup")
        return

    hamfurs = mongo_client.hamfurs.aliases

    alias = None
    if callsign[0] == "@":
        # lookup by telegram handle
        alias = hamfurs.find_one({"user_name_lower": callsign[1:].lower()})
        if alias is None:
            send_editable_message(
                message, text="No associated callsign found for given telegram handle"
            )
            return
        callsign = alias[
            "callsign"
        ]  # Follow down the rest of the code with this callsign
    else:
        # see if callsign has an assigned alias
        alias = hamfurs.find_one({"callsign": callsign.upper()})

    if alias is None:
        alias_text = None
    else:
        if alias["user_name"] is None:
            alias_text = escape_markdown(
                "{0} {1}".format(alias["user_first"], alias["user_last"])
            )
        else:
            alias_text = escape_markdown(
                "@{0} ({1} {2})".format(
                    alias["user_name"], alias["user_first"], alias["user_last"]
                )
            )

    dmr_id = get_dmr_id(callsign)

    if is_canadian(callsign):
        icdb = mongo_client.ic
        collection = icdb.callbook
        result = collection.find_one({"callsign": callsign.upper()})
        if result is None:
            send_editable_message(message, text="Callsign not found in IC database")
            return
        else:
            result["alias"] = alias_text
            if result["club"] is None:
                qualifications = []
                if result["qualifications"]["basic"]:
                    qualifications.append("Basic")
                if result["qualifications"]["5wpm"]:
                    qualifications.append("5WPM")
                if result["qualifications"]["12wpm"]:
                    qualifications.append("12WPM")
                if result["qualifications"]["advanced"]:
                    qualifications.append("Advanced")
                if result["qualifications"]["basic_honours"]:
                    qualifications.append("Basic Honours")
                result["class"] = ", ".join(qualifications)

                txt = u"""\U0001f1e8\U0001f1e6 *{callsign}* - (Person) {class}
*Name:* {name} {surname}
*Alias:* {alias}
*Location:* {city}, {province} {postcode}""".format(
                    **result
                )
            else:
                txt = u"""\U0001f1e8\U0001f1e6 *{callsign}* - (Club)
*Name*: {club[name]} {club[name2]}
*Trustee*: {name} {surname}
*Club location*: {club[city]}, {club[province]} {club[postcode]}""".format(
                    **result
                )

            if dmr_id is not None:
                txt += "\n*DMR ID*: {0}".format(dmr_id)
            send_editable_message(message, text=txt, parse_mode="Markdown")
            return

    if is_norwegian(callsign):
        nkomdb = mongo_client.nkom
        collection = nkomdb.callbook
        result = collection.find_one({"callsign": callsign.upper()})
        if result is None:
            send_editable_message(message, text="Callsign not found in Nkom database")
            return
        else:
            result["alias"] = alias_text
            if alias is None:
                txt = u"""\U0001f1f3\U0001f1f4 *{callsign}* - ({type})
*Name:* {name} {surname}{club}
*Updated:* {updated}
*Location:* {city}, {country} {postcode}""".format(
                    **result
                )
            else:
                txt = u"""\U0001f1f3\U0001f1f4 *{callsign}* - ({type})
*Name:* {name} {surname}{club}
*Alias:* {alias}
*Updated:* {updated}
*Location:* {city}, {country} {postcode}""".format(
                    **result
                )

            if dmr_id is not None:
                txt += "\n*DMR ID*: {0}".format(dmr_id)
            send_editable_message(message, text=txt, parse_mode="Markdown")
            return

    if is_australian(callsign):
        req = requests.get(
            "https://l1gfir5yi7.execute-api.us-east-1.amazonaws.com/prod/{0}".format(
                callsign
            )
        )
        if not req.ok:
            send_editable_message(message, text="Callsign not found in ACMA database")
            return
        else:
            result = req.json()
            result["alias"] = alias_text
            result["flag"] = FLAG_EMOJI["Australia"]
            result["callsign"] = callsign.upper()
            if alias is not None:
                txt = u"""{flag} *{callsign}* - ({type} - {status})
*Name:* {name}
*Alias:* {alias}
*Effective:* {date_of_effect}
*Expiry:* {date_of_expiry}
*Location:* {suburb}, {state} {postcode}
""".format(
                    **result
                )
            else:
                txt = u"""{flag} *{callsign}* - ({type} - {status})
*Name:* {name}
*Effective:* {date_of_effect}
*Expiry:* {date_of_expiry}
*Location:* {suburb}, {state} {postcode}
""".format(
                    **result
                )
            if dmr_id is not None:
                txt += "*DMR ID*: {0}\n".format(dmr_id)
            txt += "[ACMA License Page]({link})".format(**result)
            send_editable_message(
                message, text=txt, parse_mode="Markdown", disable_web_page_preview=True
            )
            return

    # TODO: error handling
    req = requests.get("https://callook.info/{0}/json".format(callsign))
    if req.status_code != requests.codes.ok:
        send_editable_message(message, text="Please specify a valid callsign")
        return
    result = req.json()

    collection = mongo_db.ve_session_counts
    ve_info = collection.find_one({"callsign": callsign.upper()})

    # check status key
    if result["status"] != "VALID":
        # Try Ham-QTH:
        data = None
        try:
            data = hamqth_client.callbook(callsign)
            if data is None:
                text = "Error in HamQTH lookup ({0})\n".format(result["status"])
                text += "(We looked everywhere, but that callsign probably isn't in any database we know about)\n"
                text += "[Submit Profile](https://hamqth.com/{0})".format(callsign)
            else:
                data["callsign"] = data["callsign"].upper()
                data["alias"] = alias_text
                data["grid"] = data.get("grid", "?")
                hamfurs_log.debug(data)
                try:
                    data["flag"] = FLAG_EMOJI[data["country"]]
                except KeyError:
                    data["flag"] = ""
                if "adr_name" not in data:
                    data["adr_name"] = "[None]"
                txt = u"""{flag} *{callsign}* (UTC{utc_offset})
*Name:* {adr_name} ({nick})
*Alias:* {alias}
*Location:* {adr_city}, {adr_country} {adr_zip} ({grid})
[HamQTH Profile](https://www.hamqth.com/{callsign})
""".format(
                    **data
                )
                if dmr_id is not None:
                    txt += "\n*DMR ID*: {0}".format(dmr_id)
                send_editable_message(
                    message,
                    text=txt,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                return
        except hamqth.Error as e:
            text = "Error in HamQTH request: {0}\n".format(e)
            text += "(Callsign probably isn't in any database we know about)\n"
            text += "[Submit Profile](https://hamqth.com/{0})".format(callsign)
        except Exception as e:
            text = "Error in HamQTH lookup."
        if alias is None and data is None:
            country = callsigns.get_country(callsign)
            try:
                flag = FLAG_EMOJI[callsigns.COUNTRY_NAMES[country]]
            except:
                flag = ""
            text = "{2} *{1}*\n*Alias:* {0}\n(That's all we know - [Update Profile](https://hamqth.com/{1}))".format(
                alias_text, callsign, flag
            )
        send_editable_message(
            message, text=text, parse_mode="Markdown", disable_web_page_preview=True
        )
        return

    result["type"] = result["type"].title()

    if ve_info is not None:
        result["ve"] = "VE (Session count: {count})".format(**ve_info)
    else:
        result["ve"] = ""

    result["alias"] = alias_text

    result["dmr_txt"] = ""
    if dmr_id is not None:
        result["dmr_txt"] = "\n*DMR ID*: {0}".format(dmr_id)

    txt = u"""\U0001f1fa\U0001f1f8 *{current[callsign]}* - ({type}) {current[operClass]} {ve}
*Name:* {name}
*Alias:* {alias}{dmr_txt}
*Location:* {address[line2]} ({location[gridsquare]})
*Granted:* {otherInfo[grantDate]}
*Expiry:* {otherInfo[expiryDate]}
[ULS license page]({otherInfo[ulsUrl]})
""".format(
        **result
    )

    if result["type"] == "Club":
        txt += u"*Trustee:* {trustee[callsign]}, {trustee[name]}".format(**result)

    send_editable_message(message, text=txt, parse_mode="Markdown")


def get_dmr_id(callsign):
    callsign = callsign.upper()
    db = mongo_client.dmr_marc.users
    r = db.find_one({"callsign": callsign})
    if r is None:
        return None
    return r["radio_id"]


def send_editable_message(
    message, text, parse_mode=None, reply_markup=None, disable_web_page_preview=None
):
    if message is None:
        hamfurs_log("send_editable_message : `message` parameter cannot be None")
        return
    chat_id = message.chat.id
    bot_messages = mongo_client.hamfurs.bot_messages
    old_message = bot_messages.find_one(
        {"chat_id": chat_id, "user_message_id": message.message_id}
    )
    new_message = None
    if old_message is not None:
        # Edit the old corresponding message
        try:
            new_message = bot.edit_message_text(
                text,
                parse_mode="Markdown",
                chat_id=chat_id,
                message_id=old_message["bot_message_id"],
                disable_web_page_preview=disable_web_page_preview,
            )
        except telebot.apihelper.ApiException as e:
            hamfurs_log.error(e)
            return
    else:
        # Send a new message and store away the ID to edit later if needed
        try:
            new_message = bot.send_message(
                chat_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=disable_web_page_preview,
            )
        except telebot.apihelper.ApiException as e:
            hamfurs_log.error(e)
            return
    document = {
        "chat_id": chat_id,
        "user_message_id": message.message_id,
        "bot_message_id": new_message.message_id,
    }
    bot_messages.replace_one(
        {"chat_id": chat_id, "user_message_id": message.message_id},
        document,
        upsert=True,
    )


def ve_lookup(callsign):
    collection = mongo_db.ve_session_counts
    result = collection.find_one({"callsign": callsign.upper()})


@bot.edited_message_handler(commands=['conditions', 'band_conditions'])
@bot.message_handler(commands=['conditions', 'band_conditions'])
def band_conditions(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, "upload_photo")

    req = requests.get("http://www.hamqsl.com/solar101vhf.php")
    if req.status_code == requests.codes.ok:
        photo = BytesIO(req.content)
        try:
            bot.send_photo(chat_id=chat_id, photo=("conditions.gif", photo))
        except error as e:
            logging.error(e)
    else:
        bot.send_message(chat_id=chat_id, text="Error while fetching band conditions")


@bot.message_handler(
    commands=[
        "mute",
    ]
)
def mute_spots(message):
    chat_id = message.chat.id
    bot.mute_spots()
    bot.send_message(chat_id, "Spotter notifications muted for the next hour.")


@bot.message_handler(
    commands=[
        "unmute",
    ]
)
def unmute_spots(message):
    chat_id = message.chat.id
    bot.unmute_spots()
    bot.send_message(chat_id, "Spotter notifications resumed.")


@bot.message_handler(
    commands=[
        "qsv",
    ]
)
def send_qsv(message):
    tokens = message.text.split(" ")
    if len(tokens) == 1:
        choice = random.choice(("MORSE", "CW", "TEXT", "RTTY", "HELL"))
    else:
        choice = tokens[1].upper()
    if choice == "TEXT":
        bot.reply_to(message, "…VVVVVVVV…")
    elif choice == "MORSE":
        bot.reply_to(message, "···— ···— ···— ···—")
    elif choice == "CW":
        message = bot.send_voice(
            message.chat.id,
            "AwADAQADAgADuQq3EXz85vkZKnreAg",
            reply_to_message_id=message.message_id,
        )
    elif choice == "RTTY":
        message = bot.send_voice(
            message.chat.id,
            "AwADAQADAQADuQq3EfwWa3yAVhOTAg",
            reply_to_message_id=message.message_id,
        )
    elif choice == "HELL":
        message = bot.send_voice(
            message.chat.id,
            "AwADAQADAwADuQq3EafVsjXqN3z5Ag",
            reply_to_message_id=message.message_id,
        )


@bot.message_handler(commands=["mpe", "power_density"])
def power_density(message):
    tokens = message.text.split()
    if len(tokens) != 5:
        bot.send_message(
            message.chat.id,
            "Usage: /power_density [PEP Watts] [Antenna Gain] [Distance in m] [Frequency in MHz]",
        )
        return

    try:
        data = calculate_power_density(
            float(tokens[1]), float(tokens[2]), float(tokens[3]), float(tokens[4])
        )
    except (ValueError, TypeError) as e:
        bot.send_message(message.chat.id, "Error: {0}".format(e))
        return

    data["controlled_compliant"] = "Uncompliant"
    data["uncontrolled_compliant"] = "Uncompliant"
    if data["power_density"] < data["mpe_controlled"]:
        data["controlled_compliant"] = "Compliant"
    if data["power_density"] < data["mpe_uncontrolled"]:
        data["uncontrolled_compliant"] = "Compliant"

    data["power"] = tokens[1]
    data["gain"] = tokens[2]
    data["distance"] = tokens[3]
    data["frequency"] = tokens[4]

    text = """{power} Watts into an antenna with gain {gain} dBi at distance {distance} m @ {frequency} MHz:

*Estimated RF Power Density:* {power_density} mW/cm²
*Field strength:* {field_strength} V/m

Maximum Permissible Exposure
    *Controlled:* {mpe_controlled} (mW/cm²) _({controlled_compliant})_
    *Uncontrolled*: {mpe_uncontrolled} (mW/cm²) _({uncontrolled_compliant})_

Minimum distance to compliance from antenna
    *Controlled:* {dx_controlled} m
    *Uncontrolled:* {dx_uncontrolled} m""".format(
        **data
    )

    bot.send_message(message.chat.id, text=text, parse_mode="Markdown")


def calculate_power_density(watts, gain, distance, frequency, ground=True):
    """
    distance in m, frequency in MHz
    """

    power = 1000.0 * watts
    eirp = power * pow(10, (gain / 10.0))
    distance *= 100

    if frequency < 1.34:
        std1 = 100.0
        std2 = 100.0
    elif frequency < 3.0:
        std1 = 100.0
        std2 = 180.0 / pow(frequency, 2)
    elif frequency < 30.0:
        std1 = 900.0 / pow(frequency, 2)
        std2 = 180.0 / pow(frequency, 2)
    elif frequency < 300.0:
        std1 = 1.0
        std2 = 0.2
    elif frequency < 1500.0:
        std1 = frequency / 300.0
        std2 = frequency / 1500.0
    elif frequency < 100000.0:
        std1 = 5.0
        std2 = 1.0
    else:
        raise ValueError("Frequency too high")

    if ground:
        ground_factor = 0.64
    else:
        ground_factor = 0.25

    power_density = (ground_factor * eirp) / (math.pi * pow(distance, 2))
    power_density = ((power_density * 10000) + 0.5) / 10000
    dx1 = math.sqrt((ground_factor * eirp) / (std1 * math.pi))
    dx1 = ((dx1 * 10) + 0.5) / 10
    dx2 = math.sqrt((ground_factor * eirp) / (std2 * math.pi))
    dx2 = ((dx2 * 10) + 0.5) / 10
    std1 = ((std1 * 100) + 0.5) / 100
    std2 = ((std2 * 100) + 0.5) / 100
    field_strength = pow(power_density * 3770, 0.5)

    return {
        "power_density": round(power_density, 5),
        "field_strength": round(field_strength, 5),
        "mpe_controlled": round(std1, 4),
        "mpe_uncontrolled": round(std2, 4),
        "dx_controlled": round((dx1 / 100), 4),
        "dx_uncontrolled": round((dx2 / 100), 4),
    }


if __name__ == "__main__":
    bot.polling()
