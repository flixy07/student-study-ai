import os
import time
import sqlite3

from flask import Flask, render_template, request, jsonify
from google import genai


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    print("WARNING: GEMINI_API_KEY is not set.")

client = genai.Client(api_key=API_KEY) if API_KEY else None

DATABASE = "study_assistant.db"


# ============================================================
# DATABASE
# ============================================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():

    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


init_database()


# ============================================================
# SAVE CHAT
# ============================================================

def save_chat(user_message, ai_response):

    connection = get_db()

    connection.execute(
        """
        INSERT INTO chat_history
        (user_message, ai_response)
        VALUES (?, ?)
        """,
        (user_message, ai_response)
    )

    connection.commit()
    connection.close()


# ============================================================
# GET CHAT HISTORY
# ============================================================

def get_chat_history():

    connection = get_db()

    chats = connection.execute(
        """
        SELECT id, user_message, ai_response, created_at
        FROM chat_history
        ORDER BY id ASC
        """
    ).fetchall()

    connection.close()

    return chats


# ============================================================
# GEMINI FUNCTION
# ============================================================

def ask_gemini(prompt):

    if not client:

        return None, "Gemini API key is not configured."


    models = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash"
    ]


    last_error = None


    for model in models:

        for attempt in range(2):

            try:

                print(
                    f"Trying model: {model}, "
                    f"attempt: {attempt + 1}"
                )


                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )


                return response.text, None


            except Exception as e:

                last_error = e

                print(
                    f"ERROR with {model}: {e}"
                )

                time.sleep(2)


    print(
        "All Gemini models failed:",
        last_error
    )


    return None, (
        "Gemini is temporarily unavailable. "
        "Please try again in a few minutes."
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# ASK AI
# ============================================================

@app.route("/ask", methods=["POST"])
def ask():

    data = request.get_json() or {}

    question = data.get(
        "question",
        ""
    ).strip()


    if not question:

        return jsonify({
            "answer": "Please enter a question."
        }), 400


    # --------------------------------------------------------
    # LOAD PREVIOUS CONVERSATION
    # --------------------------------------------------------

    history = get_chat_history()


    conversation = ""


    # Only send the most recent 20 messages
    # to avoid making the prompt unnecessarily large.

    recent_history = history[-20:]


    for chat in recent_history:

        conversation += f"""
Student:
{chat["user_message"]}

AI Study Assistant:
{chat["ai_response"]}

"""


    # --------------------------------------------------------
    # GEMINI PROMPT
    # --------------------------------------------------------

    prompt = f"""
You are a helpful AI Study Assistant.

You are having an ongoing conversation with a college student.

Previous conversation:

{conversation}

New student question:

{question}

Instructions:

- Use previous conversation when relevant.
- Understand follow-up questions.
- If the student says "it", "this", "that", etc.,
  use the previous conversation to understand the reference.
- Do not unnecessarily repeat previous answers.
- Use simple language.
- Give examples when useful.
- Use bullet points when useful.
- For programming questions, provide simple examples.
"""


    # --------------------------------------------------------
    # CALL GEMINI
    # --------------------------------------------------------

    answer, error = ask_gemini(prompt)


    if error:

        return jsonify({
            "answer": error
        }), 503


    # --------------------------------------------------------
    # SAVE CHAT
    # --------------------------------------------------------

    save_chat(
        question,
        answer
    )


    return jsonify({
        "answer": answer
    })


# ============================================================
# GET HISTORY
# ============================================================

@app.route("/history", methods=["GET"])
def history():

    chats = get_chat_history()


    history_list = []


    for chat in chats:

        history_list.append({

            "id": chat["id"],

            "question":
                chat["user_message"],

            "answer":
                chat["ai_response"],

            "created_at":
                chat["created_at"]

        })


    return jsonify({
        "history": history_list
    })


# ============================================================
# CLEAR HISTORY
# ============================================================

@app.route("/clear-history", methods=["POST"])
def clear_history():

    connection = get_db()

    connection.execute(
        "DELETE FROM chat_history"
    )

    connection.commit()
    connection.close()


    return jsonify({
        "message": "Chat history cleared."
    })


# ============================================================
# EXPLAIN
# ============================================================

@app.route("/explain", methods=["POST"])
def explain():

    data = request.get_json() or {}

    topic = data.get(
        "topic",
        ""
    ).strip()


    if not topic:

        return jsonify({
            "answer":
                "Please enter a topic to explain."
        }), 400


    prompt = f"""
You are an expert college tutor.

Explain this topic:

{topic}

Use this structure:

1. Simple Definition
2. Explanation
3. How it works
4. Easy example
5. Real-world analogy
6. Important points
7. Short summary

Use simple language.

If this is a programming topic,
include a simple code example.
"""


    answer, error = ask_gemini(prompt)


    if error:

        return jsonify({
            "answer": error
        }), 503


    return jsonify({
        "answer": answer
    })


# ============================================================
# QUIZ
# ============================================================

@app.route("/quiz", methods=["POST"])
def quiz():

    data = request.get_json() or {}

    topic = data.get(
        "topic",
        ""
    ).strip()


    if not topic:

        return jsonify({
            "answer":
                "Please enter a topic for the quiz."
        }), 400


    prompt = f"""
Create a quiz for a college student about:

{topic}

Create exactly 5 multiple-choice questions.

For every question provide:

- Question
- Four options
- Correct answer
- Short explanation

Use exactly this format:

QUESTION 1:
question

A) option
B) option
C) option
D) option

ANSWER: A

EXPLANATION:
explanation

QUESTION 2:
question

A) option
B) option
C) option
D) option

ANSWER: B

EXPLANATION:
explanation

Continue until QUESTION 5.
"""


    answer, error = ask_gemini(prompt)


    if error:

        return jsonify({
            "answer": error
        }), 503


    return jsonify({
        "answer": answer
    })


# ============================================================
# NOTES
# ============================================================

@app.route("/notes", methods=["POST"])
def notes():

    data = request.get_json() or {}

    topic = data.get(
        "topic",
        ""
    ).strip()


    if not topic:

        return jsonify({
            "answer":
                "Please enter a topic for the notes."
        }), 400


    prompt = f"""
Create simple study notes for:

{topic}

Use this structure:

TITLE

1. Definition

2. Key Concepts

3. Important Points

4. Types or Categories

5. Example

6. Advantages

7. Disadvantages

8. Exam Tips

9. Quick Revision

Keep the notes concise.

If this is a programming topic,
include simple code examples.
"""


    answer, error = ask_gemini(prompt)


    if error:

        return jsonify({
            "answer": error
        }), 503


    return jsonify({
        "answer": answer
    })


# ============================================================
# STUDY PLAN
# ============================================================

@app.route("/study-plan", methods=["POST"])
def study_plan():

    data = request.get_json() or {}

    topic = data.get(
        "topic",
        ""
    ).strip()


    if not topic:

        return jsonify({
            "answer":
                "Please enter a subject or topic."
        }), 400


    prompt = f"""
Create a 7-day study plan for:

{topic}

The student is a college student.

Create:

DAY 1
- Topics
- Practice

DAY 2
- Topics
- Practice

DAY 3
- Topics
- Practice

DAY 4
- Topics
- Practice

DAY 5
- Topics
- Practice

DAY 6
- Topics
- Practice

DAY 7
- Topics
- Practice

Also include:

Daily study duration
Revision strategy
Practice strategy
Final revision
Self-test

Keep it realistic and easy to follow.
"""


    answer, error = ask_gemini(prompt)


    if error:

        return jsonify({
            "answer": error
        }), 503


    return jsonify({
        "answer": answer
    })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )