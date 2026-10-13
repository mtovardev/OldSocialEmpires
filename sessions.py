import json
import os
import copy
import uuid
import random
import hashlib
from flask import session

from version import version_code
from engine import timestamp_now
from version import migrate_loaded_save
from constants import Constant

from bundle import VILLAGES_DIR
from database import db, Village

__villages = {}  
__saves = {} 

__initial_village = json.load(open(os.path.join(VILLAGES_DIR, "initial.json")))

def calcular_hash(data: dict) -> str:
    """Calcula un hash SHA-256 del JSON de la aldea (sin el campo _hash)."""
    data_copy = {k: v for k, v in data.items() if k != "_hash"}
    json_str = json.dumps(data_copy, sort_keys=True)
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

def load_saved_villages():
    global __villages
    global __saves
    # Empty in memory
    __villages = {}
    __saves = {}

    # Static neighbors in /villages
    for file in os.listdir(VILLAGES_DIR):
        if file == "initial.json" or not file.endswith(".json"):
            continue
        print(f" * Loading static neighbour {file}... ", end='')
        village = json.load(open(os.path.join(VILLAGES_DIR, file)))
        if not is_valid_village(village):
            print("Invalid neighbour")
            continue
        USERID = village["playerInfo"]["pid"]
        if str(USERID) in __villages:
            print(f"Ignored: duplicated PID '{USERID}'.")
        else:
            __villages[str(USERID)] = village
            print("Ok.")

    all_villages = Village.query.all()
    for village_record in all_villages:
        try:
            save = json.loads(village_record.data)
        except json.decoder.JSONDecodeError:
            print(f" * Corrupted JSON for {village_record.userid}")
            continue
        if not is_valid_village(save):
            print(f" * Invalid Save for {village_record.userid}")
            continue
        
        # Verificar hash (anti-cheat)
        hash_guardado = village_record.data_hash
        hash_calculado = calcular_hash(save)
        if hash_guardado != hash_calculado:
            print(f" [!] ANTI-CHEAT: La aldea {village_record.userid} ha sido modificada. Se ignorará.")
            continue
        
        USERID = save["playerInfo"]["pid"]
        try:
            map_name = save["playerInfo"]["map_names"][save["playerInfo"]["default_map"]]
        except:
            map_name = '?'
        print(f" * Loading save {USERID} ({map_name})... Ok.")
        __saves[str(USERID)] = save
        modified = migrate_loaded_save(save)
        if modified:
            save_session(USERID)

def new_village(empire_name: str = None, player_name: str = None) -> str:
    USERID: str = str(uuid.uuid4())
    assert USERID not in all_userid()
    village = copy.deepcopy(__initial_village)
    village["version"] = version_code
    village["playerInfo"]["pid"] = USERID
    village["maps"][0]["timestamp"] = timestamp_now()
    village["privateState"]["dartsRandomSeed"] = abs(int((2**16 - 1) * random.random()))

    if empire_name:
        village["playerInfo"]["map_names"] = [empire_name]
    if player_name:
        village["playerInfo"]["name"] = player_name

    __saves[USERID] = village
    save_session(USERID)
    print("Done.")
    return USERID

def all_saves_userid() -> list:
    return list(__saves.keys())

def all_userid() -> list:
    return list(__villages.keys()) + list(__saves.keys())

def save_info(USERID: str) -> dict:
    if USERID not in __saves:
        return None

    save = __saves[USERID]
    player_name = save["playerInfo"]["name"]
    default_map = save["playerInfo"]["default_map"]
    map_data = save["maps"][default_map]
    empire_name = str(save["playerInfo"]["map_names"][default_map])
    xp = save["maps"][default_map]["xp"]
    level = save["maps"][default_map]["level"]
    pic = save["playerInfo"].get("pic", "")
    return {
        "userid": USERID,
        "name": empire_name,
        "player_name": player_name,
        "pic": pic,
        "level": map_data["level"],
        "xp": map_data["xp"],
        "coins": map_data["coins"],
        "stone": map_data["stone"],
        "wood": map_data["wood"],
        "food": map_data["food"],
    }

def all_saves_info() -> list:
    return [save_info(uid) for uid in __saves]

def session(USERID: str) -> dict:
    assert(isinstance(USERID, str))
    return __saves[USERID] if USERID in __saves else None

def neighbor_session(USERID: str) -> dict:
    assert(isinstance(USERID, str))
    if USERID in __saves:
        return __saves[USERID]
    if USERID in __villages:
        return __villages[USERID]

def fb_friends_str(USERID: str) -> list:
    friends = []
    for key in __villages:
        vill = __villages[key]
        if vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
            continue
        frie = {"uid": vill["playerInfo"]["pid"], "pic_square": vill["playerInfo"]["pic"]}
        if not frie["pic_square"]: frie["pic_square"] = "/img/profile/1025.png"
        friends += [frie]
    for key in __saves:
        vill = __saves[key]
        if vill["playerInfo"]["pid"] == USERID:
            continue
        frie = {"uid": vill["playerInfo"]["pid"], "pic_square": vill["playerInfo"]["pic"]}
        if not frie["pic_square"]: frie["pic_square"] = "/img/profile/1025.png"
        friends += [frie]
    return friends

def neighbors(USERID: str) -> list:
    neighbors = []
    for key in __villages:
        vill = __villages[key]
        if vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
            continue
        neigh = vill["playerInfo"]
        for res in ["coins", "xp", "level", "stone", "wood", "food"]:
            neigh[res] = vill["maps"][0][res]
        neighbors += [neigh]
    for key in __saves:
        vill = __saves[key]
        if vill["playerInfo"]["pid"] == USERID:
            continue
        neigh = vill["playerInfo"]
        for res in ["coins", "xp", "level", "stone", "wood", "food"]:
            neigh[res] = vill["maps"][0][res]
        neighbors += [neigh]
    return neighbors

def is_valid_village(save: dict):
    if "playerInfo" not in save or "maps" not in save or "privateState" not in save:
        return False
    for map in save["maps"]:
        if "oil" in map or "steel" in map:
            return False
        if "stone" not in map or "food" not in map:
            return False
        if "items" not in map:
            return False
        if type(map["items"]) != list:
            return False
    return True

def save_session(USERID: str):
    village = session(USERID)
    if not village:
        print(f" [!] No se encontró la aldea {USERID}")
        return

    data_hash = calcular_hash(village)
    village_json = json.dumps(village, indent=4)

    # Buscar si ya existe en la base de datos
    record = Village.query.filter_by(userid=USERID).first()
    if record:
        record.data = village_json
        record.data_hash = data_hash
    else:
        record = Village(userid=USERID, data=village_json, data_hash=data_hash)
        db.session.add(record)

    db.session.commit()
    print(f" * Saved village {USERID} to database.")

def load_village_from_db(USERID: str):
    record = Village.query.filter_by(userid=USERID).first()
    if record:
        try:
            save = json.loads(record.data)
            __saves[USERID] = save
            return True
        except json.decoder.JSONDecodeError:
            return False
    return False