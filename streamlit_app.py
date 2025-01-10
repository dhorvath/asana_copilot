import streamlit as st
from openai import OpenAI
import requests
import asana
from asana.rest import ApiException
from pprint import pprint
import json
import datetime
import dateparser
import re

# --- Asana Copilot Functions and Variables ---
ASANA_BASE_URL = "https://app.asana.com/api/1.0"
DEFAULT_PROJECT_GID = "1209104858113361" # Replace with your project GID if needed
last_task_list = []

# Get Asana API key from environment variable
access_token = st.secrets["asana"]

# Set up the Asana API client
configuration = asana.Configuration()
configuration.access_token = access_token
api_client = asana.ApiClient(configuration)

ASANA_HEADERS = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

def create_asana_task(name, due_date=None):
    """Create a task in Asana."""
    url = f"{ASANA_BASE_URL}/tasks"
    data = {
        "data": {
            "name": name,
            "projects": [DEFAULT_PROJECT_GID]
        }
    }
    if due_date:
        data["data"]["due_on"] = due_date
    resp = requests.post(url, json=data, headers=ASANA_HEADERS)
    if resp.status_code == 201:
        return resp.json()["data"]
    else:
        return {"error": resp.text}

def list_asana_tasks(only_open=True):
    """List tasks in the default project."""
    url = f"{ASANA_BASE_URL}/projects/{DEFAULT_PROJECT_GID}/tasks"
    params = {
        "opt_fields": "name,completed"
    }
    if only_open:
        params["completed_since"] = "now"

    resp = requests.get(url, headers=ASANA_HEADERS, params=params)
    if resp.status_code == 200:
        tasks = resp.json()["data"]
        if only_open:
            tasks = [task for task in tasks if not task.get("completed", False)]
        return tasks
    else:
        return {"error": resp.text}

def complete_asana_task(task_gid):
    """Mark a task as complete."""
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}"
    data = {
        "data": {
            "completed": True
        }
    }
    resp = requests.put(url, json=data, headers=ASANA_HEADERS)
    if resp.status_code == 200:
        return resp.json()["data"]
    else:
        return {"error": resp.text}
    
def call_llm(client, user_message, conversation_history=None):
    today_date = datetime.date.today().strftime("%Y-%m-%d")
    messages = [
        {"role": "system", "content": system_prompt.format(today_date=today_date)},
        {"role": "user", "content": user_message}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=200
    )

    llm_content = response.choices[0].message.content
    print(f"Debug: Raw LLM Content: {llm_content}")  # Keep this for debugging
    return llm_content
    
def execute_turn(client, user_message):
    global last_task_list
    llm_output = call_llm(client, user_message)
    parsed = parse_llm_response(llm_output)
    action = parsed.get("action")

    if action == "CREATE_TASK":
        task_name = parsed.get("name", "").strip()
        due_date = parsed.get("due")

        if not task_name or task_name.lower() == "new task":
            task_name = st.session_state.next_task_name
            st.session_state.next_task_name = None  # Reset

        if not due_date:
            due_date = st.session_state.next_due_date
            st.session_state.next_due_date = None

        result = create_asana_task(task_name, due_date)

        if "error" in result:
            st.write("Sorry, I had trouble creating the task:", result["error"])
        else:
            message = f"I've created your task '{result['name']}' (ID: {result['gid']})."
            if due_date:
                message += f" It's due on {due_date}."
            st.write(message)

    elif action == "LIST_TASKS":
        filter_type = parsed.get("filter", "open")
        only_open = filter_type == "open"
        tasks = list_asana_tasks(only_open=only_open)

        if "error" in tasks:
            st.write("Sorry, I had trouble listing tasks:", tasks["error"])
        elif not tasks:
            st.write("You have no tasks!" if not only_open else "You have no open tasks!")
        else:
            task_type = "all" if not only_open else "open"
            st.write(f"Here are your {task_type} tasks:")
            last_task_list.clear()
            for t in tasks:
                task_info = {'name': t['name'], 'gid': t['gid']}
                last_task_list.append(task_info)
                st.write(f"- {t['name']} (ID: {t['gid']})")

    elif action == "COMPLETE_TASK":
        task_gid = parsed.get("task_gid")
        task_name = parsed.get("name")
        
        if task_gid:
            result = complete_asana_task(task_gid)
            if "error" in result:
                st.write("Sorry, I couldn’t complete the task:", result["error"])
            else:
                st.write(f"Task '{result['name']}' marked as complete.")

        elif task_name:
            tasks = list_asana_tasks()
            if "error" in tasks:
                st.write("Sorry, I had trouble fetching tasks to find a match.")
                return

            matches = [t for t in tasks if task_name.lower() in t['name'].lower()]

            if len(matches) == 1:
                task_to_close = matches[0]
                result = complete_asana_task(task_to_close["gid"])
                if "error" in result:
                    st.write(f"Sorry, I couldn’t complete the task: {result['error']}")
                else:
                    st.write(f"Task '{task_to_close['name']}' marked as complete.")

            elif len(matches) > 1:
                st.write("I found multiple tasks matching that name. "
                         "Please provide the ID of the task you'd like to close:")
                for task in matches:
                    st.write(f"- {task['name']} (ID: {task['gid']})")
            else:
                st.write(f"I couldn’t find any tasks matching '{task_name}'.")

        else:
            ordinal_map = {
                'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
                'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10
            }
            words = user_message.lower().split()
            ordinal_position = None
            for word in words:
                if word in ordinal_map:
                    ordinal_position = ordinal_map[word] - 1
                    break
                elif word.isdigit():
                    ordinal_position = int(word) - 1
                    break

            if ordinal_position is not None and last_task_list:
                if 0 <= ordinal_position < len(last_task_list):
                    task_to_close = last_task_list[ordinal_position]
                    result = complete_asana_task(task_to_close["gid"])
                    if "error" in result:
                        st.write(f"Sorry, I couldn’t complete the task: {result['error']}")
                    else:
                        st.write(f"Task '{task_to_close['name']}' marked as complete.")
                else:
                    st.write("The task number you specified is out of range.")
            else:
                st.write("Please provide a valid task name, ID, or position to close.")
    else:
        st.write(llm_output)

