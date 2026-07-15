"""
Manual integration verification script.

Requires a configured .env with real credentials.
Run: python scripts/verify_integrations.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.infrastructure.container import container


async def verify_integrations():
    print("=== TeamCLAW Integration Verification ===")

    settings = container.settings
    print(f"DATABASE_URL present: {bool(settings.database_url)}")
    print(f"GROQ_API_KEY present: {bool(settings.groq_api_key)}")
    print(f"SLACK_BOT_TOKEN present: {bool(settings.slack_bot_token)}")
    print(f"JIRA configured: {bool(settings.jira_base_url)}")

    try:
        await container.init_resources()
        print("DB connection OK")
    except Exception as e:
        print(f"DB connection failed: {e}")
        return

    dummy_text = (
        "The deadline for Project Alpha is next Friday. "
        "We defined this in the meeting today."
    )
    try:
        meaningful, reason = await container.extractor.is_meaningful(dummy_text)
        print(f"Noise filter: meaningful={meaningful} reason={reason}")
        insights = await container.extractor.extract(dummy_text)
        print(
            f"Extraction: decisions={len(insights.decisions)} "
            f"todos={len(insights.todos)} facts={len(insights.facts)}"
        )
        await container.workflow.process_message(
            dummy_text, "C000TEST", "U000TEST", "1234567890.000000"
        )
        print("Workflow executed without crash")
    except Exception as e:
        print(f"Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("=== Verification complete ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_integrations())
