import subprocess
import tempfile
import os
import asyncio
import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import base64
from PIL import Image
import io


server = Server("illustrator")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="capture-illustrator",
            description="Capture the adobe illustrator window",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="run-illustrator-script",
            description="Run ExtendScript code in Illustrator. Use 'app' to access the Illustrator application object.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "ExtendScript/JavaScript code to execute in Illustrator. It will run on the current document. you only need to make the document once",
                    }
                },
                "required": ["code"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "capture-illustrator":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            screenshot_path = f.name

        try:
            # Activate Illustrator for update
            activate_script = """
                tell application "Adobe Illustrator" to activate
                delay 1
                tell application "Claude" to activate
            """
            subprocess.run(["osascript", "-e", activate_script])

            result = subprocess.run(
                [
                    "screencapture",
                    "-R",
                    "0,0,960,1080",  # Original capture area
                    "-C",  # Capture in "compact" mode (lower quality)
                    "-T",
                    "2",  # Thumbnail mode with scale factor (smaller file size)
                    "-x",  # No sound
                    screenshot_path,
                ]
            )

            if result.returncode != 0:
                return [
                    types.TextContent(type="text", text="Failed to capture screenshot")
                ]

            # Compress with PIL
            with Image.open(screenshot_path) as img:
                # Convert to RGB if needed
                if img.mode in ("RGBA", "LA"):
                    img = img.convert("RGB")

                # Create a buffer to hold compressed image
                buffer = io.BytesIO()

                # Save as JPEG with compression
                img.save(buffer, format="JPEG", quality=50, optimize=True)

                # Get the compressed data
                compressed_data = buffer.getvalue()
                screenshot_data = base64.b64encode(compressed_data).decode("utf-8")

            return [
                types.ImageContent(
                    type="image",
                    mimeType="image/jpeg",  # Changed to JPEG
                    data=screenshot_data,
                )
            ]

        finally:
            if os.path.exists(screenshot_path):
                os.unlink(screenshot_path)
    elif name == "run-illustrator-script":
        if not arguments or "code" not in arguments:
            return [types.TextContent(type="text", text="No code provided")]

        script = arguments["code"]
        script = script.replace('"', '\\"').replace("\n", "\\n")

        # Just run the script without focus changes
        applescript = f"""
            tell application "Adobe Illustrator"
                do javascript "{script}"
            end tell
        """

        result = subprocess.run(
            ["osascript", "-e", applescript], capture_output=True, text=True
        )

        if result.returncode != 0:
            return [
                types.TextContent(
                    type="text", text=f"Error executing script: {result.stderr}"
                )
            ]

        success_message = "Script executed successfully"
        if result.stdout:
            success_message += f"\nOutput: {result.stdout}"

        return [types.TextContent(type="text", text=success_message)]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="weather",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
