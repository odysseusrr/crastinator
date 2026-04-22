import os
from flask import Flask, render_template, jsonify, request
import random
import json

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= DB SAFE LOAD
def load_db():
    try:
        with open(os.path.join(BASE_DIR, "phrases_db.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("ERROR loading DB:", e)
        return {}

PHRASES_DB = load_db()

# ================= TON SYSTÈME (inchangé logique)

TIMES = [
    18000,    # 5 heures
    432000,   # 5 jours
    3024000   # 5 semaines
]

PROJECTS = ["Intéressant", "Important", "Vital"]

# ================= STATE WEB
state = {
    "score": 0,
    "history": [],
    "blocked_until": 0,
    "mood": 0,
    "last_phrases": [],
    "click_intervals": [],
    "last_click_time": 0,
    "mood_history": [],
    "mood_raw": 0
}
from threading import Lock
state_lock = Lock()


# ================= PERSONALITY EVOLUTION
import time

def compute_mood():
    with state_lock:

        # =====================
        # 1. BASE (score long terme)
        # =====================
        s = state["score"]
        t = min(s / 100, 1.0)

        if t < 0.3:
            mood = 0
        elif t < 0.6:
            mood = 1
        elif t < 0.85:
            mood = 2
        else:
            mood = 3

        # =====================
        # 2. RYTHME (court terme)
        # =====================
        if len(state["click_intervals"]) >= 3:
            avg = sum(state["click_intervals"]) / len(state["click_intervals"])

            if avg < 2:
                mood += 1      # spam = agressif
            elif avg > 10:
                mood -= 1      # lenteur = calme

        # =====================
        # 3. DÉCROISSANCE (idle)
        # =====================
        now = time.time()
        last = state.get("last_click_time", 0)
        idle = now - last if last else 999

        if idle > 120:
            mood -= 2
        elif idle > 30:
            mood -= 1

        # clamp final
        
        mood = max(0, min(3, mood))
        state["mood_raw"] = float(mood)


        state["mood_history"].append(state["mood_raw"])

        if len(state["mood_history"]) > 20:
            state["mood_history"].pop(0)

        avg_mood = (
            sum(state["mood_history"]) / len(state["mood_history"])
            if state["mood_history"]
            else state["mood_raw"]
        )

        # drift très léger uniquement
        if len(state["mood_history"]) >= 10:
            smoothed = state["mood_raw"] * 0.95 + avg_mood * 0.05
            state["mood_raw"] = max(0, min(3, smoothed))

        state["mood_raw"] = float(state["mood_raw"])
        state["mood"] = max(0, min(3, int(round(state["mood_raw"]))))




# ================= AVOID REPETITION

def avoid_repeat(phrases):
    filtered = [p for p in phrases if p[1] not in state["last_phrases"]]

    if not filtered:
        filtered = phrases

    choice = random.choice(filtered)[1]

    state["last_phrases"].append(choice)

    if len(state["last_phrases"]) > 15:
        state["last_phrases"].pop(0)

    return choice




# ================= GET PHRASE (TON CERVEAU TRANSLATÉ)


def get_phrase(time_value, project):


    # registre du clic
    
    now = time.time()
    last = state["last_click_time"]

    if last != 0:
        delta = now - last   
    else:
        delta = None  # premier clic (neutral)
    
    if delta is not None:
        delta = max(0, min(delta, 30))
    


    # niveau temps correct

    if time_value <= 18000:
        t_level = "short"
    elif time_value <= 432000:
        t_level = "medium"
    else:
        t_level = "long"



    mood_map = {
        0: ["sarcastic"],
        1: ["sarcastic", "aggressive"],
        2: ["aggressive", "sarcastic"],
        3: ["resigned", "aggressive"]
    }

    mood_level = int(state["mood"])
    mood_level = max(0, min(3, mood_level))

    personality = random.choice(mood_map[mood_level])
    
    with state_lock:
        if delta is not None:
            state["click_intervals"].append(min(delta, 30))
            if len(state["click_intervals"]) > 20:
                state["click_intervals"].pop(0)
        
        state["score"] += 1
        
        compute_mood()
    
    level = PHRASES_DB.get(t_level, {})
    project_data = level.get(project, {})

    phrases = project_data.get(personality, [])

    # fallback intelligent
    if not phrases:
        for alt in ["sarcastic", "aggressive", "resigned"]:
            phrases = project_data.get(alt, [])
            if phrases:
                break

    if not phrases:
        return "..."

    return avoid_repeat(phrases)

# ================= API START

@app.route("/api/start", methods=["POST"])
def start():
    data = request.json

    time_idx = data.get("time")
    project_idx = data.get("project")

    if time_idx is None or project_idx is None:
        return jsonify({"error": "Invalid input"}), 400

    if time_idx < 0 or time_idx >= len(TIMES):
        return jsonify({"error": "Invalid time index"}), 400

    if project_idx < 0 or project_idx >= len(PROJECTS):
        return jsonify({"error": "Invalid project"}), 400

    time_value = TIMES[time_idx]
    project = PROJECTS[project_idx]

    return jsonify({
        "text": get_phrase(time_value, project),
        "score": state["score"]
    })

# ================= HOME
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/state")
def get_state():
    return jsonify(state)

@app.route("/api/reload-db", methods=["POST"])
def reload_db():
    global PHRASES_DB
    PHRASES_DB = load_db()
    return jsonify({"status": "reloaded"})


if __name__ == "__main__":
    app.run()
