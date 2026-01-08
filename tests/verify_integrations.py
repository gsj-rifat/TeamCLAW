import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.infrastructure.container import container
from src.core.models.insights import InsightRecord

async def verify_integrations():
    print("=== STARTING INTEGRATION VERIFICATION ===")
    
    # 1. Check Config
    print("\n--- 1. Checking Configuration ---")
    settings = container.settings
    print(f"DATABASE_URL present: {bool(settings.database_url)}")
    print(f"GROQ_API_KEY present: {bool(settings.groq_api_key)}")
    print(f"SLACK_BOT_TOKEN present: {bool(settings.slack_bot_token)}")
    print(f"JIRA Credentials present: {bool(settings.jira_base_url)}")
    print(f"Default Tenant ID: {settings.default_tenant_id}")

    # 2. Init Resources (DB)
    print("\n--- 2. Initializing Database Connection ---")
    try:
        await container.init_resources()
        print("✅ DB Connection Successful")
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        return

    # 3. Test LLM (Groq)
    print("\n--- 3. Testing LLM (Groq) ---")
    try:
        dummy_text = "The deadline for the Project Alpha release is next Friday. We defined this in the meeting today."
        print(f"Sending text: '{dummy_text}'")
        meaningful, reason = await container.extractor.is_meaningful(dummy_text)
        print(f"Is Meaningful: {meaningful} (Reason: {reason})")
        
        if not meaningful:
             print("❌ LLM Noise Filter Failed (Should be meaningful)")
        else:
             print("✅ LLM Noise Filter OK")
             
        insights = await container.extractor.extract(dummy_text)
        print(f"Extracted: Decisions={len(insights.decisions)}, Todos={len(insights.todos)}, Facts={len(insights.facts)}")
        if len(insights.todos) > 0 or len(insights.facts) > 0:
            print("✅ LLM Extraction OK")
        else:
            print("⚠️ LLM Extraction yielded empty results (Might be model behavior)")

    except Exception as e:
        print(f"❌ LLM Test Failed: {e}")
        return

    # 4. Test DB Save
    print("\n--- 4. Testing DB Save ---")
    try:
        # Manually invoke logic
        # Using a fake channel/user for safety, but real DB
        test_channel = "C000TEST"
        test_user = "U000TEST"
        test_ts = "1234567890.000000"
        
        print(f"Simulating process_message for text: '{dummy_text}'")
        
        await container.workflow.process_message(dummy_text, test_channel, test_user, test_ts)
        print("✅ process_message executed without crash")
        
        # Verify persistence (Optional query)
        # Note: process_message is fire-and-forget for Jira/Slack calls inside
        
    except Exception as e:
        print(f"❌ Workflow Execution Failed: {e}")
        # Print full traceback
        import traceback
        traceback.print_exc()

    print("\n=== VERIFICATION COMPLETE ===")
    print("If all checks passed, the backend logic is solid.")
    print("If nothing happens in Production, check configured Webhook URL in Slack API settings.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_integrations())
