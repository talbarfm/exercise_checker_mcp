#!/usr/bin/env python3
"""
GitHub Classroom MCP Server with Chained Tool Execution
Provides an interactive menu-driven interface for managing GitHub Classroom operations
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
    LoggingLevel,
)

# Initialize the MCP server
server = Server("github-classroom-mcp")


@dataclass
class UserSession:
    """User session state for tracking progress through the workflow"""

    session_id: str
    selected_classroom: Optional[Dict] = None
    selected_assignment: Optional[Dict] = None
    cloned_repos: List[Dict] = field(default_factory=list)
    current_step: str = "selecting_classroom"
    created_at: datetime = field(default_factory=datetime.now)


# Global session storage
user_sessions: Dict[str, UserSession] = {}


def run_gh_command(args: List[str], capture_output: bool = True) -> Dict[str, Any]:
    """Run a GitHub CLI command and return the result"""
    try:
        cmd = ["gh"] + args
        result = subprocess.run(
            cmd, capture_output=capture_output, text=True, check=True
        )
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "stdout": e.stdout,
            "stderr": e.stderr,
            "returncode": e.returncode,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "GitHub CLI (gh) not found. Please install it first.",
            "returncode": 1,
        }


def get_or_create_session(session_id: str = "default") -> UserSession:
    """Get existing session or create a new one"""
    if session_id not in user_sessions:
        user_sessions[session_id] = UserSession(session_id=session_id)
    return user_sessions[session_id]


@server.list_tools()
async def handle_list_tools() -> ListToolsResult:
    """List available tools"""
    tools = [
        Tool(
            name="start_classroom_workflow",
            description="Start the interactive classroom workflow - lists classrooms and guides through the process",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional, defaults to 'default')",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="select_classroom",
            description="Select a classroom by number from the list",
            inputSchema={
                "type": "object",
                "properties": {
                    "classroom_number": {
                        "type": "integer",
                        "description": "The number of the classroom to select",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional, defaults to 'default')",
                    },
                },
                "required": ["classroom_number"],
            },
        ),
        Tool(
            name="select_assignment",
            description="Select an assignment by number from the list",
            inputSchema={
                "type": "object",
                "properties": {
                    "assignment_number": {
                        "type": "integer",
                        "description": "The number of the assignment to select",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional, defaults to 'default')",
                    },
                },
                "required": ["assignment_number"],
            },
        ),
        Tool(
            name="select_student",
            description="Select a student by number to view their pull requests",
            inputSchema={
                "type": "object",
                "properties": {
                    "student_number": {
                        "type": "integer",
                        "description": "The number of the student to select",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (optional, defaults to 'default')",
                    },
                },
                "required": ["student_number"],
            },
        ),
        Tool(
            name="reset_session",
            description="Reset the current session and start over",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to reset (optional, defaults to 'default')",
                    }
                },
                "required": [],
            },
        ),
    ]
    return ListToolsResult(tools=tools)


@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls"""

    if name == "start_classroom_workflow":
        session_id = arguments.get("session_id", "default")
        return await handle_start_workflow(session_id)

    elif name == "select_classroom":
        classroom_number = arguments["classroom_number"]
        session_id = arguments.get("session_id", "default")
        return await handle_select_classroom(classroom_number, session_id)

    elif name == "select_assignment":
        assignment_number = arguments["assignment_number"]
        session_id = arguments.get("session_id", "default")
        return await handle_select_assignment(assignment_number, session_id)

    elif name == "select_student":
        student_number = arguments["student_number"]
        session_id = arguments.get("session_id", "default")
        return await handle_select_student(student_number, session_id)

    elif name == "reset_session":
        session_id = arguments.get("session_id", "default")
        return await handle_reset_session(session_id)

    else:
        raise ValueError(f"Unknown tool: {name}")


async def handle_start_workflow(session_id: str) -> CallToolResult:
    """Start the interactive workflow by listing classrooms"""
    session = get_or_create_session(session_id)
    session.current_step = "selecting_classroom"

    # Get list of classrooms
    result = run_gh_command(["classroom", "list", "--json", "id,name,title"])

    if not result["success"]:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {result['stderr']}")]
        )

    try:
        classrooms = json.loads(result["stdout"])
        if not classrooms:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="No classrooms found. Please check your GitHub Classroom access.",
                    )
                ]
            )

        # Store classrooms in session for later use
        session.classrooms = classrooms

        output = "🏫 Available Classrooms:\n"
        output += "======================\n\n"

        for i, classroom in enumerate(classrooms, 1):
            output += f"{i}. {classroom['title']} (ID: {classroom['id']})\n"

        output += "\n🏫 Call 'select_classroom' with the number to view assignments."

        return CallToolResult(content=[TextContent(type="text", text=output)])

    except json.JSONDecodeError:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Error parsing classroom data: {result['stdout']}",
                )
            ]
        )


async def handle_select_classroom(
    classroom_number: int, session_id: str
) -> CallToolResult:
    """Select a classroom and show its assignments"""
    session = get_or_create_session(session_id)

    if not hasattr(session, "classrooms") or not session.classrooms:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="No classrooms available. Please call 'start_classroom_workflow' first.",
                )
            ]
        )

    if classroom_number < 1 or classroom_number > len(session.classrooms):
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Invalid classroom number. Please select between 1 and {len(session.classrooms)}",
                )
            ]
        )

    # Get selected classroom
    selected_classroom = session.classrooms[classroom_number - 1]
    session.selected_classroom = selected_classroom
    session.current_step = "selecting_assignment"

    # Get assignments for this classroom
    result = run_gh_command(
        [
            "classroom",
            "list-assignments",
            "--classroom-id",
            str(selected_classroom["id"]),
            "--json",
            "id,title,name,deadline",
        ]
    )

    if not result["success"]:
        return CallToolResult(
            content=[
                TextContent(
                    type="text", text=f"Error fetching assignments: {result['stderr']}"
                )
            ]
        )

    try:
        assignments = json.loads(result["stdout"])
        if not assignments:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"No assignments found for classroom: {selected_classroom['title']}",
                    )
                ]
            )

        # Store assignments in session
        session.assignments = assignments

        output = f"✅ Selected Classroom: {selected_classroom['title']}\n\n"
        output += "📚 Available Assignments:\n"
        output += "========================\n\n"

        for i, assignment in enumerate(assignments, 1):
            deadline = assignment.get("deadline", "No deadline")
            output += f"{i}. {assignment['title']} (ID: {assignment['id']})\n"
            output += f"   📅 Deadline: {deadline}\n\n"

        output += (
            "🚀 Call 'select_assignment' with the number to clone student repositories."
        )

        return CallToolResult(content=[TextContent(type="text", text=output)])

    except json.JSONDecodeError:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Error parsing assignment data: {result['stdout']}",
                )
            ]
        )


