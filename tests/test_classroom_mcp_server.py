#!/usr/bin/env python3
"""
Test suite for the GitHub Classroom MCP Server
"""

from exercise_checker_mcp.classroom_mcp_server import (
    UserSession,
    run_gh_command,
    get_or_create_session,
    handle_list_tools,
    handle_call_tool,
    handle_start_workflow,
    handle_select_classroom,
    handle_select_assignment,
    handle_select_student,
    handle_reset_session,
    user_sessions
)

import asyncio
import json
import pytest
import subprocess
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import sys
import os


class TestUserSession:
    """Test the UserSession dataclass"""

    def test_user_session_creation(self):
        """Test creating a new UserSession"""
        session = UserSession(session_id="test_session")
        
        assert session.session_id == "test_session"
        assert session.selected_classroom is None
        assert session.selected_assignment is None
        assert session.cloned_repos == []
        assert session.current_step == "selecting_classroom"
        assert session.created_at is not None

class TestGitHubCommands:
    """Test GitHub CLI command execution"""
    
    @patch('subprocess.run')
    def test_run_gh_command_success(self, mock_run):
        """Test successful GitHub CLI command execution"""
        # Mock successful command execution
        mock_result = Mock()
        mock_result.stdout = '{"id": 123, "name": "test"}'
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = run_gh_command(["classroom", "list"])
        
        assert result["success"] is True
        assert result["stdout"] == '{"id": 123, "name": "test"}'
        assert result["returncode"] == 0
        mock_run.assert_called_once()
 

class TestSessionManagement:
    """Test session management functions"""
    
    def setup_method(self):
        """Clear user_sessions before each test"""
        user_sessions.clear()
    
    def test_get_or_create_session_new(self):
        """Test creating a new session"""
        session = get_or_create_session("new_session")
        
        assert session.session_id == "new_session"
        assert "new_session" in user_sessions
        assert user_sessions["new_session"] == session
    
    def test_get_or_create_session_existing(self):
        """Test getting an existing session"""
        # Create a session first
        original_session = get_or_create_session("existing_session")
        
        # Get the same session again
        retrieved_session = get_or_create_session("existing_session")
        
        assert retrieved_session == original_session
        assert len(user_sessions) == 1

class TestToolListing:
    """Test tool listing functionality"""
    
    @pytest.mark.asyncio
    async def test_handle_list_tools(self):
        """Test that all expected tools are listed"""
        result = await handle_list_tools()
        
        tool_names = [tool.name for tool in result.tools]
        expected_tools = [
            "start_classroom_workflow",
            "select_classroom", 
            "select_assignment",
            "select_student",
            "reset_session"
        ]
        
        assert all(tool in tool_names for tool in expected_tools)
        assert len(result.tools) == 5

