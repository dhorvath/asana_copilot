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

# Initialize settings for dateparser
settings = {
    "PREFER_DATES_FROM": "future",
    "RELATIVE_BASE": datetime.datetime.now()
}

# Asana API configuration and helper functions
ASANA_BASE_URL = "https://app.asana.com/api/1.0"
DEFAULT_PROJECT_GID = "1209104858113361"

def create_asana_task(name, due_date=None, asana_token=None):
    """Create a task in Asana."""
    headers = {
        "Authorization": f"Bearer {asana_token}",
        "Content-Type": "application/json"
    }
    url = f"{ASANA_BASE_URL}/tasks"
    data = {
        "data": {
            "name": name,
            "projects": [DEFAULT_PROJECT_GID]
        }
    }
    if due_date:
        data["data"]["due_on"] = due_date
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code == 201:
        return resp.json()["data"]
    else:
        return {"error": resp.text}

def list_asana_tasks(only_open=True, asana_token=None):
    """List tasks in the default project."""
    headers = {
        "Authorization": f"Bearer {asana_token}",
        "Content-Type": "application/json"
    }
    url = f"{ASANA_BASE_URL}/projects/{DEFAULT_PROJECT_GID}/tasks"
    params = {
        "opt_fields": "name,completed"
    }
    if only_open:
        params["completed_since"] = "now"

    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        tasks = resp.json()["data"]
        if only_open:
            tasks = [task for task in tasks if not task.get("completed", False)]
        return tasks
    else:
        return {"error": resp.text}

def complete_asana_task(task_gid, asana_token=None):
    """Mark a task as complete."""
    headers = {
        "Authorization": f"Bearer {asana_token}",
        "Content-Type": "application/json"
    }
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}"
    data = {
        "data": {
            "completed": True
        }
    }
    resp = requests.put(url, json=data, headers=headers)
    if resp.status_code == 200:
        return resp.json()["data"]
    else:
        return {"error": resp.text}

def parse_llm_response(llm_output):
    """Parse the LLM response into a structured format."""
    try:
        print(f"Debug: Raw LLM Content: {llm_output}")
        
        # Strip the backticks and "json" tag if present
        if llm_output.startswith("```json") and llm_output.endswith("```"):
            llm_output = llm_output.strip("```").strip("json").strip()
        
        print(f"Debug: Cleaned LLM Output: {llm_output}")
        
        # Parse the cleaned JSON
        parsed_response = json.loads(llm_output)
        print(f"Debug: Parsed Response: {parsed_response}")
        return parsed_response
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse LLM response: {e}")
        return {"action": "NONE"}  # Fallback
    except Exception as e:
        print(f"Error: Unexpected issue in parse_llm_response: {e}")
        return {"action": "NONE"}  # Fallback

def extract_task_id_from_message(message):
    """Extract task ID from the user message."""
    match = re.search(r'\b\d{10,}\b', message)  # Look for 10+ digit numbers
    if match:
        return match.group(0)
    return None

# System prompt
system_prompt = """
You are a friendly AI Copilot that helps users interface with Asana -- namely creating new tasks, listing tasks, and marking tasks as complete.
You will interpret the user's request and respond with structured JSON.
Today's date is {today_date}.

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
"""

def get_formatted_prompt():
    """Format the system prompt with today's date."""
    today = datetime.datetime.now()
    formatted_date = today.strftime('%Y-%m-%d')
    # Replace {today_date} with actual date, but preserve other curly braces
    return system_prompt.replace("{today_date}", formatted_date)

# Show title and description
st.title("🎯 Asana Copilot")
st.write(
    "This chatbot helps you manage Asana tasks. You can create tasks, list tasks, "
    "and mark tasks as complete. You'll need both OpenAI and Asana API keys to proceed."
)

# Get API keys
openai_api_key = st.text_input("OpenAI API Key", type="password")
asana_api_key = st.text_input("Asana API Key", type="password")

if not openai_api_key or not asana_api_key:
    st.info("Please add both API keys to continue.", icon="🗝️")
else:
    # Initialize OpenAI client
    client = OpenAI(api_key=openai_api_key)

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_task_list" not in st.session_state:
        st.session_state.last_task_list = []
    if "waiting_for" not in st.session_state:
        st.session_state.waiting_for = None

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Handle user input
    if prompt := st.chat_input("How can I help with your Asana tasks?"):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get LLM response
        messages = [
            {"role": "system", "content": get_formatted_prompt()},
            *[{"role": m["role"], "content": m["content"]} 
              for m in st.session_state.messages]
        ]

        print("Debug - Messages being sent to OpenAI:", messages)

        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.2,
            max_tokens=200
        )

        llm_content = response.choices[0].message.content
        print(f"Debug: Raw LLM Content: {llm_content}")
        parsed = parse_llm_response(llm_content)
        action = parsed.get("action")

        with st.chat_message("assistant"):
            if action == "CREATE_TASK":
                name = parsed.get("name", "").strip()
                due_date = parsed.get("due")
                should_create_task = True
                
                # If we're waiting for a task name from a previous interaction
                if st.session_state.waiting_for == "task_name":
                    name = prompt.strip()
                    if not name:
                        response_text = "Task name cannot be empty. Please try again."
                        should_create_task = False
                    else:
                        st.session_state.task_name = name
                        st.session_state.waiting_for = "due_date"
                        response_text = ("Do you want to set a due date? Enter a date like 'tomorrow', "
                                       "'next Friday', or '2025-01-15', or just press Enter to skip")
                        should_create_task = False
                    
                # If we're waiting for a due date from a previous interaction
                elif st.session_state.waiting_for == "due_date":
                    name = st.session_state.task_name
                    if prompt.strip():  # If user provided a date
                        parsed_date = dateparser.parse(
                            prompt,
                            settings={
                                "PREFER_DATES_FROM": "future",
                                "RELATIVE_BASE": datetime.datetime.now()
                            }
                        )
                        if parsed_date:
                            due_date = parsed_date.strftime('%Y-%m-%d')
                        else:
                            st.error("I couldn't understand the due date. Skipping it.")
                            due_date = None
                    
                    # Create the task
                    result = create_asana_task(name, due_date, asana_api_key)
                    if "error" in result:
                        response_text = f"Sorry, I had trouble creating the task: {result['error']}"
                    else:
                        response_text = f"Created task '{result['name']}'"
                        if due_date:
                            response_text += f" due on {due_date}"
                        response_text += "."
                    
                    # Clear the waiting state
                    st.session_state.waiting_for = None
                    st.session_state.pop('task_name', None)
                    
                # Initial task creation request
                elif not name or name.lower() == "new task":
                    response_text = "What would you like the name of the task to be?"
                    st.session_state.waiting_for = "task_name"
                    should_create_task = False
                    
                # If we have a name from the initial command but no due date
                else:
                    if not due_date:
                        st.session_state.task_name = name
                        st.session_state.waiting_for = "due_date"
                        response_text = ("Do you want to set a due date? Enter a date like 'tomorrow', "
                                       "'next Friday', or '2025-01-15', or just press Enter to skip")
                        should_create_task = False
                    else:
                        # We have both name and due date, create the task
                        result = create_asana_task(name, due_date, asana_api_key)
                        if "error" in result:
                            response_text = f"Sorry, I had trouble creating the task: {result['error']}"
                        else:
                            response_text = f"Created task '{result['name']}'"
                            if due_date:
                                response_text += f" due on {due_date}"
                            response_text += "."
                    
                st.write(response_text)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_text})

            elif action == "LIST_TASKS":
                filter_type = parsed.get("filter", "open")
                only_open = filter_type == "open"
                tasks = list_asana_tasks(only_open=only_open, asana_token=asana_api_key)
                
                if "error" in tasks:
                    response_text = f"Sorry, I had trouble listing tasks: {tasks['error']}"
                elif not tasks:
                    response_text = "You have no tasks!" if not only_open else "You have no open tasks!"
                else:
                    task_type = "open" if only_open else "all"
                    response_text = f"Here are your {task_type} tasks:\n"
                    st.session_state.last_task_list = []
                    for t in tasks:
                        task_info = {'name': t['name'], 'gid': t['gid']}
                        st.session_state.last_task_list.append(task_info)
                        response_text += f"- {t['name']} (ID: {t['gid']})\n"
                
                st.write(response_text)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_text})

            elif action == "COMPLETE_TASK":
                task_gid = parsed.get("task_gid")
                task_name = parsed.get("name")
                position = parsed.get("position")
                
                if task_gid:
                    result = complete_asana_task(task_gid, asana_api_key)
                    if "error" in result:
                        response_text = f"Sorry, I couldn't complete the task: {result['error']}"
                    else:
                        response_text = f"Task '{result['name']}' marked as complete."
                
                elif task_name:
                    tasks = list_asana_tasks(asana_token=asana_api_key)
                    if "error" in tasks:
                        response_text = "Sorry, I had trouble fetching tasks to find a match."
                    else:
                        matches = [t for t in tasks if task_name.lower() in t['name'].lower()]
                        
                        if len(matches) == 1:
                            task_to_close = matches[0]
                            result = complete_asana_task(task_to_close["gid"], asana_api_key)
                            if "error" in result:
                                response_text = f"Sorry, I couldn't complete the task: {result['error']}"
                            else:
                                response_text = f"Task '{task_to_close['name']}' marked as complete."
                        elif len(matches) > 1:
                            response_text = "I found multiple tasks matching that name. Please specify which one:\n"
                            for task in matches:
                                response_text += f"- {task['name']} (ID: {task['gid']})\n"
                        else:
                            response_text = f"I couldn't find any tasks matching '{task_name}'."
                
                elif position is not None:
                    if st.session_state.last_task_list:
                        try:
                            position = int(position) - 1  # Convert to 0-based index
                            if 0 <= position < len(st.session_state.last_task_list):
                                task_to_close = st.session_state.last_task_list[position]
                                result = complete_asana_task(task_to_close["gid"], asana_api_key)
                                if "error" in result:
                                    response_text = f"Sorry, I couldn't complete the task: {result['error']}"
                                else:
                                    response_text = f"Task '{task_to_close['name']}' marked as complete."
                            else:
                                response_text = "The task number you specified is out of range."
                        except ValueError:
                            response_text = "Please provide a valid task number."
                    else:
                        response_text = "Please list your tasks first before referring to them by position."
                
                else:
                    response_text = "Please provide a valid task name, ID, or position to complete."
                
                st.write(response_text)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_text})

            else:
                st.write(llm_content)
                st.session_state.messages.append(
                    {"role": "assistant", "content": llm_content})
