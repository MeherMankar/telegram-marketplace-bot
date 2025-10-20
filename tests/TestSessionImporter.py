import pytest
import tempfile
import os
from app.utils.session_importer import SessionImporter

class TestSessionImporter:
    
    @pytest.mark.asyncio
    async def test_import_string_session_invalid(self):
        """Test importing invalid session string"""
        result = await SessionImporter.import_session(session_string="invalid_session")
        assert "error" in result
        assert not result.get("success", False)
    
    @pytest.mark.asyncio
    async def test_import_file_session_unsupported_format(self):
        """Test importing unsupported file format"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            temp_file.write(b"test content")
            temp_file_path = temp_file.name
        
        try:
            result = await SessionImporter.import_session(file_path=temp_file_path)
            assert "error" in result
            assert "Unsupported file format" in result["error"]
        finally:
            os.unlink(temp_file_path)
    
    @pytest.mark.asyncio
    async def test_import_json_session_no_session_string(self):
        """Test importing JSON file without session_string"""
        import json
        
        with tempfile.NamedTemporaryFile(suffix=".json", mode='w', delete=False) as temp_file:
            json.dump({"some_key": "some_value"}, temp_file)
            temp_file_path = temp_file.name
        
        try:
            result = await SessionImporter.import_session(file_path=temp_file_path)
            assert "error" in result
            assert "No session_string found" in result["error"]
        finally:
            os.unlink(temp_file_path)
    
    def test_session_importer_initialization(self):
        """Test SessionImporter can be initialized"""
        importer = SessionImporter()
        assert importer is not None