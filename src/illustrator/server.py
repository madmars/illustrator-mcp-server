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
            name="view",
            description="View a screenshot of the Adobe Illustrator window",
            inputSchema={
                "type": "object",
                "properties": {
                    "return_to_app": {
                        "type": "string",
                        "description": "App name to return to after screenshot (e.g., Terminal, ChatGPT, Claude, etc.)",
                    }
                },
            },
        ),
        types.Tool(
            name="run",
            description="Run ExtendScript code in Illustrator",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "ExtendScript/JavaScript code to execute in Illustrator. It will run on the current document. You only need to make the document once.",
                    }
                },
                "required": ["code"],
            },
        ),
    ]


def captureIllustrator(return_to_app: str | None = None) -> list[types.TextContent | types.ImageContent]:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        screenshot_path = f.name

    try:
        activate_script = """
            tell application "Adobe Illustrator" to activate
            delay 1
        """
        if return_to_app:
            activate_script += f'tell application "{return_to_app}" to activate\n'

        subprocess.run(["osascript", "-e", activate_script])

        result = subprocess.run(
            [
                "screencapture",
                "-R",
                "0,0,960,1080",
                "-C",
                "-T",
                "2",
                "-x",
                screenshot_path,
            ]
        )

        if result.returncode != 0:
            return [types.TextContent(type="text", text="Failed to capture screenshot")]

        with Image.open(screenshot_path) as img:
            if img.mode in ("RGBA", "LA"):
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=50, optimize=True)
            compressed_data = buffer.getvalue()
            screenshot_data = base64.b64encode(compressed_data).decode("utf-8")

        return [
            types.ImageContent(
                type="image",
                mimeType="image/jpeg",
                data=screenshot_data,
            )
        ]

    finally:
        if os.path.exists(screenshot_path):
            os.unlink(screenshot_path)


def runIllustratorScript(code: str) -> list[types.TextContent]:
    script = code.replace('"', '\\"').replace("\n", "\\n")

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


@server.call_tool()
async def handleCallTool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "view":
        return captureIllustrator(arguments.get("return_to_app") if arguments else None)
    elif name == "run":
        if not arguments or "code" not in arguments:
            return [types.TextContent(type="text", text="No code provided")]
        return runIllustratorScript(arguments["code"])
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="illustrator",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
