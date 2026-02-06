"""
SQL Query Loader Utility

This module provides a centralized way to load and access SQL queries from external files.
It helps keep SQL statements organized and maintainable.

Usage:
    from sql_loader import SQLLoader
    
    sql = SQLLoader()
    
    # Load a specific query
    query = sql.get_query('user_queries', 'create_user')
    
    # Load all queries from a file
    all_user_queries = sql.get_queries('user_queries')
    
    # Load schema statements
    create_tables = sql.get_schema('create_tables')
"""

import os
from typing import Dict, List, Optional
from pathlib import Path

class SQLLoader:
    """Loads and manages SQL queries from external files."""
    
    def __init__(self, sql_dir: str = None):
        """Initialize the SQL loader.
        
        Args:
            sql_dir: Path to the SQL directory. Defaults to './sql' relative to this file.
        """
        if sql_dir is None:
            sql_dir = Path(__file__).parent / 'sql'
        
        self.sql_dir = Path(sql_dir)
        self.queries_dir = self.sql_dir / 'queries'
        self.schema_dir = self.sql_dir / 'schema'
        
        # Cache for loaded queries
        self._query_cache: Dict[str, Dict[str, str]] = {}
        self._schema_cache: Dict[str, List[str]] = {}
    
    def get_query(self, file_name: str, query_name: str) -> Optional[str]:
        """Get a specific query from a SQL file.
        
        Args:
            file_name: Name of the SQL file (without .sql extension)
            query_name: Comment identifier for the query (e.g., 'Create new user')
            
        Returns:
            The SQL query string, or None if not found
        """
        queries = self.get_queries(file_name)
        return queries.get(query_name)
    
    def get_queries(self, file_name: str) -> Dict[str, str]:
        """Get all queries from a SQL file.
        
        Args:
            file_name: Name of the SQL file (without .sql extension)
            
        Returns:
            Dictionary mapping query names to SQL strings
        """
        if file_name not in self._query_cache:
            self._load_queries(file_name)
        
        return self._query_cache.get(file_name, {})
    
    def get_schema(self, schema_name: str) -> List[str]:
        """Get schema statements from a SQL file.
        
        Args:
            schema_name: Name of the schema file (without .sql extension)
            
        Returns:
            List of SQL statements
        """
        if schema_name not in self._schema_cache:
            self._load_schema(schema_name)
        
        return self._schema_cache.get(schema_name, [])
    
    def _load_queries(self, file_name: str) -> None:
        """Load queries from a SQL file and parse them."""
        sql_file = self.queries_dir / f"{file_name}.sql"
        
        if not sql_file.exists():
            print(f"Warning: SQL file not found: {sql_file}")
            self._query_cache[file_name] = {}
            return
        
        try:
            with open(sql_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            queries = self._parse_queries(content)
            self._query_cache[file_name] = queries
            
        except Exception as e:
            print(f"Error loading SQL file {sql_file}: {e}")
            self._query_cache[file_name] = {}
    
    def _load_schema(self, schema_name: str) -> None:
        """Load schema statements from a SQL file."""
        sql_file = self.schema_dir / f"{schema_name}.sql"
        
        if not sql_file.exists():
            print(f"Warning: Schema file not found: {sql_file}")
            self._schema_cache[schema_name] = []
            return
        
        try:
            with open(sql_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            statements = self._parse_schema(content)
            self._schema_cache[schema_name] = statements
            
        except Exception as e:
            print(f"Error loading schema file {sql_file}: {e}")
            self._schema_cache[schema_name] = []
    
    def _parse_queries(self, content: str) -> Dict[str, str]:
        """Parse SQL queries from file content.
        
        Expects queries to be preceded by comments that describe them.
        """
        queries = {}
        lines = content.split('\n')
        current_query = []
        current_comment = None
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Check for comment that describes a query
            if line.startswith('-- ') and not line.startswith('-- Params:'):
                # Save previous query if exists
                if current_comment and current_query:
                    sql = '\n'.join(current_query).strip()
                    if sql:
                        queries[current_comment] = sql
                
                # Start new query
                current_comment = line[3:].strip()  # Remove '-- '
                current_query = []
            
            # Check for SQL statements (not comments)
            elif not line.startswith('--') and line:
                current_query.append(line)
        
        # Save last query
        if current_comment and current_query:
            sql = '\n'.join(current_query).strip()
            if sql:
                queries[current_comment] = sql
        
        return queries
    
    def _parse_schema(self, content: str) -> List[str]:
        """Parse schema statements from file content."""
        # Split by semicolon and clean up
        statements = []
        current_statement = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('--'):
                continue
            
            current_statement.append(line)
            
            # Check if statement is complete (ends with semicolon)
            if line.endswith(';'):
                statement = ' '.join(current_statement).strip()
                if statement:
                    statements.append(statement)
                current_statement = []
        
        # Add any remaining statement
        if current_statement:
            statement = ' '.join(current_statement).strip()
            if statement:
                statements.append(statement)
        
        return statements
    
    def list_query_files(self) -> List[str]:
        """List all available query files."""
        if not self.queries_dir.exists():
            return []
        
        return [f.stem for f in self.queries_dir.glob('*.sql')]
    
    def list_schema_files(self) -> List[str]:
        """List all available schema files."""
        if not self.schema_dir.exists():
            return []
        
        return [f.stem for f in self.schema_dir.glob('*.sql')]

# Global instance for easy access
sql_loader = SQLLoader()