class TestWorkflowHandlers:
    """Test the workflow handler functions"""
    
    def setup_method(self):
        """Clear user_sessions before each test"""
        user_sessions.clear()
    
    @pytest.mark.asyncio
    @patch('exercise_checker_mcp.classroom_mcp_server.run_gh_command')
    async def test_handle_start_workflow_success(self, mock_run_gh):
        """Test successful workflow start"""
        # Mock successful classroom list
        mock_run_gh.return_value = {
            "success": True,
            "stdout": json.dumps([
                {"id": 123, "name": "python-2025", "title": "Python Programming 2025"},
                {"id": 456, "name": "java-2025", "title": "Java Programming 2025"}
            ]),
            "stderr": "",
            "returncode": 0
        }
        
        result = await handle_start_workflow("test_session")
        
        assert result.content[0].text is not None
        assert "Available Classrooms" in result.content[0].text
        assert "Python Programming 2025" in result.content[0].text
        assert "Java Programming 2025" in result.content[0].text
    
    @pytest.mark.asyncio
    @patch('exercise_checker_mcp.classroom_mcp_server.run_gh_command')
    async def test_handle_start_workflow_failure(self, mock_run_gh):
        """Test workflow start with GitHub CLI error"""
        mock_run_gh.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "Error: Not authenticated",
            "returncode": 1
        }
        
        result = await handle_start_workflow("test_session")
        
        assert "Error:" in result.content[0].text
        assert "Not authenticated" in result.content[0].text
    
    @pytest.mark.asyncio
    @patch('exercise_checker_mcp.classroom_mcp_server.run_gh_command')
    async def test_handle_select_classroom_success(self, mock_run_gh):
        """Test successful classroom selection"""
        # Setup session with classrooms
        session = get_or_create_session("test_session")
        session.classrooms = [
            {"id": 123, "name": "python-2025", "title": "Python Programming 2025"},
            {"id": 456, "name": "java-2025", "title": "Java Programming 2025"}
        ]
        
        # Mock successful assignment list
        mock_run_gh.return_value = {
            "success": True,
            "stdout": json.dumps([
                {"id": 789, "title": "Docker Exercise", "name": "docker-exercise", "deadline": "2024-01-15"},
                {"id": 101, "title": "API Exercise", "name": "api-exercise", "deadline": None}
            ]),
            "stderr": "",
            "returncode": 0
        }
        
        result = await handle_select_classroom(1, "test_session")
        
        assert result.content[0].text is not None
        assert "Selected Classroom: Python Programming 2025" in result.content[0].text
        assert "Available Assignments" in result.content[0].text
        assert session.selected_classroom["id"] == 123
    
    @pytest.mark.asyncio
    async def test_handle_select_classroom_invalid_number(self):
        """Test classroom selection with invalid number"""
        # Setup session with classrooms
        session = get_or_create_session("test_session")
        session.classrooms = [
            {"id": 123, "name": "python-2025", "title": "Python Programming 2025"}
        ]
        
        result = await handle_select_classroom(5, "test_session")
        
        assert "Invalid classroom number" in result.content[0].text
    
    @pytest.mark.asyncio
    @patch('exercise_checker_mcp.classroom_mcp_server.run_gh_command')
    async def test_handle_select_assignment_success(self, mock_run_gh):
        """Test successful assignment selection and cloning"""
        # Setup session with assignments
        session = get_or_create_session("test_session")
        session.assignments = [
            {"id": 789, "title": "Docker Exercise", "name": "docker-exercise", "deadline": "2024-01-15"},
            {"id": 101, "title": "API Exercise", "name": "api-exercise", "deadline": None}
        ]
        
        # Mock successful cloning
        mock_run_gh.return_value = {
            "success": True,
            "stdout": "",
            "stderr": "",
            "returncode": 0
        }
        
        with patch('pathlib.Path.iterdir') as mock_iterdir:
            # Mock cloned repositories
            mock_repo1 = Mock()
            mock_repo1.name = "student1-repo"
            mock_repo1.is_dir.return_value = True
            mock_repo1.absolute.return_value = Path("/tmp/student1-repo")
            
            mock_repo2 = Mock()
            mock_repo2.name = "student2-repo"
            mock_repo2.is_dir.return_value = True
            mock_repo2.absolute.return_value = Path("/tmp/student2-repo")
            
            mock_iterdir.return_value = [mock_repo1, mock_repo2]
            
            result = await handle_select_assignment(1, "test_session")
        
        assert result.content[0].text is not None
        assert "Selected Assignment: Docker Exercise" in result.content[0].text
        assert "Successfully cloned" in result.content[0].text
        assert session.selected_assignment["id"] == 789
        assert len(session.cloned_repos) == 2
    
    @pytest.mark.asyncio
    async def test_handle_select_student_success(self):
        """Test successful student selection"""
        # Setup session with cloned repos
        session = get_or_create_session("test_session")
        session.cloned_repos = [
            {"name": "student1-repo", "path": "/tmp/student1-repo"},
            {"name": "student2-repo", "path": "/tmp/student2-repo"}
        ]
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            # Mock git remote command
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "git@github.com:classroom/student1-repo.git"
            mock_subprocess.return_value = mock_result
            
            # Mock GitHub CLI PR list
            with patch('exercise_checker_mcp.classroom_mcp_server.run_gh_command') as mock_gh:
                mock_gh.return_value = {
                    "success": True,
                    "stdout": json.dumps([
                        {
                            "number": 1,
                            "title": "Add Docker support",
                            "author": {"login": "student1"},
                            "state": "open",
                            "createdAt": "2024-01-10T10:00:00Z"
                        }
                    ]),
                    "stderr": "",
                    "returncode": 0
                }
                
                result = await handle_select_student(1, "test_session")
        
        assert result.content[0].text is not None
        assert "Selected Student: student1-repo" in result.content[0].text
        assert "Pull Requests" in result.content[0].text
    
    @pytest.mark.asyncio
    async def test_handle_reset_session(self):
        """Test session reset functionality"""
        # Create a session first
        session = get_or_create_session("test_session")
        session.selected_classroom = {"id": 123, "title": "Test Classroom"}
        session.selected_assignment = {"id": 456, "title": "Test Assignment"}
        
        assert "test_session" in user_sessions
        
        result = await handle_reset_session("test_session")
        
        assert "Session reset successfully" in result.content[0].text
        assert "test_session" not in user_sessions

