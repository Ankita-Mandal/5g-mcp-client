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

load_dotenv()  # load environment variables from .env

# Claude model constant
ANTHROPIC_MODEL = "claude-sonnet-4-5"


class MCPClient:
    def __init__(self, server_path: str):
        self.server_path = server_path
        self._anthropic: Anthropic | None = None

    @property
    def anthropic(self) -> Anthropic:
        if self._anthropic is None:
            self._anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return self._anthropic

    async def handle_elicitation(
        self,
        message: str,
        response_type: type | None,
        params: ElicitRequestParams,
        context: RequestContext
    ) -> ElicitResult | object:
        """Handle confirmation requests from gNB server"""
        print(f"\n{'='*60}")
        print(f"gNB CONFIRMATION REQUIRED")
        print(f"{'='*60}")
        print(f"{message}")
    
        response = input("\nContinue with this operation? (y/n): ").strip().lower()
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

    def create_client(self) -> Client:
        """Create FastMCP client with handlers"""
        return Client(
            self.server_path,
            elicitation_handler=self.handle_elicitation,
            log_handler=self.handle_logging
        )

    async def process_query(self, client: Client, query: str) -> str:
        """Process a query using Claude and available tools"""
        
        async with client:
            messages = [{"role": "user", "content": query}]

            # Get available tools using FastMCP
            tools_response = await client.list_tools()
            available_tools = [
                {"name": tool.name, "description": tool.description, "input_schema": tool.inputSchema}
                for tool in tools_response
            ]

            # Initial Claude API call
            response = self.anthropic.messages.create(
                model=ANTHROPIC_MODEL, max_tokens=1000, messages=messages, tools=available_tools
            )

            # Process response and handle tool calls
            final_text = []

            for content in response.content:
                if content.type == "text":
                    final_text.append(content.text)
                elif content.type == "tool_use":
                    tool_name = content.name
                    tool_args = content.input

                    # Execute tool call using FastMCP
                    result = await client.call_tool(tool_name, tool_args)
                    final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                    # Continue conversation with tool results
                    if hasattr(content, "text") and content.text:
                        messages.append({"role": "assistant", "content": content.text})
                    messages.append({"role": "user", "content": str(result.content)})

                    # Get next response from Claude
                    response = self.anthropic.messages.create(
                        model=ANTHROPIC_MODEL,
                        max_tokens=1000,
                        messages=messages,
                    )

                    final_text.append(response.content[0].text)

            return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == "quit":
                    break

                response = await self.process_query(self.client,query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    server_path = sys.argv[1]
    client = MCPClient(server_path)
    
    # Check if we have a valid API key to continue
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nNo ANTHROPIC_API_KEY found. To query these tools with Claude, set your API key:")
        print("  export ANTHROPIC_API_KEY=your-api-key-here")
        return

    # Test connection and show available tools
    test_client = client.create_client()
    async with test_client:
        tools = await test_client.list_tools()
        print(f"\nConnected to server with tools: {[tool.name for tool in tools]}")

    await client.chat_loop()


if __name__ == "__main__":
    import sys

    asyncio.run(main())