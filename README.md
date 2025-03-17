# 🎯 Asana Copilot

Asana Copilot is a Streamlit-based chatbot that helps you manage your Asana tasks using natural language. Built with OpenAI's GPT-4, it provides an intuitive interface for creating, listing, and completing tasks in Asana.

## Features

- 📝 **Create Tasks**: Create new tasks with optional due dates
- 📋 **List Tasks**: View all tasks or just open tasks
- ✅ **Complete Tasks**: Mark tasks as complete using task names or IDs
- 💬 **Natural Language**: Interact with Asana using conversational language

## Prerequisites

- Python 3.8+
- OpenAI API key
- Asana API key
- Asana Project ID

## Installation

1. Clone the repository:
2. Install required packages:

bash
pip install -r requirements.txt

## Usage

1. Run the Streamlit app:

bash
streamlit run streamlit_app.py

2. Enter your OpenAI and Asana API keys in the interface

3. Start interacting with the chatbot! Example commands:
   - "Create a task"
   - "List my open tasks"
   - "List all my tasks"
   - "Complete task X"

## Configuration

Update the `DEFAULT_PROJECT_GID` in `streamlit_app.py` with your Asana project ID.

## Security Note

API keys are handled through Streamlit's interface and are not stored permanently. Always keep your API keys secure and never commit them to version control.

## TESTING TESTING

Testing Zapier Webhooks

Testing #3!!!!

Testing #4!!!!

Testing #5!!!!
