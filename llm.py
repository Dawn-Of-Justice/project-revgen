from dotenv import load_dotenv
from groq import Groq
import os
from print_color import print
import json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = 'llama-3.3-70b-versatile'

def tv_off():
    pass

def tv_on():
    pass

def tv_volume_up():
    pass

def tv_volume_down():
    pass

def modem_off():
    pass

def modem_on():
    pass

def volume_up():
    pass

def volume_down():
    pass

def volume_mute():
    pass

def volume_set():
    pass
    
def channel_up():
    pass

def channel_down():
    pass

def channel_set():
    pass

def change_input():
    pass


def run_conversation(user_prompt):
    messages=[
        {
            "role": "system",
            "content": """  You are an AI assistant running on a custom hardware to help old people use electronic devices easliy. 
                            You will be given an input in english. You need to select the appropriate action based on the input.
                            The idea is that the user will speak in their native language and it will be given to google cloud for traslation,
                            and be given to the AI. The AI will perform the appropriate action by returning the signal requested by the user."""
        },
        {
            "role": "user",
            "content": user_prompt,
        }
    ]
    # Define the available tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Evaluate a mathematical expression",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "The mathematical expression to evaluate",
                        }
                    },
                    "required": ["expression"],
                },
            },
        }
    ]
    
    # Make the initial API call to Groq
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=False,
        tools=tools,
        tool_choice="auto",
        max_completion_tokens=4096
    )
    
    # Extract the response and any tool calls
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls
    
    if tool_calls:
        # Add the assistant's response to the conversation
        messages.append({
            "role": "assistant",
            "content": response_message.content,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                } for tool_call in tool_calls
            ]
        })

        # Process each tool call
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # Call the calculate function
            function_response = calculate(
                expression=function_args.get("expression")
            )
            
            # Add the tool response to the conversation
            messages.append({
                "role": "tool",
                "content": function_response,
                "tool_call_id": tool_call.id
            })
        
        # Make the second API call with the updated conversation
        second_response = client.chat.completions.create(
            model=MODEL,
            messages=messages
        )
        
        return second_response.choices[0].message.content
    
    # If no tool calls were made, return the initial response
    return response_message.content

if __name__ == "__main__":
    user_prompt = "What is 25 * 4 + 10?"
    print(run_conversation(user_prompt))