async def handle_select_assignment(
    assignment_number: int, session_id: str
) -> CallToolResult:
    """Select an assignment and clone student repositories"""
    session = get_or_create_session(session_id)

    if not hasattr(session, "assignments") or not session.assignments:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="No assignments available. Please select a classroom first.",
                )
            ]
        )

    if assignment_number < 1 or assignment_number > len(session.assignments):
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Invalid assignment number. Please select between 1 and {len(session.assignments)}",
                )
            ]
        )

    # Get selected assignment
    selected_assignment = session.assignments[assignment_number - 1]
    session.selected_assignment = selected_assignment
    session.current_step = "cloning_repos"

    output = f"✅ Selected Assignment: {selected_assignment['title']}\n\n"
    output += "📥 Cloning student repositories...\n"

    # Clone student repositories
    clone_result = run_gh_command(
        ["classroom", "clone", "student-repos", "-a", str(selected_assignment["id"])],
        capture_output=False,
    )

    if not clone_result["success"]:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Error cloning repositories: {clone_result['stderr']}",
                )
            ]
        )

    # Get list of cloned repositories
    cloned_dirs = [
        d for d in Path.cwd().iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    # Store cloned repos in session
    session.cloned_repos = []
    for repo_dir in cloned_dirs:
        session.cloned_repos.append(
            {"name": repo_dir.name, "path": str(repo_dir.absolute())}
        )

    session.current_step = "selecting_student"

    output += f"✅ Successfully cloned {len(session.cloned_repos)} repositories!\n\n"
    output += "👥 Student Repositories:\n"
    output += "=======================\n\n"

    for i, repo in enumerate(session.cloned_repos, 1):
        output += f"{i}. {repo['name']}\n"

    output += "\n🔍 Call 'select_student' with the number to view their pull requests."

    return CallToolResult(content=[TextContent(type="text", text=output)])


async def handle_select_student(student_number: int, session_id: str) -> CallToolResult:
    """Select a student and show their pull requests"""
    session = get_or_create_session(session_id)

    if not hasattr(session, "cloned_repos") or not session.cloned_repos:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="No student repositories available. Please select an assignment first.",
                )
            ]
        )

    if student_number < 1 or student_number > len(session.cloned_repos):
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Invalid student number. Please select between 1 and {len(session.cloned_repos)}",
                )
            ]
        )

    # Get selected student's repository
    selected_repo = session.cloned_repos[student_number - 1]
    repo_name = selected_repo["name"]

    output = f"✅ Selected Student: {repo_name}\n\n"
    output += "🔍 Checking for pull requests...\n\n"

    # Try to get pull requests for this repository
    # Note: We need to determine the full repository name
    # This might require additional logic to map cloned repo names to full GitHub repo names

    # For now, let's show a message about the repository
    output += f"📁 Repository: {repo_name}\n"
    output += f" Path: {selected_repo['path']}\n\n"

    # Try to list PRs if we can determine the repo name
    # This is a simplified approach - in practice you might need to parse the git remote
    try:
        # Change to the repository directory
        original_dir = Path.cwd()
        repo_path = Path(selected_repo["path"])

        if repo_path.exists():
            # Try to get git remote to determine full repo name
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            if remote_result.returncode == 0:
                remote_url = remote_result.stdout.strip()
                # Extract owner/repo from git URL
                if "github.com" in remote_url:
                    # Handle both SSH and HTTPS URLs
                    if remote_url.startswith("git@"):
                        repo_full_name = remote_url.split(":")[1].replace(".git", "")
                    else:
                        repo_full_name = remote_url.split("github.com/")[1].replace(
                            ".git", ""
                        )

                    # List PRs for this repository
                    pr_result = run_gh_command(
                        [
                            "pr",
                            "list",
                            "--repo",
                            repo_full_name,
                            "--json",
                            "number,title,author,state,createdAt",
                        ]
                    )

                    if pr_result["success"]:
                        try:
                            prs = json.loads(pr_result["stdout"])
                            if prs:
                                output += " Pull Requests:\n"
                                output += "================\n\n"

                                for pr in prs:
                                    output += f"#{pr['number']}: {pr['title']}\n"
                                    output += f"   👤 Author: {pr['author']['login']}\n"
                                    output += f"   📊 State: {pr['state']}\n"
                                    output += f"   📅 Created: {pr['createdAt']}\n\n"
                            else:
                                output += (
                                    "📋 No pull requests found for this repository.\n"
                                )
                        except json.JSONDecodeError:
                            output += " Error parsing pull request data.\n"
                    else:
                        output += (
                            f"📋 Error fetching pull requests: {pr_result['stderr']}\n"
                        )
                else:
                    output += "📋 Could not determine GitHub repository name.\n"
            else:
                output += "📋 Could not get git remote information.\n"
        else:
            output += "📋 Repository directory not found.\n"

    except Exception as e:
        output += f"📋 Error checking pull requests: {str(e)}\n"

    output += "\n🔄 Call 'reset_session' to start over with a new workflow."

    return CallToolResult(content=[TextContent(type="text", text=output)])


async def handle_reset_session(session_id: str) -> CallToolResult:
    """Reset the session and start over"""
    if session_id in user_sessions:
        del user_sessions[session_id]

    output = "🔄 Session reset successfully!\n\n"
    output += "🏫 Call 'start_classroom_workflow' to begin a new workflow."

    return CallToolResult(content=[TextContent(type="text", text=output)])


async def main():
    """Main function to run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="github-classroom-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None,
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
