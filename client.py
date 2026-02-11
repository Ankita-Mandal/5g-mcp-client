import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.logging import LogMessage
from fastmcp.client.elicitation import ElicitResult, ElicitRequestParams, RequestContext

load_dotenv()
ANTHROPIC_MODEL = "claude-sonnet-4-5"

class MCPClient:
    def __init__(self):
        self._anthropic: Anthropic | None = None
        self.conversation_history = []

    @property
    def anthropic(self) -> Anthropic:
        if self._anthropic is None:
            self._anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return self._anthropic

    async def handle_elicitation(self, message: str, response_type: type | None, params: ElicitRequestParams, context: RequestContext) -> ElicitResult | object:
        """Handle confirmation requests from gNB server"""
        #TODO: Confirmation by button click on the Glasses
        print(f"\n{'='*60}")
        print(f"gNB CONFIRMATION REQUIRED")
        print(f"{'='*60}")
        print(f"{message}")
    
        response = input("\nContinue with this operation? (y/n): ").strip().lower() #TODO: Replace with button click
        confirmed = response in ("y", "yes")
    
        if confirmed:
            print("Operation confirmed")
            # For response_type=None, return None directly (implicit accept)
            if response_type is None:
                return None
            else:
                return response_type()
        else:
            print("Operation cancelled")
            return ElicitResult(action="decline")

    async def handle_logging(self, message: LogMessage):
        """Handle log messages from gNB server"""
        level_name = message.level.upper()
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        log_line = f"[{timestamp}] [gNB-{level_name}] {message.data}"
        
        if message.extra:
            log_line += f" | {message.extra}"
            
        print(log_line)

    async def process_query(self, client: Client, query: str, tools: list) -> str:
        """Process a query using Claude and available tools"""
        
        # 1. Add user query
        self.conversation_history.append({"role": "user", "content": query})
        
        # 2. Get Claude's response
        response = self.anthropic.messages.create(
            model=ANTHROPIC_MODEL, 
            max_tokens=1000, 
            messages=self.conversation_history, 
            tools=tools
        )
        
        # 3. Add Claude's response to history (including tool calls)
        self.conversation_history.append({"role": "assistant", "content": response.content})
        
        # Collect tool calls and prepare display text
        tool_calls = [content for content in response.content if content.type == "tool_use"]
        final_text = [content.text for content in response.content if content.type == "text"]
        
        # 4. Execute tools and add results
        if tool_calls:
            tool_results = []
            for tool_call in tool_calls:
                result = await client.call_tool(tool_call.name, tool_call.input)
                final_text.append(f"[Calling tool {tool_call.name} with args {tool_call.input}]")
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result.content
                })
            
            # Add ALL tool results as one user message
            self.conversation_history.append({"role": "user", "content": tool_results})
            
            # 5. Get Claude's final interpretation
            final_response = self.anthropic.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1000,
                messages=self.conversation_history,
            )
            
            self.conversation_history.append({"role": "assistant", "content": final_response.content})
            final_text.extend([content.text for content in final_response.content if content.type == "text"])

        return "\n".join(final_text)

    async def chat_loop(self, client: Client, available_tools: list):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        #TODO: Add voice input to prompt text / process_query pipeline
        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == "quit":
                    break

                response = await self.process_query(client, query, available_tools)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")


async def main():
    # Check if we have a valid API key before connecting
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nNo ANTHROPIC_API_KEY found. To query these tools with Claude, set your API key:")
        return

    # Create MCPClient instance once
    mcp_client = MCPClient()
    
    async with Client("../ar_gnb_server/server.py", elicitation_handler=mcp_client.handle_elicitation) as client:
        await client.ping()

        # List available operations
        tools = await client.list_tools()
        available_tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.inputSchema}
            for tool in tools
        ]
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        print(f"\nConnected to server with tools: {[tool.name for tool in tools]}")
        print(f"\nConnected to server with resources: {[resource.name for resource in resources]}")
        print(f"\nConnected to server with prompts: {[prompt.name for prompt in prompts]}")

        # Start chat loop with the connected client
        await mcp_client.chat_loop(client, available_tools)

if __name__ == "__main__":
    asyncio.run(main())