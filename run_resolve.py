from services.resolver_service import resolver_service
import sys

if __name__ == "__main__":
    print("🚀 Starting Automated Prediction Resolution...")
    try:
        resolver_service.resolve_expired_issues()
        print("✅ Resolution process completed.")
    except Exception as e:
        print(f"❌ Error during resolution: {e}")
        sys.exit(1)
