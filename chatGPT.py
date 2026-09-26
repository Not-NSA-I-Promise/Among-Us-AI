import requests
from utility import getGameData, in_meeting, get_chat_messages, clear_chat, translatePlayerColorID, allTasksDone, get_nearby_players, load_G, get_kill_list, get_num_alive_players
import botlink
import time
import pyautogui
import networkx as nx
import re
import sys, os
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/task-solvers")
from task_utility import get_dimensions, get_screen_coords, wake, get_screen_ratio

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "80"))
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.8"))
OLLAMA_THINK = os.environ.get("OLLAMA_THINK", "false").lower() in ("1", "true", "yes")
try:
    with open("OllamaConfig.txt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().upper()
            value = value.strip()
            if key == "HOST":
                OLLAMA_HOST = value
            elif key == "MODEL":
                OLLAMA_MODEL = value
            elif key == "NUM_PREDICT":
                OLLAMA_NUM_PREDICT = int(value)
            elif key == "TEMPERATURE":
                OLLAMA_TEMPERATURE = float(value)
            elif key == "THINK":
                OLLAMA_THINK = value.lower() in ("1", "true", "yes")
except FileNotFoundError:
    pass

def check_ollama() -> bool:
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return True
    except requests.RequestException:
        return False

# This used to raise SystemExit(0) here, at import time, when Ollama was
# unreachable. That silently killed the whole bot: the model being down is a
# degraded mode, not a reason to exit. Reachability is now checked lazily by
# ask(), so the rest of the game keeps working without the model.
OLLAMA_REACHABLE = None

with open("sendDataDir.txt") as f:
    line = f.readline().rstrip()
    MEETING_PATH = line + "\\meetingData.txt"
    VOTE_TIME_PATH = line + "\\timerData.txt"
f.close()

def get_caller_color():
    with open(MEETING_PATH) as f:
        line = f.readline().rstrip()
        return translatePlayerColorID(int(line))
    
def get_dead_players():
    with open(MEETING_PATH) as f:
        f.readline().rstrip()
        line = f.readline().rstrip()
        return [translatePlayerColorID(int(x)) for x in line.strip('][').split(", ")[:-1]]
    
names_dict = {}
def get_names_dict():
    with open(MEETING_PATH) as f:
        f.readline().rstrip()
        f.readline().rstrip()
        big_long_input = f.readline().rstrip().strip('][').split(", ")
        for item in big_long_input:
            item = item.split("/")
            names_dict[item[0]] = int(item[1])
        return names_dict
    
def get_last_task():
    with open("last_task.txt") as f:
        line = f.readline().rstrip()
        return line
    
def get_last_room():
    with open("last_area.txt") as f:
        line = f.readline().rstrip()
        return line
    
def get_meeting_time():
    with open(VOTE_TIME_PATH) as f:
        time = int(f.readline())
    return time

def ask_gpt(prompts : list) -> str:
    print("sent prompt")
    payload = {
        "model": OLLAMA_MODEL,
        "messages": prompts,
        "stream": False,
        "think": OLLAMA_THINK,
        "options": {
            "num_predict": OLLAMA_NUM_PREDICT,
            "temperature": OLLAMA_TEMPERATURE,
        },
    }
    message = ""
    for attempt in range(2):
        response = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        message = (data.get("message", {}) or {}).get("content", "") or ""
        if message.strip():
            break
        # Thinking models can burn the whole num_predict budget on reasoning and
        # return empty content - retry once with thinking explicitly disabled.
        if OLLAMA_THINK:
            break
        print("empty response, retrying with think=false")
        payload["think"] = False
    print("returned message")
    return message.rstrip()

# min difference is 46
cols_dict = {"RED" : (208, 68, 74), "BLUE" : (62, 91, 234), "GREEN" : (55, 156, 95), "PINK" : (241, 123, 217), 
             "ORANGE" : (241, 156, 70), "YELLOW" : (241, 246, 130), "BLACK" : (97, 111, 122), "WHITE" : (223, 240, 251),
             "PURPLE" : (134, 91, 214), "BROWN" : (138, 110, 83), "CYAN" : (95, 245, 245), "LIME" : (108, 244, 107),
             "MAROON" : (121, 75, 95), "ROSE" : (241, 213, 236), "BANANA" : (239, 244, 199), "GRAY" : (142, 162, 181),
             "TAN" : (162, 163, 156), "CORAL" : (226, 136, 144), "GREY" : (142, 162, 181), "SKIP" : ()}

def col_diff(col1 : tuple, col2 : tuple) -> int:
    return abs(col1[0] - col2[0]) + abs(col1[1] - col2[1]) + abs(col1[2] - col2[2])

def find_col_pos(dimensions, col : str):
    x = dimensions[0] + round(dimensions[2] / 7.38)
    y = dimensions[1] + round(dimensions[3] / 4.30)

    x_offset = round(dimensions[2] / 3.68)
    y_offset = round(dimensions[3] / 7.88)

    for i in range(3):
        for j in range(5):
            pixel = pyautogui.pixel(x + x_offset * i, y + y_offset * j)
            if col != "SKIP" and col_diff(cols_dict[col], pixel) < 30:
                return (x + x_offset * i, y + y_offset * j)
    return None

def skip(dimensions):
    wake()

    # skip
    time.sleep(0.3)
    pyautogui.click(dimensions[0] + round(dimensions[2] / 6.74), dimensions[1] + round(dimensions[3] / 1.15), duration=0.2)
    time.sleep(0.3)
    pyautogui.click(dimensions[0] + round(dimensions[2] / 3.87), dimensions[1] + round(dimensions[3] / 1.17), duration=0.2)

def vote(color : str = "SKIP"):
    dimensions = get_dimensions()

    # close chat through the game API, same reason as opening it
    if not botlink.close_chat():
        coords = botlink.read_ui_coords().get("chat")
        if coords:
            wake()
            pyautogui.click(dimensions[0] + coords[0], dimensions[1] + coords[1], duration=0.3)
    time.sleep(0.5)

    color = color.upper()
    if color == "SKIP":
        index = -1
    else:
        index = botlink.COLOR_NAMES.index(color) if color in botlink.COLOR_NAMES else -1

    # Drive MeetingHud.Select/Confirm via the plugin. Falls back to the old
    # pixel voting path if the command channel is not answering.
    if botlink.cast_vote(index):
        time.sleep(0.5)
        return
    wake()
    pos = find_col_pos(dimensions, color)
    if pos is None:
        skip(dimensions)
    else:
        pyautogui.click(pos, duration=0.2)
        pyautogui.click(pos[0] + round(dimensions[2] / 8.07), pos[1], duration=0.2)

# Everything below used to sit at module level, which meant import chatGPT",

# vote area and voted. Importing a module must never do that. It is now the
# explicit meeting_flow(), called by main.py, and the per-turn voting it did
# is a decision the model makes through agent.py rather than a hardcoded loop.

def meeting_flow():
    """Run one meeting: gather context, ask the model, act on its answer.

    This is the only place in the codebase allowed to drive a meeting, and even
    here the model chooses the vote - the code only executes what it says.
    """
    data = getGameData()

    color : str = data['color']
    role : str = data['status']
    tasks : str = ' '.join(data['tasks'])
    task_locations : str = ' '.join(data['task_locations'])
    G = load_G("SHIP")
    nearby_players = get_nearby_players(G)

    tasks_prompt : str = "You finished all your tasks" if allTasksDone() else f"Your last completed task was {get_last_task()}"
    dead_str : str = str(get_dead_players()).strip("][").replace("'", '')
    kill_prompt : str = ""
    kill_data = get_kill_list()
    for kill in kill_data:
        if kill[0] == color:
            kill_prompt += kill[1] + ", "
    if len(kill_prompt) > 0:
        kill_prompt = kill_prompt[:-2]
        kill_prompt = "You killed " + kill_prompt + " last round."

    found_prompt = f'You found the body in {get_last_room()}.' if get_caller_color() == color and len(dead_str) != 0 else ''

    # Specific role (Engineer/Scientist/Tracker/...) from the plugin, plus whoever was
    # standing near the victim when they died.
    role_name = botlink.get_role()
    role_prompt = f'Your specific role is {role_name} ({botlink.get_role_ability(role_name)}).' if role_name != "Unknown" else ''

    presence = botlink.read_kill_presence()
    if presence:
        witnesses = ", ".join(f"{c} was {d} tiles away" for c, d in presence.items())
        presence_prompt = f'When the body was found, {witnesses}.'
    else:
        presence_prompt = ''

    meeting_start_time = time.time()
    time.sleep(4.5)

    try:
        location_prompt = f"Your tasks are in {task_locations}" if None not in task_locations else ""
    except TypeError:
        location_prompt = ""

    # Before the meeting, you were {"not near anyone" if len(nearby_players) == 0 else "near " + nearby_players}
    prompts =   [
                    {"role": "system", "content": 
                     re.sub(' +', ' ', f'''You are playing the game Among Us in a meeting with your crewmates. Your color is {color}.
                     {get_caller_color()} called the meeting. {"Nobody is" if len(dead_str) == 0 else dead_str + " are"} dead. {tasks_prompt}. The last room you were in was {get_last_room()}.
                     Before the meeting, you were {"not near anyone" if len(nearby_players) == 0 else "near " + str(nearby_players).strip("][")}. {kill_prompt} {found_prompt} {presence_prompt}
                     The prompts you see that are not from you, {color}, are messages from your crewmates. Your role is {role}. {role_prompt} Your tasks are {tasks}. 
                     There are {get_num_alive_players()} players left alive.
                     {location_prompt}. Your crewmates' and your messages are identified by their color in the prompt. 
                     Reply to prompts with very few words and don't be formal. Try to only use 1 sentence, preferably an improper one. Never return more than 80 alphanumeric characters at a time.
                     Try to win by voting the impostor out. If your crewmates are agreeing on someone, go along with it unless you are sus of someone else. 
                     If your role is impostor, try to get other people voted off by calling them sus and suggesting the group vote them off.
                     If you are imposter, do not vote out your fellow imposters'''.replace('\n', ' '))
                    },

                     {"role": "system", "content": "If someone says 'where' without much context, they are asking where the body was found"},
                     {"role": "system", "content": f"If someone says 'what' or '?' without much context, they are asking {get_caller_color()} why the meeting was called"},
                     #{"role": "system", "content": "If you decide to vote, respond by saying 'VOTE: {COLOR to vote}' or 'VOTE: skip' to skip"},
                     {"role": "system", "content": f"If people say {color} is sus or should be voted off, you need to defend youself."},
                     {"role": "system", "content": f"If you are the imposter, try gaslighting people"}, 
                     {"role": "system", "content": "Your responses MUST be of the form {YOUR COLOR}: {your message}. Do not respond in the form {OTHER PLAYER'S COLOR}: { message }."}
                ]

    clear_chat()
    seen_chats = []

    dimensions = get_dimensions()

    # Open the chat through the game's own API (InGamePlayerList.SetActive) rather
    # than clicking a fixed pixel ratio, which was landing on the Settings button.
    # Falls back to a template-free coordinate from uiCoords.txt if the command
    # channel is unavailable.
    if not botlink.open_chat():
        coords = botlink.read_ui_coords().get("chat")
        if coords:
            wake()
            pyautogui.click(dimensions[0] + coords[0], dimensions[1] + coords[1], duration=0.3)
    time.sleep(0.5)

    x = dimensions[0] + round(dimensions[2] / 3)
    y = dimensions[1] + round(dimensions[3] / 1.28)

    pyautogui.click(x,y, duration=0.3)
    time.sleep(0.1)

    decided_to_vote : bool = False

    while in_meeting() and not decided_to_vote:
        if time.time() - meeting_start_time > get_meeting_time() - 8:
            break
        is_new_chats = False
        chat_history = get_chat_messages()

        for chat in chat_history:
            if chat not in seen_chats:
                if f"{color}: " in chat:
                    prompts.append({"role": "assistant", "content": chat})
                else:
                    prompts.append({"role": "user", "content": chat})
                    is_new_chats = True
                seen_chats.append(chat)

        try:
            if is_new_chats:
                pyautogui.click(x,y)
                time.sleep(0.1)
                response = ask_gpt(prompts)
                new_response = " "
                for line in response.splitlines():
                    if "VOTE: " in line:
                        print("Decided to vote")
                        if "skip" in line.lower():
                            decided_to_vote = True
                            break
                        decided_to_vote = True
                        break
                    if f"{color}: " not in line:
                        print(f"skipped: {line}")
                        continue
                    new_response += line

                response = new_response.replace(f'{color}: ', '')
                print("res: " + response)
                if len(response) <= 100:
                    pyautogui.typewrite(f"{response.lower()}\n", interval=0.025)
                is_new_chats = False
                time.sleep(4)
        except requests.RequestException as e:
            print(f"Ollama request failed: {e}")
            break

    get_names_dict()

    while time.time() - meeting_start_time < get_meeting_time() - 12:
        time.sleep(1/15)

    prompts.append({"role": "user", "content": "You have 10 seconds left to vote. How do you vote? Your response should be formatted as 'VOTE: {COLOR to vote}' or 'VOTE: skip' to skip"})
    res = ask_gpt(prompts)
    col_array = ["RED", "BLUE", "GREEN", "PINK",
                    "ORANGE", "YELLOW", "BLACK", "WHITE",
                    "PURPLE", "BROWN", "CYAN", "LIME",
                    "MAROON", "ROSE", "BANANA", "GRAY",
                    "TAN", "CORAL", "GREY"]
    c = "skip"
    for color1 in col_array:
        if color1 in res.upper() and color1 != color:
            c = color1
    if c == "skip":
        for name in names_dict:
            if name.lower() in res.lower() and translatePlayerColorID(names_dict[name]) != color:
                c = translatePlayerColorID(names_dict[name])
    print("Vote: " + res)
    print(c)
    vote(c.upper())
    time.sleep(10)
