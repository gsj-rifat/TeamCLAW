from src.infrastructure.config import settings
from src.adapters.groq_adapter import GroqAdapter
from src.adapters.sqlite_adapter import SqliteAdapter
from src.adapters.slack_adapter import SlackAdapter
from src.adapters.jira_adapter import JiraAdapter
from src.core.logic.extraction import InsightExtractor
from src.core.logic.reporting import ReportBuilder
from src.core.logic.sop import SopGenerator
from src.core.logic.workflow import MessageWorkflow

class Container:
    def __init__(self):
        # Configuration
        self.settings = settings
        
        # Adapters
        self.db = SqliteAdapter(settings.insights_db_path)
        self.llm = GroqAdapter(settings.groq_api_key, settings.groq_model)
        self.slack = SlackAdapter(settings.slack_bot_token)
        self.jira = JiraAdapter(
            settings.jira_base_url,
            settings.jira_email,
            settings.jira_api_token
        )
        
        # Logic / Business Layer
        self.extractor = InsightExtractor(self.llm)
        self.reporter = ReportBuilder(self.db, self.llm)
        self.sop_gen = SopGenerator(self.llm, self.db)
        
        # Workflows
        self.workflow = MessageWorkflow(self.extractor, self.db, self.jira, self.slack)

    async def init_resources(self):
        """Initialize async resources (DB connections, etc.)"""
        await self.db.init_db()

# Global container instance
container = Container()