class TestToolCallHandler:
    """Test the main tool call handler"""
    
    def setup_method(self):
        """Clear user_sessions before each test"""
        user_sessions.clear()
    
    @pytest.mark.asyncio
    async def test_handle_call_tool_start_workflow(self):
        """Test calling start_classroom_workflow through the main handler"""
        with patch('exercise_checker_mcp.classroom_mcp_server.handle_start_workflow') as mock_handler:
            mock_result = Mock()
            mock_result.content = [Mock(text="Test result")]
            mock_handler.return_value = mock_result
            
            result = await handle_call_tool("start_classroom_workflow", {"session_id": "test"})
            
            mock_handler.assert_called_once_with("test")
            assert result == mock_result
    
    @pytest.mark.asyncio
    async def test_handle_call_tool_select_classroom(self):
        """Test calling select_classroom through the main handler"""
        with patch('exercise_checker_mcp.classroom_mcp_server.handle_select_classroom') as mock_handler:
            mock_result = Mock()
            mock_result.content = [Mock(text="Test result")]
            mock_handler.return_value = mock_result
            
            result = await handle_call_tool("select_classroom", {
                "classroom_number": 1,
                "session_id": "test"
            })
            
            mock_handler.assert_called_once_with(1, "test")
            assert result == mock_result
    
    @pytest.mark.asyncio
    async def test_handle_call_tool_unknown(self):
        """Test calling an unknown tool"""
        with pytest.raises(ValueError, match="Unknown tool: unknown_tool"):
            await handle_call_tool("unknown_tool", {})

class TestIntegration:
    """Integration tests for the complete workflow"""
    
    def setup_method(self):
        """Clear user_sessions before each test"""
        user_sessions.clear()
    
    @pytest.mark.asyncio
    @patch('exercise_checker_mcp.classroom_mcp_server.run_gh_command')
    async def test_complete_workflow(self, mock_run_gh):
        """Test a complete workflow from start to finish"""
        # Mock all GitHub CLI calls
        mock_run_gh.side_effect = [
            # Classroom list
            {
                "success": True,
                "stdout": json.dumps([
                    {"id": 123, "name": "python-2025", "title": "Python Programming 2025"}
                ]),
                "stderr": "",
                "returncode": 0
            },
            # Assignment list
            {
                "success": True,
                "stdout": json.dumps([
                    {"id": 789, "title": "Docker Exercise", "name": "docker-exercise", "deadline": "2024-01-15"}
                ]),
                "stderr": "",
                "returncode": 0
            },
            # Clone repositories
            {
                "success": True,
                "stdout": "",
                "stderr": "",
                "returncode": 0
            }
        ]
        
        # Test workflow start
        result1 = await handle_start_workflow("test_session")
        assert "Available Classrooms" in result1.content[0].text
        
        # Test classroom selection
        result2 = await handle_select_classroom(1, "test_session")
        assert "Selected Classroom: Python Programming 2025" in result2.content[0].text
        
        # Test assignment selection
        with patch('pathlib.Path.iterdir') as mock_iterdir:
            mock_repo = Mock()
            mock_repo.name = "student-repo"
            mock_repo.is_dir.return_value = True
            mock_repo.absolute.return_value = Path("/tmp/student-repo")
            mock_iterdir.return_value = [mock_repo]
            
            result3 = await handle_select_assignment(1, "test_session")
            assert "Selected Assignment: Docker Exercise" in result3.content[0].text
        
        # Test session reset
        result4 = await handle_reset_session("test_session")
        assert "Session reset successfully" in result4.content[0].text

if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"]) 