def extract_task_id_from_message(message):
    """Extract task ID from message."""
    match = re.search(r'\b\d{10,}\b', message)
    if match:
        return match.group(0)
    return None

def parse_llm_response(llm_output):
    """Parse LLM response, ensure it's a dict with an 'action' key, and handle errors."""
    try:
        print(f"Debug: Raw LLM Content: {llm_output}")

        # Attempt to parse the JSON directly
        parsed_response = json.loads(llm_output)

        print(f"Debug: Parsed Response: {parsed_response}")

        # Check if the parsed response is a dictionary
        if isinstance(parsed_response, dict):
            # Check if the 'action' key is present
            if "action" in parsed_response:
                return parsed_response
            else:
                print(f"Error: 'action' key missing in LLM response.")
                return {"action": "NONE"}  # Default action
        else:
            print(f"Error: LLM response is not a dictionary.")
            return {"action": "NONE"}  # Default action

    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse LLM response as JSON: {e}")
        return {"action": "NONE"}
    except Exception as e:
        print(f"Error: Unexpected issue in parse_llm_response: {e}")
        return {"action": "NONE"}

system_prompt = """
You are a friendly AI Copilot that helps users interface with Asana -- namely creating new tasks, listing tasks, and marking tasks as complete.

You will interpret the user's request and respond with structured JSON.

Today's date is {today_date}.

**IMPORTANT: ALWAYS RESPOND IN JSON FORMAT. Your response MUST contain an "action" key.**

Rules:
1. If the user asks to create a task, respond with:
   { "action": "CREATE_TASK", "name": "<TASK NAME>", "due": "<YYYY-MM-DD>" }
   If they gave a date in any format. For words like 'tomorrow', interpret it as {today_date} + 1 day, etc.
   If no date is given or you cannot parse it, omit the 'due' field.
2. If the user asks to list tasks, respond with:
   {"action": "LIST_TASKS", "filter": "open"}  # For "list my open tasks" or similar
   {"action": "LIST_TASKS", "filter": "all"}  # For "list all my tasks" or similar
   If the user specifies "open tasks" or similar, return only incomplete tasks. If the user specifies "all tasks," return all tasks (completed and incomplete).
   If the intent is unclear, default to showing only open tasks.
3. If the user asks to complete a task, respond with:
   { "action": "COMPLETE_TASK", "task_gid": "<ID>" }
   OR
   { "action": "COMPLETE_TASK", "name": "<TASK NAME>" }
   OR
   { "action": "COMPLETE_TASK", "position": <NUMBER> }
   Use 'position' if the user refers to a task by its position in the list (e.g., "third one").
4. If no action is needed, respond with:
   { "action": "NONE" }

Examples:
- User: "Close task 1209105096577103"
  Response: { "action": "COMPLETE_TASK", "task_gid": "1209105096577103" }

- User: "Can you close rub jason's feet?"
  Response: { "action": "COMPLETE_TASK", "name": "rub jason's feet" }

- User: "List all my tasks"
  Response: { "action": "LIST_TASKS" }

- User: "Create a task called 'Finish report' due tomorrow"
  Response: { "action": "CREATE_TASK", "name": "Finish report", "due": "2025-01-08" }

- User: "Close the third one"
  Response: { "action": "COMPLETE_TASK", "position": 3 }

- User: "Complete task number 5"
  Response: { "action": "COMPLETE_TASK", "position": 5 }

- {"action": "LIST_TASKS", "filter": "open"}  # For "list my open tasks"
- {"action": "LIST_TASKS", "filter": "all"}  # For "list all my tasks"
- {"action": "CREATE_TASK", "name": "Task Name", "due": "2025-01-15"}
- {"action": "COMPLETE_TASK", "task_gid": "1209105096577103"}

Again, always respond in JSON format. Example:
{
  "action": "CREATE_TASK",
  "name": "Submit Assignment",
  "due": "2023-12-31"
}

If no action is required, respond with:
{
  "action": "NONE"
}
"""

# --- Streamlit UI ---
st.title("Asana Copilot")

# Get the OpenAI API key from environment variable
openai_api_key = st.secrets["open_ai_key"]

if not openai_api_key:
    st.info("Please add your OpenAI API key to continue.", icon="🗝️")
else:
    client = OpenAI(api_key=openai_api_key)

    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.next_task_name = None
        st.session_state.next_due_date = None

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("What is up?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            response = execute_turn(client, prompt)
            
        st.session_state.messages.append({"role": "assistant", "content": response})