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
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.client.transports import StdioTransport

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

    def handle_logging(self, message: LogMessage):
        """Handle log messages from gNB server with enhanced display"""
        level_name = message.level.upper()
        timestamp = datetime.now().strftime("%H:%M:%S")
    
        # Enhanced formatting for different log levels
        if level_name == "INFO":
            log_line = f"[{timestamp}] [SERVER-{level_name}] {message.data}"
        elif level_name == "ERROR":
            log_line = f"[{timestamp}] [SERVER-{level_name}] {message.data}"
        elif level_name == "WARNING":
            log_line = f"[{timestamp}] [SERVER-{level_name}] {message.data}"
        else:
            log_line = f"[{timestamp}] [SERVER-{level_name}] {message.data}"
    
        if message.extra:
            log_line += f" | {message.extra}"
            print(log_line)

    async def process_query(self, client: Client, query: str, tools: list) -> str:
        """Process a query using Claude and available tools with real-time intermediate display"""
        
        # 1. Add user query
        self.conversation_history.append({"role": "user", "content": query})
        
        # 2. Get Claude's initial response
        print("\nClaude: ")
        response = self.anthropic.messages.create(
            model=ANTHROPIC_MODEL, 
            max_tokens=7000,
            messages=self.conversation_history, 
            tools=tools
        )
        print(f"Input tokens: {response.usage.input_tokens}")
        print(f"Output tokens: {response.usage.output_tokens}")
        # 3. Add Claude's response to history
        self.conversation_history.append({"role": "assistant", "content": response.content})
        
        # Display initial text content immediately
        initial_text = [content.text for content in response.content if content.type == "text"]
        if initial_text:
            print("\n".join(initial_text))
        
        # Check for tool calls
        tool_calls = [content for content in response.content if content.type == "tool_use"]
        
        # 4. Execute tools and show real-time results
        if tool_calls:
            print(f"\n** Tool Execution ({len(tool_calls)} tool(s)):**")
            tool_results = []
            
            for i, tool_call in enumerate(tool_calls, 1):
                print(f"\n[{i}] Calling tool '{tool_call.name}' with args: {tool_call.input}")
                
                # Execute tool and show result immediately
                result = await client.call_tool(tool_call.name, tool_call.input)
                print(f"[{i}] Tool '{tool_call.name}' completed")
                
                # Show a preview of the result if it's not too long
                result_preview = str(result.content)[:200] + "..." if len(str(result.content)) > 200 else str(result.content)
                print(f"[{i}] Result preview: {result_preview}")
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result.content
                })
            
            # Add ALL tool results as one user message
            self.conversation_history.append({"role": "user", "content": tool_results})
            
            # 5. Get Claude's final analysis
            print(f"\n** Claude's Analysis of Tool Results:**")
            final_response = self.anthropic.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=7000,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 3200
                }, 
                messages=self.conversation_history,
            )
            print(f"Input tokens: {final_response.usage.input_tokens}")
            print(f"Output tokens: {final_response.usage.output_tokens}")
            self.conversation_history.append({"role": "assistant", "content": final_response.content})
            final_analysis = [content.text for content in final_response.content if content.type == "text"]
            
            if final_analysis:
                print("\n".join(final_analysis))
            
            # Return combined response for history
            return "\n".join(initial_text + [f"[Tool: {tc.name}]" for tc in tool_calls] + final_analysis)
        
        else:
            # No tools called, just return the initial response
            return "\n".join(initial_text)


    async def chat_loop(self, client: Client, available_tools: list):
        """Run an interactive chat loop with real-time display"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
    
        while True:
            try:
                query = input("\nQuery: ").strip()
            
                if query.lower() == "quit":
                    break

                # Process query with real-time display (no need to print response)
                await self.process_query(client, query, available_tools)
            
                print("\n" + "="*60)  # Separator between queries

            except Exception as e:
                print(f"Error: {e}")

async def main():
    # Check if we have a valid API key before connecting
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nNo ANTHROPIC_API_KEY found. To query these tools with Claude, set your API key:")
        return

    # Create MCPClient instance once
    mcp_client = MCPClient()
    
    # Configure multiple transports
    config = {
        "mcpServers": {
            "usrp_gnb_server": {
                "command": "python",
                "args": ["../ar_gnb_server/server.py"],
                "env": {
                    "OAI_DOCUMENTATION_DIR": "/home/xmili/Documents/Abhiram/USRPworkarea/oai-setup/openairinterface5g/doc",
                    "ANTHROPIC_API_KEY": api_key
                }
            },
            "remote_x5g_server": {
                "url": "http://localhost:8080/mcp",
                "transport": "http",
                "headers": {
                    "Content-Type": "application/json"
                }
            }
        }
    }
    
    async with Client(config, elicitation_handler=mcp_client.handle_elicitation) as client:
        await client.ping()

        # List available operations (tools will now be namespaced)
        tools = await client.list_tools()
        available_tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.inputSchema}
            for tool in tools
        ]
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        server_names = list(config["mcpServers"].keys())
        primary_server = server_names[0] if server_names else "unknown"
 
        print(f"\nConnected to '{primary_server}' with tools: {[tool.name for tool in tools]}")
        print(f"\nConnected to '{primary_server}' with resources: {[resource.name for resource in resources]}")
        print(f"\nConnected to '{primary_server}' with prompts: {[prompt.name for prompt in prompts]}")
        
        # Start chat loop with the connected client
        await mcp_client.chat_loop(client, available_tools)

if __name__ == "__main__":
    asyncio.run(main())